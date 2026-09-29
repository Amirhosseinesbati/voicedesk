"""Pure scheduling rules shared by availability and booking."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class DomainError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("timezone_required", "An ISO date and time with a UTC offset is required.")
    return value.astimezone(timezone.utc)


def stored_utc(value: datetime) -> datetime:
    """SQLite discards tzinfo; all stored instants are UTC by convention."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def checked_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise DomainError("invalid_timezone", "Use a valid IANA timezone.") from exc


def validate_local_instant(value: datetime, timezone_name: str) -> datetime:
    """Require a real, unambiguous instant; offset disambiguates a DST fold."""
    instant = aware_utc(value)
    local = instant.astimezone(checked_zone(timezone_name))
    if value.utcoffset() == timedelta(0):
        return instant
    if local.replace(tzinfo=None) != value.replace(tzinfo=None) or local.utcoffset() != value.utcoffset():
        raise DomainError("timezone_mismatch", "The date, UTC offset, and timezone do not agree.")
    return instant


def blocks(start: datetime, end: datetime, minutes: int = 15) -> list[datetime]:
    start = aware_utc(start)
    end = aware_utc(end)
    if end <= start or start.minute % minutes or start.second or start.microsecond:
        raise DomainError("invalid_slot", "Appointment times must align to 15-minute blocks.")
    values = []
    cursor = start
    while cursor < end:
        values.append(cursor)
        cursor += timedelta(minutes=minutes)
    return values


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return stored_utc(a_start) < stored_utc(b_end) and stored_utc(b_start) < stored_utc(a_end)


def within_hours(start: datetime, end: datetime, intervals: list[dict], timezone_name: str) -> bool:
    zone = checked_zone(timezone_name)
    local_start = aware_utc(start).astimezone(zone)
    local_end = aware_utc(end).astimezone(zone)
    if local_start.date() != local_end.date():
        return False
    start_clock = local_start.strftime("%H:%M")
    end_clock = local_end.strftime("%H:%M")
    return any(item["start"] <= start_clock and end_clock <= item["end"] for item in intervals)
