from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
import hashlib
import sqlite3
from unittest.mock import Mock, patch

from workstate.legacy import LegacyImport
from workstate.models import Activity, minute_at
from workstate.report import build_report
from workstate.service import Service
from test_core import RepositoryFixture


class LegacyTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.source = self.test_directory / 'pcstate.db'
        self.minute = minute_at(date(2026, 8, 20), 10)
        self.services = []

    def tearDown(self):
        for service in self.services:
            service.close()
        super().tearDown()

    def create_source(self, rows=None, columns='time INTEGER PRIMARY KEY, is_active INTEGER, prog_name TEXT, process TEXT, title TEXT'):
        rows = rows if rows is not None else [(self.minute, 1, 'VSCode - Project', 'Code.exe', 'main.py - Project - VSCode')]
        with closing(sqlite3.connect(self.source)) as db:
            db.execute(f'CREATE TABLE activity ({columns})')
            if rows:
                db.executemany(f"INSERT INTO activity VALUES ({','.join('?' for _ in rows[0])})", rows)
            db.commit()

    def service(self):
        service = Service(self.repo)
        service.desktop = Mock(select_legacy_database=Mock(return_value=self.source))
        self.services.append(service)
        return service

    def preview(self, service):
        result = service.dispatch('importPreview')
        self.assertTrue(result['ok'], result)
        return result['data']

    def assert_no_snapshots(self):
        self.assertEqual(list(self.test_directory.glob('.import-*')), [])

    def test_import_preserves_raw_records_current_settings_and_existing_minutes(self):
        title = '报告, "研究"\n第二行 - Word'
        self.create_source([(self.minute,1,'old editor','Code.exe','main.py - Project - VSCode'),
                            (self.minute+1,1,'old browser','chrome.exe','GitHub - Google Chrome'),
                            (self.minute+2,0,None,None,None), (self.minute+3,1,'旧版名称',None,title)])
        settings = self.repo.save_settings({'dayStartHour':0, 'customIdeProcesses':['trae']})
        existing = Activity(self.minute+1,False,'new.exe','本版记录')
        self.repo.write(existing)
        before = hashlib.sha256(self.source.read_bytes()).digest()
        service = self.service()
        preview = self.preview(service)
        self.assertEqual((preview['total'],preview['newRecords'],preview['duplicates'],preview['fallbackCount']),(4,3,1,1))
        self.assertEqual(self.repo.inventory()['recordCount'],1)
        result = service.dispatch('importCommit',{'token':preview['token']})
        self.assertTrue(result['ok'],result)
        self.assertEqual((result['data']['imported'],result['data']['duplicates']),(3,1))
        rows = self.repo.query(self.minute,self.minute+4)
        self.assertEqual(rows[1],existing)
        self.assertEqual(rows[0].title,'main.py - Project - VSCode')
        self.assertEqual(rows[2],Activity(self.minute+2,False,'未知程序',''))
        self.assertEqual(rows[3],Activity(self.minute+3,True,'旧版名称',title))
        self.assertEqual(self.repo.settings(),settings)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(),before)
        self.assertEqual(build_report(self.repo,'2026-08-20','2026-08-20')['summary']['activeMinutes'],2)
        self.assert_no_snapshots()

    def test_three_column_format_retains_legacy_names_and_timestamp_units(self):
        self.create_source([(self.minute,1,'Chrome浏览器 - GitHub'),(self.minute+1,0,'旧版名称')],
                           'time INTEGER PRIMARY KEY, is_active INTEGER, prog_name TEXT')
        with closing(LegacyImport(self.source,self.repo)) as source:
            self.assertEqual(source.fallback_count,2)
            self.repo.import_legacy(source)
        self.assertEqual(self.repo.query(self.minute,self.minute+2),[
            Activity(self.minute,True,'Chrome浏览器 - GitHub',''),Activity(self.minute+1,False,'旧版名称','')])

    def test_win_title_is_used_when_new_title_column_is_empty(self):
        self.create_source([(self.minute,1,'旧名','旧窗口标题','Code.exe',''),
                            (self.minute+1,1,'旧名','更早标题','Code.exe','新窗口标题')],
                           'time INTEGER PRIMARY KEY, is_active INTEGER, prog_name TEXT, win_title TEXT, process TEXT, title TEXT')
        with closing(LegacyImport(self.source,self.repo)) as source:
            self.repo.import_legacy(source)
        self.assertEqual([row.title for row in self.repo.query(self.minute,self.minute+2)],['旧窗口标题','新窗口标题'])

    def test_preview_snapshot_is_stable_if_original_changes(self):
        self.create_source()
        service = self.service()
        preview = self.preview(service)
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE activity SET title='later title'")
            db.execute('INSERT INTO activity VALUES (?,?,?,?,?)',(self.minute+1,1,'New','new.exe','later record'))
            db.commit()
        result = service.dispatch('importCommit',{'token':preview['token']})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['imported'],1)
        self.assertEqual(self.repo.query(self.minute,self.minute+2),[Activity(self.minute,True,'Code.exe','main.py - Project - VSCode')])

    def test_committed_wal_records_are_included_without_modifying_source(self):
        self.create_source()
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('INSERT INTO activity VALUES (?,?,?,?,?)',(self.minute+1,0,'Idle','idle.exe','idle'))
            db.commit()
            before = self.source.read_bytes()
            with closing(LegacyImport(self.source,self.repo)) as source:
                self.assertEqual(source.total,2)
                self.repo.import_legacy(source)
            self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(self.repo.inventory()['recordCount'],2)

    def test_repeat_import_and_replay_do_not_duplicate_or_overwrite(self):
        self.create_source()
        service = self.service()
        first = self.preview(service)
        self.assertEqual(service.dispatch('importCommit',{'token':first['token']})['data']['imported'],1)
        self.assertFalse(service.dispatch('importCommit',{'token':first['token']})['ok'])
        second = self.preview(service)
        self.assertEqual((second['newRecords'],second['duplicates']),(0,1))
        self.assertEqual(service.dispatch('importCommit',{'token':second['token']})['data']['imported'],0)
        self.assertEqual(self.repo.inventory()['recordCount'],1)
        self.assert_no_snapshots()

    def test_recount_conflicts_when_new_version_records_after_preview(self):
        self.create_source()
        service = self.service()
        preview = self.preview(service)
        current = Activity(self.minute,False,'current.exe','recorded after preview')
        self.repo.write(current)
        result = service.dispatch('importCommit',{'token':preview['token']})
        self.assertTrue(result['ok'])
        self.assertEqual((result['data']['imported'],result['data']['duplicates']),(0,1))
        self.assertEqual(self.repo.query(self.minute,self.minute+1),[current])

    def test_cancel_replacement_expiry_and_exit_remove_snapshots(self):
        self.create_source()
        service = self.service()
        first = self.preview(service)
        second = self.preview(service)
        self.assertFalse(service.dispatch('importCancel',{'token':first['token']})['data'])
        self.assertEqual(len(list(self.test_directory.glob('.import-*'))),1)
        self.assertTrue(service.dispatch('importCancel',{'token':second['token']})['data'])
        self.assert_no_snapshots()
        with patch('workstate.service.time.monotonic',return_value=0):
            expired = self.preview(service)
        with patch('workstate.service.time.monotonic',return_value=601):
            self.assertFalse(service.dispatch('importCommit',{'token':expired['token']})['ok'])
        self.assert_no_snapshots()
        self.preview(service)
        service.close()
        self.assert_no_snapshots()

    def test_cancelled_file_dialog_and_non_desktop_requests_do_not_write(self):
        service = self.service()
        service.desktop.select_legacy_database.return_value = None
        self.assertEqual(service.dispatch('importPreview')['data'],{'cancelled':True})
        service.desktop = None
        self.assertFalse(service.dispatch('importPreview',{'path':str(self.repo.path)})['ok'])
        self.assertEqual(self.repo.inventory()['recordCount'],0)
        self.assert_no_snapshots()

    def test_invalid_rows_abort_before_any_import(self):
        self.create_source([(self.minute,1,'ok','Code.exe','valid'),(self.minute+1,2,'bad','bad.exe','invalid')])
        result = self.service().dispatch('importPreview')
        self.assertFalse(result['ok'])
        self.assertIn('第 2 条',result['error'])
        self.assertEqual(self.repo.inventory()['recordCount'],0)
        self.assert_no_snapshots()

    def test_corrupt_empty_and_unrelated_databases_are_rejected(self):
        service = self.service()
        self.source.write_bytes(b'not sqlite')
        self.assertFalse(service.dispatch('importPreview')['ok'])
        self.source.unlink()
        self.create_source([])
        self.assertIn('没有活动记录',service.dispatch('importPreview')['error'])
        service.desktop.select_legacy_database.return_value = self.repo.path
        self.assertIn('当前正在使用',service.dispatch('importPreview')['error'])
        unrelated = self.test_directory / 'unrelated.db'
        with closing(sqlite3.connect(unrelated)) as db:
            db.execute('CREATE TABLE activity (minute INTEGER PRIMARY KEY, active INTEGER)')
        service.desktop.select_legacy_database.return_value = unrelated
        self.assertIn('不是原版',service.dispatch('importPreview')['error'])
        self.assert_no_snapshots()

    def test_import_transaction_rolls_back_if_destination_write_fails(self):
        self.create_source([(self.minute,1,'one','one.exe','one'),(self.minute+1,1,'two','two.exe','two')])
        service = self.service()
        preview = self.preview(service)
        with self.repo.connect() as db:
            db.execute(f"CREATE TRIGGER fail_import BEFORE INSERT ON activity WHEN NEW.minute={self.minute+1} BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertLogs('workstate.service',level='ERROR'):
            result = service.dispatch('importCommit',{'token':preview['token']})
        self.assertFalse(result['ok'])
        self.assertEqual(self.repo.inventory()['recordCount'],0)
        self.assert_no_snapshots()

    def test_concurrent_confirmation_only_imports_once(self):
        self.create_source()
        service = self.service()
        preview = self.preview(service)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: service.dispatch('importCommit',{'token':preview['token']}),range(2)))
        self.assertEqual(sum(result['ok'] for result in results),1)
        self.assertEqual(self.repo.inventory()['recordCount'],1)
        self.assert_no_snapshots()
