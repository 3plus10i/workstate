"""Keep release metadata and the updater's asset contract consistent."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workstate.updates import version_tuple


def current_version(root=ROOT):
    return re.search(r'__version__ = "([^"]+)"', (root / 'workstate/__init__.py').read_text(encoding='utf-8')).group(1)


def release_notes(root=ROOT, version=None):
    version = version or current_version(root)
    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\n(.*?)(?=^## |^\[\d|\Z)', changelog, re.M | re.S)
    if not match or not match[2].strip():
        raise ValueError(f'CHANGELOG.md 缺少 {version} 的日期和更新说明')
    date.fromisoformat(match[1])
    return match[2].strip() + '\n'


def validate(root=ROOT, tag=None):
    version = current_version(root)
    version_tuple(version)
    metadata = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    package = json.loads((root / 'frontend/package.json').read_text(encoding='utf-8'))
    lock = json.loads((root / 'frontend/package-lock.json').read_text(encoding='utf-8'))
    if {version, metadata['project']['version'], package['version'], lock['version'], lock['packages']['']['version']} != {version}:
        raise ValueError('程序、Python 元数据、前端和锁文件的版本号不一致')
    if tag is not None and tag != f'v{version}':
        raise ValueError(f'Git 标签必须为 v{version}')
    release_notes(root, version)
    return version


def set_version(version, root=ROOT):
    version_tuple(version)
    for name, pattern in [('workstate/__init__.py', r'(__version__ = ")[^"]+(\")'), ('pyproject.toml', r'(?m)^(version = ")[^"]+(\")')]:
        path = root / name
        path.write_text(re.sub(pattern, lambda match: match[1] + version + match[2], path.read_text(encoding='utf-8'), count=1), encoding='utf-8', newline='\n')
    for name in ('package.json', 'package-lock.json'):
        path = root / 'frontend' / name
        data = json.loads(path.read_text(encoding='utf-8'))
        data['version'] = version
        if name == 'package-lock.json':
            data['packages']['']['version'] = version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    path = root / 'README.md'
    path.write_text(re.sub(r'WorkState-\d+\.\d+\.\d+-Windows.zip', f'WorkState-{version}-Windows.zip', path.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')


def validate_package(path, version):
    if path.name != f'WorkState-{version}-Windows.zip':
        raise ValueError('发布包名称与版本号不一致')
    with zipfile.ZipFile(path) as archive:
        if sorted(archive.namelist()) != ['WorkState/README.md', 'WorkState/WorkState.exe'] or archive.testzip():
            raise ValueError('发布包必须仅包含 WorkState.exe 和 README.md，且内容完整')
        with archive.open('WorkState/WorkState.exe') as file:
            if file.read(2) != b'MZ':
                raise ValueError('发布包中没有有效的 Windows 程序')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check')
    check.add_argument('--tag')
    setter = commands.add_parser('set-version')
    setter.add_argument('version')
    notes = commands.add_parser('notes')
    notes.add_argument('--output', type=Path)
    package = commands.add_parser('check-package')
    package.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'set-version':
            set_version(args.version)
            print(f'Version set to {args.version}. Update CHANGELOG.md before releasing.')
        elif args.command == 'check':
            print(f'Release metadata verified: {validate(tag=args.tag)}')
        elif args.command == 'notes':
            content = release_notes()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(content, encoding='utf-8')
            else:
                print(content, end='')
        else:
            validate_package(args.path, validate())
            print('Release package verified.')
    except (ValueError, KeyError, AttributeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
