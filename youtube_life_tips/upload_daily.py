"""Upload today's rendered Short to the explicitly configured channel for 07:00 KST."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


def upload_resumable(video: Path, metadata: dict[str, object], access_token: str) -> dict[str, object]:
    payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    initiate = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video.stat().st_size),
        },
        method="POST",
    )
    _, headers, _ = api_call(initiate)
    upload_url = next((value for key, value in headers.items() if key.lower() == "location"), None)
    if not upload_url:
        raise RuntimeError("YouTube API did not return a resumable upload URL")

    total = video.stat().st_size
    offset = 0
    final_body = b""
    with video.open("rb") as stream:
        while offset < total:
            chunk = stream.read(CHUNK_SIZE)
            end = offset + len(chunk) - 1
            request = urllib.request.Request(
                upload_url,
                data=chunk,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                },
                method="PUT",
            )
            status, _, body = api_call(request)
            if status in (200, 201):
                final_body = body
                offset = total
            elif status == 308:
                offset = end + 1
            else:
                raise RuntimeError(f"unexpected resumable upload status: {status}")
    if not final_body:
        raise RuntimeError("YouTube upload ended without a completed video response")
    return json.loads(final_body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Asia/Seoul date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--publish-at-kst", help="one-off release time in KST, e.g. 2026-10-23T08:30")
    parser.add_argument("--dry-run", action="store_true", help="validate local files/config without uploading")
    args = parser.parse_args()
    day = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    day_dir = WORK / day.isoformat()
    result_path = day_dir / "upload.json"
    if result_path.exists():
        print(f"Already uploaded or scheduled for {day.isoformat()}; leaving existing result untouched.")
        return
    metadata_path = day_dir / "metadata.json"
    video_path = day_dir / f"life-tip-{day.isoformat()}.mp4"
    if not metadata_path.is_file() or not video_path.is_file():
        raise FileNotFoundError("today's rendered MP4 and metadata.json are both required")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
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
    config = load_local_config()
    channel_id = str(config.get("youtube_channel_id", "")).strip()
    if not channel_id or channel_id == "REPLACE_WITH_LIFE_TIPS_CHANNEL_ID":
        raise ValueError("state/config.local.json must contain the separate life-tips channel ID")
    now = datetime.now(KST)
    if args.publish_at_kst:
        publish_at = parse_publish_at(day, args.publish_at_kst)
        validate_publish_window(publish_at, now, one_off=True)
    else:
        publish_time = str(config.get("publish_time_kst", "07:00"))
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
        },
    }
    uploaded = upload_resumable(video_path, video_metadata, access_token)
    video_id = uploaded.get("id")
    if not video_id:
        raise RuntimeError("YouTube response did not contain a video ID")
    result = {
        "date": day.isoformat(),
        "channel_id": channel_id,
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "scheduled_publish_at_kst": publish_at.isoformat(),
        "title": metadata["title"],
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
