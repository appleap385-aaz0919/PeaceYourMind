from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import codex_mailbox


class CodexFailureTests(unittest.TestCase):
    def test_uncertain_visual_edit_is_not_generated_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            daily = root / "daily"
            run.mkdir()
            daily.mkdir()
            (run / "developer-visual-repair-1-attempt.json").write_text("{}")
            with patch.object(codex_mailbox, "call_codex") as stage:
                with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "uncertain"):
                    codex_mailbox.repair_storyboard(root, run, daily, {}, 1)
                stage.assert_not_called()
            with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "at most two"):
                codex_mailbox.repair_storyboard(root, run, daily, {}, 3)

    def test_failed_visual_edit_keeps_the_original_art(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            daily = root / "daily"
            run.mkdir()
            daily.mkdir()
            (daily / "storyboard.png").write_bytes(b"original-art")
            def stage(_root, target, name, _prompt, **_kwargs):
                path = target / f"{name}.json"
                codex_mailbox.atomic_json(path, {"status": "failed", "failure_reason": "ImageGen unavailable"})
                return path
            with patch.object(codex_mailbox, "call_codex", side_effect=stage):
                with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "ImageGen unavailable"):
                    codex_mailbox.repair_storyboard(root, run, daily, {}, 1)
            self.assertEqual((daily / "storyboard.png").read_bytes(), b"original-art")
            self.assertEqual((daily / "repairs/before-visual-1/storyboard.png").read_bytes(), b"original-art")

    def test_version_probe_is_reused_until_the_executable_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "codex.exe"
            exe.write_bytes(b"first")
            result = subprocess.CompletedProcess([], 0, "codex-cli test", "")
            with patch.dict(codex_mailbox.os.environ, {"LIFETIPS_CODEX_EXE": str(exe)}), \
                 patch.object(codex_mailbox, "_verified_codex_files", set()), \
                 patch.object(codex_mailbox.subprocess, "run", return_value=result) as run:
                self.assertEqual(codex_mailbox.codex_executable(), exe)
                self.assertEqual(codex_mailbox.codex_executable(), exe)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.kwargs["timeout"], 60)
                exe.write_bytes(b"updated executable")
                self.assertEqual(codex_mailbox.codex_executable(), exe)
                self.assertEqual(run.call_count, 2)

    def test_usage_error_reports_actual_event_instead_of_printed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = json.dumps({"type": "error", "message": "You've hit your usage limit. Try later."})
            result = subprocess.CompletedProcess([], 1, output, "printed source code")
            with patch.object(codex_mailbox, "codex_executable", return_value=root / "codex.exe"), \
                 patch.object(codex_mailbox.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "main-draft: You've hit your usage limit"):
                    codex_mailbox.call_codex(root, root / "run", "main-draft", "draft")


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
            "category_choice_reason": "식품과 의류 후보를 비교해 더 유용한 방법을 선택함",
            "viewer_value": {
                "common_approach": "얼룩을 힘주어 문지른다",
                "better_decision": "물로 불린 뒤 닦는다",
                "why_it_matters": "얼룩을 쉽게 제거할 수 있다",
                "new_insight": "얼룩의 종류에 따라 세척법을 바꾼다",
                "decision_points": [
                    {"when": "얼룩이 말랐을 때", "do": "먼저 불린다", "result": "문지르는 힘이 줄어든다"},
                    {"when": "얼룩이 불었을 때", "do": "부드럽게 닦는다", "result": "섬유 손상을 줄인다"},
                ],
            },
            "hook": "바로 써보세요",
            "title": "생활 팁 #Shorts",
            "spoken_script": "설명 설명 설명 설명",
            "scenes": [{"narration": "설명", "caption": "설명", "visual_action": "설명에 맞는 행동"} for _ in range(4)],
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
            self.make_plan(day, "evergreen_fallback", fallback_reason="유용한 계절 팁을 두 출처에서 확인하지 못함"),
            day,
        )

    def test_plan_requires_a_specific_viewer_decision(self) -> None:
        day = date(2026, 10, 22)
        plan = self.make_plan(day, "seasonal")
        del plan["viewer_value"]["new_insight"]
        with self.assertRaisesRegex(ValueError, "concrete new decision"):
            codex_mailbox.validate_plan(plan, day)
        plan["viewer_value"] = {"common_approach": "냉장 보관", "better_decision": "", "why_it_matters": "신선도"}
        with self.assertRaisesRegex(ValueError, "concrete new decision"):
            codex_mailbox.validate_plan(plan, day)
        plan["viewer_value"]["better_decision"] = None
        with self.assertRaisesRegex(ValueError, "concrete new decision"):
            codex_mailbox.validate_plan(plan, day)

    def test_plan_accepts_one_complete_result_but_requires_a_decision(self) -> None:
        day = date(2026, 10, 22)
        plan = self.make_plan(day, "seasonal")
        plan["viewer_value"]["decision_points"] = [{
            "when": "칠하지 않은 통원목에 눌린 자국이 생기면",
            "do": "젖은 천과 다리미로 조금씩 가열한다",
            "result": "눌린 섬유를 부풀려 주변을 깎아내는 수고를 줄인다",
        }]
        codex_mailbox.validate_plan(plan, day)
        plan["viewer_value"]["decision_points"] = []
        with self.assertRaisesRegex(ValueError, "one to three"):
            codex_mailbox.validate_plan(plan, day)
        plan["viewer_value"]["decision_points"] = [{"when": "찍혔을 때", "do": "", "result": "복원"}]
        with self.assertRaisesRegex(ValueError, "one to three"):
            codex_mailbox.validate_plan(plan, day)

    def test_review_requires_usefulness_and_narration_flow(self) -> None:
        review = {
            "approved": True, "selection_rule_pass": True, "category_balance_pass": True, "originality_pass": True,
            "sources_verified": True, "safety_pass": True,
            "usefulness_pass": False, "novelty_pass": True, "density_pass": True, "flow_pass": True,
            "naturalness_pass": True,
            "usefulness_reason": "냉장고에 넣으라는 일반적인 조언뿐이다",
            "novelty_reason": "새로운 판단이 있다",
            "density_reason": "서로 다른 두 판단이 있다",
            "flow_reason": "네 장면이 자연스럽게 이어진다",
            "naturalness_reason": "일상적인 구어체로 소리 내 읽기 쉽다",
            "problem_relevance_score": 4,
            "practical_payoff_score": 4,
            "surprise_score": 4,
            "watch_worthiness_score": 4,
            "problem_relevance_reason": "많은 시청자가 겪는다",
            "practical_payoff_reason": "실패를 막는다",
            "surprise_reason": "근거가 행동을 바꾼다",
            "watch_worthiness_reason": "바로 적용할 수 있다",
            "viewer_recap": "먼저 세탁하고 말린 뒤 물을 뿌려 결과를 확인한다",
            "scene_count": 4,
            "transition_checks": [{"from_scene": i, "to_scene": i + 1, "clear": True, "evidence": "앞 행동을 끝낸 뒤 다음 행동을 한다"} for i in range(1, 4)],
        }
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)
        review["usefulness_pass"] = True
        review["flow_pass"] = False
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)
        review["flow_pass"] = True
        codex_mailbox.validate_review(review)
        for required_check in ("safety_pass", "sources_verified"):
            review[required_check] = False
            with self.subTest(required_check=required_check), self.assertRaises(codex_mailbox.WorkflowSkipped):
                codex_mailbox.validate_review(review)
            review[required_check] = True
        review["surprise_score"] = 3
        with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "at least 4 of 5"):
            codex_mailbox.validate_review(review, 4)
        review["surprise_score"] = 4
        review["scene_count"] = 5
        with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "scene_count must match"):
            codex_mailbox.validate_review(review, 4)
        review["scene_count"] = 4
        review["density_pass"] = False
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)
        review["density_pass"] = True
        review["novelty_pass"] = False
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)
        review["novelty_pass"] = True
        review["novelty_reason"] = None
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)
        review["novelty_reason"] = "새로운 판단이 있다"
        review["usefulness_reason"] = None
        with self.assertRaises(codex_mailbox.WorkflowSkipped):
            codex_mailbox.validate_review(review)

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
        self.assertIn("portrait 3:4", prompts["developer_image"])
        self.assertIn("regardless of row count", prompts["developer_image"])
        self.assertIn("water above and covering the entire soil mass", prompts["developer_image"])
        self.assertIn("watch_worthiness_score", prompts["review"])
        self.assertIn("at least 4 on every axis", prompts["main_draft"])
        self.assertIn("content.json", prompts["main_audit"])
        self.assertIn("usefulness_pass", prompts["review"])
        self.assertIn("novelty_pass", prompts["review"])
        self.assertIn("density_pass", prompts["review"])
        self.assertIn("20-second compression test", prompts["main_draft"])
        self.assertIn("flow_pass", prompts["review"])
        self.assertIn("naturalness_pass", prompts["review"])
        self.assertIn("spoken_korean_valid", prompts["main_audit"])
        self.assertIn("category_balance_pass", prompts["review"])
        self.assertIn("three candidate tips from different household categories", prompts["main_draft"])
        self.assertIn("creator videos, practitioner", prompts["main_draft"])
        self.assertIn("Separate discovery from verification", prompts["main_draft"])
        self.assertIn("substantial original educational value", prompts["main_draft"])
        self.assertIn("two independent viewer-side signals", prompts["main_draft"])
        self.assertIn("read the label/manual and follow its instructions", prompts["main_draft"])
        self.assertIn("sources are independent", prompts["review"])
        self.assertIn("two independent viewer-side signals", prompts["review"])
        self.assertIn("Attribution is not permission", prompts["review"])
        self.assertIn("viewer_value_valid", prompts["main_audit"])
        self.assertIn("novelty_valid", prompts["main_audit"])
        self.assertIn("density_valid", prompts["main_audit"])
        self.assertIn("narration_flow_valid", prompts["main_audit"])

    def test_narrow_six_row_output_is_rejected_and_working_portrait_width_is_accepted(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            day_dir = root / "work" / "daily" / "2026-11-09"
            day_dir.mkdir(parents=True)
            image_path = day_dir / "storyboard.png"
            Image.new("RGB", (733, 2146), color="navy").save(image_path)
            with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "high-resolution portrait grid"):
                codex_mailbox.validate_new_storyboard(image_path, day_dir, root)
            Image.new("RGB", (887, 1774), color="navy").save(image_path)
            self.assertEqual(len(codex_mailbox.validate_new_storyboard(image_path, day_dir, root)), 64)
            Image.new("RGB", (1086, 1448), color="navy").save(image_path)
            self.assertEqual(len(codex_mailbox.validate_new_storyboard(image_path, day_dir, root)), 64)
            Image.new("RGB", (1280, 1280), color="navy").save(image_path)
            with self.assertRaisesRegex(codex_mailbox.WorkflowSkipped, "high-resolution portrait grid"):
                codex_mailbox.validate_new_storyboard(image_path, day_dir, root)

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
