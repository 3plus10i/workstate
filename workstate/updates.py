"""Manual release checks and bounded downloads; no application data is sent."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from . import __version__

REPOSITORY = '3plus10i/workstate'
PROJECT_HOME = f'https://github.com/{REPOSITORY}'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MIRROR = 'https://gh-proxy.org/'
MAX_PACKAGE = 128 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('版本号必须为 x.y.z 格式')
    return tuple(map(int, value.split('.')))


def source_url(url, source):
    if source not in {'github', 'ghproxy'}:
        raise ValueError('更新源无效')
    return MIRROR + url if source == 'ghproxy' else url


class NetworkFailure(ValueError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    source: str
    size: int

    @property
    def filename(self):
        return f'WorkState-{self.version}-Windows.zip'

    def asset_url(self, name):
        return source_url(f'{PROJECT_HOME}/releases/download/v{self.version}/{name}', self.source)


class ReleaseClient:
    def __init__(self, opener=urlopen):
        self.opener = opener

    def open(self, url, timeout=8):
        request = Request(url, headers={'User-Agent': f'WorkState/{__version__}', 'Accept': 'application/json' if '/api.github.com/' in url or url.startswith('https://api.github.com/') else 'application/octet-stream'})
        try:
            return self.opener(request, timeout=timeout)
        except HTTPError as error:
            if error.code in {403, 408, 429} or error.code >= 500:
                raise NetworkFailure('更新服务器暂时不可用，请稍后重试') from error
            raise
        except (URLError, OSError, TimeoutError) as error:
            raise NetworkFailure('连接更新服务器失败，请检查网络后重试') from error

    def read(self, url, limit):
        try:
            with self.open(url) as response:
                data = response.read(limit + 1)
        except HTTPError:
            raise
        except (OSError, URLError, TimeoutError) as error:
            raise NetworkFailure('连接更新服务器失败，请检查网络后重试') from error
        if len(data) > limit:
            raise ValueError('更新信息超过大小限制')
        return data

    def latest(self):
        for source in ('github', 'ghproxy'):
            try:
                raw = self.read(source_url(LATEST_URL, source), 1024 * 1024)
                break
            except NetworkFailure:
                if source == 'ghproxy':
                    raise
            except HTTPError as error:
                if error.code == 404:
                    return None
                raise ValueError(f'检查更新失败（HTTP {error.code}）') from error
        try:
            data = json.loads(raw)
            version = data['tag_name'].removeprefix('v')
            version_tuple(version)
            if data.get('draft') is not False or data.get('prerelease') is not False or data['tag_name'] != f'v{version}':
                raise ValueError('不是正式发布版本')
            expected = {f'WorkState-{version}-Windows.zip', 'SHA256SUMS.txt'}
            assets = {asset['name']: asset for asset in data['assets']}
            if not expected <= assets.keys():
                raise ValueError('发布附件不完整，请联系项目维护者')
            for name in expected:
                asset = assets[name]
                if asset.get('state') != 'uploaded' or asset.get('browser_download_url') != f'{PROJECT_HOME}/releases/download/v{version}/{name}':
                    raise ValueError('发布附件格式不符合约定')
            size = assets[f'WorkState-{version}-Windows.zip']['size']
            if type(size) is not int or not 0 < size <= MAX_PACKAGE:
                raise ValueError('发布包大小无效')
            return Release(version, str(data.get('body') or '').strip()[:32000], source, size)
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError('更新信息格式不正确，请稍后重试') from error

    def download(self, release, directory, progress, cancelled):
        try:
            sums = self.read(release.asset_url('SHA256SUMS.txt'), 16 * 1024).decode('utf-8-sig')
            hashes = [line.split()[0].lower() for line in sums.splitlines() if len(line.split()) == 2 and line.split()[1] == release.filename]
            if len(hashes) != 1 or not re.fullmatch('[0-9a-f]{64}', hashes[0]):
                raise ValueError('发布包校验信息缺失或无效')
            package = directory / 'package.zip'
            digest, received, started = hashlib.sha256(), 0, time.monotonic()
            with self.open(release.asset_url(release.filename), timeout=15) as response, package.open('wb') as output:
                while chunk := response.read(128 * 1024):
                    if cancelled.is_set():
                        raise ValueError('下载已取消')
                    received += len(chunk)
                    if received > release.size or received > MAX_PACKAGE or time.monotonic() - started > 600:
                        raise ValueError('下载超出大小或时间限制，请重试')
                    output.write(chunk)
                    digest.update(chunk)
                    progress(received, release.size)
            if received != release.size or digest.hexdigest() != hashes[0]:
                raise ValueError('下载校验失败，请重新下载')
            executable = directory / 'new.exe'
            with zipfile.ZipFile(package) as archive:
                names = archive.namelist()
                if len(names) != 2 or set(names) != {'WorkState/WorkState.exe', 'WorkState/README.md'}:
                    raise ValueError('发布包内容不符合约定')
                info = archive.getinfo('WorkState/WorkState.exe')
                if not 0 < info.file_size <= MAX_PACKAGE:
                    raise ValueError('程序文件大小无效')
                with archive.open(info) as source, executable.open('wb') as target:
                    shutil.copyfileobj(source, target)
            with executable.open('rb') as file:
                if file.read(2) != b'MZ':
                    raise ValueError('发布包中没有有效的 Windows 程序')
                file.seek(0)
                exe_hash = hashlib.file_digest(file, 'sha256').hexdigest()
            return executable, exe_hash
        except HTTPError as error:
            raise ValueError(f'下载失败（HTTP {error.code}），请稍后重试') from error
        except (OSError, URLError, TimeoutError) as error:
            raise ValueError('下载失败，请检查网络后重新下载') from error
        except (zipfile.BadZipFile, UnicodeDecodeError) as error:
            raise ValueError('发布包或校验文件损坏，请重新下载') from error


class Updater:
    def __init__(self, executable, data_directory, supported=True, demo=False, client=None, cache=None):
        self.executable = Path(executable).resolve()
        self.data_directory = Path(data_directory).resolve()
        self.supported = supported
        self.demo = demo
        self.client = client or ReleaseClient()
        self.cache = Path(cache) if cache else Path(tempfile.gettempdir()) / 'WorkState-updates'
        self._lock = threading.RLock()
        self._cancelled = threading.Event()
        self.release = None
        self.directory = None
        self.executable_hash = None
        self._state = {'phase': 'idle', 'supported': supported, 'version': None, 'notes': '', 'source': None, 'received': 0, 'total': 0, 'error': ''}

    def status(self):
        with self._lock:
            return {**self._state, 'supported': self.supported}

    def check(self):
        with self._lock:
            if self._state['phase'] in {'checking', 'downloading', 'installing'}:
                raise ValueError('更新操作正在进行')
            self.release = None
            self._state.update(phase='checking', error='', version=None, notes='', source=None, received=0, total=0)
        try:
            release = self.client.latest()
            with self._lock:
                self.release = release
                newer = release and version_tuple(release.version) > version_tuple(__version__)
                self._state.update(phase='available' if newer else 'latest' if release else 'unpublished', version=release.version if release else None, notes=release.notes if release else '', source=release.source if release else None, received=0, total=release.size if release else 0)
        except Exception as error:
            with self._lock:
                self._state.update(phase='error', error=str(error) if isinstance(error, ValueError) else '检查更新失败，请稍后重试')
        return self.status()

    def download(self):
        with self._lock:
            if not self.supported:
                raise ValueError('请在正式桌面程序中安装更新')
            if not self.release or self._state['phase'] not in {'available', 'error', 'ready'} or version_tuple(self.release.version) <= version_tuple(__version__):
                raise ValueError('请先检查是否有可用更新')
            if self.directory:
                if not self.directory.resolve().is_relative_to(self.cache.resolve()) or self.directory.resolve() == self.cache.resolve():
                    raise ValueError('更新缓存目录无效')
                shutil.rmtree(self.directory)
            self.cache.mkdir(parents=True, exist_ok=True)
            self.directory = Path(tempfile.mkdtemp(prefix='update-', dir=self.cache))
            self._cancelled.clear()
            self._state.update(phase='downloading', error='', received=0)
            threading.Thread(target=self._download, name='update-download', daemon=True).start()
        return self.status()

    def _download(self):
        try:
            def progress(received, total):
                with self._lock:
                    self._state.update(received=received, total=total)
            _, self.executable_hash = self.client.download(self.release, self.directory, progress, self._cancelled)
            with self._lock:
                self._state['phase'] = 'ready'
        except Exception as error:
            with self._lock:
                self._state.update(phase='error', error=str(error) if isinstance(error, ValueError) else '下载更新失败，请稍后重试')

    def prepare_install(self):
        from .update_worker import prepare_install
        with self._lock:
            if not self.supported or self._state['phase'] != 'ready':
                raise ValueError('请先完成更新下载')
            self._state['phase'] = 'installing'
            try:
                prepare_install(self)
            except Exception as error:
                self._state.update(phase='ready', error='无法启动更新，请确认程序目录可写后重试')
                raise ValueError(self._state['error']) from error

    def close(self):
        self._cancelled.set()
