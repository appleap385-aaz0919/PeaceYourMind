"""Focused safety checks for date scheduling and channel isolation."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import upload_daily
from youtube_auth import state_path


class UploadScheduleTests(unittest.TestCase):
    def test_new_uploads_disclose_ai_and_keep_each_release_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = date(2099, 1, 1)
            for slot, key, publish_at in (
                ("am", "2099-01-01", "2098-12-31T22:00:00Z"),
                ("pm", "2099-01-01-pm", "2099-01-01T10:00:00Z"),
            ):
                with self.subTest(slot=slot):
                    folder = root / key
                    folder.mkdir()
                    (folder / "life-tip-2099-01-01.mp4").write_bytes(b"test-video")
                    (folder / "metadata.json").write_text(json.dumps({
                        "date": day.isoformat(), "slot": slot, "release_key": key,
                        "title": "test", "description": "test", "sources": ["https://example.org"],
                        "width": 720, "height": 1280, "duration_seconds": 30,
                    }), encoding="utf-8")
                    with (
                        patch.object(upload_daily, "WORK", root),
                        patch.object(upload_daily, "load_local_config", return_value={"youtube_channel_id": "UC-LIFE"}),
                        patch.object(upload_daily, "load_oauth_client"),
                        patch.object(upload_daily, "get_access_token", return_value="fake-token"),
                        patch.object(upload_daily, "my_channels", return_value=[{"id": "UC-LIFE"}]),
                        patch.object(upload_daily, "upload_resumable", return_value={"id": "MOCK"}) as upload,
                    ):
                        upload_daily.upload_day(day, Namespace(slot=slot, publish_at_kst=None, dry_run=False))
                    status = upload.call_args.args[1]["status"]
                    self.assertIs(status["containsSyntheticMedia"], True)
                    self.assertEqual(status["publishAt"], publish_at)
                    self.assertEqual(status["privacyStatus"], "private")

    def test_seven_am_korea_maps_to_previous_day_utc(self) -> None:
        scheduled = upload_daily.publish_at_for(date(2026, 10, 22), "07:00")
        self.assertEqual(scheduled.isoformat(), "2026-10-22T07:00:00+09:00")
        self.assertEqual(
            scheduled.astimezone(upload_daily.ZoneInfo("UTC")).isoformat(),
            "2026-10-21T22:00:00+00:00",
        )

    def test_one_off_release_parses_and_requires_fifteen_minutes_lead(self) -> None:
        scheduled = upload_daily.parse_publish_at(date(2026, 10, 23), "2026-10-23T08:30")
        now = datetime(2026, 10, 23, 8, 0, tzinfo=upload_daily.KST)
        upload_daily.validate_publish_window(scheduled, now, one_off=True)
        with self.assertRaisesRegex(RuntimeError, "at least 15 minutes"):
            upload_daily.validate_publish_window(
                scheduled, datetime(2026, 10, 23, 8, 16, tzinfo=upload_daily.KST), one_off=True
            )

    def test_one_off_release_must_match_requested_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "requested --date"):
            upload_daily.parse_publish_at(date(2026, 10, 23), "2026-10-24T08:30")

    def test_oauth_files_cannot_escape_private_state_folder(self) -> None:
        with self.assertRaises(ValueError):
            state_path({"oauth_token_file": "state/../../.git/config"}, "oauth_token_file", "state/youtube_token.json")

    @patch("upload_daily.my_channels", return_value=[{"id": "UC-LIFE", "title": "Life Tips"}])
    def test_expected_channel_is_accepted(self, _mock_channels: object) -> None:
        upload_daily.validate_channel("fake-token", "UC-LIFE")

    @patch("upload_daily.my_channels", return_value=[{"id": "UC-PIM", "title": "Peace in Mind"}])
    def test_wrong_channel_is_rejected_before_upload(self, _mock_channels: object) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not expose configured life-tips channel"):
            upload_daily.validate_channel("fake-token", "UC-LIFE")


if __name__ == "__main__":
    unittest.main()
