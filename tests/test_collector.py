from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from workstate.collector import Collector, idle_seconds
from workstate.models import Activity
from workstate.service import Service
from workstate.storage import Repository


class ClockEvent:
    def __init__(self, collector, skipped=False, paused=False):
        self.calls = 0
        self.collector = collector
        self.skipped = skipped
        self.paused = paused

    def is_set(self):
        return False

    def wait(self, _):
        self.calls += 1
        if self.paused:
            self.collector.set_paused(True)
        return self.calls > 1


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / '.runtime' / 'tests'
        self.path = self.root / uuid.uuid4().hex
        self.path.mkdir(parents=True)
        self.repository = Repository(self.path)

    def tearDown(self):
        assert self.path.resolve().is_relative_to(self.root.resolve())
        shutil.rmtree(self.path)

    def sample(self, times, pause=False):
        sequence = iter(times)
        collector = Collector(self.repository, clock=lambda: next(sequence))
        collector.stop_event = ClockEvent(collector, paused=pause)
        with patch('workstate.collector.foreground', return_value=('Code.exe','file.py - Project - VSCode')), patch('workstate.collector.idle_seconds',return_value=15):
            collector._run()
        return collector

    def test_records_completed_minute(self):
        collector = self.sample([6001,6001,6061,6061,6061])
        self.assertEqual(collector.last_minute,100)
        rows = self.repository.query(100,102)
        self.assertEqual(rows,[Activity(100,True,'Code.exe','file.py - Project - VSCode')])

    def test_no_fill_after_sleep(self):
        self.sample([6001,6001,9661,9661,9661])
        self.assertEqual(self.repository.inventory()['recordCount'],0)

    def test_blacklisted_process_is_not_recorded(self):
        sequence = iter([6001,6001,6061,6061,6061])
        collector = Collector(self.repository, clock=lambda: next(sequence))
        collector.stop_event = ClockEvent(collector)
        with patch('workstate.collector.foreground', return_value=('LockApp.exe','锁屏')), patch('workstate.collector.idle_seconds',return_value=75):
            collector._run()
        rows = self.repository.query(100,101)
        self.assertEqual(rows,[])
        self.assertIsNone(collector.last_minute)

    def test_blacklist_comments_and_setting_changes_take_effect(self):
        self.repository.save_settings({'excludedProcesses':['cOdE.EXE // 编辑器']})
        self.sample([6001,6001,6061,6061,6061])
        self.assertEqual(self.repository.inventory()['recordCount'],0)
        self.repository.save_settings({'excludedProcesses':[]})
        self.sample([6061,6061,6121,6121,6121])
        self.assertEqual(self.repository.query(101,102)[0].process,'Code.exe')

    def test_collection_does_not_expire_old_records_or_create_archives(self):
        self.repository.write(Activity(1,True,'old.exe'))
        self.sample([6001,6001,6061,6061,6061])
        self.assertEqual(self.repository.inventory()['recordCount'],2)
        self.assertFalse((self.path/'archives').exists())

    def test_no_write_if_paused_during_interval(self):
        self.sample([6001,6001,6061,6061,6061],pause=True)
        self.assertEqual(self.repository.inventory()['recordCount'],0)

    def test_invalid_pause_and_settings_are_rejected(self):
        service = Service(self.repository)
        self.assertFalse(service.dispatch('recording',{'paused':'yes'})['ok'])
        self.assertFalse(service.dispatch('saveSettings',{'dayStartHour':True})['ok'])
        self.assertFalse(service.dispatch('unknown')['ok'])


if __name__ == '__main__':
    unittest.main()
