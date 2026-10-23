"""Persist a YouTube upload session and resume from server-confirmed bytes."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from reliability import RetryableError, atomic_json, is_transient


def fingerprint(video: Path, metadata: dict) -> str:
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=True).encode())
    with video.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def header(headers: dict, name: str) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def confirmed_offset(headers: dict, total: int) -> int:
    value = header(headers, "range")
    if value is None:
        return 0
    match = re.fullmatch(r"bytes=0-(\d+)", value)
    if not match or not 0 < int(match[1]) + 1 <= total:
        raise ValueError("invalid server upload Range; refusing to guess the next byte")
    return int(match[1]) + 1


def recovered_receipt(day_dir: Path) -> dict | None:
    if (day_dir / "upload.json").exists():
        return None
    session_path = day_dir / "upload_session.json"
    if not session_path.exists():
        return None
    session = json.loads(session_path.read_text(encoding="utf-8"))
    response = session.get("response", {})
    context = session.get("receipt_context", {})
    if not response.get("id") or not context.get("date") or not context.get("channel_id"):
        return None
    if context["date"] != day_dir.name:
        raise ValueError("saved upload response date mismatch")
    result = {**context, "video_id": response["id"],
              "url": f"https://www.youtube.com/shorts/{response['id']}"}
    atomic_json(day_dir / "upload.json", result)
    return result


def upload(video: Path, metadata: dict, token: str, *, api_call, chunk_size: int,
           session_path: Path, receipt_context: dict, deadline: datetime | None = None) -> dict:
    total = video.stat().st_size
    identity = fingerprint(video, metadata)
    session = json.loads(session_path.read_text(encoding="utf-8")) if session_path.exists() else {}
    if session and (session.get("fingerprint") != identity or session.get("receipt_context") != receipt_context):
        raise ValueError("upload session belongs to different content/channel; reconcile before replacing it")
    if session.get("response", {}).get("id"):
        return session["response"]
    if session.get("url") and not session["url"].startswith("https://www.googleapis.com/"):
        raise ValueError("unexpected saved upload URL")

    def within_deadline():
        if deadline and datetime.now(deadline.tzinfo) >= deadline:
            raise RuntimeError("upload deadline reached; retained session for reconciliation")

    def request_with_retry(request):
        for attempt in range(4):
            try:
                return api_call(request)
            except Exception as exc:
                if not is_transient(exc) or attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    if not session.get("url"):
        within_deadline()
        # No media bytes are sent until the session URL has been saved locally.
        initiate = urllib.request.Request(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(total)}, method="POST")
        _, headers, _ = request_with_retry(initiate)
        url = header(headers, "location")
        if not url or not url.startswith("https://www.googleapis.com/"):
            raise ValueError("missing or unexpected resumable upload URL")
        session = {"url": url, "fingerprint": identity, "receipt_context": receipt_context}
        atomic_json(session_path, session)
        offset = 0
    else:
        offset = None  # Always query the server after restart; local offsets are not authoritative.

    failures = 0
    high_water = 0
    with video.open("rb") as stream:
        while True:
            querying = offset is None or offset == total
            if querying:
                request = urllib.request.Request(session["url"], data=b"", headers={
                    "Authorization": f"Bearer {token}", "Content-Length": "0",
                    "Content-Range": f"bytes */{total}"}, method="PUT")
            else:
                within_deadline()
                stream.seek(offset)
                chunk = stream.read(chunk_size)
                request = urllib.request.Request(session["url"], data=chunk, headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{total}"}, method="PUT")
            try:
                status, headers, body = api_call(request)
            except Exception as exc:
                if not is_transient(exc):
                    # In particular, never silently replace an expired/unknown session with a new upload.
                    raise
                failures += 1
                if failures > 3:
                    raise RetryableError("upload temporarily unavailable; saved session will be queried on retry") from exc
                time.sleep(2 ** (failures - 1))
                offset = None
                continue
            if status in (200, 201):
                response = json.loads(body)
                if not response.get("id"):
                    raise ValueError("completed upload response has no video ID")
                response_channel = response.get("snippet", {}).get("channelId")
                if response_channel and response_channel != receipt_context.get("channel_id"):
                    raise ValueError("upload response channel mismatch; reconcile before retry")
                session["response"] = response
                atomic_json(session_path, session)
                return response
            if status != 308:
                raise RuntimeError(f"unexpected resumable upload status: {status}")
            next_offset = confirmed_offset(headers, total)
            if next_offset == total or (not querying and next_offset <= offset):
                failures += 1
                if failures > 3:
                    raise RetryableError("upload made no confirmed progress; saved session retained")
                time.sleep(2 ** (failures - 1))
            elif next_offset > high_water:
                failures = 0
                high_water = next_offset
            offset = next_offset
