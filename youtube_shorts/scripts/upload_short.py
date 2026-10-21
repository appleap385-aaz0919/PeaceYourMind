#!/usr/bin/env python3
"""Upload a ready Short. Publishing defaults to a private draft."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


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
    date_key = metadata.get("date_kst")
    if not isinstance(date_key, str) or not date_key:
        parser.error("metadata must contain date_kst")

    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.is_file() else {}
    if date_key in state:
        raise SystemExit(f"Already uploaded for {date_key}: {state[date_key]['video_id']}")

    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if args.publish_at_kst:
        publish_at = datetime.fromisoformat(args.publish_at_kst).replace(tzinfo=KST)
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
    response = request.execute()
    state[date_key] = {
        "video_id": response["id"],
        "privacy": status["privacyStatus"],
        "publish_at": status.get("publishAt"),
    }
    save_state(args.state, state)
    print(f"Uploaded {date_key}: https://youtube.com/shorts/{response['id']}")


if __name__ == "__main__":
    main()
