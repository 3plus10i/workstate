"""One transport-independent application API for desktop and local development."""
from datetime import date, datetime, timedelta
import hmac
import logging
import secrets
import threading
import time
import sys

from . import __version__
from .models import minute_at, month_before, parse_range
from .legacy import LegacyImport
from .report import build_report
from .settings import DEFAULT_PROGRAMS, validate_settings
from .updates import Updater

log = logging.getLogger(__name__)
PAUSE_MINUTES = (5, 60, 240, 1440)


class Service:
    def __init__(self, repository, demo=False, collector=None, clock=None, timer_factory=None):
        self.repository = repository
        self.demo = demo
        self.collector = collector
        self.paused = False
        self.desktop = None
        self._cleanup_plan = None
        self._cleanup_lock = threading.Lock()
        self._recording_lock = threading.RLock()
        self._clock = clock or time.time
        self._timer_factory = timer_factory or threading.Timer
        self._resume_at = None
        self._resume_timer = None
        self._pause_revision = 0
        self._closed = False
        self._import_lock = threading.RLock()
        self._import_plan = None
        self.updater = Updater(sys.executable, repository.directory, supported=False, demo=demo)

    def _set_recording(self, minutes=None):
        with self._recording_lock:
            if self._closed:
                raise ValueError("程序已退出")
            if minutes is None and not self.paused:
                return
            self._pause_revision += 1
            if self._resume_timer:
                self._resume_timer.cancel()
                self._resume_timer = None
            self.paused = minutes is not None
            self._resume_at = self._clock() + minutes * 60 if self.paused else None
            if self.collector:
                self.collector.set_paused(self.paused)
            if self.paused:
                self._schedule_resume(minutes * 60, self._pause_revision)

    def _schedule_resume(self, seconds, revision):
        self._resume_timer = self._timer_factory(seconds, lambda: self._resume_if_due(revision))
        self._resume_timer.daemon = True
        self._resume_timer.start()

    def _resume_if_due(self, revision=None):
        with self._recording_lock:
            if self._closed or not self.paused or (revision is not None and revision != self._pause_revision):
                return
            remaining = self._resume_at - self._clock()
            if remaining <= 0:
                self._set_recording()
            elif revision is not None:
                # A backwards wall-clock adjustment must not resume before the displayed time.
                self._schedule_resume(remaining, revision)

    def close(self):
        self.updater.close()
        with self._recording_lock:
            self._closed = True
            self._pause_revision += 1
            if self._resume_timer:
                self._resume_timer.cancel()
                self._resume_timer = None
        with self._import_lock:
            if self._import_plan:
                self._import_plan[2].close()
                self._import_plan = None

    def status(self):
        with self._recording_lock:
            self._resume_if_due()
            collector = self.collector
            resume_at = datetime.fromtimestamp(self._resume_at).astimezone().isoformat() if self._resume_at is not None else None
            return {"demo": self.demo, "paused": self.paused, "resumeAt": resume_at, "collecting": collector is not None and not self.paused, "active": collector.active if collector else False, "error": collector.error if collector else None, "lastMinute": collector.last_minute if collector else None, "now": datetime.now().astimezone().isoformat(), "version": __version__}

    def dispatch(self, method, payload=None):
        try:
            payload = payload or {}
            if not isinstance(payload, dict):
                raise ValueError("请求格式无效")
            data = self._dispatch(method, payload)
            return {"ok": True, "data": data}
        except (ValueError, TypeError, KeyError) as error:
            return {"ok": False, "error": str(error)}
        except Exception:
            log.exception("Application operation failed: %s", method)
            return {"ok": False, "error": "操作失败，请检查数据目录和可用磁盘空间后重试。"}

    def _dispatch(self, method, payload):
        if method == 'updateStatus':
            return self.updater.status()
        if method == 'updateCheck':
            return self.updater.check()
        if method == 'updateDownload':
            return self.updater.download()
        if method == 'updateInstall' and self.desktop:
            self.updater.prepare_install()
            timer = threading.Timer(0.5, self.desktop.quit)
            timer.daemon = True
            timer.start()
            return self.updater.status()
        if method == "bootstrap":
            return {"settings": self.repository.settings(), "programDefaults": DEFAULT_PROGRAMS, "storage": self.repository.inventory(), "status": self.status(), "startup": self.desktop.startup_enabled() if self.desktop else False}
        if method == "status":
            return self.status()
        if method == "report":
            expanded = payload.get("expanded")
            if expanded is not None and type(expanded) is not bool:
                raise ValueError("细分开关格式无效")
            return build_report(self.repository, payload["start"], payload["end"], expanded)
        if method == "recent":
            now = int(datetime.now().timestamp() // 60)
            end = payload.get("endMinute", now)
            page, size = payload.get("page", 1), payload.get("pageSize", 30)
            if type(page) is not int or page < 1 or type(size) is not int or size not in (30, 60, 120):
                raise ValueError("分页参数无效")
            if type(end) is not int or not 0 < end <= now:
                raise ValueError("查询时间无效")
            return self.repository.recent(end, page, size)
        if method == "saveSettings":
            return self.repository.save_settings(payload)
        if method == "activityPreview":
            if set(payload) - {"dayStartHour", "excludedProcesses"}:
                raise ValueError("预览参数无效")
            settings = validate_settings({**self.repository.settings(), **payload})
            today = (datetime.now() - timedelta(hours=settings["dayStartHour"])).date().isoformat()
            summary = build_report(self.repository, today, today, False, settings)["summary"]
            return {"date": today, "oneMinute": summary["rawActiveMinutes"], "fiveMinutes": summary["fiveMinuteActiveMinutes"]}
        if method == "recording":
            if set(payload) == {"paused"} and payload["paused"] is False:
                self._set_recording()
            elif set(payload) == {"pauseMinutes"} and type(payload["pauseMinutes"]) is int and payload["pauseMinutes"] in PAUSE_MINUTES:
                self._set_recording(payload["pauseMinutes"])
            else:
                raise ValueError("请选择暂停 5 分钟、1 小时、4 小时或 1 天")
            return self.status()
        if method == "storage":
            return self.repository.inventory()
        if method == "importPreview" and self.desktop:
            source = self.desktop.select_legacy_database()
            if not source:
                return {'cancelled': True}
            with self._import_lock:
                if self._closed:
                    raise ValueError("程序已退出")
                if self._import_plan:
                    self._import_plan[2].close()
                    self._import_plan = None
                snapshot = LegacyImport(source, self.repository)
                try:
                    preview = self.repository.preview_import(snapshot)
                except BaseException:
                    snapshot.close()
                    raise
                token = secrets.token_urlsafe(24)
                self._import_plan = (token, time.monotonic() + 600, snapshot)
                return {**preview, 'token': token}
        if method in {'importCommit', 'importCancel'}:
            with self._import_lock:
                plan = self._import_plan
                token = payload.get('token')
                matches = isinstance(token, str) and plan and hmac.compare_digest(token, plan[0])
                if not matches:
                    if method == 'importCancel':
                        return False
                    raise ValueError("导入预览已失效，请重新选择旧数据库")
                self._import_plan = None
                try:
                    if method == 'importCancel':
                        return True
                    if time.monotonic() > plan[1] or self._closed:
                        raise ValueError("导入预览已失效，请重新选择旧数据库")
                    result = self.repository.import_legacy(plan[2])
                    return {**result, 'storage': self.repository.inventory()}
                finally:
                    plan[2].close()
        if method == "cleanupPreview":
            mode = payload.get("mode")
            if mode == "range":
                first, last = date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])
                if last < first:
                    raise ValueError("结束日期不能早于开始日期")
                begin, finish = minute_at(first), minute_at(last + timedelta(days=1))
                latest = last
                selection = {"mode": mode, "start": first.isoformat(), "end": last.isoformat()}
            elif mode == "before":
                before = date.fromisoformat(payload["before"])
                begin, finish = None, minute_at(before)
                latest = before
                selection = {"mode": mode, "before": before.isoformat()}
            else:
                raise ValueError("请选择清理方式")
            if latest > date.today():
                raise ValueError("清理日期不能晚于今天")
            count = self.repository.count_range(begin, finish)
            token = secrets.token_urlsafe(24) if count else None
            with self._cleanup_lock:
                self._cleanup_plan = (token, time.monotonic() + 300, begin, finish, count) if token else None
            return {**selection, "count": count, "token": token}
        if method == "cleanup":
            token = payload.get("token")
            with self._cleanup_lock:
                plan = self._cleanup_plan
                if not isinstance(token, str) or not plan or not hmac.compare_digest(token, plan[0]) or time.monotonic() > plan[1]:
                    raise ValueError("清理预览已失效，请重新预览后确认")
                self._cleanup_plan = None
            result = self.repository.delete_range(plan[2], plan[3], plan[4])
            return {**result, "storage": self.repository.inventory()}
        if method == "export":
            first_day, last_day, first, last = parse_range(payload["start"], payload["end"], self.repository.settings()["dayStartHour"])
            if last_day >= month_before(first_day, -12):
                raise ValueError("导出区间最长为一年，请缩小日期区间")
            content, count = self.repository.export(first, last)
            name = f"WorkState_{payload['start']}_{payload['end']}.csv"
            if self.desktop:
                return self.desktop.save_export(content, name, count)
            return {"content": content, "filename": name, "count": count}
        if method == "openData" and self.desktop:
            self.desktop.open_data()
            return True
        if method == "startup" and self.desktop:
            if type(payload.get("enabled")) is not bool:
                raise ValueError("开机启动开关格式无效")
            self.desktop.set_startup(payload["enabled"])
            return self.desktop.startup_enabled()
        if method == "quit" and self.desktop:
            self.desktop.quit()
            return True
        raise ValueError("此操作仅在桌面应用中可用" if method in {"openData", "startup", "quit", "importPreview"} else "未知操作")
