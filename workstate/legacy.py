"""Read-only snapshots of the original PCState database formats."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import time
from tempfile import TemporaryDirectory

from .models import Activity


class LegacyImport:
    def __init__(self, source, repository):
        source = Path(source).resolve()
        if not source.is_file():
            raise ValueError("旧数据库文件不存在")
        if source.samefile(repository.path):
            raise ValueError("不能导入当前正在使用的数据库")
        self.filename = source.name
        self._temporary = TemporaryDirectory(prefix='.import-', dir=repository.directory, ignore_cleanup_errors=True)
        self.path = Path(self._temporary.name) / 'legacy.sqlite3'
        try:
            # SQLite backup includes committed WAL records and gives preview/confirmation
            # one consistent snapshot even if the original recorder is still running.
            with closing(self._connect(source)) as original, closing(sqlite3.connect(self.path)) as snapshot:
                last_progress = time.monotonic()
                def progress(status, remaining, total):
                    nonlocal last_progress
                    if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                        if time.monotonic() - last_progress > 5:
                            raise ValueError("旧数据库正在写入，请稍后重试或先退出旧版程序")
                    else:
                        last_progress = time.monotonic()
                original.backup(snapshot, pages=1024, progress=progress, sleep=0.1)
            with closing(self._connect(self.path)) as db:
                table = db.execute("SELECT sql FROM sqlite_master WHERE name='activity' AND type='table'").fetchone()
                columns = db.execute('PRAGMA table_info(activity)').fetchall()
                names = {column[1].casefold() for column in columns}
                if not table or 'VIRTUAL' in table[0].upper() or not {'time', 'is_active', 'prog_name'} <= names:
                    raise ValueError("不是原版 PCState 的数据库，请选择旧版 pcstate.db 文件")
                primary = [column[1].casefold() for column in columns if column[5]]
                if primary != ['time']:
                    raise ValueError("旧数据库的记录结构不受支持")
                optional = [name if name in names else 'NULL' for name in ('process', 'title', 'win_title')]
                self._select = f"SELECT time, is_active, prog_name, {', '.join(optional)} FROM activity ORDER BY time"
                self.fallback_count = db.execute(f"SELECT COUNT(*) FROM activity WHERE LENGTH(TRIM(COALESCE({optional[0]},'')))=0 AND LENGTH(TRIM(COALESCE(prog_name,'')))>0").fetchone()[0]
            self.total = 0
            self.first_minute = self.last_minute = None
            for row in self.records():
                self.total += 1
                if self.first_minute is None:
                    self.first_minute = row.minute
                self.last_minute = row.minute
            if not self.total:
                raise ValueError("旧数据库中没有活动记录")
        except (sqlite3.Error, OSError) as error:
            self.close()
            raise ValueError("无法读取旧数据库，请确认文件完整且可访问") from error
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _connect(path):
        db = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)
        db.execute('PRAGMA trusted_schema=OFF')
        return db

    def records(self):
        with closing(self._connect(self.path)) as db:
            for index, (minute, active, name, process, title, win_title) in enumerate(db.execute(self._select), 1):
                valid = (type(minute) is int and minute >= 0 and type(active) is int and active in (0, 1)
                         and all(value is None or isinstance(value, str) for value in (name, process, title, win_title)))
                if valid:
                    try:
                        datetime.fromtimestamp(minute * 60)
                    except (ValueError, OverflowError, OSError):
                        valid = False
                if not valid:
                    raise ValueError(f"旧数据库第 {index} 条记录格式无效，未导入任何数据")
                raw_process = process if process and process.strip() else ''
                fallback = name if name and name.strip() else '未知程序'
                yield Activity(minute, bool(active), raw_process or fallback, title or win_title or '')

    def summary(self):
        return {'filename': self.filename, 'total': self.total, 'firstMinute': self.first_minute,
                'lastMinute': self.last_minute, 'fallbackCount': self.fallback_count}

    def close(self):
        self._temporary.cleanup()
