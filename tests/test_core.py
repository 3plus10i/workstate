from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
from datetime import date, datetime, timedelta
import io
from pathlib import Path
import shutil
import sqlite3
import uuid
import unittest
from unittest.mock import patch

from workstate.classification import classify
from workstate.models import Activity, minute_at, month_before
from workstate.report import build_report
from workstate.service import Service
from workstate.settings import validate_settings
from workstate.storage import Repository


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.settings = validate_settings({})

    def test_explicit_ide_project_and_remote_title(self):
        for suffix in ("Visual Studio Code", "VSCode", "Code"):
            self.assertEqual(classify("Code.exe", f"main.py - Project alpha - {suffix}", self.settings).context, "Project alpha")
        self.assertEqual(classify("Code.exe", "● main.py - Project alpha [WSL: Ubuntu] - Visual Studio Code", self.settings).context, "Project alpha")

    def test_unknown_ide_and_loose_file_do_not_fragment(self):
        for title in ("main.py - Visual Studio Code", "An unfamiliar title"):
            self.assertEqual(classify("Code.exe", title, self.settings).context, "")

    def test_complete_document_identity_and_compatibility(self):
        a = classify("WINWORD.EXE", "abcdefghijklmnopqrstuvwx-A.docx - Word", self.settings)
        b = classify("WINWORD.EXE", "abcdefghijklmnopqrstuvwx-B.docx - Word", self.settings)
        self.assertNotEqual(a.context, b.context)
        self.assertEqual(classify("WINWORD.EXE", "报告.docx - 兼容性模式 - Word", self.settings).context, "报告")

    def test_site_keywords_match_anywhere_in_browser_titles(self):
        self.assertEqual(classify("chrome.exe", "How to use GitHub actions - Google Chrome", self.settings).context, "GitHub")
        self.assertEqual(classify("msedge.exe", "ChatGPT - Microsoft Edge", self.settings).context, "ChatGPT")
        self.assertEqual(classify("firefox.exe", "A guide to GitHub - Mozilla Firefox", self.settings).context, "GitHub")
        self.assertEqual(classify("chrome.exe", "Docker tutorial - Google Chrome", self.settings).context, "")
        self.assertEqual(classify("unknown.exe", "GitHub", self.settings).context, "")

    def test_site_keywords_prefer_longest_literal_case_insensitive_match(self):
        settings = validate_settings({"siteNames": ["Git", "GitHub", "GitHub Actions", "C++"]})
        self.assertEqual(classify("chrome.exe", "How to use GITHUB ACTIONS - Google Chrome", settings).context,"GitHub Actions")
        self.assertEqual(classify("msedge.exe", "Learn C++ - Microsoft Edge", settings).context,"C++")

    def test_browser_suffix_never_becomes_a_site_keyword(self):
        settings = validate_settings({'siteNames': [
            'Google Chrome', 'Google', 'Chrome', 'Microsoft Edge', 'Microsoft',
            'Edge', 'Mozilla Firefox', 'Mozilla', 'Firefox', '豆包',
        ]})
        for process, suffix in (
            ('chrome.exe', 'Google Chrome'), ('chrome.exe', 'Chrome'),
            ('chrome.exe', 'Chromium'), ('msedge.exe', 'Microsoft Edge'),
            ('msedge.exe', 'Microsoft\u200b Edge'), ('msedge.exe', 'Edge'),
            ('firefox.exe', 'Mozilla Firefox'), ('firefox.exe', 'Firefox'),
        ):
            for separator in (' - ', ' — ', ' – '):
                with self.subTest(process=process, suffix=suffix, separator=separator):
                    title = '项目数据保存方式分析 - 豆包' + separator + suffix
                    self.assertEqual(classify(process, title, settings).context, '豆包')
            self.assertEqual(classify(process, suffix, settings).context, '')
        self.assertEqual(classify('chrome', '页面 - 豆包 - Google Chrome [测试]', settings).context, '豆包')

    def test_browser_suffix_cleanup_preserves_real_page_keywords(self):
        settings = validate_settings({'siteNames': ['Google Scholar', 'Google', '豆包']})
        self.assertEqual(classify('chrome', 'Google Scholar - Google Chrome', settings).context, 'Google Scholar')
        self.assertEqual(classify('chrome', 'Google 搜索 - Google Chrome', settings).context, 'Google')
        self.assertEqual(classify('chrome', '页面 - 豆包', settings).context, '豆包')
        # Page topics can still contain website keywords: this is a title heuristic.
        self.assertEqual(classify('chrome', 'Google 使用方法 - 豆包 - Google Chrome', settings).context, 'Google')

    def test_custom_browser_suffix_requires_the_configured_process_name(self):
        settings = validate_settings({'customBrowserProcesses': ['brave'], 'siteNames': ['Brave', '豆包']})
        self.assertEqual(classify('Brave.exe', '页面 - 豆包 - Brave', settings).context, '豆包')
        # Do not blindly discard the last segment: it may be the website name.
        self.assertEqual(classify('Brave.exe', '页面 - 豆包', settings).context, '豆包')

    def test_rule_switches(self):
        settings = validate_settings({"splitIde": False, "splitDocuments": False, "splitSites": False})
        for proc, title in (("Code.exe", "file.py - project - VSCode"), ("WINWORD.EXE", "report.docx - Word"), ("chrome.exe", "GitHub - Google Chrome")):
            self.assertEqual(classify(proc, title, settings).context, "")

    def test_unknown_process_does_not_group_by_title(self):
        self.assertEqual(classify("unknown.exe", "Every new title", self.settings).context, "")

    def test_custom_ide_requires_opt_in_and_recognizable_project(self):
        title = "main.py - Project alpha - Trae"
        self.assertEqual(classify('Trae.exe', title, self.settings).context, '')
        settings = validate_settings({'customIdeProcesses': ['Trae.EXE']})
        for title in (title, 'Project alpha - Trae', '● main.py - Project alpha [SSH: host] - Trae'):
            identity = classify('Trae.exe', title, settings)
            self.assertEqual((identity.context, identity.kind), ('Project alpha', 'project'))
        for title in ('main.py - Trae', 'Untitled', 'Welcome to Trae'):
            self.assertEqual(classify('Trae.exe', title, settings).context, '')
        settings['splitIde'] = False
        self.assertEqual(classify('Trae.exe', 'Project alpha - Trae', settings).context, '')

    def test_custom_office_and_browser_follow_existing_rules(self):
        settings = validate_settings({'customDocumentProcesses': ['wps'], 'customBrowserProcesses': ['brave'],
                                      'siteNames': ['Git', 'GitHub', 'GitHub Actions']})
        document = classify('wps.exe', '研究报告.docx [只读] - WPS Office', settings)
        self.assertEqual((document.context, document.kind), ('研究报告', 'document'))
        site = classify('brave.exe', 'Learn GITHUB ACTIONS - Brave', settings)
        self.assertEqual((site.context, site.kind), ('GitHub Actions', 'site'))
        settings.update(splitDocuments=False, splitSites=False)
        self.assertEqual(classify('wps.exe', '研究报告.docx - WPS Office', settings).context, '')
        self.assertEqual(classify('brave.exe', 'GitHub Actions - Brave', settings).context, '')


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parents[1] / '.runtime' / 'tests'
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.test_directory = self.test_root / uuid.uuid4().hex
        self.test_directory.mkdir()
        self.repo = Repository(self.test_directory)

    def tearDown(self):
        assert self.test_directory.resolve().is_relative_to(self.test_root.resolve())
        shutil.rmtree(self.test_directory)

    def put(self, day, count=3, process="Code.exe", title="main.py - Project - VSCode", hour=10, active=True):
        rows = [Activity(minute_at(day, hour) + i, active, process, title) for i in range(count)]
        self.repo.write_many(rows)
        return rows


class RepositoryTests(RepositoryFixture):
    def test_calendar_month_cutoff_leap_year(self):
        self.assertEqual(month_before(date(2024, 5, 31), 1), date(2024, 4, 30))
        self.assertEqual(month_before(date(2024, 2, 29), -12), date(2025, 2, 28))

    def test_records_survive_reopen_without_expiry_or_csv(self):
        rows = self.put(date(2001, 5, 20)) + self.put(date(2026, 8, 20))
        reopened = Repository(self.test_directory)
        self.assertEqual(reopened.query(minute_at(date(2000,1,1)), minute_at(date(2027,1,1))), rows)
        self.assertEqual(reopened.inventory()["recordCount"], 6)
        self.assertFalse((self.test_directory / 'archives').exists())
        self.assertFalse(list(self.test_directory.glob('*.csv')))

    def test_existing_csv_files_are_not_read_or_modified(self):
        directory = self.test_directory / 'archives'
        directory.mkdir()
        path = directory / '2020-02.csv'
        path.write_text('existing file', encoding='utf-8')
        self.assertEqual(self.repo.query(minute_at(date(2020,1,1)), minute_at(date(2020,3,1))), [])
        self.assertEqual(path.read_text(encoding='utf-8'), 'existing file')

    def test_export_unicode_quotes_and_linebreaks(self):
        title = '报告, "研究"\n第二行'
        self.put(date(2026, 8, 20), 1, title=title)
        content, count = self.repo.export(minute_at(date(2026, 8, 20)), minute_at(date(2026, 8, 21)))
        self.assertEqual(count, 1)
        record = next(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
        self.assertEqual(record["title"], title)
        self.assertIsNotNone(datetime.fromisoformat(record["timestamp"]).tzinfo)

    def test_concurrent_writes_and_reads(self):
        first = minute_at(date(2026, 8, 20))
        def operation(i):
            self.repo.write(Activity(first + i, True, "app.exe"))
            self.repo.query(first, first + 100)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(operation, range(100)))
        self.assertEqual(self.repo.inventory()["recordCount"], 100)

    def test_upsert_minute_no_duplicate(self):
        rows = self.put(date(2026, 8, 20), 1)
        self.repo.write(Activity(rows[0].minute, False, 'changed.exe'))
        self.assertEqual(self.repo.inventory()["recordCount"], 1)
        self.assertFalse(self.repo.query(rows[0].minute, rows[0].minute+1)[0].active)

    def test_settings_validation_and_roundtrip(self):
        for invalid in ({"idleSeconds": True}, {"detailThreshold": 0}, {"siteNames": [42]}, {"splitIde": "yes"}, {"unknown": 1}, {"displayNames": {"": "a"}}):
            with self.assertRaises(ValueError):
                self.repo.save_settings(invalid)
        expected = self.repo.save_settings({"dayStartHour": 0, "detailThreshold": 15})
        self.assertEqual(self.repo.settings(), expected)

    def test_custom_process_settings_normalize_and_persist_without_ambiguity(self):
        settings = self.repo.save_settings({'ideProcesses': [' Trae.EXE ', 'trae', 'CODE'],
                                            'documentProcesses': ['WPS.exe'], 'browserProcesses': ['Brave']})
        self.assertEqual(settings['ideProcesses'], ['trae', 'code'])
        self.assertEqual(settings['documentProcesses'], ['wps'])
        self.assertEqual(settings['browserProcesses'], ['brave'])
        self.assertEqual(Repository(self.test_directory).settings(), settings)
        for invalid in ({'customIdeProcesses': ['C:\\Trae.exe']}, {'customIdeProcesses': ['.exe']},
                        {'customIdeProcesses': [True]}, {'customBrowserProcesses': 'brave'},
                        {'customBrowserProcesses': ['code']},
                        {'customIdeProcesses': ['shared'], 'customDocumentProcesses': ['SHARED.exe']}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.repo.save_settings(invalid)


class CleanupTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.service = Service(self.repo)

    def test_range_includes_end_day_and_uses_midnight_independent_of_report_setting(self):
        first = minute_at(date(2026,8,20))
        last = minute_at(date(2026,8,22))
        self.repo.write_many([Activity(first-1,True,'before'),Activity(first,True,'inside'),
                              Activity(last-1,False,'inside'),Activity(last,True,'after')])
        settings = self.repo.settings()
        preview = self.service.dispatch('cleanupPreview', {'mode':'range','start':'2026-08-20','end':'2026-08-21'})['data']
        self.assertEqual(preview['count'],2)
        self.assertEqual(self.repo.inventory()['recordCount'],4)
        result = self.service.dispatch('cleanup', {'token':preview['token']})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['deletedRows'],2)
        self.assertEqual([r.process for r in self.repo.query(first-1,last+1)],['before','after'])
        self.assertEqual(self.repo.settings(),settings)
        self.assertFalse(self.service.dispatch('cleanup', {'token':preview['token']})['ok'])

    def test_before_excludes_selected_day(self):
        self.put(date(2001,1,1),1)
        self.put(date(2026,8,19),1)
        self.put(date(2026,8,20),1)
        preview = self.service.dispatch('cleanupPreview', {'mode':'before','before':'2026-08-20'})['data']
        self.assertEqual(preview['count'],2)
        self.assertTrue(self.service.dispatch('cleanup', {'token':preview['token']})['ok'])
        report = build_report(self.repo,'2026-08-20','2026-08-20')
        self.assertEqual(report['summary']['activeMinutes'],1)

    def test_before_uses_midnight_even_when_report_day_starts_at_four(self):
        cutoff = minute_at(date(2026,8,20))
        self.repo.write_many([Activity(cutoff-1,True,'old'),Activity(cutoff,True,'midnight'),Activity(cutoff+120,True,'after')])
        self.repo.save_settings({"dayStartHour":4})
        preview = self.service.dispatch('cleanupPreview',{'mode':'before','before':'2026-08-20'})['data']
        self.assertEqual(preview['count'],1)
        self.assertTrue(self.service.dispatch('cleanup',{'token':preview['token']})['ok'])
        self.assertEqual([r.minute for r in self.repo.query(cutoff-1,cutoff+121)],[cutoff,cutoff+120])
        self.assertEqual(build_report(self.repo,'2026-08-19','2026-08-19')['summary']['activeMinutes'],2)

    def test_new_records_require_new_preview(self):
        self.put(date(2026,8,20),1)
        selection = {'mode':'range','start':'2026-08-20','end':'2026-08-20'}
        preview = self.service.dispatch('cleanupPreview',selection)['data']
        self.put(date(2026,8,20),1,hour=11)
        result = self.service.dispatch('cleanup',{'token':preview['token']})
        self.assertFalse(result['ok'])
        self.assertIn('记录已变化',result['error'])
        self.assertEqual(self.repo.inventory()['recordCount'],2)

    def test_preview_token_expiry_and_replacement(self):
        self.put(date(2026,8,20),1)
        selection = {'mode':'before','before':'2026-08-21'}
        with patch('workstate.service.time.monotonic',return_value=0):
            preview = self.service.dispatch('cleanupPreview',selection)['data']
        with patch('workstate.service.time.monotonic',return_value=301):
            self.assertFalse(self.service.dispatch('cleanup',{'token':preview['token']})['ok'])
        first = self.service.dispatch('cleanupPreview',selection)['data']
        second = self.service.dispatch('cleanupPreview',selection)['data']
        self.assertFalse(self.service.dispatch('cleanup',{'token':first['token']})['ok'])
        self.assertTrue(self.service.dispatch('cleanup',{'token':second['token']})['ok'])

    def test_invalid_requests_and_empty_preview_do_not_delete(self):
        self.put(date(2026,8,20),1)
        for selection in ({'mode':'all'},{'mode':'range','start':'2026-08-21','end':'2026-08-20'},
                          {'mode':'before','before':'bad'},{'mode':'range','start':'2026-08-20','end':'2999-01-01'}):
            self.assertFalse(self.service.dispatch('cleanupPreview',selection)['ok'])
        self.assertFalse(self.service.dispatch('cleanup',{'mode':'before','before':'2027-01-01'})['ok'])
        self.assertFalse(self.service.dispatch('cleanup',{'token':'forged'})['ok'])
        empty = self.service.dispatch('cleanupPreview',{'mode':'before','before':'2000-01-01'})['data']
        self.assertIsNone(empty['token'])
        self.assertEqual(self.repo.inventory()['recordCount'],1)

    def test_delete_is_atomic_on_database_failure(self):
        self.put(date(2026,8,20),2)
        with self.repo.connect() as db:
            db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON activity BEGIN SELECT RAISE(ABORT, 'test'); END")
        preview = self.service.dispatch('cleanupPreview',{'mode':'before','before':'2026-08-21'})['data']
        with self.assertLogs('workstate.service',level='ERROR'):
            self.assertFalse(self.service.dispatch('cleanup',{'token':preview['token']})['ok'])
        self.assertEqual(self.repo.inventory()['recordCount'],2)

    def test_manual_export_limit_is_one_calendar_year(self):
        for first,last in [('2025-01-01','2025-12-31'),('2024-01-01','2024-12-31')]:
            self.assertTrue(self.service.dispatch('export',{'start':first,'end':last})['ok'])
        with patch.object(self.repo,'export') as exporter:
            for first,last in [('2025-01-01','2026-01-01'),('2024-01-01','2025-01-01')]:
                result = self.service.dispatch('export',{'start':first,'end':last})
                self.assertFalse(result['ok'])
                self.assertIn('最长为一年',result['error'])
            exporter.assert_not_called()

    def test_compaction_failure_reports_committed_deletion(self):
        self.put(date(2026,8,20),2)
        preview = self.service.dispatch('cleanupPreview',{'mode':'before','before':'2026-08-21'})['data']
        connect = self.repo.connect
        @contextmanager
        def fail_vacuum():
            with connect() as db:
                class Proxy:
                    def execute(self, sql, *args):
                        if sql == 'VACUUM':
                            raise sqlite3.OperationalError('simulated disk full')
                        return db.execute(sql, *args)
                yield Proxy()
        with patch.object(self.repo,'connect',fail_vacuum):
            result = self.service.dispatch('cleanup',{'token':preview['token']})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['deletedRows'],2)
        self.assertFalse(result['data']['compacted'])
        self.assertEqual(self.repo.inventory()['recordCount'],0)

    def test_concurrent_confirmation_can_only_delete_once(self):
        self.put(date(2026,8,20),2)
        preview = self.service.dispatch('cleanupPreview',{'mode':'before','before':'2026-08-21'})['data']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service.dispatch('cleanup',{'token':preview['token']}),range(2)))
        self.assertEqual(sum(result['ok'] for result in results),1)
        self.assertEqual(self.repo.inventory()['recordCount'],0)


class ReportTests(RepositoryFixture):
    def heatmap_rows(self):
        first = date(2026, 7, 31)
        self.repo.save_settings({'dayStartHour': 4})
        for offset in range(4):
            begin = minute_at(first + timedelta(days=offset)) + 4 * 60
            self.repo.write_many(Activity(begin + minute, active, 'Code.exe', 'Demo') for minute, active in
                                 [(0, True), (4, False), (5, True), (59, True), (60, False), (119, True), (1439, False)])
        return first

    def test_up_to_three_days_preserve_five_minute_activity_and_recording_coverage(self):
        first = self.heatmap_rows()
        expected_activity, expected_coverage = [0] * 288, [0] * 288
        for slot in (0, 1, 11, 23):
            expected_activity[slot] = 1
        for slot in (1, 11, 12, 23, 287):
            expected_coverage[slot] = 1
        expected_coverage[0] = 2
        for count in (1, 2, 3):
            with self.subTest(days=count):
                report = build_report(self.repo, first.isoformat(), (first + timedelta(days=count-1)).isoformat())
                for day in report['days']:
                    self.assertEqual(day['slots'], expected_activity)
                    self.assertEqual(day['coverage'], expected_coverage)
                self.assertEqual(report['summary']['activeMinutes'], count * 4)
                self.assertEqual(report['summary']['observedMinutes'], count * 7)
                self.assertEqual(sum(app['minutes'] for app in report['apps']), count * 4)
                self.assertEqual(sum(sum(hour.values()) for day in report['days'] for hour in day['hourly']), count * 4)

    def test_four_or_more_days_keep_hourly_activity_and_coverage(self):
        first = self.heatmap_rows()
        expected_activity, expected_coverage = [0] * 24, [0] * 24
        expected_activity[0], expected_activity[1] = 3, 1
        expected_coverage[0], expected_coverage[1], expected_coverage[23] = 4, 2, 1
        for count in (4, 32):
            with self.subTest(days=count):
                report = build_report(self.repo, first.isoformat(), (first + timedelta(days=count-1)).isoformat())
                for day in report['days'][:4]:
                    self.assertEqual(day['slots'], expected_activity)
                    self.assertEqual(day['coverage'], expected_coverage)
                for day in report['days'][4:]:
                    self.assertEqual(day['slots'], [0] * 24)
                    self.assertEqual(day['coverage'], [0] * 24)
                self.assertEqual(report['summary']['activeMinutes'], 16)
                self.assertEqual(report['summary']['observedMinutes'], 28)

    def test_custom_ide_uses_same_daily_threshold_and_preserves_totals(self):
        day = date(2026, 8, 20)
        self.repo.save_settings({'dayStartHour': 0, 'customIdeProcesses': ['trae']})
        self.put(day, 16, process='Trae.exe', title='main.py - Project alpha - Trae')
        self.put(day + timedelta(days=1), 15, process='Trae.exe', title='Project alpha - Trae')
        report = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), True)
        self.assertEqual(report['summary']['activeMinutes'], 31)
        self.assertEqual(sorted((app['context'], app['minutes']) for app in report['apps']), [('', 15), ('Project alpha', 16)])
        coarse = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), False)
        self.assertEqual([(app['context'], app['minutes']) for app in coarse['apps']], [('', 31)])

    def test_context_threshold_is_strictly_daily_and_conserves_totals(self):
        day = date(2026, 8, 20)
        self.repo.save_settings({"dayStartHour": 0, "detailThreshold": 15})
        self.put(day, 16)
        self.put(day, 3, title="x.py - Short project - VSCode", hour=11)
        self.put(day + timedelta(days=1), 15)
        one = build_report(self.repo, day.isoformat(), day.isoformat(), True)
        both = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), True)
        coarse = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), False)
        self.assertEqual(len(one["apps"]), 2)
        self.assertEqual(len(both["apps"]), 2)
        detailed = next(app for app in both["apps"] if app["context"])
        self.assertEqual(detailed["context"], "Project")
        self.assertEqual(detailed["minutes"], 16)
        self.assertEqual(list(both["days"][1]["hourly"][10]), ["code"])
        self.assertEqual(both["summary"]["activeMinutes"], coarse["summary"]["activeMinutes"])
        self.assertEqual(sum(a["minutes"] for a in both["apps"]), 34)
        self.assertEqual(sum(sum(h.values()) for d in both["days"] for h in d["hourly"]), 34)

    def test_small_daily_contexts_do_not_qualify_by_range_total(self):
        day = date(2026, 8, 20)
        self.put(day, 10)
        self.put(day + timedelta(days=1), 10)
        report = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), True)
        self.assertEqual(len(report["apps"]), 1)
        self.assertEqual(report["apps"][0]["context"], "")

    def test_daily_threshold_follows_four_am_boundary(self):
        day = date(2026, 8, 20)
        self.put(day, 8, hour=23)
        self.put(day + timedelta(days=1), 8, hour=2)
        self.put(day + timedelta(days=1), 15, hour=4)
        report = build_report(self.repo, day.isoformat(), (day+timedelta(days=1)).isoformat(), True)
        detailed = next(app for app in report["apps"] if app["context"])
        self.assertEqual(detailed["minutes"], 16)
        self.assertEqual(report["days"][1]["active"], 15)

    def test_four_am_cross_day_and_month_boundary(self):
        day = date(2026, 7, 31)
        self.put(day, 1, hour=23)
        self.put(day+timedelta(days=1), 1, hour=2)
        self.put(day+timedelta(days=1), 1, hour=4)
        report = build_report(self.repo, day.isoformat(), day.isoformat())
        self.assertEqual(report["summary"]["activeMinutes"], 2)
        self.assertEqual(report["days"][0]["slots"][19*12], 1)
        self.assertEqual(report["days"][0]["slots"][22*12], 1)

    def test_idle_and_missing_differ(self):
        day = date(2026, 8, 20)
        self.put(day, 5, active=False)
        report = build_report(self.repo, day.isoformat(), day.isoformat())
        self.assertEqual(report["summary"]["activeMinutes"], 0)
        self.assertEqual(report["summary"]["observedMinutes"], 5)
        self.assertEqual(report["summary"]["idleMinutes"], 5)
        self.assertEqual(sum(report["days"][0]["coverage"]), 5)

    def test_blacklist_casefold_and_immediate_view_update(self):
        day = date(2026, 8, 20)
        self.put(day, 2, process="LockApp.EXE")
        report = build_report(self.repo, day.isoformat(), day.isoformat())
        self.assertEqual(report["summary"]["observedMinutes"], 0)

    def test_blacklist_comments_preserved_but_ignored_by_filter(self):
        day = date(2026, 8, 20)
        settings = self.repo.save_settings({"excludedProcesses": ["// comment", "Code.EXE // 编辑器"]})
        self.assertEqual(settings["excludedProcesses"][1], "Code.EXE // 编辑器")
        self.put(day, 2)
        self.assertEqual(build_report(self.repo, day.isoformat(), day.isoformat())["apps"], [])
        self.assertEqual(self.repo.inventory()["recordCount"], 2)

    def test_invalid_range_envelope(self):
        service = Service(self.repo)
        for payload in ({"start":"bad", "end":"2026-08-20"}, {"start":"2026-08-21", "end":"2026-08-20"}, {"start":"2026-08-20", "end":"2026-08-21", "expanded":"yes"}):
            self.assertFalse(service.dispatch("report", payload)["ok"])


class RecentTests(RepositoryFixture):
    def test_raw_eight_hour_window_paging_and_snapshot(self):
        end = int(datetime.now().timestamp() // 60)
        self.repo.write_many(Activity(end-i, i % 2 == 0, "LockApp.exe", '原始, "标题"\n第二行') for i in range(0, 500))
        service = Service(self.repo)
        first = service.dispatch("recent", {"endMinute": end})["data"]
        self.assertEqual(first["total"], 480)
        self.assertEqual(first["rows"][0]["minute"], end-1)
        self.assertEqual(len(first["rows"]), 30)
        self.assertEqual(first["rows"][0]["process"], "LockApp.exe")
        self.assertEqual(first["rows"][0]["title"], '原始, "标题"\n第二行')
        for size in (30, 60, 120):
            rows = []
            for page in range(1, 480 // size + 1):
                rows += service.dispatch("recent", {"endMinute": end, "page": page, "pageSize": size})["data"]["rows"]
            self.assertEqual([r["minute"] for r in rows], list(range(end-1, end-481, -1)))
        last = service.dispatch("recent", {"endMinute": end, "page": 99, "pageSize": 120})["data"]
        self.assertEqual(last["page"], 4)

    def test_invalid_paging_and_empty_window(self):
        service = Service(self.repo)
        for payload in ({"pageSize": 240}, {"page": True}, {"page": 0}, {"endMinute": "now"}, {"endMinute": 99999999999}):
            self.assertFalse(service.dispatch("recent", payload)["ok"])
        result = service.dispatch("recent")["data"]
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["rows"], [])

    def test_fixed_idle_and_new_defaults(self):
        settings = validate_settings({"idleSeconds": 300})
        self.assertEqual(settings["idleSeconds"], 60)
        self.assertEqual(settings["detailThreshold"], 15)
        self.assertEqual(settings["excludedProcesses"], ["LockApp // Windows锁屏", "LogonUI // Windows登录"])


if __name__ == "__main__":
    unittest.main()
