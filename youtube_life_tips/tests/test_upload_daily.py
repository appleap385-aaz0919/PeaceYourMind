"""Focused safety checks for date scheduling and channel isolation."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import upload_daily
from youtube_auth import state_path


class UploadScheduleTests(unittest.TestCase):
    def test_seven_am_korea_maps_to_previous_day_utc(self) -> None:
        scheduled = upload_daily.publish_at_for(date(2026, 10, 22), "07:00")
        self.assertEqual(scheduled.isoformat(), "2026-10-22T07:00:00+09:00")
        self.assertEqual(
            scheduled.astimezone(upload_daily.ZoneInfo("UTC")).isoformat(),
            "2026-10-21T22:00:00+00:00",
        )

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
