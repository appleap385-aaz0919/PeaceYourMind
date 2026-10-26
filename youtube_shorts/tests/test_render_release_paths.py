import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_short


class RenderReleasePathsTests(unittest.TestCase):
    def test_renderer_writes_to_the_directory_used_by_each_release_uploader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for slot, key in (("am", "2026-10-26"), ("pm", "2026-10-26-pm")):
                with self.subTest(slot=slot):
                    work = root / "work" / key
                    work.mkdir(parents=True)
                    manifest = work / "2026-10-26.json"
                    manifest.write_text(json.dumps({
                        "date_kst": "2026-10-26", "slot": slot,
                        "verse_id": "1th.5.18", "reference": "1 Thess 5:18",
                        "text": "Give thanks", "translation": "test",
                    }), encoding="utf-8")
                    with (
                        patch.object(render_short, "__file__", str(root / "scripts" / "render_short.py")),
                        patch.object(sys, "argv", ["render_short.py", str(manifest)]),
                        patch.object(render_short, "synthesize_text") as tts,
                        patch.object(render_short, "media_duration", return_value=2),
                        patch.object(render_short, "app_scenes", return_value=([Path("input"), Path("verse"), Path("videos")], [])) as scenes,
                        patch.object(render_short, "render_mp4") as render,
                    ):
                        render_short.main()
                    self.assertEqual(render.call_args.args[3], work / "short-draft.mp4")
                    self.assertEqual(scenes.call_args.args[1], work)
                    self.assertTrue(all(call.args[1].parent == work / "narration" for call in tts.call_args_list))
