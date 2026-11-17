from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from codex_mailbox import save_tiktok_copy


class TikTokExportTests(unittest.TestCase):
    def test_new_manual_video_preserves_existing_export_and_retries_reuse_copy(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            day = date(2026, 11, 5)
            existing = root / "tiktok_uploads" / str(day) / "life-tip-2026-11-05-manual.mp4"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"earlier video kept by user")
            source = root / "approved.mp4"
            source.write_bytes(b"new approved video")

            exported = save_tiktok_copy(source, day, "manual", root)
            self.assertEqual(existing.read_bytes(), b"earlier video kept by user")
            self.assertEqual(exported.name, "life-tip-2026-11-05-manual-2.mp4")
            self.assertEqual(exported.read_bytes(), source.read_bytes())
            self.assertEqual(save_tiktok_copy(source, day, "manual", root), exported)
            self.assertEqual(len(list(existing.parent.glob("*.mp4"))), 2)
