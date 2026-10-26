import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_schedule as schedule
import choose_verse
import notify_result


class ReleaseTests(unittest.TestCase):
    def test_primary_and_retry_resolve_to_the_same_release(self):
        now = datetime(2026, 10, 26, 4, tzinfo=schedule.KST)
        am = [schedule.resolve({"schedule": cron}, now) for cron in ("30 16 * * *", "15 17 * * *")]
        pm = [schedule.resolve({"schedule": cron}, now) for cron in ("30 4 * * *", "15 5 * * *")]
        self.assertEqual(am[0], am[1])
        self.assertEqual(pm[0], pm[1])
        self.assertEqual(am[0]["release_key"], "2026-10-26")
        self.assertEqual(pm[0]["release_key"], "2026-10-26-pm")
        self.assertIn("T19:00", pm[0]["publish_at_kst"])

    def test_two_releases_advance_verse_pool_without_repeating(self):
        pool = [{"id": str(i), "ref": "시 1:1", "text": "text"} for i in range(20)]
        day = date(2026, 10, 26)
        chosen = [choose_verse.make_manifest(day + timedelta(days=i), pool, slot)["verse_id"]
                  for i in range(3) for slot in ("am", "pm")]
        self.assertEqual(len(set(chosen)), 6)
        self.assertEqual(int(chosen[0]), (day.toordinal() - 1) % 20)

    def test_success_email_is_sent_once_per_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "uploads.json"
            state.write_text(json.dumps({"2026-10-26": {"video_id": "AM"},
                                         "2026-10-26-pm": {"video_id": "PM"}}), encoding="utf-8")
            smtp = Mock()
            with patch.object(notify_result.smtplib, "SMTP_SSL", return_value=smtp), patch.object(notify_result, "persist"):
                args = ("success", "run", state, "sender@example.invalid", "receiver@example.invalid", "mock")
                self.assertTrue(notify_result.notify("2026-10-26", *args))
                self.assertFalse(notify_result.notify("2026-10-26", *args))
                self.assertTrue(notify_result.notify("2026-10-26-pm", *args))
                self.assertFalse(notify_result.notify("2026-10-26-pm", *args))
            self.assertEqual(smtp.send_message.call_count, 2)

    def test_uncertain_smtp_send_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "uploads.json"
            state.write_text(json.dumps({"2026-10-26": {"video_id": "AM"}}), encoding="utf-8")
            smtp = Mock()
            def send(message):
                self.assertEqual(json.loads(state.read_text())["2026-10-26"]["success_email"]["status"], "attempted")
                raise OSError("connection lost after DATA")
            smtp.send_message.side_effect = send
            with patch.object(notify_result.smtplib, "SMTP_SSL", return_value=smtp), patch.object(notify_result, "persist"):
                args = ("2026-10-26", "success", "run", state, "a@b.invalid", "c@d.invalid", "mock")
                with self.assertRaises(OSError):
                    notify_result.notify(*args)
                self.assertFalse(notify_result.notify(*args))
            smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
