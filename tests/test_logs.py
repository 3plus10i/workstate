from datetime import date, datetime
import logging
import os
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch
import uuid

from workstate.logs import MonthlyLogHandler


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2024, 5, 31)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / '.runtime' / 'tests'
        self.path = self.root / uuid.uuid4().hex
        self.path.mkdir(parents=True)

    def tearDown(self):
        assert self.path.resolve().is_relative_to(self.root.resolve())
        shutil.rmtree(self.path)

    def test_one_calendar_month_retention_and_legacy_backups(self):
        for suffix in ('2024-04-29', '2024-04-30', '2024-05-01', '1', '2', 'notes'):
            (self.path / f'workstate.log.{suffix}').write_text('diagnostic', encoding='utf-8')
        old = datetime(2024, 4, 29, 12).timestamp()
        recent = datetime(2024, 5, 10, 12).timestamp()
        os.utime(self.path / 'workstate.log.1', (old, old))
        os.utime(self.path / 'workstate.log.2', (recent, recent))
        (self.path / 'pcstate.log.2024-04-29').write_text('old brand, expired')
        (self.path / 'pcstate.log.2024-05-10').write_text('old brand, recent')
        (self.path / 'activity.sqlite3').write_text('keep', encoding='utf-8')
        with patch('workstate.logs.date', FixedDate):
            handler = MonthlyLogHandler(self.path)
            try:
                self.assertFalse((self.path / 'workstate.log.2024-04-29').exists())
                self.assertFalse((self.path / 'workstate.log.1').exists())
                self.assertFalse((self.path / 'pcstate.log.2024-04-29').exists())
                self.assertTrue((self.path / 'pcstate.log.2024-05-10').exists())
                for suffix in ('2024-04-30', '2024-05-01', '2', 'notes'):
                    self.assertTrue((self.path / f'workstate.log.{suffix}').exists())
                self.assertEqual((self.path / 'activity.sqlite3').read_text(), 'keep')
            finally:
                handler.close()

    def test_daily_rotation_and_cleanup_without_new_messages(self):
        handler = MonthlyLogHandler(self.path)
        try:
            record = logging.LogRecord('test',logging.INFO,'test',1,'before rollover',(),None)
            handler.handle(record)
            handler.rolloverAt = int(time.time()) - 1
            (self.path / 'workstate.log.2001-01-01').write_text('expired')
            handler.maintain()
            handler.handle(logging.LogRecord('test',logging.INFO,'test',2,'after rollover',(),None))
            self.assertFalse((self.path / 'workstate.log.2001-01-01').exists())
            self.assertIn('after rollover',(self.path / 'workstate.log').read_text())
            archives = list(self.path.glob('workstate.log.*'))
            self.assertEqual(len(archives),1)
            self.assertIn('before rollover',archives[0].read_text())
        finally:
            handler.close()
