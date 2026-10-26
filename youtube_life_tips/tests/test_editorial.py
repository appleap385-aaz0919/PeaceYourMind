import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from editorial import validate_script, validate_comprehension
from render_daily import checked_text_lines, fitted_text, fonts, overlay_for_scene, validate_layout
import codex_mailbox as mailbox
from reliability import atomic_json


class EditorialTests(unittest.TestCase):
    def test_scene_split_cannot_drop_transition_words(self):
        plan = {"spoken_script": "세탁과 건조를 마친 뒤 물을 뿌려보세요.", "scenes": [
            {"narration": "물을 뿌려보세요.", "visual_action": "마른 옷에 물을 뿌린다"}]}
        with self.assertRaisesRegex(ValueError, "complete spoken_script"):
            validate_script(plan)
        plan["scenes"][0]["narration"] = plan["spoken_script"]
        validate_script(plan)

    def test_generic_flow_approval_without_transition_evidence_fails(self):
        with self.assertRaises(ValueError):
            validate_comprehension({"viewer_recap": "세탁 후 확인한다", "flow_pass": True})
        review = {"viewer_recap": "세탁 후 물방울로 추가 처리 여부를 판단한다", "transition_checks": [
            {"from_scene": i, "to_scene": i + 1, "clear": True, "evidence": "세탁과 건조를 마친 뒤"}
            for i in range(1, 4)]}
        validate_comprehension(review)
        broken = copy.deepcopy(review)
        broken["transition_checks"][1]["clear"] = False
        with self.assertRaises(ValueError):
            validate_comprehension(broken)

    def test_original_truncated_hook_is_reflowed_without_losing_words(self):
        hook, caption, small = fonts()
        text = "가을에 꺼낸 고어텍스 재킷, 겉감이 젖는다고 바로 발수제를 덧바르세요?"
        draw = ImageDraw.Draw(Image.new("RGB", (720, 1280)))
        lines, font = fitted_text(draw, text, hook, 630, 2, 36, "hook")
        self.assertEqual(" ".join(lines), text)
        self.assertLessEqual(len(lines), 2)
        self.assertGreaterEqual(font.size, 36)
        with self.assertRaises(ValueError):
            fitted_text(draw, text * 5, hook, 630, 2, 36, "hook")

    def test_six_scenes_and_all_five_transitions_are_supported(self):
        plan = {"hook": "확인하세요", "spoken_script": " ".join(["설명"] * 6),
                "scenes": [{"narration": "설명", "caption": "한 가지 행동", "visual_action": "행동"} for _ in range(6)],
                "storyboard_grid": {"columns": 2, "rows": 3}}
        validate_script(plan)
        validate_layout(plan)
        review = {"viewer_recap": "앞 행동을 마친 뒤 다음 행동", "transition_checks": [
            {"from_scene": i, "to_scene": i + 1, "clear": True, "evidence": "앞 행동을 마친 뒤"} for i in range(1, 6)]}
        validate_comprehension(review, 6)
        with self.assertRaises(ValueError):
            validate_comprehension(review, 4)

    def test_caption_overflow_and_unbroken_long_word_are_rejected(self):
        draw = ImageDraw.Draw(Image.new("RGB", (720, 1280)))
        _, font, _ = fonts()
        for text in ("물방울 확인 " * 30, "가" * 80):
            with self.subTest(text=text), self.assertRaises(ValueError):
                checked_text_lines(draw, text, font, 575, 3, "caption")

    def test_short_headline_and_explicit_line_breaks_keep_all_words(self):
        draw = ImageDraw.Draw(Image.new("RGB", (720, 1280)))
        font, _, _ = fonts()
        text = "고어텍스가 젖으면\n발수제부터?"
        lines = checked_text_lines(draw, text, font, 630, 2, "hook")
        self.assertEqual(lines, text.splitlines())
        self.assertTrue(all(draw.textlength(line, font=font) <= 630 for line in lines))

    def test_overflow_is_revised_and_reviewed_before_media_generation(self):
        plan = {"date": "2026-10-26", "season": "가을", "topic_strategy": "seasonal",
                "topic": "test", "title": "test",
                "viewer_value": {"common_approach": "a", "better_decision": "b", "why_it_matters": "c"},
                "hook": "긴 설명 " * 80, "spoken_script": "설명 다음 설명",
                "scenes": [{"narration": n, "caption": "짧은 설명", "visual_action": "행동"} for n in ("설명", "다음 설명")],
                "sources": [{"title": "source", "url": "https://example.org"}] * 2}
        fixed = {**plan, "hook": "먼저 확인하세요"}
        review = dict.fromkeys(("approved", "selection_rule_pass", "originality_pass", "sources_verified",
                               "safety_pass", "usefulness_pass", "flow_pass"), True)
        review.update(usefulness_reason="a", flow_reason="b", viewer_recap="앞 행동 뒤 확인",
                      transition_checks=[{"from_scene": 1, "to_scene": 2, "clear": True, "evidence": "다음 설명"}])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stages = []
            def stage(root, run, name, prompt, **kwargs):
                stages.append(name)
                path = run / (name + ".json")
                atomic_json(path, fixed if name.startswith("main-refine") else review)
                return path
            prompts = {"review": str(root / "draft.json"), "main_approve": "repair"}
            with patch.object(mailbox, "call_codex", side_effect=stage):
                result = mailbox.refine_editorial_plan(plan, date(2026, 10, 26), root, root, prompts, None)
                self.assertEqual(result, fixed)
                self.assertEqual(stages, ["main-refine-1", "final-review-1"])
                mailbox.refine_editorial_plan(fixed, date(2026, 10, 26), root, root, prompts, None)
                self.assertEqual(len(stages), 2)

    def test_unfixed_overflow_stops_only_after_two_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = {"date": "2026-10-26"}
            path = root / "broken.json"
            atomic_json(path, broken)
            with patch.object(mailbox, "call_codex", return_value=path) as call:
                with self.assertRaisesRegex(mailbox.WorkflowSkipped, "repair attempts exhausted"):
                    mailbox.refine_editorial_plan(broken, date(2026, 10, 26), root, root,
                                                 {"review": "review", "main_approve": "repair"}, None)
                self.assertEqual(call.call_count, 2)
