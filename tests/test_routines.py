import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from aos.config import PROJECT_ROOT
from aos.routines import ALLOWED_COMMANDS, RoutineError, Schedule, load_routines


def dt(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm)  # 2026-10-09 is a Friday


class ScheduleParseTests(unittest.TestCase):
    def test_valid_forms(self):
        self.assertEqual(Schedule.parse("every 5m").interval, timedelta(minutes=5))
        self.assertEqual(Schedule.parse("EVERY 2h").interval, timedelta(hours=2))
        s = Schedule.parse("daily 06:30")
        self.assertEqual((s.kind, s.hour, s.minute), ("daily", 6, 30))
        w = Schedule.parse("weekly mon,thu 08:00")
        self.assertEqual(w.weekdays, (0, 3))
        self.assertEqual(Schedule.parse("weekly sunday 18:30").weekdays, (6,))
        self.assertEqual(Schedule.parse("weekly so 18:30").weekdays, (6,))  # German abbreviations still accepted

    def test_invalid_forms_have_helpful_messages(self):
        for bad in ["", "sometimes", "every 0m", "every 30s", "daily 25:00", "daily 06:61", "weekly xyz 08:00", "every 5"]:
            with self.assertRaises(RoutineError, msg=bad):
                Schedule.parse(bad)
        with self.assertRaisesRegex(RoutineError, "Allowed"):
            Schedule.parse("every day")


class DueTests(unittest.TestCase):
    def test_daily_due_after_slot_and_only_once(self):
        s = Schedule.parse("daily 06:30")
        self.assertIsNone(s.due_slot(dt(9, 6, 29), dt(9, 6, 30)))  # before the slot: today's slot has not come yet
        slot = s.due_slot(dt(9, 6, 31), None)
        self.assertEqual(slot, dt(9, 6, 30))
        self.assertIsNone(s.due_slot(dt(9, 12, 0), slot))  # already done

    def test_missed_slot_catches_up_once(self):
        s = Schedule.parse("daily 06:30")
        last = dt(6, 6, 30)  # laptop was off for 3 days
        slot = s.due_slot(dt(9, 15, 0), last)
        self.assertEqual(slot, dt(9, 6, 30))  # only the latest slot, not three
        self.assertIsNone(s.due_slot(dt(9, 15, 5), slot))

    def test_before_first_slot_of_day_uses_yesterday(self):
        s = Schedule.parse("daily 06:30")
        self.assertEqual(s.due_slot(dt(9, 5, 0), dt(7, 6, 30)), dt(8, 6, 30))

    def test_weekly(self):
        s = Schedule.parse("weekly mon,thu 08:00")
        self.assertEqual(s.latest_slot(dt(9, 12, 0)), dt(8, 8, 0))  # Thu 2026-10-08
        self.assertEqual(s.next_slot(dt(9, 12, 0)), dt(12, 8, 0))  # Mon 2026-10-12

    def test_every(self):
        s = Schedule.parse("every 15m")
        self.assertEqual(s.due_slot(dt(9, 10, 0), None), dt(9, 10, 0))
        self.assertIsNone(s.due_slot(dt(9, 10, 13), dt(9, 10, 0)))  # 13 min: not due yet (14 min would be, thanks to the 60 s slack)
        self.assertEqual(s.due_slot(dt(9, 10, 15), dt(9, 10, 0)), dt(9, 10, 15))
        self.assertEqual(s.next_due(dt(9, 10, 5), dt(9, 10, 0)), dt(9, 10, 15))

    def test_next_due(self):
        s = Schedule.parse("daily 06:30")
        self.assertEqual(s.next_due(dt(9, 12, 0), dt(9, 6, 30)), dt(10, 6, 30))
        self.assertEqual(s.next_due(dt(9, 12, 0), dt(8, 6, 30)), dt(9, 12, 0))  # overdue = now


class LoadTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "routines.toml"
            p.write_text(text, encoding="utf-8")
            return load_routines(p)

    def test_defaults_and_limits(self):
        r = self.load('[[routine]]\nid = "digest"\nschedule = "daily 06:30"\ncommand = "digest"\ntimeout_s = 999999\n')[0]
        self.assertTrue(r.enabled)
        self.assertEqual(r.timeout_s, 3600)  # upper bound
        self.assertEqual(r.machine, ("any",))
        self.assertTrue(r.runs_on("whatever"))

    def test_command_defaults_to_id_and_must_be_whitelisted(self):
        self.assertEqual(self.load('[[routine]]\nid = "digest"\nschedule = "daily 06:30"\n')[0].command, "digest")
        for evil in ["rm -rf /", "powershell -c x", "digest && calc", "../../x", "python"]:
            with self.assertRaisesRegex(RoutineError, "not allowed"):
                self.load(f'[[routine]]\nid = "x"\nschedule = "daily 06:30"\ncommand = "{evil}"\n')

    def test_validation_errors(self):
        with self.assertRaisesRegex(RoutineError, "Duplicate"):
            self.load('[[routine]]\nid="a"\nschedule="daily 06:30"\ncommand="digest"\n[[routine]]\nid="a"\nschedule="daily 07:00"\ncommand="digest"\n')
        with self.assertRaisesRegex(RoutineError, "invalid"):
            self.load('[[routine]]\nid="Bad ID"\nschedule="daily 06:30"\ncommand="digest"\n')
        with self.assertRaisesRegex(RoutineError, "schedule"):
            self.load('[[routine]]\nid="a"\nschedule="sometime"\ncommand="digest"\n')
        with self.assertRaisesRegex(RoutineError, "TOML"):
            self.load("[[routine]\nbroken")
        with self.assertRaises(RoutineError):
            load_routines(Path("does-not-exist.toml"))

    def test_machine_matching_is_case_insensitive_and_supports_lists(self):
        r = self.load('[[routine]]\nid="a"\nschedule="daily 06:30"\ncommand="digest"\nmachine=["Laptop", "Server"]\n')[0]
        self.assertTrue(r.runs_on("laptop"))
        self.assertTrue(r.runs_on("SERVER"))
        self.assertFalse(r.runs_on("phone"))

    def test_argv_uses_only_the_fixed_arguments(self):
        r = self.load('[[routine]]\nid="a"\nschedule="daily 06:30"\ncommand="mapcheck"\n')[0]
        self.assertEqual(r.argv()[1:], ["-P", "-m", "aos", "mapcheck"])  # -P: the working folder never shadows a module

    def test_shipped_routines_file_is_valid(self):
        routines = load_routines(PROJECT_ROOT / "routines.toml")
        self.assertTrue(routines)
        self.assertTrue(all(r.command in ALLOWED_COMMANDS for r in routines))
        # riskier routines are off by default
        by_id = {r.id: r for r in routines}
        self.assertFalse(by_id["git-pull"].enabled)
        self.assertFalse(by_id["claude-weekly-review"].enabled)


if __name__ == "__main__":
    unittest.main()
