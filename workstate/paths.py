from pathlib import Path


def default_data_directory(base, demo=False):
    base = Path(base)
    current = base / 'WorkState' / ('demo' if demo else 'data')
    previous = base / 'PCState' / 'data'
    if not demo and not (current / 'activity.sqlite3').exists() and (previous / 'activity.sqlite3').is_file():
        return previous
    return current
