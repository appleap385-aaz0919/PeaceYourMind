#!/usr/bin/env python3
"""Email the result of the scheduled daily Short using Gmail SMTP."""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "youtube_shorts" / "state" / "uploads.json"


def build_message(date_kst: str, status: str, run_url: str, state_path: Path) -> EmailMessage:
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    upload = state.get(date_kst, {}) if date_kst else {}
    video_id = upload.get("video_id")
    succeeded = status == "success" and bool(video_id)

    message = EmailMessage()
    message["Subject"] = f"{'성공' if succeeded else '확인 필요'}: 오늘의 Peace in Mind 쇼츠 ({date_kst or '날짜 미확인'})"
    message.set_content(
        "오늘의 유튜브 쇼츠가 오전 7시(KST) 공개 예약되었습니다.\n"
        f"영상: https://youtube.com/shorts/{video_id}\n"
        f"실행 결과: {run_url}\n"
        if succeeded
        else "오늘의 쇼츠 생성 또는 예약 게시가 완료되지 않았습니다.\n"
        f"실행 결과와 오류 확인: {run_url}\n"
        f"실행 상태: {status}\n"
    )
    return message


def main() -> None:
    sender = os.environ["SMTP_USER"]
    recipient = os.environ["NOTIFY_TO"]
    password = os.environ["SMTP_APP_PASSWORD"]
    date_kst = os.environ.get("RUN_DATE_KST", "")
    run_url = os.environ["RUN_URL"]
    status = os.environ.get("RUN_STATUS", "unknown")

    message = build_message(date_kst, status, run_url, STATE_PATH)
    message["From"] = sender
    message["To"] = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    print(f"Daily result email sent to {recipient}.")


if __name__ == "__main__":
    main()
