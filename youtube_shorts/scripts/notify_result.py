#!/usr/bin/env python3
"""Email the result of the scheduled daily Short using Gmail SMTP."""

from __future__ import annotations

import json
import os
import smtplib
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from pathlib import Path
from upload_ledger import persist, save_state


ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "youtube_shorts" / "state" / "uploads.json"


def build_message(date_kst: str, status: str, run_url: str, state_path: Path) -> EmailMessage:
    ledger_error = False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        if not isinstance(state, dict):
            raise ValueError("invalid ledger")
    except (OSError, ValueError):
        state, ledger_error = {}, True
    upload = state.get(date_kst, {}) if date_kst else {}
    if not isinstance(upload, dict):
        upload, ledger_error = {}, True
    video_id = upload.get("video_id")
    succeeded = bool(video_id)

    message = EmailMessage()
    label = date_kst.replace("-pm", " 오후 7시") if date_kst.endswith("-pm") else f"{date_kst} 오전 7시"
    message["Subject"] = f"{'성공' if succeeded else '확인 필요'}: Peace in Mind 쇼츠 ({label})"
    if succeeded:
        body = (
            f"등록 영수증 확인. 공개 지정: {upload.get('publish_at', '미기록')}\n"
            f"영상: https://youtube.com/shorts/{video_id}\n"
            f"후속 작업 상태: {status}. 실제 공개 여부는 YouTube 상태 확인이 필요합니다.\n"
        )
    elif upload:
        body = "업로드 완료 여부가 불확실하여 중복 방지를 위해 재업로드를 중지했습니다.\n"
    else:
        body = "오늘의 쇼츠 생성 또는 예약 게시가 완료되지 않았습니다.\n"
    if ledger_error:
        body = "업로드 원장을 읽을 수 없습니다. 기존 영상 확인 전 재업로드하지 마세요.\n"
    message.set_content(body + f"실행 결과: {run_url}\n실행 상태: {status}\n")
    return message


def notify(date_key: str, status: str, run_url: str, state_path: Path,
           sender: str, recipient: str, password: str) -> bool:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    record = state.get(date_key, {})
    if not isinstance(record, dict):
        record = {}
    succeeded = bool(record.get("video_id"))
    if succeeded and record.get("success_email", {}).get("status") in {"attempted", "sent"}:
        print(f"Success email already handled for {date_key}; skipping duplicate notification.")
        return False
    message = build_message(date_key, status, run_url, state_path)
    message["From"] = sender
    message["To"] = recipient
    # Retry connection/login only. Never retransmit after an uncertain SMTP send.
    for attempt in range(3):
        try:
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
            smtp.login(sender, password)
            break
        except (OSError, smtplib.SMTPException):
            if "smtp" in locals():
                smtp.close()
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    try:
        if succeeded:
            record["success_email"] = {"status": "attempted", "run_url": run_url,
                                       "at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
            save_state(state_path, state)
            persist(state_path)
        smtp.send_message(message)
        if succeeded:
            record["success_email"]["status"] = "sent"
            save_state(state_path, state)
            persist(state_path)
    finally:
        smtp.close()
    print(f"Release result email sent to {recipient}.")
    return True


def main() -> None:
    date_key = (os.environ.get("RUN_KEY") or os.environ.get("RUN_DATE_KST")
                or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    notify(date_key, os.environ.get("RUN_STATUS", "unknown"), os.environ["RUN_URL"], STATE_PATH,
           os.environ["SMTP_USER"], os.environ["NOTIFY_TO"], os.environ["SMTP_APP_PASSWORD"])


if __name__ == "__main__":
    main()
