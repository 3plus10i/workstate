"""Permanent SQLite records with explicit cleanup and manual CSV export."""
from contextlib import closing, contextmanager
import csv
from dataclasses import astuple
from datetime import datetime
import io
import json
from pathlib import Path
import sqlite3
import threading

from .models import Activity
from .settings import validate_settings

CSV_FIELDS = ["schema_version", "timestamp", "minute", "active", "process", "title"]


def write_csv(stream, rows):
    writer = csv.writer(stream)
    writer.writerow(CSV_FIELDS)
    for row in rows:
        stamp = datetime.fromtimestamp(row.minute * 60).astimezone().isoformat(timespec="minutes")
        writer.writerow([1, stamp, row.minute, int(row.active), row.process, row.title])


class Repository:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "activity.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS activity (
                    minute INTEGER PRIMARY KEY,
                    active INTEGER NOT NULL CHECK(active IN (0,1)),
                    process TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def settings(self):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='preferences'").fetchone()
        return validate_settings(json.loads(row[0]) if row else {})

    def save_settings(self, settings):
        result = validate_settings(settings)
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('preferences', ?)", (json.dumps(result, ensure_ascii=False),))
        return result

    def write(self, row: Activity):
        self.write_many([row])

    def write_many(self, rows):
        with self.lock, self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO activity VALUES (?,?,?,?)", (astuple(r) for r in rows))

    def recent(self, end_minute, page, page_size):
        start_minute = max(0, end_minute - 480)
        with self.lock, self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM activity WHERE minute>=? AND minute<?", (start_minute, end_minute)).fetchone()[0]
            page = min(page, max(1, (total + page_size - 1) // page_size))
            rows = db.execute(
                "SELECT * FROM activity WHERE minute>=? AND minute<? ORDER BY minute DESC LIMIT ? OFFSET ?",
                (start_minute, end_minute, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "start": datetime.fromtimestamp(start_minute * 60).astimezone().isoformat(),
            "end": datetime.fromtimestamp(end_minute * 60).astimezone().isoformat(),
            "endMinute": end_minute, "page": page, "pageSize": page_size, "total": total,
            "rows": [{"minute": row[0], "time": datetime.fromtimestamp(row[0] * 60).astimezone().isoformat(), "active": bool(row[1]), "process": row[2], "title": row[3]} for row in rows],
        }

    def query(self, start: int, end: int):
        with self.lock, self.connect() as db:
            return [Activity(r[0], bool(r[1]), r[2], r[3]) for r in db.execute(
                "SELECT * FROM activity WHERE minute>=? AND minute<? ORDER BY minute", (start, end)
            )]

    def count_range(self, start, end):
        with self.lock, self.connect() as db:
            return db.execute(
                "SELECT COUNT(*) FROM activity WHERE (? IS NULL OR minute>=?) AND minute<?", (start, start, end)
            ).fetchone()[0]

    def delete_range(self, start, end, expected_count):
        with self.lock:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute(
                    "SELECT COUNT(*) FROM activity WHERE (? IS NULL OR minute>=?) AND minute<?", (start, start, end)
                ).fetchone()[0]
                if count != expected_count:
                    raise ValueError("范围内的记录已变化，请重新预览后清理")
                removed = db.execute(
                    "DELETE FROM activity WHERE (? IS NULL OR minute>=?) AND minute<?", (start, start, end)
                ).rowcount
            compacted = True
            try:
                with self.connect() as db:
                    db.execute("VACUUM")
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                # Deletion has committed; free pages can still be reused if compaction fails.
                compacted = False
            return {"deletedRows": removed, "compacted": compacted}

    def preview_import(self, source):
        with self.lock, self.connect() as db:
            db.execute('ATTACH DATABASE ? AS legacy', (str(source.path),))
            duplicates = db.execute('SELECT COUNT(*) FROM legacy.activity old JOIN main.activity current ON old.time=current.minute').fetchone()[0]
        return {**source.summary(), 'duplicates': duplicates, 'newRecords': source.total - duplicates}

    def import_legacy(self, source):
        with self.lock, self.connect() as db, closing(source.records()) as records:
            db.execute('BEGIN IMMEDIATE')
            before = db.total_changes
            db.executemany('INSERT INTO activity (minute,active,process,title) VALUES (?,?,?,?) ON CONFLICT(minute) DO NOTHING',
                           (astuple(row) for row in records))
            imported = db.total_changes - before
        return {**source.summary(), 'imported': imported, 'duplicates': source.total - imported}

    def inventory(self):
        with self.lock, self.connect() as db:
            count, first, last = db.execute("SELECT COUNT(*), MIN(minute), MAX(minute) FROM activity").fetchone()
            return {"directory": str(self.directory), "databaseBytes": self.path.stat().st_size,
                    "recordCount": count, "firstMinute": first, "lastMinute": last}

    def export(self, start: int, end: int):
        stream = io.StringIO(newline="")
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT * FROM activity WHERE minute>=? AND minute<? ORDER BY minute", (start, end))
            count = 0
            def records():
                nonlocal count
                for r in rows:
                    count += 1
                    yield Activity(r[0], bool(r[1]), r[2], r[3])
            write_csv(stream, records())
        return "\ufeff" + stream.getvalue(), count
