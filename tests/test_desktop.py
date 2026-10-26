import sys
from unittest.mock import MagicMock, call, patch

from workstate.desktop import Desktop
from workstate.service import Service
from test_core import RepositoryFixture


class DesktopTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.service = Service(self.repo)
        self.addCleanup(self.service.close)
        self.desktop = Desktop(self.service)
        self.service.desktop = self.desktop
        self.desktop._window = MagicMock()
        self.desktop._tray = MagicMock(visible=True)

    def test_export_notification_can_open_each_exports_actual_directory(self):
        webview = MagicMock()
        with patch.dict(sys.modules, {'webview': webview}), patch('workstate.desktop.os.startfile') as open_folder:
            for name in ('导出目录', 'another folder'):
                directory = self.test_directory / name
                directory.mkdir()
                self.desktop._window.create_file_dialog.return_value = (str(directory / '活动记录'),)
                result = self.desktop.save_export('\ufeff标题\n"Project alpha"\n', 'default.csv', 1)
                self.assertEqual(result['filename'], '活动记录.csv')
                self.assertEqual(result['count'], 1)
                self.assertEqual(result['directory'], str(directory.resolve()))
                self.assertEqual((directory / result['filename']).read_text(encoding='utf-8'), '\ufeff标题\n"Project alpha"\n')
                self.assertFalse(list(directory.glob('*.tmp')))
            first_directory = str((self.test_directory / '导出目录').resolve())
            self.assertTrue(self.service.dispatch('openExportDirectory', {'directory': first_directory})['ok'])
            open_folder.assert_called_once_with(first_directory)

    def test_cancelled_or_failed_exports_do_not_offer_a_folder(self):
        with patch.dict(sys.modules, {'webview': MagicMock()}):
            self.desktop._window.create_file_dialog.return_value = None
            self.assertEqual(self.desktop.save_export('data', 'default.csv', 1), {'cancelled': True})
            self.desktop._window.create_file_dialog.return_value = str(self.test_directory / 'failed.csv')
            with patch('workstate.desktop.os.replace', side_effect=OSError('save failed')):
                with self.assertRaises(OSError):
                    self.desktop.save_export('data', 'default.csv', 1)
            self.assertFalse(self.desktop._export_directories)
            with patch('workstate.desktop.os.startfile') as open_folder:
                self.assertFalse(self.service.dispatch('openExportDirectory', {'directory': str(self.test_directory)})['ok'])
                open_folder.assert_not_called()

    def test_reopening_resets_page_before_showing_and_keeps_recording_running(self):
        with patch.object(self.service, 'close') as close_service:
            self.assertFalse(self.desktop._closing())
            self.desktop.show()
            close_service.assert_not_called()
        self.assertEqual(self.desktop._window.method_calls, [
            call.hide(),
            call.evaluate_js("window.dispatchEvent(new Event('workstate:shown'))"),
            call.show(), call.restore(),
        ])
        self.desktop._window.reset_mock()
        self.desktop.show()
        self.desktop._window.evaluate_js.assert_not_called()

    def test_background_launch_resets_the_page_on_first_open(self):
        self.desktop._hidden = True
        self.desktop.show()
        self.assertEqual(self.desktop._window.method_calls, [
            call.evaluate_js("window.dispatchEvent(new Event('workstate:shown'))"),
            call.show(), call.restore(),
        ])
