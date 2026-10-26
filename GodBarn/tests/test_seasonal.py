"""Calendar discovery preserves recorded history and never changes a catalog."""

import copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from GodBarn import seasonal


def crop(start=None, end=None):
    return {"name": "seasonal-crop", "type": "seed", "archive": {
        "availability": {"start": start, "end": end}}}


class SeasonalTests(unittest.TestCase):
    def test_local_system_date_survives_utc_midnight_and_manual_override(self):
        local_now = datetime(2026, 10, 21, 23, 30, tzinfo=timezone(timedelta(hours=-3), "ADT"))
        # This instant is already October 22 in UTC. The calendar follows the Mac.
        self.assertEqual(local_now.astimezone(timezone.utc).date(), date(2026, 10, 22))
        with patch.object(seasonal, "datetime") as clock:
            clock.now.return_value.astimezone.return_value = local_now
            day, context = seasonal.calendar_context()
            clock.now.assert_called_once_with()
            clock.now.return_value.astimezone.assert_called_once_with()
        self.assertEqual(day, date(2026, 10, 21))
        self.assertEqual(context, {"systemDate": "2026-10-21", "date": "2026-10-21",
                                   "timezone": "ADT", "mode": "annual", "override": False})
        day, context = seasonal.calendar_context("2011-12-25", now=local_now)
        self.assertEqual(day, date(2011, 12, 25))
        self.assertEqual(context["systemDate"], "2026-10-21")
        self.assertEqual(context["date"], "2011-12-25")
        self.assertTrue(context["override"])

    def test_recorded_window_recurs_with_inclusive_boundaries(self):
        candy_corn = crop("2011-10-05", "2011-11-10")
        before = copy.deepcopy(candy_corn)
        for day, expected in ((date(2026, 10, 4), "out"), (date(2026, 10, 5), "in"),
                              (date(2026, 11, 10), "in"), (date(2026, 11, 11), "out")):
            with self.subTest(day=day):
                result = seasonal.crop_season(candy_corn, day)
                self.assertEqual(result["status"], expected)
                self.assertEqual((result["start"], result["end"]), ("2011-10-05", "2011-11-10"))
                self.assertEqual((result["startMonthDay"], result["endMonthDay"]), ("10-05", "11-10"))
        self.assertEqual(candy_corn, before)

    def test_cross_year_window_does_not_activate_summer(self):
        winter = crop("2010-12-15", "2011-01-10")
        for day, expected in ((date(2026, 12, 14), "out"), (date(2026, 12, 15), "in"),
                              (date(2027, 1, 10), "in"), (date(2027, 1, 11), "out"),
                              (date(2026, 7, 1), "out")):
            with self.subTest(day=day):
                self.assertEqual(seasonal.crop_season(winter, day)["status"], expected)

    def test_february_29_boundaries_clamp_to_february_28_without_spilling(self):
        leap_day = crop("2012-02-29", "2012-02-29")
        self.assertEqual(seasonal.crop_season(leap_day, date(2026, 2, 28))["status"], "in")
        self.assertEqual(seasonal.crop_season(leap_day, date(2026, 3, 1))["status"], "out")
        self.assertEqual(seasonal.crop_season(leap_day, date(2028, 2, 28))["status"], "out")
        self.assertEqual(seasonal.crop_season(leap_day, date(2028, 2, 29))["status"], "in")
        self.assertEqual(seasonal.crop_season(crop("2012-02-01", "2012-02-29"), date(2026, 2, 28))["status"], "in")

    def test_missing_malformed_reversed_and_multi_year_windows_stay_unknown(self):
        unknowns = [{"type": "seed", "archived": True}, crop(), crop("2011-10-05", None),
                    crop("2011-2-1", "2011-02-02"), crop("2011-02-30", "2011-03-01"),
                    crop("2011-11-10", "2011-10-05"), crop("1970-01-01", "9999-12-31"),
                    crop("2011-01-01", "2012-01-02")]
        for item in unknowns:
            with self.subTest(item=item):
                self.assertEqual(seasonal.crop_season(item, date(2026, 10, 21)), {"status": "unknown"})
        self.assertIsNone(seasonal.crop_season({"type": "tree"}, date(2026, 10, 21)))

    def test_full_year_window_does_not_collapse_to_a_single_anniversary(self):
        annual = crop("2011-01-01", "2012-01-01")
        for day in (date(2026, 1, 1), date(2026, 6, 20), date(2026, 12, 31)):
            self.assertEqual(seasonal.crop_season(annual, day)["status"], "in")

    def test_filters_and_counts_include_only_crops_and_annotation_is_detached(self):
        items = [crop("2011-10-05", "2011-11-10"), crop("2010-12-15", "2011-01-10"),
                 {"name": "unknown", "type": "seed"}, {"name": "cow", "type": "animal"}]
        day = date(2026, 10, 21)
        self.assertEqual(seasonal.seasonal_counts(items, day), {"in": 1, "out": 1, "known": 2, "unknown": 1, "total": 3})
        for selected, count in (("in", 1), ("out", 1), ("known", 2), ("unknown", 1), ("", 4)):
            self.assertEqual(sum(seasonal.matches_season(item, day, selected) for item in items), count)
        annotated = seasonal.annotate_item(items[0], day)
        self.assertIsNot(annotated, items[0])
        self.assertNotIn("seasonal", items[0])

    def test_invalid_calendar_controls_are_rejected(self):
        for value in ("2026-02-30", "2026-2-01", "today", "2026-10-21T00:00:00", " 2026-10-21"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                seasonal.calendar_context(value)
        with self.assertRaises(ValueError):
            seasonal.validate_filter("summer")


if __name__ == "__main__":
    unittest.main()
