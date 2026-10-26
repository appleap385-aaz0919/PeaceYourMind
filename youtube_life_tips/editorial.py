"""Check the handoff between a continuous script and its visual scenes."""


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
