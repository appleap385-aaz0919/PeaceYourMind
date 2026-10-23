"""Durable upload intent/receipt checkpoints, isolated from preview artifacts."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "youtube_shorts/state/uploads.json"


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def persist(path: Path = STATE) -> None:
    if os.environ.get("PYM_PERSIST_LEDGER") != "true":
        return
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    if relative != "youtube_shorts/state/uploads.json":
        raise ValueError("only the upload ledger may be committed by this helper")

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "--", relative)
    if git("diff", "--cached", "--name-only", "--", relative).stdout.strip():
        git("commit", "-m", "chore: checkpoint YouTube upload", "--", relative)
    for attempt in range(3):
        try:
            git("-c", "rebase.autoStash=true", "pull", "--rebase", "origin", "main")
            git("push", "origin", "HEAD:main")
            return
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise RuntimeError("upload ledger push failed; retain receipt and reconcile before a new upload")
            time.sleep(2 ** attempt)


if __name__ == "__main__":
    if STATE.exists():
        persist()
