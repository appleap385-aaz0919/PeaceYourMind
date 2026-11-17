from __future__ import annotations

import importlib.util
import unittest
import sys
from types import SimpleNamespace
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_short.py"


class RenderFilterTests(unittest.TestCase):
    def test_edge_tts_preserves_text_and_maps_segment_rates(self) -> None:
        spec = importlib.util.spec_from_file_location("render_short", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        save = AsyncMock()
        communicate = Mock(return_value=SimpleNamespace(save=save))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"edge_tts": SimpleNamespace(Communicate=communicate)}):
            output = Path(tmp) / "audio" / "verse.mp3"
            for multiplier, expected in [(0.94, "-6%"), (0.88, "-12%")]:
                module.synthesize_text("one\ntwo", output, "ko-KR-InJoonNeural", multiplier)
                communicate.assert_called_with("one two", "ko-KR-InJoonNeural", rate=expected, pitch="-5Hz")
            self.assertEqual(save.await_count, 2)
            self.assertTrue(output.parent.is_dir())

    def test_edge_failure_propagates_without_paid_fallback(self) -> None:
        spec = importlib.util.spec_from_file_location("render_short", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"edge_tts": SimpleNamespace(Communicate=Mock(side_effect=RuntimeError("offline")))}):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                module.synthesize_text("text", Path(tmp) / "voice.mp3", "ko-KR-InJoonNeural")

    def test_xfade_inputs_restore_fps_after_setpts(self) -> None:
        spec = importlib.util.spec_from_file_location("render_short", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with patch.object(module.subprocess, "run") as run:
            module.render_mp4(
                [Path("one.png"), Path("two.png"), Path("three.png")],
                [1.0, 1.0, 1.0], [(Path("voice.mp3"), 0.0)],
                Path("out.mp4"), "ffmpeg",
            )
        command = run.call_args.args[0]
        graph = command[command.index("-filter_complex") + 1]
        for index in range(3):
            self.assertIn(
                f"[{index}:v]setpts=PTS-STARTPTS,fps=30,settb=AVTB,setsar=1[v{index}]",
                graph,
            )
        self.assertEqual(graph.count("xfade="), 2)
        self.assertIn("offset=1.680", graph)


if __name__ == "__main__":
    unittest.main()
