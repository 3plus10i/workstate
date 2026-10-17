from datetime import datetime
from unittest.mock import Mock

from workstate.service import PAUSE_MINUTES, Service
from test_core import RepositoryFixture


class FakeTimer:
    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class RecordingTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 10, 15, 12).timestamp()
        self.timers = []
        self.collector = Mock(active=True, error=None, last_minute=None)

        def timer_factory(seconds, callback):
            timer = FakeTimer(seconds, callback)
            self.timers.append(timer)
            return timer

        self.service = Service(self.repo, collector=self.collector,
                               clock=lambda: self.now, timer_factory=timer_factory)

    def tearDown(self):
        self.service.close()
        super().tearDown()

    def pause(self, minutes=5):
        result = self.service.dispatch('recording', {'pauseMinutes': minutes})
        self.assertTrue(result['ok'], result)
        return result['data']

    def test_each_duration_sets_deadline_and_cancels_previous_wait(self):
        for minutes in PAUSE_MINUTES:
            with self.subTest(minutes=minutes):
                status = self.pause(minutes)
                self.assertTrue(status['paused'])
                self.assertFalse(status['collecting'])
                self.assertEqual(datetime.fromisoformat(status['resumeAt']).timestamp(), self.now + minutes * 60)
                self.assertEqual(self.timers[-1].seconds, minutes * 60)
                self.assertTrue(self.timers[-1].started)
                self.assertTrue(self.timers[-1].daemon)
        self.assertTrue(all(t.cancelled for t in self.timers[:-1]))
        self.collector.set_paused.assert_called_with(True)

    def test_rejects_indefinite_and_unsupported_pause_without_changing_state(self):
        for payload in ({'paused': True}, {}, {'pauseMinutes': 0}, {'pauseMinutes': 10},
                        {'pauseMinutes': True}, {'pauseMinutes': '5'},
                        {'pauseMinutes': 5, 'paused': True}):
            with self.subTest(payload=payload):
                self.assertFalse(self.service.dispatch('recording', payload)['ok'])
        self.assertFalse(self.service.status()['paused'])
        self.assertEqual(self.timers, [])
        self.collector.set_paused.assert_not_called()

    def test_timer_resumes_collection_at_deadline(self):
        self.pause()
        self.now += 300
        self.timers[-1].callback()
        self.collector.set_paused.assert_called_with(False)
        status = self.service.status()
        self.assertFalse(status['paused'])
        self.assertTrue(status['collecting'])
        self.assertIsNone(status['resumeAt'])

    def test_status_recovers_expired_pause_after_sleep(self):
        self.pause(60)
        self.now += 7200
        self.assertFalse(self.service.status()['paused'])
        self.assertTrue(self.timers[-1].cancelled)
        self.collector.set_paused.assert_called_with(False)

    def test_early_timer_after_clock_change_waits_until_displayed_deadline(self):
        self.pause()
        self.now -= 60
        self.timers[-1].callback()
        self.assertTrue(self.service.status()['paused'])
        self.assertEqual(self.timers[-1].seconds, 360)
        self.now += 360
        self.timers[-1].callback()
        self.assertFalse(self.service.status()['paused'])

    def test_manual_resume_cancels_wait_and_stale_callback_cannot_end_later_pause(self):
        self.pause()
        old_timer = self.timers[-1]
        self.assertFalse(self.service.dispatch('recording', {'paused': False})['data']['paused'])
        self.assertTrue(old_timer.cancelled)
        self.pause(240)
        self.now += 300
        old_timer.callback()
        self.assertTrue(self.service.status()['paused'])
        self.collector.set_paused.assert_called_with(True)

    def test_exit_cancels_wait_and_fresh_start_records_normally(self):
        self.pause()
        timer = self.timers[-1]
        self.service.close()
        self.now += 300
        timer.callback()
        self.assertTrue(timer.cancelled)
        self.collector.set_paused.assert_called_once_with(True)
        self.assertFalse(self.service.dispatch('recording', {'paused': False})['ok'])
        restarted = Service(self.repo, collector=self.collector)
        self.addCleanup(restarted.close)
        self.assertFalse(restarted.status()['paused'])
        self.assertIsNone(restarted.status()['resumeAt'])

    def test_redundant_resume_does_not_reset_minute_collection(self):
        self.assertTrue(self.service.dispatch('recording', {'paused': False})['ok'])
        self.collector.set_paused.assert_not_called()
