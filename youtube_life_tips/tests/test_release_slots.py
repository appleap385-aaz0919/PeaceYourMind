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

    def test_both_releases_run_with_separate_artifacts_and_receipts(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "preflight"), \
             patch.object(m, "send_result_email", return_value="sent") as mail:
            root = Path(tmp)
            plan = {"date": str(DAY), "season": "가을", "topic_strategy": "seasonal", "topic": "tip",
                    "hook": "hook", "title": "tip", "viewer_value": {
                        "common_approach": "a", "better_decision": "b", "why_it_matters": "c"},
                    "scenes": [{"narration": "text", "caption": "text"} for _ in range(4)],
                    "sources": [{"title": "source", "url": "https://example.org"} for _ in range(2)]}
            def stage(root_arg, run_dir, name, prompt, **kwargs):
                daily = root / "work/daily" / run_dir.name
                result = plan
                if name == "review":
                    result = dict.fromkeys(("approved", "selection_rule_pass", "originality_pass", "sources_verified",
                                            "safety_pass", "usefulness_pass", "flow_pass"), True)
                    result.update(usefulness_reason="useful", flow_reason="connected")
                elif name == "developer-image":
                    Image.new("RGB", (900, 1400), "red" if run_dir.name.endswith("-pm") else "blue").save(daily / "storyboard.png")
                    result = {"status": "ok", "built_in_imagegen_called": True}
                elif name == "main-audit":
                    result = {"approved": True, "checks": dict.fromkeys(("plan_matches_content", "sources_verified",
                        "season_decision_valid", "history_distinct", "viewer_value_valid", "narration_flow_valid",
                        "four_scenes_match_plan", "captions_readable", "no_visual_defects", "dimensions_valid",
                        "audio_present", "duration_valid"), True)}
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
            with patch.object(m, "call_codex", side_effect=stage), patch.object(m.subprocess, "run", side_effect=external), \
                 patch.object(m, "make_render_contact_sheet", return_value=root / "contact.png"):
                for slot, hour in (("am", 3), ("pm", 15)):
                    request = root / f"{slot}.json"
                    atomic_json(request, {"date": str(DAY), "slot": slot})
                    with patch.object(m, "now_kst", return_value=datetime(2026, 10, 26, hour, tzinfo=m.KST)):
                        result = m.process_request(request, root)
                        self.assertEqual(result["status"], "scheduled", result)
                        self.assertEqual(result["url"], slot)
                        self.assertEqual(m.process_request(request, root)["url"], slot)
            self.assertEqual(mail.call_count, 2)


if __name__ == "__main__":
    unittest.main()
