"""Check the handoff between a continuous script and its visual scenes."""

import json
import math
from pathlib import Path


STORYBOARD_MIN_ASPECT = 1.25


def demo_storyboard_grid(scene_count: int) -> dict[str, int]:
    """Keep hand-action photos near square without fixing the scene count."""
    columns = 2 if scene_count <= 8 else 3
    return {"columns": columns, "rows": math.ceil(scene_count / columns)}


def validate_script(plan: dict) -> None:
    script = plan.get("spoken_script")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("spoken_script must contain the continuous narration written before scene splitting")
    scenes = plan.get("scenes", [])
    joined = " ".join(scene.get("narration", "") for scene in scenes)
    if " ".join(script.split()) != " ".join(joined.split()):
        raise ValueError("scene narrations must preserve the complete spoken_script in order")
    if any(not isinstance(scene.get("visual_action"), str) or not scene["visual_action"].strip() for scene in scenes):
        raise ValueError("each scene needs a visual_action explaining what the viewer should see")


def validate_comprehension(review: dict, scene_count: int | None = None) -> None:
    recap = review.get("viewer_recap")
    if not isinstance(recap, str) or not recap.strip():
        raise ValueError("review must retell the action and decision from a first-time viewer's perspective")
    reported_count = review.get("scene_count")
    if (scene_count is not None and reported_count is not None
            and (type(reported_count) is not int or reported_count != scene_count)):
        raise ValueError("review scene_count must match the approved scene count")
    transitions = review.get("transition_checks")
    expected = scene_count - 1 if scene_count is not None else review.get("scene_count", 4) - 1
    if not isinstance(transitions, list) or len(transitions) != expected:
        raise ValueError("review must check every scene transition")
    for index, transition in enumerate(transitions, start=1):
        if (not isinstance(transition, dict)
                or transition.get("from_scene") != index
                or transition.get("to_scene") != index + 1
                or transition.get("clear") is not True
                or not isinstance(transition.get("evidence"), str)
                or not transition["evidence"].strip()):
            raise ValueError("each scene transition needs a clear verdict and specific wording as evidence")


def latest_editorial_review_path(run_dir: Path) -> Path:
    """Resolve the review that approved the current final wording, not the first draft."""
    run_dir = Path(run_dir).resolve()
    marker_path = run_dir / "editorial-ready.json"
    if not marker_path.is_file():
        raise ValueError("final editorial review marker is missing")
    review_name = json.loads(marker_path.read_text(encoding="utf-8")).get("review")
    if (not isinstance(review_name, str) or Path(review_name).name != review_name
            or not review_name.startswith("final-review-") or not review_name.endswith(".json")):
        raise ValueError("final editorial review marker does not name a final review")
    review_path = run_dir / review_name
    if not review_path.is_file():
        raise ValueError("final editorial review file is missing")
    return review_path
