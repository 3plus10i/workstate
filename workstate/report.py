from collections import Counter
from datetime import datetime, timedelta

from .classification import classify
from .models import parse_range
from .settings import excluded_processes


def build_report(repository, start, end, expanded=None):
    settings = repository.settings()
    first, last, begin, finish = parse_range(start, end, settings["dayStartHour"])
    rows = repository.query(begin, finish)
    expanded = settings["expandContexts"] if expanded is None else expanded
    excluded = excluded_processes(settings)
    identities = {}
    candidates = Counter()
    for row in rows:
        raw_key = (row.process, row.title if expanded else "")
        identity = identities.get(raw_key)
        if identity is None:
            identity = classify(row.process, raw_key[1], settings)
            identities[raw_key] = identity
        if identity.key in excluded:
            continue
        if expanded and row.active and identity.context:
            logical = (datetime.fromtimestamp(row.minute * 60) - timedelta(hours=settings["dayStartHour"])).date()
            candidates[(logical, identity.key, identity.context)] += 1
    count = (last - first).days + 1
    slot_minutes = 5 if count <= 3 else 60
    days = []
    for i in range(count):
        day = first + timedelta(days=i)
        days.append({"date": day.isoformat(), "active": 0, "observed": 0, "slots": [0] * (1440 // slot_minutes), "coverage": [0] * (1440 // slot_minutes), "hourly": [dict() for _ in range(24)]})
    applications, hourly_totals = {}, [0] * 24
    for row in rows:
        identity = identities[(row.process, row.title if expanded else "")]
        if identity.key in excluded:
            continue
        stamp = datetime.fromtimestamp(row.minute * 60)
        logical = (stamp - timedelta(hours=settings["dayStartHour"])).date()
        index = (logical - first).days
        if not 0 <= index < count:
            continue
        hour = (stamp.hour - settings["dayStartHour"]) % 24
        slot = (hour * 60 + stamp.minute) // slot_minutes
        day = days[index]
        day["observed"] += 1
        day["coverage"][slot] += 1
        if not row.active:
            continue
        detail = identity.context if expanded and candidates[(logical, identity.key, identity.context)] > settings["detailThreshold"] else ""
        key = identity.key + ("::" + detail if detail else "")
        if key not in applications:
            applications[key] = {"key": key, "app": identity.app, "context": detail, "kind": identity.kind if detail else "app", "minutes": 0}
        applications[key]["minutes"] += 1
        day["active"] += 1
        day["slots"][slot] += 1
        day["hourly"][hour][key] = day["hourly"][hour].get(key, 0) + 1
        hourly_totals[hour] += 1
    ranked = sorted(applications.values(), key=lambda a: (-a["minutes"], a["key"]))
    active = sum(d["active"] for d in days)
    observed = sum(d["observed"] for d in days)
    peak = max(range(24), key=lambda i: hourly_totals[i]) if active else None
    return {"start": start, "end": end, "dayStartHour": settings["dayStartHour"], "expanded": expanded, "threshold": settings["detailThreshold"], "days": days, "apps": ranked, "summary": {"activeMinutes": active, "observedMinutes": observed, "idleMinutes": observed - active, "dailyAverage": round(active / count), "recordedDays": sum(d["observed"] > 0 for d in days), "peakHour": (peak + settings["dayStartHour"]) % 24 if peak is not None else None, "topApp": ranked[0] if ranked else None}}
