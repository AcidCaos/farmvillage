"""Read-only annual discovery of crops with recovered availability dates.

The source dates remain historical evidence. Repeating their month/day windows
is a God Barn browsing rule, not a restored original event or purchase gate.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from functools import lru_cache
import re


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILTERS = frozenset(("", "all", "in", "out", "known", "unknown"))


def calendar_context(calendar_date="", *, now=None):
    """Use the host's local calendar, with an optional browsing-only date."""
    local_now = datetime.now().astimezone() if now is None else now
    system_day = local_now.date()
    if calendar_date:
        if not isinstance(calendar_date, str) or not ISO_DATE.fullmatch(calendar_date):
            raise ValueError("Calendar date must use YYYY-MM-DD.")
        try:
            selected_day = date.fromisoformat(calendar_date)
        except ValueError as error:
            raise ValueError("Choose a valid calendar date in YYYY-MM-DD format.") from error
    else:
        selected_day = system_day
    return selected_day, {"systemDate": system_day.isoformat(), "date": selected_day.isoformat(),
                          "timezone": local_now.tzname() or str(local_now.tzinfo or "Local time"),
                          "mode": "annual", "override": bool(calendar_date)}


def validate_filter(value=""):
    if value not in FILTERS:
        raise ValueError("Seasonal filter must be in, out, known, or unknown.")
    return value


@lru_cache(maxsize=8192)
def _recorded_window(start, end):
    if not ISO_DATE.fullmatch(start) or not ISO_DATE.fullmatch(end):
        return None
    try:
        start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return None
    # Sentinel dates and multi-year sales do not establish an annual season.
    if not 1 <= (end_day - start_day).days + 1 <= 366:
        return None
    return start_day, end_day


def crop_season(item, day):
    """Return a crop annotation; non-crops have no seasonal classification."""
    if item.get("type") != "seed":
        return None
    archive = item.get("archive")
    availability = archive.get("availability") if isinstance(archive, dict) else None
    if not isinstance(availability, dict):
        return {"status": "unknown"}
    start, end = availability.get("start"), availability.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return {"status": "unknown"}
    window = _recorded_window(start, end)
    if window is None:
        return {"status": "unknown"}
    start_day, end_day = window

    def anniversary(source):
        # A recorded Feb 29 boundary falls on Feb 28 in non-leap years.
        return date(day.year, source.month, min(source.day, monthrange(day.year, source.month)[1]))

    annual_start, annual_end = anniversary(start_day), anniversary(end_day)
    if start_day.year != end_day.year and annual_start <= annual_end:
        # A valid <=366-day source window that reaches the next anniversary
        # covers the full year, rather than just the coincident boundary date.
        active = True
    elif annual_start <= annual_end:
        active = annual_start <= day <= annual_end
    else:
        active = day >= annual_start or day <= annual_end
    return {"status": "in" if active else "out", "start": start, "end": end,
            "startMonthDay": start[5:], "endMonthDay": end[5:]}


def matches_season(item, day, selected_filter):
    if selected_filter in ("", "all"):
        return True
    season = crop_season(item, day)
    if season is None:
        return False
    return season["status"] != "unknown" if selected_filter == "known" else season["status"] == selected_filter


def seasonal_counts(items, day):
    counts = {"in": 0, "out": 0, "known": 0, "unknown": 0, "total": 0}
    for item in items:
        season = crop_season(item, day)
        if season is not None:
            counts[season["status"]] += 1
            counts["total"] += 1
    counts["known"] = counts["in"] + counts["out"]
    return counts


def annotate_item(item, day):
    season = crop_season(item, day)
    return dict(item, seasonal=season) if season is not None else item
