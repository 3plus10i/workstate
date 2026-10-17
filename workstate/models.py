from dataclasses import dataclass
from datetime import date, datetime, timedelta
import calendar


@dataclass(frozen=True, slots=True)
class Activity:
    minute: int
    active: bool
    process: str
    title: str = ""


def month_before(day: date, months: int = 3) -> date:
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def minute_at(day: date, hour: int = 0) -> int:
    return int(datetime(day.year, day.month, day.day, hour).timestamp() // 60)


def parse_range(start: str, end: str, day_start: int) -> tuple[date, date, int, int]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("结束日期不能早于开始日期")
    if (last - first).days > 3660:
        raise ValueError("一次最多查看十年的记录，请缩小日期区间")
    return first, last, minute_at(first, day_start), minute_at(last + timedelta(days=1), day_start)
