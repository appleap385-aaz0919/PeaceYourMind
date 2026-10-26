"""Fault-injection checks: no real network, image generation, uploads, or email."""
import json
import argparse
import contextlib
import io
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import codex_mailbox as m
import resumable_upload as r
import upload_daily as uploader
from reliability import RetryableError, atomic_json, file_lock, read_receipt

DAY = date(2026, 10, 24)
NOW = datetime(2026, 10, 24, 3, 0, tzinfo=m.KST)


class ResumableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / DAY.isoformat()
        self.root.mkdir()
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"abcdefgh")
        self.context = {"date": DAY.isoformat(), "channel_id": "UC-LIFE"}

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, api):
        return r.upload(self.video, {}, "mock", api_call=api, chunk_size=4,
                        session_path=self.root / "upload_session.json", receipt_context=self.context)

    @patch("resumable_upload.time.sleep")
    def test_partial_ack_uses_server_offset(self, _sleep):
        with patch("upload_daily.api_call", side_effect=[
            (200, {"Location": "https://www.googleapis.com/upload/mock"}, b""),
            (308, {"Range": "bytes=0-1"}, b""),
            (308, {"Range": "bytes=0-5"}, b""),
            (201, {}, b'{"id":"MOCK"}'),
        ]) as api:
            self.assertEqual(self.upload(api)["id"], "MOCK")
        self.assertEqual(api.call_args_list[2].args[0].get_header("Content-range"), "bytes 2-5/8")
        self.assertEqual(api.call_args_list[2].args[0].data, b"cdef")

    @patch("resumable_upload.time.sleep")
    def test_lost_completion_response_queries_same_session(self, _sleep):
        with patch("upload_daily.api_call", side_effect=[
            (200, {"Location": "https://www.googleapis.com/upload/mock"}, b""),
            TimeoutError("timed out"), (200, {}, b'{"id":"MOCK"}'),
        ]) as api:
            self.assertEqual(self.upload(api)["id"], "MOCK")
        self.assertEqual(api.call_args_list[2].args[0].get_header("Content-range"), "bytes */8")
        self.assertEqual(sum(call.args[0].method == "POST" for call in api.call_args_list), 1)
        receipt = r.recovered_receipt(self.root)
        self.assertEqual(receipt["video_id"], "MOCK")

    @patch("resumable_upload.time.sleep")
    def test_restart_queries_saved_session_without_new_post(self, _sleep):
        atomic_json(self.root / "upload_session.json", {
            "url": "https://www.googleapis.com/upload/mock", "fingerprint": r.fingerprint(self.video, {}),
            "receipt_context": self.context,
        })
        with patch("upload_daily.api_call", side_effect=[(308, {"range": "bytes=0-3"}, b""),
                                                       (200, {}, b'{"id":"MOCK"}')]) as api:
            self.upload(api)
        self.assertTrue(all(call.args[0].method == "PUT" for call in api.call_args_list))
        self.assertEqual(api.call_args_list[1].args[0].data, b"efgh")

    def test_changed_content_never_starts_second_session(self):
        atomic_json(self.root / "upload_session.json", {"fingerprint": "old", "receipt_context": self.context})
        with patch("upload_daily.api_call") as api, self.assertRaises(ValueError):
            self.upload(api)
        api.assert_not_called()

    @patch("resumable_upload.time.sleep")
    def test_repeated_server_errors_are_bounded_and_keep_session(self, _sleep):
        with patch("upload_daily.api_call", side_effect=[
            (200, {"Location": "https://www.googleapis.com/upload/mock"}, b""),
            *[RuntimeError("HTTP 503") for _ in range(4)],
        ]) as api, self.assertRaises(RetryableError):
            self.upload(api)
        self.assertEqual(api.call_count, 5)
        self.assertTrue((self.root / "upload_session.json").exists())

    def test_expired_session_fails_closed(self):
        atomic_json(self.root / "upload_session.json", {
            "url": "https://www.googleapis.com/upload/mock", "fingerprint": r.fingerprint(self.video, {}),
            "receipt_context": self.context,
        })
        with patch("upload_daily.api_call", side_effect=RuntimeError("HTTP 404")) as api, self.assertRaises(RuntimeError):
            self.upload(api)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args[0].method, "PUT")

    def test_invalid_receipt_is_not_treated_as_success(self):
        path = self.root / "upload.json"
        atomic_json(path, {"date": DAY.isoformat()})
        with self.assertRaises(ValueError):
            read_receipt(path, DAY.isoformat())

    def test_upload_lock_prevents_second_uploader(self):
        with file_lock(self.root / "upload.lock"):
            with self.assertRaises(OSError), file_lock(self.root / "upload.lock"):
                pass

    def test_unicode_title_cannot_fail_after_successful_upload(self):
        (self.root / f"life-tip-{DAY}.mp4").write_bytes(b"mock-video")
        atomic_json(self.root / "metadata.json", {
            "date": str(DAY), "title": "Tip 🍀 #Shorts", "description": "audit", "sources": ["audit"],
            "width": 720, "height": 1280, "duration_seconds": 20,
        })
        output = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")
        with patch.object(uploader, "WORK", self.root.parent), \
             patch.object(uploader, "load_local_config", return_value={"youtube_channel_id": "UC-LIFE"}), \
             patch.object(uploader, "load_oauth_client", return_value={}), \
             patch.object(uploader, "get_access_token", return_value="mock"), \
             patch.object(uploader, "validate_channel"), patch.object(uploader, "validate_publish_window"), \
             patch.object(uploader, "upload_resumable", return_value={"id": "MOCK"}), \
             contextlib.redirect_stdout(output):
            uploader.upload_day(DAY, argparse.Namespace(publish_at_kst=None, dry_run=False))
        self.assertEqual(read_receipt(self.root / "upload.json", str(DAY))["video_id"], "MOCK")


class MailboxRecoveryTests(unittest.TestCase):
    def test_transient_preflight_is_queued_for_watcher_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight", side_effect=TimeoutError()):
            root = Path(tmp)
            result = m.enqueue_today(root, at=NOW)
            self.assertEqual(result["status"], "pending")
            self.assertTrue((root / "work/mailbox/inbox" / f"{DAY}.json").exists())

    def test_success_survives_too_close_one_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(m.report_path(DAY, root), {"date": str(DAY), "status": "scheduled", "url": "original"})
            result = m.enqueue_today(root, at=NOW, publish_at_kst="2026-10-24T03:05")
            self.assertEqual(result["status"], "scheduled")
            self.assertEqual(result["url"], "original")

    def test_receipt_overrides_failed_report_on_recovery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "send_result_email", return_value=None):
            root = Path(tmp)
            atomic_json(root / "work/mailbox/processing" / f"{DAY}.json", {"date": str(DAY)})
            atomic_json(m.report_path(DAY, root), {"date": str(DAY), "status": "failed"})
            atomic_json(root / "work/daily" / str(DAY) / "upload.json", {
                "date": str(DAY), "video_id": "MOCK", "channel_id": "UC-LIFE", "url": "saved",
            })
            m.recover_processing_requests(root)
            report = json.loads(m.report_path(DAY, root).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "scheduled")
            self.assertEqual(report["url"], "saved")

    def test_retry_limit_and_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "now_kst", return_value=NOW):
            root = Path(tmp)
            pending = m.retry_report(DAY, {"attempt": 1}, TimeoutError(), root)
            self.assertEqual(pending["status"], "retry_pending")
            failed = m.retry_report(DAY, {"attempt": 3}, TimeoutError(), root)
            self.assertEqual(failed["status"], "failed")
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "now_kst", return_value=NOW.replace(hour=6, minute=29, second=30)):
            self.assertEqual(m.retry_report(DAY, {"attempt": 1}, TimeoutError(), Path(tmp))["status"], "failed")

    def test_restart_preserves_pending_retry_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "now_kst", return_value=NOW):
            root = Path(tmp)
            atomic_json(root / "work/mailbox/processing" / f"{DAY}.json", {"date": str(DAY), "attempt": 1})
            m.retry_report(DAY, {"attempt": 1}, TimeoutError(), root)
            m.recover_processing_requests(root)
            request = root / "work/mailbox/inbox" / f"{DAY}.json"
            self.assertEqual(json.loads(request.read_text())["attempt"], 1)

    def test_stage_timeout_respects_remaining_time(self):
        with patch.object(m, "now_kst", return_value=NOW):
            self.assertEqual(m.stage_timeout(NOW + timedelta(seconds=30), 900), 30)
            with self.assertRaises(m.WorkflowSkipped):
                m.stage_timeout(NOW, 900)

    def test_image_attempt_is_not_repeated_after_timeout(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "codex_executable", return_value=Path("mock.exe")), \
             patch.object(m.subprocess, "run", side_effect=subprocess.TimeoutExpired("mock", 900)) as run:
            root = Path(tmp)
            with self.assertRaises(m.WorkflowSkipped):
                m.call_codex(root, root / "runs", "developer-image", "mock")
            with self.assertRaises(m.WorkflowSkipped):
                m.call_codex(root, root / "runs", "developer-image", "mock")
            self.assertEqual(run.call_count, 1)

    def test_successful_stages_are_reused_after_upload_failure(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "now_kst", return_value=NOW) as clock, \
             patch.object(m, "preflight"), patch.object(m, "send_result_email", return_value=None):
            root = Path(tmp)
            run_dir = root / "work/mailbox/runs" / str(DAY)
            daily = root / "work/daily" / str(DAY)
            request = root / "request.json"
            atomic_json(request, {"date": str(DAY)})
            stages, renders, uploads = [], [], []
            plan = {"date": str(DAY), "season": "가을", "topic_strategy": "seasonal", "topic": "tip",
                    "viewer_value": {
                        "common_approach": "문지르기", "better_decision": "불린 뒤 닦기", "why_it_matters": "쉽게 닦기",
                    },
                    "hook": "hook", "title": "tip #Shorts", "scenes": [{"narration": "text", "caption": "text"} for _ in range(4)],
                    "sources": [{"title": "source", "url": "https://example.org"} for _ in range(2)]}
            def stage(root_arg, run_arg, name, prompt, **kwargs):
                stages.append(name)
                result = plan
                if name == "review":
                    result = dict.fromkeys(["approved", "selection_rule_pass", "originality_pass", "sources_verified", "safety_pass", "usefulness_pass", "flow_pass"], True)
                    result.update({"usefulness_reason": "새 행동을 알려준다", "flow_reason": "장면이 자연스럽게 이어진다"})
                if name == "developer-image":
                    Image.new("RGB", (900, 1400), "blue").save(daily / "storyboard.png")
                    result = {"status": "ok", "built_in_imagegen_called": True}
                if name == "main-audit":
                    keys = ["plan_matches_content", "sources_verified", "season_decision_valid", "history_distinct", "viewer_value_valid", "narration_flow_valid", "four_scenes_match_plan", "captions_readable", "no_visual_defects", "dimensions_valid", "audio_present", "duration_valid"]
                    result = {"approved": True, "checks": dict.fromkeys(keys, True)}
                path = run_arg / f"{name}.json"
                atomic_json(path, result)
                return path
            def external(args, **kwargs):
                if "render_daily.py" in str(args[1]):
                    renders.append(args)
                    (daily / f"life-tip-{DAY}.mp4").write_bytes(b"mock-video")
                    atomic_json(daily / "metadata.json", {"narration_seconds": [1] * 4})
                else:
                    uploads.append(args)
                    self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")
                    if len(uploads) == 1:
                        return subprocess.CompletedProcess(args, 1, "", "HTTP 503 temporarily unavailable")
                    atomic_json(daily / "upload.json", {"date": str(DAY), "channel_id": "UC-LIFE", "video_id": "MOCK", "url": "saved"})
                return subprocess.CompletedProcess(args, 0, "", "")
            with patch.object(m, "call_codex", side_effect=stage), patch.object(m.subprocess, "run", side_effect=external), \
                 patch.object(m, "make_render_contact_sheet", return_value=daily / "contact.png"):
                self.assertEqual(m.process_request(request, root)["status"], "retry_pending")
                clock.return_value = NOW + timedelta(minutes=2)
                self.assertEqual(m.process_request(request, root)["status"], "scheduled")
            self.assertEqual(len(renders), 1)
            self.assertEqual(stages.count("developer-image"), 1)
            self.assertEqual(stages.count("main-audit"), 1)
            self.assertEqual(len(uploads), 2)


if __name__ == "__main__":
    unittest.main()
