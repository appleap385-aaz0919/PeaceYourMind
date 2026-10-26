"""Upload today's rendered Short to the explicitly configured channel for 07:00 KST."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import resumable_upload
from reliability import atomic_json, file_lock, read_receipt
from life_schedule import release_key, publish_clock

from youtube_auth import get_access_token, load_local_config, load_oauth_client, my_channels, state_path


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work" / "daily"
KST = ZoneInfo("Asia/Seoul")
CHUNK_SIZE = 8 * 1024 * 1024


def publish_at_for(day: date, clock: str) -> datetime:
    hour, minute = (int(value) for value in clock.split(":"))
    local_time = datetime.combine(day, datetime_time(hour, minute), tzinfo=KST)
    return local_time


def parse_publish_at(day: date, value: str) -> datetime:
    """Parse one explicitly selected release time and require it to be for this KST date."""
    scheduled = datetime.fromisoformat(value)
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=KST)
    else:
        scheduled = scheduled.astimezone(KST)
    if scheduled.date() != day:
        raise ValueError("--publish-at-kst must be on the requested --date")
    return scheduled


def validate_publish_window(publish_at: datetime, now: datetime, *, one_off: bool) -> None:
    minimum_lead = timedelta(minutes=15 if one_off else 30)
    if now > publish_at - minimum_lead:
        if one_off:
            raise RuntimeError("one-off scheduled publishing requires at least 15 minutes of lead time")
        raise RuntimeError("missed the configured publishing cutoff; today's post is skipped")


def validate_channel(access_token: str, target_id: str) -> None:
    channels = my_channels(access_token)
    if not any(channel["id"] == target_id for channel in channels):
        available = ", ".join(f"{c['title']} ({c['id']})" for c in channels) or "none"
        raise RuntimeError(f"authenticated Google account does not expose configured life-tips channel; found: {available}")


def api_call(request: urllib.request.Request) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 308:
            return exc.code, dict(exc.headers.items()), exc.read()
        detail = exc.read().decode("utf-8", "replace")[:1500]
        raise RuntimeError(f"YouTube upload API failed ({exc.code}): {detail}") from exc


def upload_resumable(video: Path, metadata: dict[str, object], access_token: str,
                     *, receipt_context: dict | None = None, deadline: datetime | None = None) -> dict[str, object]:
    return resumable_upload.upload(
        video, metadata, access_token, api_call=api_call, chunk_size=CHUNK_SIZE,
        session_path=video.parent / "upload_session.json",
        receipt_context=receipt_context or {}, deadline=deadline,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Asia/Seoul date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--slot", choices=("am", "pm"), default="am")
    parser.add_argument("--publish-at-kst", help="one-off release time in KST, e.g. 2026-10-23T08:30")
    parser.add_argument("--dry-run", action="store_true", help="validate local files/config without uploading")
    args = parser.parse_args()
    day = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    with file_lock(WORK / release_key(day, args.slot) / "upload.lock"):
        upload_day(day, args)


def upload_day(day: date, args: argparse.Namespace) -> None:
    slot = getattr(args, "slot", "am")
    key = release_key(day, slot)
    day_dir = WORK / key
    result_path = day_dir / "upload.json"
    config = load_local_config()
    channel_id = str(config.get("youtube_channel_id", "")).strip()
    resumable_upload.recovered_receipt(day_dir)
    if read_receipt(result_path, day.isoformat(), channel_id, slot):
        print(f"Already uploaded or scheduled for {day.isoformat()}; leaving existing result untouched.")
        return
    metadata_path = day_dir / "metadata.json"
    video_path = day_dir / f"life-tip-{day.isoformat()}.mp4"
    if not metadata_path.is_file() or not video_path.is_file():
        raise FileNotFoundError("today's rendered MP4 and metadata.json are both required")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("slot", "am") != slot or metadata.get("release_key", key) != key:
        raise ValueError("render metadata belongs to a different release slot")
    if metadata.get("date") != day.isoformat() or not metadata.get("sources"):
        raise ValueError("render metadata is missing today's date or source records")
    if not metadata.get("title") or len(metadata["title"]) > 100:
        raise ValueError("YouTube title must be present and at most 100 characters")
    if not metadata.get("description") or len(metadata["description"]) > 5000:
        raise ValueError("YouTube description must be present and at most 5000 characters")
    if metadata.get("width") != 720 or metadata.get("height") != 1280:
        raise ValueError("only the validated 720x1280 render can be uploaded")
    if float(metadata.get("duration_seconds", 0)) <= 0 or float(metadata["duration_seconds"]) > 55.5:
        raise ValueError("only a validated Short up to 55.5 seconds can be uploaded")
    if not channel_id or channel_id == "REPLACE_WITH_LIFE_TIPS_CHANNEL_ID":
        raise ValueError("state/config.local.json must contain the separate life-tips channel ID")
    now = datetime.now(KST)
    if args.publish_at_kst:
        publish_at = parse_publish_at(day, args.publish_at_kst)
        if ("pm" if publish_at.hour >= 12 else "am") != slot:
            raise ValueError("--publish-at-kst must match the selected --slot")
        validate_publish_window(publish_at, now, one_off=True)
    else:
        publish_time = publish_clock(slot)
        publish_at = publish_at_for(day, publish_time)
        validate_publish_window(publish_at, now, one_off=False)
    if args.dry_run:
        print(json.dumps({
            "date": day.isoformat(), "channel_id": channel_id,
            "title": metadata.get("title"), "video_bytes": video_path.stat().st_size,
            "publish_at_kst": publish_at.isoformat(), "dry_run": True,
        }, ensure_ascii=False, indent=2))
        return

    client_path = state_path(config, "oauth_client_file", "state/google_oauth_client.json")
    token_path = state_path(config, "oauth_token_file", "state/youtube_token.json")
    client = load_oauth_client(client_path)
    access_token = get_access_token(client, token_path)
    validate_channel(access_token, channel_id)
    video_metadata = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "categoryId": "26",
            "tags": ["생활꿀팁", "살림팁", "Shorts"],
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    receipt_context = {
        "date": day.isoformat(), "channel_id": channel_id,
        "slot": slot, "release_key": key,
        "scheduled_publish_at_kst": publish_at.isoformat(), "title": metadata["title"],
    }
    uploaded = upload_resumable(
        video_path, video_metadata, access_token, receipt_context=receipt_context,
        deadline=publish_at - timedelta(minutes=5),
    )
    video_id = uploaded.get("id")
    if not video_id:
        raise RuntimeError("YouTube response did not contain a video ID")
    result = {
        "date": day.isoformat(),
        "slot": slot, "release_key": key,
        "channel_id": channel_id,
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "scheduled_publish_at_kst": publish_at.isoformat(),
        "title": metadata["title"],
    }
    atomic_json(result_path, result)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
