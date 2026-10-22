from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import codex_mailbox


class KoreanSeasonTests(unittest.TestCase):
    def test_korean_months_map_to_expected_seasons(self) -> None:
        self.assertEqual(codex_mailbox.season_for(date(2026, 3, 1)), "봄")
        self.assertEqual(codex_mailbox.season_for(date(2026, 6, 1)), "여름")
        self.assertEqual(codex_mailbox.season_for(date(2026, 9, 1)), "가을")
        self.assertEqual(codex_mailbox.season_for(date(2026, 12, 1)), "겨울")
        self.assertEqual(codex_mailbox.season_for(date(2026, 2, 1)), "겨울")

    def make_plan(self, day: date, strategy: str, **extra: object) -> dict[str, object]:
        return {
            "date": day.isoformat(),
            "season": codex_mailbox.season_for(day),
            "topic_strategy": strategy,
            "topic": "계절 생활 팁",
            "hook": "바로 써보세요",
            "title": "생활 팁 #Shorts",
            "scenes": [{"narration": "설명", "caption": "설명"} for _ in range(4)],
            "sources": [
                {"title": "기관 안내 1", "url": "https://example.org/1"},
                {"title": "기관 안내 2", "url": "https://example.org/2"},
            ],
            **extra,
        }

    def test_seasonal_plan_is_accepted_for_current_season(self) -> None:
        day = date(2026, 10, 22)
        codex_mailbox.validate_plan(self.make_plan(day, "seasonal"), day)

    def test_evergreen_fallback_requires_reason(self) -> None:
        day = date(2026, 10, 22)
        with self.assertRaisesRegex(ValueError, "fallback requires a reason"):
            codex_mailbox.validate_plan(self.make_plan(day, "evergreen_fallback"), day)
        codex_mailbox.validate_plan(
            self.make_plan(day, "evergreen_fallback", fallback_reason="계절 자료 두 곳에서 확인하지 못함"),
            day,
        )

    def test_plan_must_record_the_current_korean_season(self) -> None:
        day = date(2026, 10, 22)
        plan = self.make_plan(day, "seasonal")
        plan["season"] = "여름"
        with self.assertRaisesRegex(ValueError, "current Korean season"):
            codex_mailbox.validate_plan(plan, day)


class PromptConstructionTests(unittest.TestCase):
    def test_prompts_build_before_stage_files_exist(self) -> None:
        day = date(2026, 10, 23)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "work" / "mailbox" / "runs" / day.isoformat()
            day_dir = root / "work" / "daily" / day.isoformat()
            prompts = codex_mailbox.build_prompts(day, run_dir, day_dir)
        self.assertIn("draft.json", prompts["review"])
        self.assertIn("draft.json", prompts["main_approve"])
        self.assertIn("approved.json", prompts["developer_image"])
        self.assertIn("content.json", prompts["main_audit"])

    def test_storyboard_validator_does_not_compare_the_image_to_itself(self) -> None:
        from PIL import Image

        day = date(2026, 10, 23)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            day_dir = root / "work" / "daily" / day.isoformat()
            day_dir.mkdir(parents=True)
            image_path = day_dir / "storyboard.png"
            Image.new("RGB", (900, 1400), color="blue").save(image_path)
            digest = codex_mailbox.validate_new_storyboard(image_path, day_dir, root)
        self.assertEqual(len(digest), 64)


class MailboxQueueTests(unittest.TestCase):
    def test_final_report_sends_email_but_pending_report_does_not(self) -> None:
        day = date(2026, 10, 22)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = root / "state"
            state.mkdir()
            (state / "config.local.json").write_text(json.dumps({
                "email_notifications": {"enabled": True},
            }), encoding="utf-8")
            (root / "send_result_email.ps1").write_text("", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, "Email sent.", "")
            with patch("codex_mailbox.subprocess.run", return_value=completed) as run:
                pending = codex_mailbox.write_report(day, "pending", "enqueue", root=root)
                self.assertNotIn("email_notification", pending)
                self.assertEqual(run.call_count, 0)
                final = codex_mailbox.write_report(day, "scheduled", "complete", root=root)
            self.assertEqual(final["email_notification"], "sent")
            self.assertEqual(run.call_count, 1)

    def test_missed_cutoff_writes_skip_report_without_preflight(self) -> None:
        day = date(2026, 10, 22)
        current = datetime(2026, 10, 22, 6, 30, tzinfo=codex_mailbox.KST)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(codex_mailbox, "preflight", side_effect=AssertionError("must not run")):
                result = codex_mailbox.enqueue_today(root=root, at=current)
            self.assertEqual(result["status"], "skipped")
            saved = json.loads(codex_mailbox.report_path(day, root).read_text(encoding="utf-8"))
            self.assertEqual(saved["reason"], "missed_0630_kst_upload_cutoff")

    def test_enqueue_is_idempotent_for_existing_report(self) -> None:
        day = date(2026, 10, 22)
        current = datetime(2026, 10, 22, 5, 0, tzinfo=codex_mailbox.KST)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_mailbox.atomic_json(codex_mailbox.report_path(day, root), {"date": day.isoformat(), "status": "skipped"})
            with patch.object(codex_mailbox, "preflight", side_effect=AssertionError("must not run")):
                result = codex_mailbox.enqueue_today(root=root, at=current)
            self.assertEqual(result["status"], "skipped")

    def test_one_off_enqueue_retries_only_a_missed_routine_cutoff(self) -> None:
        day = date(2026, 10, 23)
        current = datetime(2026, 10, 23, 7, 0, tzinfo=codex_mailbox.KST)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = codex_mailbox.report_path(day, root)
            codex_mailbox.atomic_json(report, {
                "date": day.isoformat(), "status": "skipped", "reason": "missed_0630_kst_upload_cutoff",
            })
            with patch.object(codex_mailbox, "preflight", return_value=("UC-LIFE", "07:00")):
                result = codex_mailbox.enqueue_today(
                    root=root, at=current, publish_at_kst="2026-10-23T08:30",
                )
            self.assertEqual(result["status"], "pending")
            self.assertEqual(result["publish_at_kst"], "2026-10-23T08:30+09:00")
            self.assertFalse(report.exists())
            self.assertTrue((report.parent / "history" / "2026-10-23-missed-routine-cutoff.json").is_file())

    def test_one_off_enqueue_rejects_release_with_too_little_lead(self) -> None:
        day = date(2026, 10, 23)
        current = datetime(2026, 10, 23, 8, 16, tzinfo=codex_mailbox.KST)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = codex_mailbox.enqueue_today(
                root=Path(temp_dir), at=current, publish_at_kst="2026-10-23T08:30",
            )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "one_off_release_has_less_than_15_minutes_lead_time")

    def test_later_one_off_can_replace_a_previously_too_close_release(self) -> None:
        day = date(2026, 10, 23)
        current = datetime(2026, 10, 23, 8, 19, tzinfo=codex_mailbox.KST)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = codex_mailbox.report_path(day, root)
            codex_mailbox.atomic_json(report, {
                "date": day.isoformat(), "status": "skipped",
                "reason": "one_off_release_has_less_than_15_minutes_lead_time",
            })
            with patch.object(codex_mailbox, "preflight", return_value=("UC-LIFE", "07:00")):
                result = codex_mailbox.enqueue_today(
                    root=root, at=current, publish_at_kst="2026-10-23T08:50",
                )
            self.assertEqual(result["status"], "pending")
            self.assertEqual(result["publish_at_kst"], "2026-10-23T08:50+09:00")

    def test_recover_processing_moves_unreported_request_back_to_inbox(self) -> None:
        day = date(2026, 10, 23)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processing = root / "work" / "mailbox" / "processing"
            processing.mkdir(parents=True)
            request = processing / f"{day.isoformat()}.json"
            request.write_text(json.dumps({"date": day.isoformat()}), encoding="utf-8")
            codex_mailbox.recover_processing_requests(root)
            self.assertFalse(request.exists())
            self.assertTrue((root / "work" / "mailbox" / "inbox" / request.name).is_file())

    def test_recover_processing_archives_request_with_existing_report(self) -> None:
        day = date(2026, 10, 23)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processing = root / "work" / "mailbox" / "processing"
            processing.mkdir(parents=True)
            request = processing / f"{day.isoformat()}.json"
            request.write_text(json.dumps({"date": day.isoformat()}), encoding="utf-8")
            codex_mailbox.atomic_json(codex_mailbox.report_path(day, root), {"date": day.isoformat(), "status": "skipped"})
            codex_mailbox.recover_processing_requests(root)
            self.assertFalse(request.exists())
            self.assertTrue((root / "work" / "mailbox" / "archive" / request.name).is_file())


if __name__ == "__main__":
    unittest.main()
