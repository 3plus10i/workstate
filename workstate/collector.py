"""Minute-boundary sampler. Do not invent history across sleep, pause or restart."""
import ctypes
from ctypes import wintypes
import logging
import threading
import time

from .models import Activity
from .classification import process_key
from .settings import IDLE_SECONDS, excluded_processes

log = logging.getLogger(__name__)


def idle_seconds():
    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    value = LastInput()
    value.cbSize = ctypes.sizeof(value)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(value)):
        return 10**9
    # Both values are DWORD milliseconds: compare modulo 2**32 (49.7-day rollover).
    tick = ctypes.windll.kernel32.GetTickCount()
    return ((tick & 0xFFFFFFFF) - value.dwTime & 0xFFFFFFFF) / 1000


def foreground():
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    window = user.GetForegroundWindow()
    if not window:
        return "", ""
    title = ctypes.create_unicode_buffer(4096)
    user.GetWindowTextW(window, title, len(title))
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        process = path.value.rsplit("\\", 1)[-1] if handle and kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) else ""
    finally:
        if handle:
            kernel.CloseHandle(handle)
    return process, title.value


class Collector:
    def __init__(self, repository, clock=time.time):
        self.repository = repository
        self.clock = clock
        self.stop_event = threading.Event()
        self.paused = False
        self.error = None
        self.active = False
        self.last_minute = None
        self._revision = 0
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="activity-sampler", daemon=True)
        self._thread.start()

    def stop(self):
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def set_paused(self, paused):
        self.paused = paused
        self._revision += 1

    def _run(self):
        while not self.stop_event.is_set():
            previous = int(self.clock() // 60)
            revision = self._revision
            if self.stop_event.wait(60 - self.clock() % 60 + 0.05):
                break
            current = int(self.clock() // 60)
            try:
                if self.paused or revision != self._revision or current != previous + 1:
                    continue
                process, title = foreground()
                self.active = idle_seconds() < IDLE_SECONDS
                if process_key(process) in excluded_processes(self.repository.settings()):
                    continue
                self.repository.write(Activity(previous, self.active, process, title))
                self.last_minute = previous
                self.error = None
            except Exception:
                self.error = "活动记录失败，请检查数据目录；已有记录已保留"
                log.exception("Collection failed")
