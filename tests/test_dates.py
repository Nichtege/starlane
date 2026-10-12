import unittest
from datetime import date

from aos import dates as D

TODAY = date(2026, 10, 9)


class DateTests(unittest.TestCase):
    def test_iso_week_name(self):
        self.assertEqual(D.iso_week_name(TODAY), "2026-W41")
        self.assertEqual(D.iso_week_name(date(2026, 1, 1)), "2026-W01")
        self.assertEqual(D.iso_week_name(date(2024, 12, 30)), "2025-W01")  # ISO year boundary

    def test_week_bounds(self):
        self.assertEqual(D.week_bounds(TODAY), (date(2026, 10, 5), date(2026, 10, 11)))

    def test_find_dates_formats(self):
        self.assertEqual(D.find_dates("Submission 10.11.2026", TODAY), [date(2026, 11, 10)])
        self.assertEqual(D.find_dates("deadline: 2026-11-10", TODAY), [date(2026, 11, 10)])
        self.assertEqual(D.find_dates("**Tue 6.10. Quiz**", TODAY), [date(2026, 10, 6)])
        self.assertEqual(D.find_dates("Mon 12.10 – Sun 18.10", TODAY), [date(2026, 10, 12), date(2026, 10, 18)])
        self.assertEqual(D.find_dates("Tuesday 13.10. review", TODAY), [date(2026, 10, 13)])
        self.assertEqual(D.find_dates("Thurs 15.10.", TODAY), [date(2026, 10, 15)])

    def test_german_weekday_abbreviations_still_accepted(self):
        self.assertEqual(D.find_dates("**Di 6.10. Test**", TODAY), [date(2026, 10, 6)])
        self.assertEqual(D.find_dates("Mo 12.10 – So 18.10", TODAY), [date(2026, 10, 12), date(2026, 10, 18)])

    def test_weekday_must_match_date(self):
        self.assertEqual(D.find_dates("Mon 6.10. does not match", TODAY), [])  # 6.10.2026 is a Tuesday
        self.assertEqual(D.find_dates("Mo 6.10. passt nicht", TODAY), [])

    def test_decimals_versions_and_units_are_not_dates(self):
        self.assertEqual(D.find_dates("Version 3.12 and chapter 4.2, 5.5 pages", TODAY), [])
        self.assertEqual(D.find_dates("Thu 1.10 h and Sun 2.5 million", date(2026, 10, 1)), [])

    def test_invalid_dates_ignored(self):
        self.assertEqual(D.find_dates("31.02.2026 and 2026-13-40", TODAY), [])

    def test_year_chosen_nearest_to_today(self):
        # New Year's Eve seen in December: 'Thu 31.12.' belongs to 2026 (a Thursday), not 2025
        self.assertEqual(D.find_dates("Thu 31.12.", date(2026, 12, 20)), [date(2026, 12, 31)])
        # a January date seen in December belongs to next year
        self.assertEqual(D.find_dates("Fri 15.1.", date(2026, 12, 20)), [date(2027, 1, 15)])

    def test_countdown_text(self):
        self.assertEqual(D.countdown_text(TODAY, TODAY), "today")
        self.assertEqual(D.countdown_text(date(2026, 10, 10), TODAY), "tomorrow")
        self.assertEqual(D.countdown_text(date(2026, 10, 8), TODAY), "yesterday")
        self.assertEqual(D.countdown_text(date(2026, 11, 10), TODAY), "in 32 days")
        self.assertEqual(D.countdown_text(date(2026, 10, 6), TODAY), "3 days ago")

    def test_formatting_is_english(self):
        self.assertEqual(D.fmt_date(date(2026, 10, 6)), "Tue 6 Oct")
        self.assertEqual(D.fmt_day(date(2026, 1, 15)), "15 Jan")
        self.assertEqual(D.WEEKDAYS[TODAY.weekday()], "Friday")

    def test_parse_iso(self):
        self.assertEqual(D.parse_iso("2026-11-10"), date(2026, 11, 10))
        self.assertIsNone(D.parse_iso("10.11.2026"))
        self.assertIsNone(D.parse_iso(""))
        self.assertIsNone(D.parse_iso("2026-02-30"))


if __name__ == "__main__":
    unittest.main()
