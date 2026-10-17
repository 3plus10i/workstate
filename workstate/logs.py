"""Daily diagnostic log rotation with one calendar month of retention."""
from datetime import date, datetime
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import time

from .models import month_before


class MonthlyLogHandler(TimedRotatingFileHandler):
    def __init__(self, directory):
        super().__init__(Path(directory) / 'workstate.log', when='midnight', backupCount=1, encoding='utf-8')
        self.maintain()

    def getFilesToDelete(self):
        cutoff = month_before(date.today(), 1)
        base = Path(self.baseFilename)
        expired = []
        for prefix in (base.name, 'pcstate.log'):
            for path in base.parent.glob(prefix + '.*'):
                suffix = path.name[len(prefix) + 1:]
                if not path.is_file():
                    continue
                try:
                    day = date.fromisoformat(suffix)
                except ValueError:
                    # Recognize backups from the earlier size-based logger as well.
                    if not suffix.isdigit():
                        continue
                    day = datetime.fromtimestamp(path.stat().st_mtime).date()
                if day < cutoff:
                    expired.append(str(path))
        return sorted(expired)

    def maintain(self):
        with self.lock:
            if time.time() >= self.rolloverAt:
                self.doRollover()
            for name in self.getFilesToDelete():
                Path(name).unlink(missing_ok=True)


def configure_logging(directory):
    handler = MonthlyLogHandler(directory)
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    return handler
