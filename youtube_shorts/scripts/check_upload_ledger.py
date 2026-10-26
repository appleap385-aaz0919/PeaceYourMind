#!/usr/bin/env python3
"""Skip scheduled retries when today's Short is already in the upload ledger."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from release_schedule import release_key


DEFAULT_STATE = Path(__file__).resolve().parents[1] / "state" / "uploads.json"
KST = ZoneInfo("Asia/Seoul")


def already_uploaded(date_key: str, state_path: Path) -> bool:
    if not state_path.is_file():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError(f"Upload ledger must contain a JSON object: {state_path}")
    record = state.get(date_key)
    if record is None:
        return False
    if not isinstance(record, dict) or not isinstance(record.get("video_id"), str) or not record["video_id"]:
        raise ValueError(f"Upload for {date_key} is incomplete or uncertain; reconcile its receipt before retrying")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="KST date in YYYY-MM-DD format (defaults to today)")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--slot", choices=("am", "pm"), default=os.environ.get("RUN_SLOT", "am"))
    args = parser.parse_args()

    day = args.date or os.environ.get("RUN_DATE_KST") or datetime.now(KST).date().isoformat()
    date_key = release_key(day, args.slot)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"date_kst={day}\nrelease_key={date_key}\n")

    is_scheduled = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
    uploaded = is_scheduled and already_uploaded(date_key, args.state)
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"already_uploaded={'true' if uploaded else 'false'}\n")

    if uploaded:
        print(f"A Short is already recorded for {date_key}; skipping duplicate work.")
    else:
        print(f"No scheduled upload is recorded for {date_key}; continuing.")


if __name__ == "__main__":
    main()
