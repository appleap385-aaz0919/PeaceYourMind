"""Persist concrete demonstration instructions before spending an image call."""

import hashlib
import json

from reliability import atomic_json


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def validate_direction(direction, scene_count):
    if not isinstance(direction, dict):
        raise ValueError("scene direction must be a JSON object")
    if direction.get("feasible") is not True:
        raise ValueError("demonstration is not ready: " + str(direction.get("reason", "missing feasibility decision")))
    if not isinstance(direction.get("object_identity"), str) or not direction["object_identity"].strip():
        raise ValueError("scene direction needs stable object identities")
    if direction.get("unresolved_risks") != []:
        raise ValueError("scene direction has unresolved physical or visual risks")
    panels = direction.get("panels")
    if not isinstance(panels, list) or len(panels) != scene_count:
        raise ValueError("scene direction must cover every scene exactly once")
    fields = ("before_state", "hand_action", "orientation_and_contact", "after_state", "continuity")
    for number, panel in enumerate(panels, 1):
        if not isinstance(panel, dict) or type(panel.get("scene")) is not int or panel["scene"] != number:
            raise ValueError("scene direction must use ordered one-based scene numbers")
        if any(not isinstance(panel.get(key), str) or not panel[key].strip() for key in fields):
            raise ValueError(f"scene {number} lacks a concrete state, action, contact or continuity instruction")
        checks = panel.get("critical_checks")
        if not isinstance(checks, list) or not checks or any(not isinstance(item, str) or not item.strip() for item in checks):
            raise ValueError(f"scene {number} needs observable checks for the actual instruction")
        incidental = panel.get("incidental_details")
        if not isinstance(incidental, list) or any(not isinstance(item, str) for item in incidental):
            raise ValueError(f"scene {number} needs an incidental-details list")


def prepare_scene_direction(plan, root, run_dir, common_prompt, call, deadline):
    """One direction pass and at most one correction, shared by samples and releases."""
    output = run_dir / "scene-direction.json"
    marker = run_dir / "scene-direction-ready.json"
    signature = plan_hash(plan)
    if output.exists() and marker.exists():
        cached = json.loads(marker.read_text(encoding="utf-8"))
        if (cached.get("plan_sha256") == signature
                and cached.get("direction_sha256") == hashlib.sha256(output.read_bytes()).hexdigest()):
            direction = json.loads(output.read_text(encoding="utf-8"))
            validate_direction(direction, len(plan["scenes"]))
            return output
    prompt = common_prompt + (
        "\nROLE: DEMONSTRATION DIRECTOR. Read the approved.json in this run folder. Do not select another topic, "
        "rewrite narration/captions/facts, invoke ImageGen, render, upload, or start a server. "
        "Convert the approved instruction into concrete photorealistic hand-and-work panels. "
        "Fix object identity, before-state, exact hand action, orientation/contact, and after-state for EVERY scene. "
        "State continuity explicitly, including a result-first flashforward or a conditional example using a different object. "
        "Determine whether the operation can be taught faithfully with the available panels. "
        "For bends, cuts, knots or continuous wire, account for every end, joint and load path; show a closeup "
        "of critical contact rather than an invented attachment or an unexplained jump. "
        "Do not assume a complicated object will become correct during image repairs. "
        "Report an unresolved physical relationship as infeasible BEFORE image generation. "
        "All actions and conditions must follow the verified plan; no invented mechanics, measurements or results. "
        "Separate critical checks (physical correctness, safety, spoken instructions and observable outcome) "
        "from incidental appearance (cloth color, decorative folds, background, exact hand pose when instruction/safety are equivalent). "
        "A prop detail absent from the spoken instruction must not become a new safety or instructional requirement "
        "without a stated factual reason. Do not classify an actual action, required material, contact point or safety condition as incidental. "
        f"Read {run_dir / 'approved.json'}. Return ONLY JSON: "
        '{"feasible":true,"reason":"specific feasibility explanation","object_identity":"stable objects/materials",'
        '"unresolved_risks":[],"panels":[{"scene":1,"before_state":"...","hand_action":"...",'
        '"orientation_and_contact":"...","after_state":"...","continuity":"...",'
        '"critical_checks":["visible instruction/result"],"incidental_details":["optional appearance"]}]}. '
        "For infeasible output set feasible=false and list concrete unresolved_risks; never claim success without a workable demonstration."
    )
    version = "" if not marker.exists() else "-" + signature[:12]
    for attempt in range(2):
        stage = "scene-direction" + version if attempt == 0 else "scene-direction-refine-1" + version
        stage_output = run_dir / f"{stage}.json"
        if not stage_output.exists():
            stage_output = call(root, run_dir, stage, prompt, deadline=deadline)
        direction = json.loads(stage_output.read_text(encoding="utf-8"))
        try:
            validate_direction(direction, len(plan["scenes"]))
        except ValueError as exc:
            if (isinstance(direction, dict) and direction.get("feasible") is False) or attempt == 1:
                raise
            prompt += "\nCORRECT THE DIRECTION JSON ONLY: " + str(exc) + "\nPREVIOUS RESULT: " + json.dumps(direction, ensure_ascii=False)
            continue
        atomic_json(output, direction)
        atomic_json(marker, {"plan_sha256": signature,
                             "direction_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
        return output
