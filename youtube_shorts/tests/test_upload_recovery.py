"""Upload checkpoint/recovery tests with all remote mutations mocked."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_upload_ledger as check
import notify_result as notify
import recover_upload_receipt as recovery
import upload_short as uploader
import upload_ledger as ledger
from upload_ledger import save_state


class UploadCheckpointTests(unittest.TestCase):
    def setUp(self):
        media_patch = patch.object(uploader, "MediaFileUpload")
        media_patch.start()
        self.addCleanup(media_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "uploads.json"
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"x" * 2048)
        self.metadata = self.root / "metadata.json"
        self.metadata.write_text(json.dumps({"status": "ready", "date_kst": "2026-10-24",
                                             "title": "audit", "description": "audit", "tags": []}), encoding="utf-8")
        self.token = self.root / "token.json"
        self.token.write_text("{}", encoding="utf-8")
        self.argv = ["upload_short", str(self.video), str(self.metadata), "--token", str(self.token), "--state", str(self.state)]

    def tearDown(self):
        self.temp.cleanup()

    def test_intent_is_persisted_before_upload_and_receipt_after_upload(self):
        snapshots = []
        request = Mock()
        def execute(**kwargs):
            self.assertEqual(snapshots[0]["2026-10-24"]["status"], "uploading")
            self.assertEqual(kwargs, {"num_retries": 3})
            return {"id": "MOCK", "snippet": {"channelId": "UCLQczQnzBHzB8jOO0sMeP2w"}}
        request.execute.side_effect = execute
        client = Mock()
        client.videos.return_value.insert.return_value = request
        with patch.object(sys, "argv", self.argv), patch.object(uploader, "get_credentials"), \
             patch.object(uploader, "build", return_value=client), \
             patch.object(uploader, "persist", side_effect=lambda path: snapshots.append(json.loads(path.read_text(encoding="utf-8")))):
            uploader.main()
        self.assertEqual(snapshots[-1]["2026-10-24"]["video_id"], "MOCK")
        self.assertIs(client.videos.return_value.insert.call_args.kwargs["body"]["status"]["containsSyntheticMedia"], True)
        self.assertEqual(json.loads((self.root / "upload_receipt.json").read_text())["video_id"], "MOCK")

    def test_intent_push_failure_prevents_upload(self):
        client = Mock()
        with patch.object(sys, "argv", self.argv), patch.object(uploader, "get_credentials"), \
             patch.object(uploader, "build", return_value=client), \
             patch.object(uploader, "persist", side_effect=RuntimeError("push failed")), self.assertRaises(RuntimeError):
            uploader.main()
        client.videos.return_value.insert.return_value.execute.assert_not_called()

    def test_evening_upload_preserves_the_existing_morning_receipt(self):
        save_state(self.state, {"2026-10-24": {"video_id": "AM"}})
        metadata = json.loads(self.metadata.read_text(encoding="utf-8"))
        metadata.update(slot="pm", release_key="2026-10-24-pm")
        self.metadata.write_text(json.dumps(metadata), encoding="utf-8")
        client = Mock()
        client.videos.return_value.insert.return_value.execute.return_value = {"id": "PM"}
        with patch.object(sys, "argv", self.argv), patch.object(uploader, "get_credentials"), \
             patch.object(uploader, "build", return_value=client), patch.object(uploader, "persist"):
            uploader.main()
        records = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(records["2026-10-24"]["video_id"], "AM")
        self.assertEqual(records["2026-10-24-pm"]["video_id"], "PM")
        self.assertEqual(records["2026-10-24-pm"]["date_kst"], "2026-10-24")
        self.assertTrue(check.already_uploaded("2026-10-24-pm", self.state))
        self.assertIs(client.videos.return_value.insert.call_args.kwargs["body"]["status"]["containsSyntheticMedia"], True)

    def test_unknown_previous_upload_blocks_new_insert(self):
        save_state(self.state, {"2026-10-24": {"status": "uploading"}})
        with patch.object(sys, "argv", self.argv), patch.object(uploader, "build") as build, self.assertRaises(SystemExit):
            uploader.main()
        build.assert_not_called()
        with self.assertRaises(ValueError):
            check.already_uploaded("2026-10-24", self.state)

    def test_post_upload_push_failure_keeps_receipt(self):
        client = Mock()
        client.videos.return_value.insert.return_value.execute.return_value = {"id": "MOCK"}
        with patch.object(sys, "argv", self.argv), patch.object(uploader, "get_credentials"), \
             patch.object(uploader, "build", return_value=client), \
             patch.object(uploader, "persist", side_effect=[None, RuntimeError("push failed")]), self.assertRaises(RuntimeError):
            uploader.main()
        self.assertEqual(json.loads((self.root / "upload_receipt.json").read_text())["video_id"], "MOCK")
        self.assertTrue(check.already_uploaded("2026-10-24", self.state))

    def test_failure_email_preserves_uploaded_video_link(self):
        save_state(self.state, {"2026-10-24": {"video_id": "MOCK", "publish_at": "2026-10-24T07:00+09:00"}})
        message = notify.build_message("2026-10-24", "failure", "https://example.org/run", self.state)
        self.assertIn("https://youtube.com/shorts/MOCK", message.get_content())
        self.assertIn("failure", message.get_content())
        self.assertNotIn("완료되지 않았습니다", message.get_content())
        self.assertNotIn("???", message.get_content())

    def test_prior_artifact_restores_completed_receipt(self):
        day = "2026-10-24"
        intent = {"status": "uploading", "operation_id": "op", "channel_id": "UC-PIM"}
        save_state(self.state, {day: intent})
        receipt = {**intent, "date_kst": day, "status": "uploaded", "video_id": "MOCK"}
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("upload_receipt.json", json.dumps(receipt))
        listing = json.dumps({"artifacts": [{"name": f"pim-upload-receipt-{day}", "expired": False,
                                            "archive_download_url": "https://example.org/zip"}]}).encode()
        opener = Mock()
        responses = [io.BytesIO(listing), io.BytesIO(zipped.getvalue())]
        opener.open.side_effect = responses
        with patch.object(recovery, "STATE", self.state), patch.object(recovery, "persist") as persist, \
             patch.object(recovery.urllib.request, "build_opener", return_value=opener), \
             patch.dict(os.environ, {"GH_TOKEN": "mock", "GITHUB_REPOSITORY": "mock/repo"}):
            self.assertTrue(recovery.recover(day))
        self.assertEqual(json.loads(self.state.read_text())[day]["video_id"], "MOCK")
        persist.assert_called_once()

    def test_checkpoint_reaches_isolated_git_remote(self):
        remote = self.root / "remote.git"
        checkout = self.root / "checkout"
        def git(*args, cwd=None):
            return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout
        git("init", "--bare", str(remote))
        git("init", "-b", "main", str(checkout))
        git("config", "user.name", "audit", cwd=checkout)
        git("config", "user.email", "audit@example.invalid", cwd=checkout)
        path = checkout / "youtube_shorts/state/uploads.json"
        save_state(path, {})
        git("add", ".", cwd=checkout)
        git("commit", "-m", "initial", cwd=checkout)
        git("remote", "add", "origin", str(remote), cwd=checkout)
        git("push", "-u", "origin", "main", cwd=checkout)
        save_state(path, {"2026-10-24": {"status": "uploading"}})
        with patch.object(ledger, "ROOT", checkout), patch.dict(os.environ, {"PYM_PERSIST_LEDGER": "true"}):
            ledger.persist(path)
        saved = json.loads(git("--git-dir", str(remote), "show", "main:youtube_shorts/state/uploads.json"))
        self.assertEqual(saved["2026-10-24"]["status"], "uploading")


if __name__ == "__main__":
    unittest.main()
