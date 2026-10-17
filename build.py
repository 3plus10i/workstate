"""Build a reproducible desktop distribution from the current interpreter."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from shutil import copy2, rmtree
from workstate import __version__

ROOT = Path(__file__).resolve().parent


def run(command, cwd=ROOT):
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-frontend', action='store_true')
    parser.add_argument('--release', action='store_true', help='also create a ZIP distribution')
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'release', help='output directory within this project')
    args = parser.parse_args()
    args.dist_dir = args.dist_dir.resolve()
    if not args.dist_dir.is_relative_to(ROOT):
        parser.error('--dist-dir must be inside the project')
    run([sys.executable, 'tools/release.py', 'check'])
    if not args.skip_frontend:
        run(['npm.cmd' if os.name == 'nt' else 'npm', 'ci'], ROOT / 'frontend')
        run(['npm.cmd' if os.name == 'nt' else 'npm', 'test'], ROOT / 'frontend')
        run(['npm.cmd' if os.name == 'nt' else 'npm', 'run', 'build'], ROOT / 'frontend')
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'])
    os.environ['PYINSTALLER_CONFIG_DIR'] = str(ROOT / 'build' / '.cache')
    from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo
    numbers = (*map(int, __version__.split('.')), 0)
    version_info = VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers), kids=[
        StringFileInfo([StringTable('040904B0', [StringStruct(key, value) for key, value in {
            'CompanyName': '3plus10i', 'FileDescription': 'WorkState - 电脑活动记录工具',
            'FileVersion': __version__, 'ProductName': 'WorkState', 'ProductVersion': __version__,
            'OriginalFilename': 'WorkState.exe',
        }.items()])]), VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
    ])
    version_path = ROOT / 'build' / 'version-info.txt'
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(str(version_info), encoding='utf-8')
    distribution = (args.dist_dir / 'WorkState').resolve()
    if not distribution.is_relative_to(ROOT):
        parser.error('distribution must be inside the project')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--name=WorkState', f'--icon={ROOT / "public" / "workstate.ico"}', f'--distpath={distribution}', '--workpath=build/workstate', '--specpath=build', f'--add-data={ROOT / "viewer"};viewer', f'--add-data={ROOT / "public"};public', '--collect-data=webview', '--collect-data=pythonnet', '--hidden-import=webview.platforms.winforms', '--hidden-import=webview.platforms.edgechromium', '--hidden-import=pystray._win32', '--exclude-module=PyQt5', '--exclude-module=PyQt6', '--exclude-module=PySide2', '--exclude-module=PySide6', '--exclude-module=matplotlib', '--exclude-module=numpy', '--exclude-module=pandas', '--exclude-module=scipy', '--exclude-module=tkinter', 'main.py']
    command.insert(-1, f'--additional-hooks-dir={ROOT / "build_hooks"}')
    command.insert(-1, f'--version-file={version_path}')
    run(command)
    copy2(ROOT / 'docs' / 'release-readme.md', distribution / 'README.md')
    # Retire generated files left by the previous folder-based distribution.
    for name in ('_internal', 'docs', 'CHANGELOG.md', '使用说明.txt'):
        obsolete = distribution / name
        if not obsolete.exists():
            continue
        if not obsolete.resolve().is_relative_to(distribution.resolve()):
            raise ValueError(f'Refusing to remove a path outside the distribution: {obsolete}')
        if obsolete.is_dir():
            rmtree(obsolete)
        else:
            obsolete.unlink()
    if args.release:
        with zipfile.ZipFile(ROOT / 'release' / f'WorkState-{__version__}-Windows.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ('WorkState.exe', 'README.md'):
                path = distribution / name
                archive.write(path, path.relative_to(distribution.parent))
        package = ROOT / 'release' / f'WorkState-{__version__}-Windows.zip'
        with package.open('rb') as file:
            digest = hashlib.file_digest(file, 'sha256').hexdigest()
        (ROOT / 'release' / 'SHA256SUMS.txt').write_text(f'{digest}  {package.name}\n', encoding='utf-8')
        run([sys.executable, 'tools/release.py', 'check-package', str(package)])
    print(f'Ready: {distribution / "WorkState.exe"}')


if __name__ == '__main__':
    main()
