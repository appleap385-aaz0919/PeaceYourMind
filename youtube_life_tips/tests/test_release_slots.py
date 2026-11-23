import json
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import codex_mailbox as m
from life_schedule import release_key
from reliability import atomic_json, read_receipt

DAY = date(2026, 10, 26)


class ReleaseSlotTests(unittest.TestCase):
    def test_rejected_candidates_preserve_media_and_stop_after_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "work/daily/2026-10-26-manual"
            folder.mkdir(parents=True)
            request = {"date": str(DAY), "slot": "manual", "attempt": 2}
            for number in (1, 2):
                atomic_json(folder / "content.json", {"topic": f"topic {number}"})
                (folder / "storyboard.png").write_bytes(bytes([number]))
                self.assertTrue(m.prepare_next_candidate(request, "bad visual", root))
                self.assertEqual(request["candidate_attempt"], number + 1)
                self.assertEqual(request["attempt"], 0)
                self.assertTrue((folder / f"rejected-candidates/{number}/storyboard.png").exists())
                self.assertFalse((folder / "storyboard.png").exists())
            self.assertFalse(m.prepare_next_candidate(request, "bad visual", root))
            self.assertEqual(len(request["rejected_candidates"]), 3)

    def test_third_final_rejection_is_cancelled_without_uploading(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, 12, tzinfo=m.KST)), \
             patch.object(m, "send_result_email", return_value=None), \
             patch.object(m, "preflight", side_effect=m.FinalReviewRejected("bad visual")), \
             patch.object(m.subprocess, "run") as external:
            root = Path(tmp)
            path = root / "request.json"
            atomic_json(path, {"date": str(DAY), "slot": "manual", "publish_now": True,
                               "candidate_attempt": 3})
            result = m.process_request(path, root)
            self.assertEqual(result["status"], "cancelled", result)
            self.assertEqual(result["candidate_attempts"], 3)
            external.assert_not_called()

    def test_budget_stop_records_current_failure_without_moving_an_upload_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "work/daily/2026-10-26-pm"
            atomic_json(folder / "upload_session.json", {"status": "pending"})
            atomic_json(folder / "content.json", {"topic": "selected tip"})
            (folder / "example.mp4").write_bytes(b"keep")
            request = {"date": str(DAY), "slot": "pm"}
            self.assertFalse(m.prepare_next_candidate(request, "release time budget exhausted", root, allow_next=False))
            self.assertEqual(request["rejected_candidates"][0]["topic"], "selected tip")
            self.assertTrue((folder / "upload_session.json").exists())
            self.assertEqual((folder / "example.mp4").read_bytes(), b"keep")
            self.assertNotIn("candidate_attempt", request)

    def test_main_rejection_tries_next_topic(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, 12, tzinfo=m.KST)), \
             patch.object(m, "send_result_email", return_value=None), \
             patch.object(m, "preflight"), \
             patch.object(m, "validate_plan"), \
             patch.object(m, "validate_review"), \
             patch.object(m, "call_codex", side_effect=m.FinalReviewRejected("third topic rejected")):
            root = Path(tmp)
            request_path = root / "request.json"
            atomic_json(request_path, {"date": str(DAY), "slot": "am", "publish_now": True,
                                       "candidate_attempt": 2, "rejected_candidates": [{"candidate": 1, "topic": "first"}]})
            second = root / "work/mailbox/runs/2026-10-26/candidates/2"
            atomic_json(second / "main-draft.json", {"topic": "duplicate second", "scenes": []})
            atomic_json(second / "review.json", {"approved": True})
            atomic_json(second / "main-approve.json", {"approved": False, "reason": "duplicate topic"})
            result = m.process_request(request_path, root)
            self.assertEqual(result["status"], "cancelled", result)
            saved = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["candidate_attempt"], 3)
            self.assertEqual(saved["rejected_candidates"][-2]["topic"], "duplicate second")

    def test_immediate_release_has_its_own_key_even_after_regular_failures(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight"):
            root = Path(tmp)
            for slot in ("am", "pm"):
                atomic_json(m.report_path(DAY, root, slot), {"status": "skipped"})
            result = m.enqueue_today(root, datetime(2026, 10, 26, 20, tzinfo=m.KST),
                                     publish_now=True, editorial_instruction="Exclude knitting")
            self.assertEqual(result["slot"], "manual")
            self.assertTrue(result["publish_now"])
            self.assertEqual(result["editorial_instruction"], "Exclude knitting")
            self.assertTrue((root / "work/mailbox/inbox/2026-10-26-manual.json").exists())

    def test_morning_success_does_not_block_evening_enqueue(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight"):
            root = Path(tmp)
            atomic_json(m.report_path(DAY, root), {"date": str(DAY), "status": "scheduled", "url": "AM"})
            result = m.enqueue_today(root, datetime(2026, 10, 26, 15, tzinfo=m.KST), slot="pm")
            self.assertEqual(result["status"], "pending")
            self.assertTrue((root / "work/mailbox/inbox/2026-10-26-pm.json").is_file())
            self.assertEqual(json.loads(m.report_path(DAY, root).read_text())["url"], "AM")

    def test_evening_cutoff_and_receipt_cannot_use_morning_slot(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "send_result_email", return_value=None):
            root = Path(tmp)
            result = m.enqueue_today(root, datetime(2026, 10, 26, 18, 30, tzinfo=m.KST), slot="pm")
            self.assertEqual(result["reason"], "missed_1830_kst_upload_cutoff")
            receipt = root / "receipt.json"
            atomic_json(receipt, {"date": str(DAY), "channel_id": "UC", "video_id": "AM"})
            with self.assertRaises(ValueError):
                read_receipt(receipt, str(DAY), "UC", "pm")

    def test_no_eligible_topic_researches_three_times_without_images_or_upload(self):
        for draft in (
            {"status": "no_eligible_topic", "reason": "All candidates repeat previous tips"},
            {"date": str(DAY), "topic": "No eligible topic", "hook": "", "title": "",
             "spoken_script": "", "scenes": [], "fallback_reason": "All candidates repeat previous tips"},
        ):
            with self.subTest(draft=draft), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                request = root / "request.json"
                atomic_json(request, {"date": str(DAY), "slot": "pm"})
                def stage(_root, run_dir, name, _prompt, **_kwargs):
                    path = run_dir / f"{name}.json"
                    atomic_json(path, draft)
                    return path
                with patch.object(m, "preflight"), patch.object(m, "send_result_email", return_value=None), \
                     patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, 15, tzinfo=m.KST)), \
                     patch.object(m, "call_codex", side_effect=stage) as codex, \
                     patch.object(m.subprocess, "run") as external:
                    result = m.process_request(request, root)
                self.assertEqual(result["status"], "skipped")
                self.assertIn("no_eligible_topic: All candidates repeat previous tips", result["reason"])
                self.assertEqual(result["stage"], "topic_selection")
                self.assertEqual(json.loads(request.read_text())["candidate_attempt"], 3)
                self.assertEqual(codex.call_count, 3)
                external.assert_not_called()

    def test_both_releases_run_with_separate_artifacts_and_receipts(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight"), \
             patch.object(m, "send_result_email", return_value="sent") as mail:
            root = Path(tmp)
            plan = {"date": str(DAY), "season": "가을", "topic_strategy": "seasonal", "topic": "tip",
                    "category_choice_reason": "식품과 의류를 비교함",
                    "hook": "hook", "title": "tip", "viewer_value": {
                        "common_approach": "a", "better_decision": "b", "why_it_matters": "c", "new_insight": "d",
                        "decision_points": [{"when": "first", "do": "check", "result": "known"},
                                            {"when": "second", "do": "act", "result": "resolved"}]},
                    "spoken_script": "text text text text",
                    "scenes": [{"narration": "text", "caption": "text", "visual_action": "show the action"} for _ in range(4)],
                    "sources": [{"title": "source", "url": "https://example.org"} for _ in range(2)]}
            def stage(root_arg, run_dir, name, prompt, **kwargs):
                daily = root / "work/daily" / run_dir.name
                result = plan
                if name == "main-refine-1" and run_dir.name.endswith("-pm"):
                    result = {**plan, "description": "Corrected source evidence and safety ordering."}
                if name == "review" or name.startswith("final-review"):
                    result = dict.fromkeys(("approved", "selection_rule_pass", "category_balance_pass", "originality_pass", "sources_verified",
                                            "safety_pass", "usefulness_pass", "novelty_pass", "density_pass", "flow_pass", "naturalness_pass"), True)
                    result.update(usefulness_reason="useful", novelty_reason="new", density_reason="two decisions", flow_reason="connected", naturalness_reason="spoken naturally",
                                  problem_relevance_score=4, practical_payoff_score=4, surprise_score=4, watch_worthiness_score=4,
                                  problem_relevance_reason="common", practical_payoff_reason="useful", surprise_reason="new",
                                  watch_worthiness_reason="worthwhile")
                elif name == "scene-direction":
                    result = {"feasible": True, "object_identity": "same object", "unresolved_risks": [],
                              "panels": [{"scene": i, "before_state": "before", "hand_action": "act",
                                  "orientation_and_contact": "hold", "after_state": "after", "continuity": "next",
                                  "critical_checks": ["actual result"], "incidental_details": []} for i in range(1, 5)]}
                    self.assertNotIn("Choose a DIFFERENT topic", prompt)
                elif name == "developer-image":
                    self.assertIn("scene-direction.json", prompt)
                    Image.new("RGB", (1086, 1448), "red" if run_dir.name.endswith("-pm") else "purple" if run_dir.name.endswith("-manual") else "blue").save(daily / "storyboard.png")
                    result = {"status": "ok", "built_in_imagegen_called": True}
                    if run_dir.name.endswith("-pm"):
                        result.update(status="failed", failure_reason="The saved panel shows a protrusion instead of a groove.")
                elif name == "developer-visual-repair-1":
                    Image.new("RGB", (1086, 1448), "green").save(daily / "storyboard-visual-repair-1.png")
                    result = {"status": "failed", "built_in_imagegen_edit_called": True,
                              "failure_reason": "Saved edit needs independent confirmation of the corrected panel."}
                elif name in {"main-audit", "main-audit-repair-1"}:
                    self.assertIn("imagegen-receipt.json", prompt)
                    result = {"approved": True, "checks": dict.fromkeys(("plan_matches_content", "sources_verified",
                        "season_decision_valid", "history_distinct", "viewer_value_valid", "viewer_pull_valid", "novelty_valid", "density_valid", "narration_flow_valid", "spoken_korean_valid",
                        "scenes_match_plan", "captions_readable", "no_visual_defects", "dimensions_valid",
                        "audio_present", "duration_valid"), True)}
                    if name == "main-audit" and run_dir.name.endswith("-pm"):
                        result["approved"] = False
                        result["checks"].update(scenes_match_plan=False, no_visual_defects=False,
                                                density_valid=False, viewer_pull_valid=False)
                        result["issues"] = ["An inaccurate panel makes the otherwise approved technique hard to follow."]
                if name == "review" or name.startswith("final-review"):
                    result.update(viewer_recap="ordered actions and outcomes", transition_checks=[
                        {"from_scene": i, "to_scene": i + 1, "clear": True, "evidence": "after the previous action"}
                        for i in range(1, 4)], scene_count=4)
                if name == "final-review-0" and run_dir.name.endswith("-pm"):
                    result.update(approved=False, sources_verified=False, safety_pass=False,
                                  issues=["Remove an inaccessible extra source and move the safety condition before the action; verify the corrected plan again."])
                path = run_dir / f"{name}.json"
                atomic_json(path, result)
                return path
            def external(args, **kwargs):
                slot = args[args.index("--slot") + 1]
                daily = root / "work/daily" / release_key(DAY, slot)
                if "render_daily.py" in str(args[1]):
                    self.assertEqual(json.loads((daily / "content.json").read_text(encoding="utf-8"))["slot"], slot)
                    (daily / f"life-tip-{DAY}.mp4").write_bytes(slot.encode())
                    atomic_json(daily / "metadata.json", {"narration_seconds": [1] * 4})
                else:
                    atomic_json(daily / "upload.json", {"date": str(DAY), "slot": slot,
                        "release_key": release_key(DAY, slot), "channel_id": "UC", "video_id": slot, "url": slot})
                return subprocess.CompletedProcess(args, 0, "", "")
            with patch.object(m, "call_codex", side_effect=stage), patch.object(m, "measure_narration_duration", return_value=75), \
                 patch.object(m.subprocess, "run", side_effect=external), \
                 patch.object(m, "make_render_contact_sheet", return_value=root / "contact.png"):
                for slot, hour in (("am", 3), ("pm", 15), ("manual", 23)):
                    request = root / f"{slot}.json"
                    atomic_json(request, {"date": str(DAY), "slot": slot, "render_only": slot == "manual"})
                    with patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, hour, tzinfo=m.KST)):
                        result = m.process_request(request, root)
                        self.assertEqual(result["status"], "rendered" if slot == "manual" else "scheduled", result)
                        if slot == "manual":
                            self.assertFalse((root / "work/daily" / release_key(DAY, slot) / "upload.json").exists())
                            continue
                        self.assertEqual(json.loads(request.read_text())["attempt"], 1)
                        self.assertNotIn("candidate_attempt", json.loads(request.read_text()))
                        self.assertEqual(result["url"], slot)
                        self.assertEqual((root / "tiktok_uploads" / str(DAY) /
                                          f"life-tip-{DAY}-{slot}.mp4").read_bytes(), slot.encode())
                        self.assertEqual(m.process_request(request, root)["url"], slot)
            self.assertEqual(mail.call_count, 3)
            self.assertTrue((root / "work/daily/2026-10-26-pm/repairs/before-visual-1/storyboard.png").exists())
            self.assertTrue((root / "work/mailbox/runs/2026-10-26-pm/main-audit-repair-1.json").exists())
            receipt = json.loads((root / "work/mailbox/runs/2026-10-26-pm/imagegen-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("groove", receipt["failure_reason"])

    def test_final_report_retains_video_failure_when_last_discovery_fails(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight"), \
             patch.object(m, "send_result_email", return_value=None), \
             patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, 15, tzinfo=m.KST)):
            root = Path(tmp)
            request = root / "request.json"
            atomic_json(request, {"date": str(DAY), "slot": "pm", "candidate_attempt": 3,
                                 "rejected_candidates": [{"candidate": 1, "stage": "topic_selection"},
                                     {"candidate": 2, "stage": "final_review", "topic": "wire hanger",
                                      "reason": "invented joint", "video_created": True}]})
            def stage(_root, run_dir, name, prompt, **kwargs):
                self.assertEqual(name, "main-draft")
                self.assertIn("Choose a DIFFERENT topic", prompt)
                path = run_dir / f"{name}.json"
                atomic_json(path, {"status": "no_eligible_topic", "reason": "no new supported result"})
                return path
            with patch.object(m, "call_codex", side_effect=stage), patch.object(m.subprocess, "run") as external:
                result = m.process_request(request, root)
            self.assertEqual(result["status"], "cancelled", result)
            self.assertEqual(result["stage"], "final_review")
            self.assertEqual(result["last_failure_stage"], "topic_selection")
            self.assertEqual(len(result["candidate_results"]), 3)
            self.assertEqual(result["candidate_results"][1]["reason"], "invented joint")
            external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
