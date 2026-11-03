"""Resolve morning/evening releases while preserving legacy morning ledger keys."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
EVENING_CRONS = {"30 4 * * *", "15 5 * * *"}


def upload_publish_time(requested: datetime, now: datetime, slot: str, recover_late: bool = False) -> datetime:
    """Keep a delayed scheduled run on the same release day and away from the next slot."""
    requested = requested.astimezone(KST)
    now = now.astimezone(KST)
    if requested > now + timedelta(minutes=15):
        return requested
    if not recover_late or now > requested + timedelta(hours=4):
        raise ValueError("scheduled publish time must be at least 15 minutes in the future")
    recovered = now + timedelta(minutes=30)
    if recovered.date() != requested.date() or ("pm" if recovered.hour >= 12 else "am") != slot:
        raise ValueError("late scheduled run cannot be recovered within its release slot")
    return recovered


def release_key(day: str, slot: str = "am") -> str:
    date.fromisoformat(day)
    if slot not in {"am", "pm"}:
        raise ValueError("slot must be am or pm")
    return day if slot == "am" else f"{day}-pm"


def resolve(event: dict, now: datetime) -> dict[str, str]:
    requested = event.get("inputs", {}).get("publish_at_kst")
    if requested:
        target = datetime.fromisoformat(requested)
        target = target.replace(tzinfo=KST) if target.tzinfo is None else target.astimezone(KST)
        slot = "pm" if target.hour >= 12 else "am"
    else:
        slot = "pm" if event.get("schedule") in EVENING_CRONS else "am"
        target = now.astimezone(KST).replace(hour=19 if slot == "pm" else 7, minute=0, second=0, microsecond=0)
    day = target.date().isoformat()
    return {"date_kst": day, "slot": slot, "release_key": release_key(day, slot),
            "publish_at_kst": target.isoformat(timespec="minutes")}


def main() -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
    values = resolve(event, datetime.now(KST))
    for variable, key in (("RUN_DATE_KST", "date_kst"), ("RUN_SLOT", "slot"),
                          ("RUN_KEY", "release_key"), ("PUBLISH_AT_KST", "publish_at_kst")):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
            handle.write(f"{variable}={values[key]}\n")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
    print(f"Release: {values['release_key']} at {values['publish_at_kst']}")


if __name__ == "__main__":
    main()
