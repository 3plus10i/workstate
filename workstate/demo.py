"""Deterministic, fictional records, only in an explicitly selected demo directory."""
from datetime import date, datetime, timedelta
import random

from .models import Activity


def seed_demo(repository):
    if repository.inventory()["recordCount"]:
        return
    rng = random.Random(410)
    today = date.today()
    rows = []
    apps = [
        ("Code.exe", "report.tsx - WorkState - Visual Studio Code"),
        ("Code.exe", "analysis.py - Research notes - Visual Studio Code"),
        ("chrome.exe", "Issues · GitHub - Google Chrome"),
        ("chrome.exe", "ChatGPT - Google Chrome"),
        ("WINWORD.EXE", "实验记录.docx - Word"),
        ("zotero.exe", "Zotero"),
        ("msedge.exe", "Home - Microsoft Edge"),
        ("Weixin.exe", "微信"),
    ]
    offsets = list(range(35)) + list(range(155, 162))
    now_minute = int(datetime.now().timestamp() // 60)
    for offset in offsets:
        day = today - timedelta(days=offset)
        weekend = day.weekday() >= 5
        start = 10 * 60 + rng.randrange(35) if weekend else 9 * 60 + rng.randrange(45)
        end = 16 * 60 + rng.randrange(45) if weekend else 18 * 60 + rng.randrange(60)
        for minute in range(start, end):
            stamp = int(datetime(day.year, day.month, day.day).timestamp() // 60) + minute
            if stamp >= now_minute:
                continue
            if 12 * 60 + 15 <= minute < 13 * 60 + 10 or rng.random() < 0.035:
                continue
            hour = minute // 60
            app = apps[(hour + offset // 3) % 6] if minute % 60 < 48 else apps[6 + (offset % 2)]
            rows.append(Activity(stamp, rng.random() > 0.10, *app))
    repository.write_many(rows)
