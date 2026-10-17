"""Short-lived replacement mode of the same EXE, isolated from activity recording."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import subprocess
import sys
import threading
import time


def file_hash(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def read_job(path):
    path = Path(path).resolve()
    if path.name != 'job.json' or not path.parent.name.startswith('update-') or path.stat().st_size > 16384:
        raise ValueError('更新任务无效')
    job = json.loads(path.read_text(encoding='utf-8'))
    if job.get('protocol') != 1 or not isinstance(job.get('token'), str) or not re.fullmatch('[0-9a-f]{32}', job['token']):
        raise ValueError('更新任务格式无效')
    target = Path(job['target'])
    if not target.is_absolute() or target.suffix.lower() != '.exe' or target.resolve().is_relative_to(path.parent):
        raise ValueError('更新目标无效')
    if not Path(job['dataDirectory']).is_absolute():
        raise ValueError('数据目录无效')
    for key in ('newHash', 'oldHash'):
        if not isinstance(job.get(key), str) or not re.fullmatch('[0-9a-f]{64}', job[key]):
            raise ValueError('更新校验信息无效')
    return path, job


def independent_process(arguments):
    return subprocess.Popen(arguments, env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}, creationflags=subprocess.CREATE_NO_WINDOW)


def prepare_install(updater):
    directory = updater.directory
    target = updater.executable
    # Check write access before asking the running app to exit.
    probe = target.parent / f'.workstate-{secrets.token_hex(8)}.tmp'
    try:
        with probe.open('xb') as file:
            file.write(b'')
    finally:
        probe.unlink(missing_ok=True)
    token = secrets.token_hex(16)
    job = {'protocol': 1, 'token': token, 'target': str(target), 'dataDirectory': str(updater.data_directory),
           'version': updater.release.version, 'newHash': updater.executable_hash, 'oldHash': file_hash(target),
           'pids': [os.getpid(), os.getppid()], 'demo': updater.demo}
    job_path = directory / 'job.json'
    write_json(job_path, job)
    shutil.copy2(target, directory / 'worker.exe')
    process = independent_process([str(directory / 'worker.exe'), '--apply-update', str(job_path)])
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        ready = directory / 'worker-ready.json'
        if ready.exists() and json.loads(ready.read_text(encoding='utf-8')).get('token') == token:
            return
        if process.poll() is not None:
            raise ValueError('更新进程启动失败')
        time.sleep(0.1)
    raise ValueError('更新进程启动超时')


def wait_for_processes(pids, target, ready, timeout=45):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    try:
        for pid in pids:
            if type(pid) is not int or pid <= 0 or pid == os.getpid():
                raise ValueError('更新进程标识无效')
            handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
            if not handle:
                if ctypes.get_last_error() == 87:
                    continue
                raise OSError('无法等待原程序退出')
            handles.append(handle)
            buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)) or os.path.normcase(str(Path(buffer.value).resolve())) != os.path.normcase(str(target)):
                raise ValueError('原程序进程与更新目标不符')
        ready()
        deadline = time.monotonic() + timeout
        while True:
            results = [kernel.WaitForSingleObject(handle, 0) for handle in handles]
            if any(result not in (0, 258) for result in results):
                raise OSError('无法确认原程序退出状态')
            if all(result == 0 for result in results):
                break
            if time.monotonic() >= deadline:
                raise ValueError('等待原程序退出超时，未替换程序')
            time.sleep(0.1)
    finally:
        for handle in handles:
            kernel.CloseHandle(handle)


def replace_file(target, replacement, backup):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    if not kernel.ReplaceFileW(str(target), str(replacement), str(backup), 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def install(job_path, wait=wait_for_processes, replace=replace_file, launch=independent_process, timeout=60):
    job_path, job = read_job(job_path)
    directory, target = job_path.parent, Path(job['target']).resolve()
    source = directory / 'new.exe'
    backup = target.with_name(f'.workstate-{job["token"]}.bak')
    staging = target.with_name(f'.workstate-{job["token"]}.new')
    process, changed, stopped = None, False, False
    data_argument = str(Path(job['dataDirectory']).parent) if job.get('demo') else job['dataDirectory']
    arguments = [str(target), '--data-dir', data_argument] + (['--demo'] if job.get('demo') else [])
    try:
        if file_hash(source) != job['newHash']:
            raise ValueError('待安装程序校验失败')
        wait(job['pids'], target, lambda: write_json(directory / 'worker-ready.json', {'token': job['token']}))
        stopped = True
        if file_hash(target) != job['oldHash']:
            raise ValueError('程序文件已改变，请重新检查更新')
        shutil.copy2(source, staging)
        replace(target, staging, backup)
        changed = True
        process = launch(arguments + ['--update-result', str(job_path)])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            healthy = directory / 'healthy.json'
            if healthy.exists():
                result = json.loads(healthy.read_text(encoding='utf-8'))
                if result.get('token') == job['token'] and result.get('version') == job['version']:
                    try:
                        backup.unlink(missing_ok=True)
                        write_json(directory / 'finished.json', {'ok': True})
                    except OSError:
                        pass
                    return True
            if process.poll() is not None:
                break
            time.sleep(0.1)
        raise ValueError('新版本未能正常启动')
    except Exception as error:
        if process and process.poll() is None:
            # Only terminate the process tree started by this update operation.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=15)
            process.wait(timeout=15)
        if backup.exists() and file_hash(backup) == job['oldHash']:
            if changed and target.exists() and file_hash(target) != job['newHash']:
                raise ValueError('目标程序已被其他操作修改，已保留备份') from error
            os.replace(backup, target)
            launch(arguments)
        elif stopped and target.exists() and file_hash(target) == job['oldHash']:
            launch(arguments)
        write_json(directory / 'finished.json', {'ok': False, 'error': str(error)})
        return False
    finally:
        staging.unlink(missing_ok=True)


def confirm_startup(job_path, version, data_directory):
    path, job = read_job(job_path)
    if Path(job['target']).resolve() != Path(sys.executable).resolve() or job['version'] != version or Path(job['dataDirectory']).resolve() != Path(data_directory).resolve() or file_hash(sys.executable) != job['newHash']:
        raise ValueError('更新启动验证失败')
    write_json(path.parent / 'healthy.json', {'token': job['token'], 'version': version})

    def cleanup():
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not (path.parent / 'finished.json').exists():
            time.sleep(0.5)
        if not (path.parent / 'finished.json').exists():
            return
        directory = path.parent.resolve()
        if not directory.is_relative_to(path.parent.parent.resolve()) or directory == path.parent.parent.resolve():
            return
        for _ in range(30):
            try:
                # The directory comes from the validated, per-operation job file.
                shutil.rmtree(directory)
                return
            except OSError:
                time.sleep(1)
    threading.Thread(target=cleanup, name='update-cleanup', daemon=True).start()


def worker_main(job_path):
    try:
        success = install(job_path)
        if not success:
            path, _ = read_job(job_path)
            result = json.loads((path.parent / 'finished.json').read_text(encoding='utf-8'))
            ctypes.windll.user32.MessageBoxW(None, f'更新未完成：{result["error"]}。\n原有数据和设置已保留。', 'WorkState 更新', 0x10)
        return 0 if success else 1
    except Exception:
        ctypes.windll.user32.MessageBoxW(None, '更新未完成，请重新启动原程序后重试。原有数据和设置已保留。', 'WorkState 更新', 0x10)
        return 1
