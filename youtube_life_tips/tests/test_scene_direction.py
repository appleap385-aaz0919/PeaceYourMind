import tempfile
import unittest
from pathlib import Path

from reliability import atomic_json
from scene_direction import prepare_scene_direction, validate_direction
from render_daily import cached_voice_paths, save_voice_cache


def direction(count=2):
    return {"feasible": True, "object_identity": "same steel bowls", "unresolved_risks": [],
            "panels": [{"scene": i, "before_state": "nested bowls", "hand_action": "support and lift",
                        "orientation_and_contact": "outer bowl supported", "after_state": "separated",
                        "continuity": "same bowls; first scene previews the result",
                        "critical_checks": ["inner bowl lifted out"], "incidental_details": ["cloth color"]}
                       for i in range(1, count + 1)]}


class SceneDirectionTests(unittest.TestCase):
    def test_covers_every_scene_in_order(self):
        validate_direction(direction(), 2)
        for mutate in (lambda value: value["panels"].pop(),
                       lambda value: value["panels"][1].update(scene=1),
                       lambda value: value["panels"][0].update(critical_checks=[]),
                       lambda value: value.update(unresolved_risks=["unexplained joint"])):
            value = direction()
            mutate(value)
            with self.assertRaises(ValueError):
                validate_direction(value, 2)

    def test_infeasible_geometry_stops_before_image_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            calls = []
            def call(root, folder, stage, prompt, **kwargs):
                calls.append(stage)
                path = folder / f"{stage}.json"
                atomic_json(path, {"feasible": False, "reason": "wire continuity cannot be shown",
                                   "unresolved_risks": ["invented joint"]})
                return path
            with self.assertRaisesRegex(ValueError, "wire continuity"):
                prepare_scene_direction({"scenes": [{}, {}]}, run, run, "", call, None)
            self.assertEqual(calls, ["scene-direction"])

    def test_reuses_direction_but_regenerates_for_changed_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            calls = []
            def call(root, folder, stage, prompt, **kwargs):
                calls.append(stage)
                path = folder / f"{stage}.json"
                atomic_json(path, direction())
                return path
            plan = {"topic": "bowls", "scenes": [{}, {}]}
            for _ in range(2):
                prepare_scene_direction(plan, run, run, "", call, None)
            self.assertEqual(len(calls), 1)
            plan["topic"] = "changed"
            prepare_scene_direction(plan, run, run, "", call, None)
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(calls[0], calls[1])

    def test_malformed_direction_gets_only_one_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            calls = []
            def call(root, folder, stage, prompt, **kwargs):
                calls.append(stage)
                path = folder / f"{stage}.json"
                atomic_json(path, {"feasible": True})
                return path
            with self.assertRaises(ValueError):
                prepare_scene_direction({"scenes": [{}, {}]}, run, run, "", call, None)
            self.assertEqual(calls, ["scene-direction", "scene-direction-refine-1"])

    def test_voice_cache_preserves_measured_audio_and_invalidates_changed_narration(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plan = {"scenes": [{"narration": "first"}, {"narration": "second"}]}
            paths = [folder / f"voice-{i}.mp3" for i in range(2)]
            for i, path in enumerate(paths):
                path.write_bytes(bytes([i]))
            save_voice_cache(plan, folder, paths)
            self.assertEqual(cached_voice_paths(plan, folder), paths)
            plan["scenes"][0]["caption"] = "only caption changed"
            self.assertEqual(cached_voice_paths(plan, folder), paths)
            plan["scenes"][0]["narration"] = "changed speech"
            self.assertIsNone(cached_voice_paths(plan, folder))

    def test_voice_cache_invalidates_changed_rate_or_audio_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plan = {"scenes": [{"narration": "first"}]}
            path = folder / "voice-0.mp3"
            path.write_bytes(b"original")
            save_voice_cache(plan, folder, [path])
            plan["voice_rate"] = "+9%"
            self.assertIsNone(cached_voice_paths(plan, folder))
            plan.pop("voice_rate")
            path.write_bytes(b"different audio")
            self.assertIsNone(cached_voice_paths(plan, folder))


if __name__ == "__main__":
    unittest.main()
