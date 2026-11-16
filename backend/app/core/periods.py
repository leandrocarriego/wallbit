"""Accounting periods (`YYYY-MM`) in Argentina time."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

AR = ZoneInfo("America/Argentina/Buenos_Aires")


def period_of(moment: datetime | date) -> str:
    day = moment.astimezone(AR).date() if isinstance(moment, datetime) else moment
    return f"{day.year:04d}-{day.month:02d}"


def local_date(moment: datetime) -> date:
    return moment.astimezone(AR).date()


def shift(period: str, months: int) -> str:
    year, month = (int(x) for x in period.split("-"))
    index = year * 12 + (month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def first_day(period: str) -> date:
    year, month = (int(x) for x in period.split("-"))
    return date(year, month, 1)
