from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_short.py"


class RenderFilterTests(unittest.TestCase):
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
