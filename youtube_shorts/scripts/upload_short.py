#!/usr/bin/env python3
"""Upload a ready Short. Publishing defaults to a private draft."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from upload_ledger import persist, save_state
from release_schedule import release_key

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
KST = ZoneInfo("Asia/Seoul")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = Path(__file__).resolve().parents[1] / "state" / "uploads.json"


def get_credentials(path: Path) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("YouTube OAuth token is no longer valid. Run authorize_youtube.py again.")
    return creds




def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--token", type=Path,
                        default=Path(__file__).resolve().parents[1] / "token.local.json")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--publish-at-kst", help="YYYY-MM-DDTHH:MM; auto-publish a private upload")
    args = parser.parse_args()

    if not args.video.is_file() or args.video.stat().st_size < 1024:
        parser.error("video file is missing or empty")
    if not args.token.is_file():
        parser.error("OAuth token file is missing; run authorize_youtube.py first")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if metadata.get("status") != "ready":
        parser.error("metadata must be marked ready by build_metadata.py")
    day = metadata.get("date_kst")
    if not isinstance(day, str) or not day:
        parser.error("metadata must contain date_kst")
    slot = metadata.get("slot", "am")
    date_key = release_key(day, slot)
    if metadata.get("release_key", date_key) != date_key:
        parser.error("metadata release_key does not match date and slot")

    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.is_file() else {}
    if date_key in state:
        raise SystemExit(f"Upload already recorded or awaiting reconciliation for {date_key}; refusing a new upload")

    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if args.publish_at_kst:
        publish_at = datetime.fromisoformat(args.publish_at_kst)
        publish_at = publish_at.replace(tzinfo=KST) if publish_at.tzinfo is None else publish_at.astimezone(KST)
        if publish_at.date().isoformat() != day:
            parser.error("publish date must match metadata date_kst")
        if ("pm" if publish_at.hour >= 12 else "am") != slot:
            parser.error("publish time does not match metadata slot")
        if publish_at <= datetime.now(KST) + timedelta(minutes=15):
            parser.error("scheduled publish time must be at least 15 minutes in the future")
        status["publishAt"] = publish_at.isoformat()

    youtube = build("youtube", "v3", credentials=get_credentials(args.token), cache_discovery=False)
    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": "27",
            "defaultLanguage": metadata.get("language", "ko"),
        },
        "status": status,
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(args.video), mimetype="video/mp4", resumable=True),
        notifySubscribers=False,
    )
    operation_id = uuid.uuid4().hex
    expected_channel = "UCLQczQnzBHzB8jOO0sMeP2w"
    # Commit intent BEFORE transmitting media. A runner crash must not permit
    # the next scheduled run to blindly insert a second video.
    state[date_key] = {
        "date_kst": day, "slot": slot, "release_key": date_key, "status": "uploading", "operation_id": operation_id,
        "channel_id": expected_channel, "publish_at": status.get("publishAt"),
    }
    save_state(args.state, state)
    persist(args.state)
    response = request.execute(num_retries=3)
    receipt = {
        "date_kst": day, "slot": slot, "release_key": date_key, "status": "uploaded", "operation_id": operation_id,
        "channel_id": response.get("snippet", {}).get("channelId", expected_channel),
        "video_id": response["id"],
        "privacy": status["privacyStatus"],
        "publish_at": status.get("publishAt"),
    }
    # Save the independent receipt first, so an interrupted ledger push can be recovered.
    save_state(args.video.parent / "upload_receipt.json", receipt)
    state[date_key] = receipt
    save_state(args.state, state)
    persist(args.state)
    if receipt["channel_id"] != expected_channel:
        raise RuntimeError("uploaded video channel mismatch; inspect saved receipt")
    print(f"Uploaded {date_key}: https://youtube.com/shorts/{response['id']}")


if __name__ == "__main__":
    main()
