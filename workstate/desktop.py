import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys
import threading

from .collector import Collector
from .demo import seed_demo
from .logs import configure_logging
from .service import Service
from .storage import Repository
from .paths import default_data_directory


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


class Bridge:
    def __init__(self, service):
        self._service = service

    def dispatch(self, method, payload=None):
        return self._service.dispatch(method, payload)


class Desktop:
    def __init__(self, service, background=False, smoke_test=False, log_handler=None, update_result=None):
        self._service = service
        self._background = background
        self._window = None
        self._tray = None
        self._quitting = False
        self._event = None
        self._mutex = None
        self._smoke_test = smoke_test
        self.smoke_passed = False
        self._log_handler = log_handler
        self._update_result = update_result
        self._service.updater.supported = bool(getattr(sys, 'frozen', False)) and not service.demo
        self._service.updater.cache = Path(os.environ.get('LOCALAPPDATA', service.repository.directory)) / 'WorkState' / 'updates'

    def _check_startup(self):
        if not self._smoke_test and not self._update_result:
            return
        # Exercise the real JS/Python bridge inside WebView2; no OS input is sent.
        script = """new Promise(resolve => {
            let attempts = 0;
            const timer = setInterval(async () => {
                if (++attempts > 150) { clearInterval(timer); resolve({ready:false}); return; }
                if (!window.pywebview?.api || !document.querySelector('.chart-description')) return;
                clearInterval(timer);
                try {
                    const result = await window.pywebview.api.dispatch('bootstrap', {});
                    resolve({ready: result.ok,
                        title: document.title,
                        version: result.data.status.version,
                        pageHeadings: document.querySelectorAll('h1').length,
                        canvas: document.querySelectorAll('canvas').length,
                        font: getComputedStyle(document.body).fontSize,
                        database: result.data.storage.recordCount});
                } catch (error) { resolve({ready:false, error:String(error)}); }
            },100);
        })"""
        def complete(result):
            if self._update_result and result.get('ready'):
                from . import __version__
                from .update_worker import confirm_startup
                confirm_startup(self._update_result, __version__, self._service.repository.directory)
                self._update_result = None
            if not self._smoke_test:
                return
            result["tray"] = bool(self._tray and self._tray.visible)
            result["closeToTray"] = self._closing() is False
            self.smoke_passed = bool(result.get("ready") and result.get("canvas") and result.get("pageHeadings") == 0)
            (self._service.repository.directory / "smoke-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            self.quit()
        self._window.evaluate_js(script, callback=complete)

    def _single_instance(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = wintypes.HANDLE
        kernel.SetEvent.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        # Retain the lock namespace so v4 and WorkState cannot write the same data together.
        name = "Local\\PCState-" + hashlib.sha256(os.path.normcase(str(self._service.repository.directory)).encode()).hexdigest()[:20]
        self._mutex = kernel.CreateMutexW(None, False, name)
        already_running = ctypes.get_last_error() == 183
        self._event = kernel.CreateEventW(None, False, False, name + "-show")
        if not self._mutex or not self._event:
            raise OSError("无法建立应用实例锁")
        if already_running:
            kernel.SetEvent(self._event)
            kernel.CloseHandle(self._event)
            kernel.CloseHandle(self._mutex)
            return False
        self._kernel = kernel
        return True

    def _startup_command(self):
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            command = [str(pythonw if pythonw.exists() else Path(sys.executable)), str(resource_root() / "main.py")]
        return subprocess.list2cmdline(command + ["--background", "--data-dir", str(self._service.repository.directory)])

    def startup_enabled(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                for name in ("WorkState", "PCState"):
                    try:
                        if winreg.QueryValueEx(key, name)[0] == self._startup_command():
                            return True
                    except FileNotFoundError:
                        pass
                return False
        except OSError:
            return False

    def set_startup(self, enabled):
        import winreg
        if self._service.demo:
            raise ValueError("演示模式不会设置开机启动")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            if enabled:
                winreg.SetValueEx(key, "WorkState", 0, winreg.REG_SZ, self._startup_command())
                try:
                    previous = winreg.QueryValueEx(key, "PCState")[0]
                    executable = previous.split('"', 2)[1] if previous.startswith('"') else previous.split(' ', 1)[0]
                    if previous == self._startup_command() or Path(executable).name.casefold() in {'pcstate.exe', 'pcstatemonitor.exe'}:
                        winreg.DeleteValue(key, "PCState")
                except FileNotFoundError:
                    pass
            else:
                for name in ("WorkState", "PCState"):
                    try:
                        command = winreg.QueryValueEx(key, name)[0]
                        if name == "WorkState" or command == self._startup_command():
                            winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass

    def open_data(self):
        os.startfile(self._service.repository.directory)

    def select_legacy_database(self):
        import webview
        selection = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                    file_types=("旧版 PCState 数据库 (*.db)", "SQLite 数据库 (*.sqlite3)", "所有文件 (*.*)"))
        return (selection[0] if isinstance(selection, (tuple, list)) else selection) if selection else None

    def save_export(self, content, name, count):
        import webview
        selection = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name, file_types=("CSV 文件 (*.csv)",))
        if not selection:
            return {"cancelled": True}
        path = Path(selection[0] if isinstance(selection, (tuple, list)) else selection)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"filename": path.name, "count": count}

    def show(self, *_):
        self._window.show()
        self._window.restore()

    def quit(self, *_):
        self._quitting = True
        self._service.close()
        if self._tray:
            self._tray.stop()
        self._window.destroy()

    def _closing(self):
        if not self._quitting and self._tray and self._tray.visible:
            self._window.hide()
            return False
        return True

    def _start_background(self):
        import pystray
        from PIL import Image
        if self._service.collector:
            self._service.collector.start()
        image = Image.open(resource_root() / "public" / "workstate.ico")
        idle_image = Image.open(resource_root() / "public" / "icon_idle.ico")
        def pause_for(minutes):
            return lambda *_: self._service.dispatch("recording", {"pauseMinutes": minutes})
        self._tray = pystray.Icon("WorkState", image, "WorkState · 本地活动记录", menu=pystray.Menu(
            pystray.MenuItem("打开 WorkState", self.show, default=True),
            pystray.MenuItem("暂停记录", pystray.Menu(
                pystray.MenuItem("暂停 5 分钟", pause_for(5)),
                pystray.MenuItem("暂停 1 小时", pause_for(60)),
                pystray.MenuItem("暂停 4 小时", pause_for(240)),
                pystray.MenuItem("暂停 1 天", pause_for(1440)),
            ), visible=lambda _: not self._service.status()["paused"]),
            pystray.MenuItem("恢复记录", lambda *_: self._service.dispatch("recording", {"paused": False}),
                            visible=lambda _: self._service.status()["paused"]),
            pystray.MenuItem("打开数据目录", lambda *_: self.open_data()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.quit),
        ))
        threading.Thread(target=self._tray.run, name="system-tray", daemon=True).start()
        previous_state = None
        log_day = date.today()
        while not self._quitting:
            if self._log_handler and log_day != date.today():
                log_day = date.today()
                try:
                    self._log_handler.maintain()
                except OSError:
                    logging.getLogger(__name__).exception("Log retention failed")
            status = self._service.status()
            state = (status["demo"], status["paused"], status["resumeAt"], status["active"], status["error"])
            if state != previous_state:
                previous_state = state
                label = f"已暂停，{datetime.fromisoformat(status['resumeAt']):%m-%d %H:%M} 恢复" if status["paused"] else "演示模式" if status["demo"] else "记录异常" if status["error"] else "活跃" if status["active"] else "闲置"
                self._tray.title = f"WorkState - {label}"
                self._tray.icon = image if status["active"] and not status["paused"] else idle_image
                if self._tray.visible:
                    self._tray.update_menu()
            if self._kernel.WaitForSingleObject(self._event, 1000) == 0:
                self.show()

    def run(self, entry):
        import webview
        if not self._single_instance():
            return
        self._service.desktop = self
        self._window = webview.create_window("WorkState - 电脑活动记录工具", url=Path(entry).resolve().as_uri(), js_api=Bridge(self._service), width=1220, height=920, min_size=(960, 700), hidden=self._background, background_color="#f5f5f5", text_select=True)
        self._window.events.closing += self._closing
        self._window.events.loaded += self._check_startup
        deadline = threading.Timer(35, self.quit) if self._smoke_test else None
        if deadline:
            deadline.daemon = True
            deadline.start()
        try:
            webview.start(self._start_background, gui="edgechromium", private_mode=True, icon=str(resource_root() / "public" / "workstate.ico"))
        finally:
            if deadline:
                deadline.cancel()
            self._quitting = True
            self._service.close()
            if self._tray:
                self._tray.stop()
            if self._service.collector:
                self._service.collector.stop()
            self._kernel.CloseHandle(self._event)
            self._kernel.CloseHandle(self._mutex)


def main():
    parser = argparse.ArgumentParser(description="WorkState · 本地电脑活动记录")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--demo", action="store_true", help="使用独立演示数据，不采集真实活动")
    parser.add_argument("--background", action="store_true", help="启动时隐藏到托盘")
    parser.add_argument("--preview", action="store_true", help="启动开发预览，不采集真实活动")
    parser.add_argument("--port", type=int, default=21521)
    parser.add_argument("--smoke-test", action="store_true", help="以演示模式验证原生窗口后退出")
    parser.add_argument('--apply-update', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--update-result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.apply_update:
        from .update_worker import worker_main
        raise SystemExit(worker_main(args.apply_update))
    if args.smoke_test and not args.demo:
        parser.error("--smoke-test 必须与 --demo 一起使用")
    directory = args.data_dir or default_data_directory(os.environ.get("LOCALAPPDATA", Path.home()), args.demo)
    if args.demo and args.data_dir:
        directory = args.data_dir / "demo"
    repository = Repository(directory)
    log_handler = configure_logging(repository.directory)
    if args.demo:
        seed_demo(repository)
    html_path = resource_root() / "viewer" / "index.html"
    if not html_path.exists():
        raise SystemExit("缺少界面文件。请先在 frontend 目录运行 npm run build。")
    collector = None if args.demo or args.preview else Collector(repository)
    service = Service(repository, args.demo, collector)
    if args.preview:
        from .preview import run_preview
        try:
            run_preview(service, html_path, args.port)
        finally:
            service.close()
    else:
        desktop = Desktop(service, args.background, args.smoke_test, log_handler, args.update_result)
        desktop.run(html_path)
        if args.smoke_test and not desktop.smoke_passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
