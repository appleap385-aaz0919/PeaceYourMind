"""Release-wide limits and actionable feedback shared by manual and scheduled production."""

import hashlib
import json
from datetime import datetime, timedelta

from reliability import atomic_json

MAX_RELEASE_MINUTES = 60
MAX_CODEX_CALLS = 28
MAX_IMAGE_CALLS = 5


class ImprovementLimitReached(RuntimeError):
    """Stop this release rather than reset its budget in another candidate or retry."""


def release_run(run_dir):
    return run_dir.parent.parent if run_dir.parent.name == "candidates" else run_dir


def budget_path(run_dir):
    return release_run(run_dir) / "improvement-budget.json"


def release_deadline(run_dir, now, cutoff):
    path = budget_path(run_dir)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "started_at_kst": now.isoformat(), "codex_calls": 0, "image_calls": 0, "events": [],
        "deadline_kst": (now + timedelta(minutes=MAX_RELEASE_MINUTES)).isoformat(),
    }
    deadline = min(datetime.fromisoformat(state["deadline_kst"]), cutoff)
    state["deadline_kst"] = deadline.isoformat()
    atomic_json(path, state)
    if now >= deadline:
        raise ImprovementLimitReached("release time budget exhausted")
    return deadline


def reserve_call(run_dir, stage, now, cutoff):
    """Reserve before execution: failed or uncertain calls still cost budget."""
    deadline = release_deadline(run_dir, now, cutoff)
    path = budget_path(run_dir)
    state = json.loads(path.read_text(encoding="utf-8"))
    image = stage == "developer-image" or stage.startswith("developer-visual-repair-")
    if state["codex_calls"] >= MAX_CODEX_CALLS:
        raise ImprovementLimitReached("release Codex call budget exhausted")
    if image and state["image_calls"] >= MAX_IMAGE_CALLS:
        raise ImprovementLimitReached("release image call budget exhausted")
    state["codex_calls"] += 1
    state["image_calls"] += int(image)
    state["events"].append({"stage": stage, "candidate_run": run_dir.name, "at_kst": now.isoformat()})
    atomic_json(path, state)
    return deadline


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def correction_feedback(scope, findings):
    """Keep the reviewer evidence, and turn each failure into an explicit next action."""
    common = [
        "Identify the root cause from the quoted findings; do not merely reword the rejection.",
        "Preserve independently verified facts, safety conditions, quality thresholds and approved unaffected work.",
        "Never invent source details, add filler, slow speech, or weaken a criterion to obtain approval.",
    ]
    actions = {
        "discovery": [
            "Exclude the rejected practical actions, not only their titles or objects. Compare new creator demonstrations across different categories.",
            "Prefer a concrete repair, reuse or shortcut with visible payoff. Change search terms according to missing payoff, novelty or evidence.",
            "Separate observed creator content from independently verified method claims. Do not repeat an unavailable source without new evidence.",
        ],
        "editorial": [
            "Map every failed check to the exact unsupported claim, awkward sentence, missing transition or overflowing caption before revising.",
            "Correct structure and facts in one continuous draft, apply the project-local humanize-korean single style pass, then split into scenes and recheck meaning.",
            "Keep actual speech between 65 and 90 seconds using only necessary reproducible steps; preserve source evidence in the complete JSON.",
        ],
        "visual": [
            "Inspect ALL panels for the reported failure class, not only the first detected scene. List every affected scene in one edit.",
            "For each affected scene specify required before-state, hand action, object orientation, attachment/contact points and after-state.",
            "Preserve correct panels, identities and chronology. Do not change narration to excuse a wrong demonstration.",
        ],
    }
    return {"scope": scope, "findings": findings, "actions": common + actions[scope],
            "acceptance": "A fresh independent review must pass every original check; the repair itself is not approval."}


def record_failure(run_dir, phase, findings, artifact):
    """A repeated failed state cannot consume another correction after a restart."""
    path = run_dir / "improvement-progress.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    identity = fingerprint({"findings": findings, "artifact": artifact})
    repeated = identity in state.get(phase, [])
    state.setdefault(phase, []).append(identity)
    atomic_json(path, state)
    return not repeated
