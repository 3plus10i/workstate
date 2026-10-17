from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
import zipfile

from workstate import __version__
from workstate.updates import LATEST_URL, MIRROR, PROJECT_HOME, Release, ReleaseClient, Updater, version_tuple
from workstate.update_worker import file_hash, install, read_job, write_json
from tools.release import release_notes, set_version, validate, validate_package
from test_core import RepositoryFixture

NEXT_VERSION = '.'.join(map(str, (*version_tuple(__version__)[:2], version_tuple(__version__)[2] + 1)))

def package_bytes(entries=None):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in (entries or {'WorkState/WorkState.exe': b'MZ-new-executable', 'WorkState/README.md': b'WorkState'}).items():
            archive.writestr(name, content)
    return stream.getvalue()


def release_data(version='4.0.1', size=None):
    names = [f'WorkState-{version}-Windows.zip', 'SHA256SUMS.txt']
    return {'tag_name': f'v{version}', 'draft': False, 'prerelease': False, 'body': '修复问题\n改进更新',
            'assets': [{'name': name, 'state': 'uploaded', 'browser_download_url': f'{PROJECT_HOME}/releases/download/v{version}/{name}', 'size': size or len(package_bytes())} for name in names]}


class ReleaseClientTests(RepositoryFixture):
    def test_version_comparison_is_numeric_and_strict(self):
        self.assertGreater(version_tuple('4.10.0'), version_tuple('4.9.9'))
        for value in ('v4.0.0', '4.0', '04.0.0', '4.0.0-beta', '../evil', None):
            with self.assertRaises(ValueError):
                version_tuple(value)

    def test_github_success_does_not_use_mirror(self):
        opener = Mock(return_value=BytesIO(json.dumps(release_data()).encode()))
        release = ReleaseClient(opener).latest()
        self.assertEqual((release.version, release.source), ('4.0.1', 'github'))
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(opener.call_args.args[0].full_url, LATEST_URL)

    def test_connection_timeout_and_server_errors_fall_back(self):
        errors = [URLError('unreachable'), TimeoutError(), HTTPError(LATEST_URL, 502, 'gateway', {}, None), HTTPError(LATEST_URL, 403, 'rate limit', {'X-RateLimit-Remaining':'0'}, None)]
        for error in errors:
            opener = Mock(side_effect=[error, BytesIO(json.dumps(release_data()).encode())])
            release = ReleaseClient(opener).latest()
            self.assertEqual(release.source, 'ghproxy')
            self.assertEqual(opener.call_args_list[1].args[0].full_url, MIRROR + LATEST_URL)

    def test_response_read_timeout_also_falls_back(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = TimeoutError()
        opener = Mock(side_effect=[response, BytesIO(json.dumps(release_data()).encode())])
        self.assertEqual(ReleaseClient(opener).latest().source, 'ghproxy')

    def test_unpublished_and_invalid_content_do_not_trigger_fallback(self):
        opener = Mock(side_effect=HTTPError(LATEST_URL, 404, 'missing', {}, None))
        self.assertIsNone(ReleaseClient(opener).latest())
        self.assertEqual(opener.call_count, 1)
        for payload in (b'<html>proxy error</html>', json.dumps({**release_data(), 'prerelease': True}).encode(), json.dumps({**release_data(), 'assets': []}).encode()):
            opener = Mock(return_value=BytesIO(payload))
            with self.assertRaises(ValueError):
                ReleaseClient(opener).latest()
            self.assertEqual(opener.call_count, 1)

    def download(self, payload, source='ghproxy', expected_hash=None):
        release = Release('4.0.1', '', source, len(payload))
        digest = expected_hash or hashlib.sha256(payload).hexdigest()
        opener = Mock(side_effect=[BytesIO(f'{digest}  {release.filename}\n'.encode()), BytesIO(payload)])
        client = ReleaseClient(opener)
        result = client.download(release, self.test_directory, Mock(), SimpleNamespace(is_set=lambda: False))
        return result, opener

    def test_download_pins_checksum_and_package_to_selected_source(self):
        for source in ('github', 'ghproxy'):
            (executable, digest), opener = self.download(package_bytes(), source)
            self.assertEqual(executable.read_bytes(), b'MZ-new-executable')
            self.assertEqual(digest, file_hash(executable))
            prefix = MIRROR if source == 'ghproxy' else ''
            self.assertTrue(all(call.args[0].full_url.startswith(prefix + PROJECT_HOME) for call in opener.call_args_list))

    def test_corrupted_checksum_and_unexpected_archive_are_rejected(self):
        for payload, digest in [(package_bytes(), '0' * 64), (package_bytes({'../evil.exe': b'MZ'}), None), (package_bytes({'WorkState/WorkState.exe': b'not-an-exe', 'WorkState/README.md': b'x'}), None)]:
            with self.assertRaises(ValueError):
                self.download(payload, expected_hash=digest)
        self.assertFalse((self.test_directory.parent / 'evil.exe').exists())

    def test_no_mirror_retry_when_download_source_fails(self):
        opener = Mock(side_effect=URLError('offline'))
        with self.assertRaises(ValueError):
            ReleaseClient(opener).download(Release('4.0.1', '', 'github', 10), self.test_directory, Mock(), SimpleNamespace(is_set=lambda: False))
        self.assertEqual(opener.call_count, 1)

    def test_download_cancellation_and_size_mismatch(self):
        payload = package_bytes()
        release = Release('4.0.1', '', 'github', len(payload) - 1)
        for cancelled in (False, True):
            opener = Mock(side_effect=[BytesIO(f'{hashlib.sha256(payload).hexdigest()}  {release.filename}'.encode()), BytesIO(payload)])
            with self.assertRaises(ValueError):
                ReleaseClient(opener).download(release, self.test_directory, Mock(), SimpleNamespace(is_set=lambda: cancelled))


class UpdaterStateTests(RepositoryFixture):
    def test_check_only_offers_newer_versions_and_preserves_recording_data(self):
        before = self.repo.inventory()
        for version, expected in [(NEXT_VERSION, 'available'), (__version__, 'latest'), ('3.9.9', 'latest')]:
            updater = Updater('WorkState.exe', self.repo.directory, client=Mock(latest=Mock(return_value=Release(version, 'notes', 'github', 100))))
            self.assertEqual(updater.check()['phase'], expected)
        self.assertEqual(self.repo.inventory(), before)

    def test_failed_check_discards_previous_offer(self):
        client = Mock(latest=Mock(side_effect=[Release(NEXT_VERSION, '', 'github', 100), ValueError('offline')]))
        updater = Updater('WorkState.exe', self.repo.directory, client=client)
        self.assertEqual(updater.check()['phase'], 'available')
        self.assertEqual(updater.check()['phase'], 'error')
        self.assertIsNone(updater.release)
        with self.assertRaises(ValueError):
            updater.download()

    def test_demo_and_development_cannot_install(self):
        updater = Updater('WorkState.exe', self.repo.directory, supported=False, client=Mock(latest=Mock(return_value=Release(NEXT_VERSION, '', 'github', 100))))
        updater.check()
        with self.assertRaises(ValueError):
            updater.download()
        with self.assertRaises(ValueError):
            updater.prepare_install()


class UpdateTransactionTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.target = self.test_directory / '安装目录 空格' / 'WorkState.exe'
        self.target.parent.mkdir()
        self.target.write_bytes(b'MZ-previous-version')
        self.directory = self.test_directory / 'update-fixture'
        self.directory.mkdir()
        (self.directory / 'new.exe').write_bytes(b'MZ-new-version')
        self.job_path = self.directory / 'job.json'
        self.job = {'protocol': 1, 'token': 'a' * 32, 'target': str(self.target.resolve()), 'dataDirectory': str(self.repo.directory), 'version': '4.0.1', 'newHash': file_hash(self.directory/'new.exe'), 'oldHash': file_hash(self.target), 'pids': [100, 101], 'demo': False}
        write_json(self.job_path, self.job)
        self.wait = Mock(side_effect=lambda pids, target, ready: ready())

    def replace(self, target, replacement, backup):
        shutil.copy2(target, backup)
        replacement.replace(target)

    def test_success_keeps_data_and_configuration_and_removes_backup(self):
        settings = self.repo.save_settings({'detailThreshold': 27})
        before = self.repo.path.read_bytes()
        def launch(arguments):
            self.assertEqual(arguments[arguments.index('--data-dir')+1], str(self.repo.directory))
            write_json(self.directory/'healthy.json', {'token': self.job['token'], 'version': '4.0.1'})
            return Mock(poll=Mock(return_value=None))
        self.assertTrue(install(self.job_path, self.wait, self.replace, launch))
        self.assertEqual(self.target.read_bytes(), b'MZ-new-version')
        self.assertEqual(self.repo.path.read_bytes(), before)
        self.assertEqual(self.repo.settings(), settings)
        self.assertFalse(list(self.target.parent.glob('*.bak')))

    def test_failed_new_start_restores_original_and_restarts_it(self):
        launch = Mock(return_value=Mock(poll=Mock(return_value=1)))
        self.assertFalse(install(self.job_path, self.wait, self.replace, launch, timeout=0.01))
        self.assertEqual(self.target.read_bytes(), b'MZ-previous-version')
        self.assertEqual(launch.call_count, 2)
        self.assertNotIn('--update-result', launch.call_args.args[0])

    def test_failed_replace_or_changed_target_does_not_start_new_program(self):
        launch = Mock()
        self.assertFalse(install(self.job_path, self.wait, Mock(side_effect=OSError('locked')), launch))
        self.assertEqual(self.target.read_bytes(), b'MZ-previous-version')
        self.assertEqual(launch.call_count, 1)
        self.assertNotIn('--update-result', launch.call_args.args[0])
        launch.reset_mock()
        self.target.write_bytes(b'MZ-manually-changed')
        self.assertFalse(install(self.job_path, self.wait, self.replace, launch))
        self.assertEqual(self.target.read_bytes(), b'MZ-manually-changed')
        launch.assert_not_called()

    def test_invalid_hash_or_path_token_is_rejected(self):
        (self.directory/'new.exe').write_bytes(b'corrupted')
        self.assertFalse(install(self.job_path, self.wait, self.replace, Mock()))
        self.wait.assert_not_called()
        self.job['token'] = '../' * 10 + 'xx'
        write_json(self.job_path, self.job)
        with self.assertRaises(ValueError):
            read_job(self.job_path)


class ReleaseConventionTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.root = self.test_directory/'source'
        source = Path(__file__).resolve().parents[1]
        for name in ('workstate/__init__.py', 'pyproject.toml', 'frontend/package.json', 'frontend/package-lock.json', 'CHANGELOG.md', 'README.md'):
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source/name, target)

    def test_version_tag_and_changelog_are_all_required(self):
        self.assertEqual(validate(self.root, f'v{__version__}'), __version__)
        with self.assertRaises(ValueError):
            validate(self.root, 'v0.0.1')
        (self.root/'CHANGELOG.md').write_text('# Empty', encoding='utf-8')
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_version_command_only_changes_application_lock_metadata(self):
        before = json.loads((self.root/'frontend/package-lock.json').read_text())
        set_version(NEXT_VERSION, self.root)
        after = json.loads((self.root/'frontend/package-lock.json').read_text())
        for key in before['packages']:
            if key:
                self.assertEqual(before['packages'][key], after['packages'][key])
        with self.assertRaises(ValueError):
            validate(self.root)
        path = self.root/'CHANGELOG.md'
        path.write_text(f'# 更新记录\n\n## [{NEXT_VERSION}] - 2026-10-17\n\n- 更新说明\n', encoding='utf-8')
        self.assertEqual(validate(self.root, f'v{NEXT_VERSION}'), NEXT_VERSION)
        self.assertEqual(release_notes(self.root), '- 更新说明\n')

    def test_package_contract_rejects_extra_files(self):
        path = self.test_directory/'WorkState-4.0.0-Windows.zip'
        path.write_bytes(package_bytes())
        validate_package(path, '4.0.0')
        path.write_bytes(package_bytes({'WorkState/WorkState.exe': b'MZ', 'WorkState/README.md': b'x', 'extra.txt': b'x'}))
        with self.assertRaises(ValueError):
            validate_package(path, '4.0.0')
