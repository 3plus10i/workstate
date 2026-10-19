from datetime import date, datetime, timedelta
from unittest.mock import patch

from test_core import RepositoryFixture
from workstate.models import Activity, minute_at
from workstate.report import build_report
from workstate.service import Service


class ActivityGranularityTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.day = date(2026, 10, 17)
        self.begin = minute_at(self.day)
        self.repo.save_settings({'dayStartHour': 0})

    def report(self, days=1, expanded=False):
        return build_report(self.repo, self.day.isoformat(), (self.day + timedelta(days=days-1)).isoformat(), expanded)

    def example(self):
        self.repo.write_many([Activity(self.begin, True, 'A.exe'), Activity(self.begin+1, True, 'B.exe'),
                              Activity(self.begin+2, True, 'B.exe'), Activity(self.begin+3, False, 'A.exe'),
                              Activity(self.begin+4, False, 'A.exe')])

    def test_default_and_persisted_granularity(self):
        self.assertEqual(self.repo.settings()['activityGranularity'], 1)
        self.repo.save_settings({'activityGranularity': 5})
        self.assertEqual(type(self.repo)(self.test_directory).settings()['activityGranularity'], 5)
        for invalid in (0, 2, 60, True, '5', 5.0, None):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.repo.save_settings({'activityGranularity': invalid})

    def test_one_minute_mode_preserves_actual_activity(self):
        self.example()
        report = self.report()
        self.assertEqual(report['summary']['activeMinutes'], 3)
        self.assertEqual(report['summary']['rawActiveMinutes'], 3)
        self.assertEqual(report['summary']['fiveMinuteActiveMinutes'], 5)
        self.assertEqual({a['key']: a['minutes'] for a in report['apps']}, {'a': 1, 'b': 2})
        self.assertEqual(report['days'][0]['slots'][0], 3)
        self.assertEqual(report['days'][0]['coverage'][0], 5)

    def test_five_minute_mode_allocates_proportionally_without_changing_raw_records(self):
        self.example()
        original = self.repo.export(self.begin, self.begin+1440)
        self.repo.save_settings({'dayStartHour': 0, 'activityGranularity': 5})
        report = self.report()
        apps = {a['key']: a['minutes'] for a in report['apps']}
        self.assertAlmostEqual(apps['a'], 5/3)
        self.assertAlmostEqual(apps['b'], 10/3)
        self.assertAlmostEqual(sum(apps.values()), 5)
        self.assertEqual(report['days'][0]['hourly'][0], apps)
        self.assertEqual(report['summary']['activeMinutes'], 5)
        self.assertEqual(report['summary']['rawActiveMinutes'], 3)
        self.assertEqual(report['summary']['observedMinutes'], 5)
        self.assertEqual(report['summary']['idleMinutes'], 2)
        self.assertEqual(report['days'][0]['slots'][0], 3)
        self.assertEqual(report['days'][0]['coverage'][0], 5)
        self.assertEqual(self.repo.export(self.begin, self.begin+1440), original)

    def test_partial_slots_are_aligned_to_the_clock_and_empty_slots_add_nothing(self):
        self.repo.save_settings({'dayStartHour': 0, 'activityGranularity': 5})
        self.repo.write_many([Activity(self.begin+4, True, 'A'), Activity(self.begin+5, True, 'A'),
                              Activity(self.begin+10, False, 'A')])
        report = self.report()
        self.assertEqual(report['days'][0]['slots'][:3], [1, 1, 0])
        self.assertEqual(report['summary']['activeMinutes'], 10)
        self.assertEqual(report['summary']['rawActiveMinutes'], 2)
        self.assertEqual(report['summary']['idleMinutes'], 1)
        self.assertEqual(self.report(days=2)['days'][1]['active'], 0)

    def test_blacklisted_minutes_do_not_receive_or_dilute_allocations(self):
        self.example()
        self.repo.save_settings({'dayStartHour': 0, 'activityGranularity': 5, 'excludedProcesses': ['B // ignored']})
        report = self.report()
        self.assertEqual([(a['key'], a['minutes']) for a in report['apps']], [('a', 5)])
        self.assertEqual(report['summary']['rawActiveMinutes'], 1)
        self.assertEqual(report['summary']['observedMinutes'], 3)

    def test_four_am_boundary_and_range_sizes_preserve_daily_totals(self):
        self.repo.save_settings({'dayStartHour': 4, 'activityGranularity': 5})
        boundary = self.begin + 1440 + 4*60
        self.repo.write_many([Activity(boundary-1, True, 'A'), Activity(boundary, True, 'B')])
        one, two, four = self.report(), self.report(days=2), self.report(days=4)
        self.assertEqual(one['summary']['activeMinutes'], 5)
        for report in (two, four):
            self.assertEqual([day['active'] for day in report['days'][:2]], [5, 5])
            self.assertEqual(report['summary']['activeMinutes'], 10)
            self.assertAlmostEqual(sum(app['minutes'] for app in report['apps']), 10)
            self.assertAlmostEqual(sum(sum(hour.values()) for day in report['days'] for hour in day['hourly']), 10)
            self.assertEqual(sum(sum(day['slots']) for day in report['days']), 2)

    def test_daily_subdivision_threshold_keeps_actual_minutes_and_stays_strict(self):
        self.repo.save_settings({'dayStartHour': 0, 'activityGranularity': 5, 'detailThreshold': 15})
        for slot in range(9):
            start = self.begin + slot * 5
            self.repo.write_many([Activity(start, True, 'Code.exe', 'main.py - Demo - VSCode'),
                                  Activity(start+1, True, 'chrome'), Activity(start+2, True, 'chrome')])
        exact = self.report(expanded=True)
        self.assertFalse(any(app['context'] for app in exact['apps']))
        self.repo.write_many(Activity(self.begin+45+minute, True, 'Code.exe', 'main.py - Demo - VSCode') for minute in range(6))
        self.assertFalse(any(app['context'] for app in self.report(expanded=True)['apps']))
        self.repo.write(Activity(self.begin+55, True, 'Code.exe', 'main.py - Demo - VSCode'))
        above = self.report(expanded=True)
        detailed = next(app for app in above['apps'] if app['context'])
        self.assertEqual(detailed['context'], 'Demo')
        self.assertAlmostEqual(detailed['minutes'], 30)
        self.assertAlmostEqual(sum(app['minutes'] for app in above['apps']), 60)

    def test_unqualified_contexts_merge_after_proportional_allocation(self):
        self.repo.save_settings({'dayStartHour': 0, 'activityGranularity': 5})
        self.repo.write_many([Activity(self.begin, True, 'Code.exe', 'main.py - First - VSCode'),
                              Activity(self.begin+1, True, 'Code.exe', 'main.py - Second - VSCode'),
                              Activity(self.begin+2, True, 'chrome')])
        report = self.report(expanded=True)
        apps = {app['key']: app['minutes'] for app in report['apps']}
        self.assertAlmostEqual(apps['code'], 10/3)
        self.assertAlmostEqual(apps['chrome'], 5/3)

    def test_today_preview_uses_unsaved_day_start_and_blacklist_without_saving(self):
        self.repo.save_settings({'dayStartHour': 4})
        self.repo.write_many([Activity(self.begin+23*60, True, 'A'), Activity(self.begin+1440+60, True, 'B')])
        settings = self.repo.settings()
        service = Service(self.repo)
        try:
            with patch('workstate.service.datetime') as clock:
                clock.now.return_value = datetime(2026, 10, 18, 2, 30)
                previous = service.dispatch('activityPreview')['data']
                current = service.dispatch('activityPreview', {'dayStartHour': 0})['data']
                excluded = service.dispatch('activityPreview', {'dayStartHour': 0, 'excludedProcesses': ['B']})['data']
            self.assertEqual(previous, {'date': '2026-10-17', 'oneMinute': 2, 'fiveMinutes': 10})
            self.assertEqual(current, {'date': '2026-10-18', 'oneMinute': 1, 'fiveMinutes': 5})
            self.assertEqual(excluded['fiveMinutes'], 0)
            self.assertEqual(self.repo.settings(), settings)
            for payload in ({'dayStartHour': True}, {'excludedProcesses': 'A'}, {'other': 1}):
                self.assertFalse(service.dispatch('activityPreview', payload)['ok'])
        finally:
            service.close()
