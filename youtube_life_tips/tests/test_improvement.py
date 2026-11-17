import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import codex_mailbox as m
import improvement as i
from reliability import atomic_json


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 15, tzinfo=m.KST)

    def test_budget_survives_candidate_change_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            cutoff = self.now + timedelta(hours=3)
            deadline = i.release_deadline(run, self.now, cutoff)
            child = run / "candidates/2"
            self.assertEqual(i.release_deadline(child, self.now + timedelta(minutes=50), cutoff), deadline)
            with self.assertRaisesRegex(i.ImprovementLimitReached, "time budget"):
                i.release_deadline(child, self.now + timedelta(minutes=60), cutoff)

    def test_scheduled_cutoff_is_stricter_than_total_time_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            cutoff = self.now + timedelta(minutes=10)
            self.assertEqual(i.release_deadline(Path(tmp), self.now, cutoff), cutoff)

    def test_image_budget_counts_failed_or_uncertain_calls_across_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for n in range(i.MAX_IMAGE_CALLS):
                target = run if n == 0 else run / "candidates/2"
                i.reserve_call(target, "developer-visual-repair-1", self.now, self.now + timedelta(hours=1))
            with self.assertRaisesRegex(i.ImprovementLimitReached, "image call"):
                i.reserve_call(run, "developer-image", self.now, self.now + timedelta(hours=1))
            state = json.loads(i.budget_path(run).read_text())
            self.assertEqual(state["codex_calls"], 5)
            self.assertEqual(state["image_calls"], 5)

    def test_codex_budget_rejects_before_starting_external_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for _ in range(i.MAX_CODEX_CALLS):
                i.reserve_call(run, "review", self.now, self.now + timedelta(hours=1))
            with patch.object(m, "now_kst", return_value=self.now), patch.object(m, "codex_executable") as exe:
                with self.assertRaisesRegex(i.ImprovementLimitReached, "Codex call"):
                    m.call_codex(run, run, "main-refine-1", "repair")
                exe.assert_not_called()

    def test_identical_failed_state_is_remembered_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            self.assertTrue(i.record_failure(run, "visual", {"issue": "wrong rim"}, "image-A"))
            self.assertFalse(i.record_failure(run, "visual", {"issue": "wrong rim"}, "image-A"))
            self.assertTrue(i.record_failure(run, "visual", {"issue": "wrong rim"}, "image-B"))

    def test_next_discovery_receives_actual_review_evidence_and_changed_search_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "work/daily/2026-11-17-pm"
            run = root / "work/mailbox/runs/2026-11-17-pm"
            atomic_json(daily / "content.json", {"topic": "rejected tip"})
            atomic_json(run / "review.json", {"practical_payoff_score": 2, "issues": ["no useful result"]})
            request = {"date": "2026-11-17", "slot": "pm"}
            self.assertTrue(m.prepare_next_candidate(request, "weak payoff", root))
            feedback = request["discovery_correction"]
            self.assertEqual(feedback["findings"]["review.json"]["practical_payoff_score"], 2)
            self.assertIn("Change search terms", " ".join(feedback["actions"]))

    def test_expired_release_returns_terminal_result_without_new_candidate_or_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "work/mailbox/runs/2026-11-17-pm"
            i.release_deadline(run, self.now, self.now + timedelta(hours=3))
            path = root / "request.json"
            atomic_json(path, {"date": "2026-11-17", "slot": "pm"})
            with patch.object(m, "now_kst", return_value=self.now + timedelta(minutes=61)), \
                 patch.object(m, "send_result_email", return_value=None), \
                 patch.object(m, "preflight") as preflight, patch.object(m, "call_codex") as codex:
                result = m.process_request(path, root)
            self.assertEqual(result["stage"], "improvement_limit")
            self.assertEqual(result["status"], "cancelled")
            preflight.assert_not_called()
            codex.assert_not_called()

    def test_expired_budget_does_not_schedule_another_transient_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "work/mailbox/runs/2026-11-17-pm"
            i.release_deadline(run, self.now, self.now + timedelta(hours=3))
            with patch.object(m, "now_kst", return_value=self.now + timedelta(minutes=60)), \
                 patch.object(m, "send_result_email", return_value=None):
                result = m.retry_report(self.now.date(), {"slot": "pm", "attempt": 1}, RuntimeError("HTTP 503"), root)
            self.assertEqual(result["status"], "failed")

    def test_service_failure_is_not_treated_as_an_editorial_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(m, "validate_plan"), patch("render_daily.validate_layout"), \
                 patch.object(m, "call_codex", side_effect=m.WorkflowSkipped("Codex quota unavailable")) as codex:
                with self.assertRaisesRegex(m.WorkflowSkipped, "quota"):
                    m.refine_editorial_plan({"scenes": []}, self.now.date(), root, root,
                                            {"review": "review", "main_approve": "repair"}, None)
            self.assertEqual(codex.call_count, 1)
            self.assertFalse((root / "editorial-feedback.json").exists())


if __name__ == "__main__":
    unittest.main()
