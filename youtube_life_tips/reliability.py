"""Local durable records, process locks, and bounded transient-error handling."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import uuid
from contextlib import contextmanager
from pathlib import Path


class RetryableError(RuntimeError):
    pass


def is_transient(error: BaseException | str) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {408, 429, 500, 502, 503, 504}
    if isinstance(error, (RetryableError, TimeoutError, ConnectionError, urllib.error.URLError)):
        return True
    text = str(error).lower()
    return bool(re.search(r"\b(408|429|500|502|503|504)\b", text)) or any(
        word in text for word in ("timed out", "timeout", "temporarily unavailable", "connection reset",
                                 "connection aborted", "connection refused", "name resolution",
                                 "cannot connect", "network is unreachable", "remote end closed")
    )


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_receipt(path: Path, day: str, channel_id: str | None = None, slot: str = "am") -> dict | None:
    if not path.exists():
        return None
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(receipt, dict) or receipt.get("date") != day
            or receipt.get("slot", "am") != slot
            or not isinstance(receipt.get("video_id"), str) or not receipt["video_id"]
            or not receipt.get("channel_id")
            or (channel_id and receipt["channel_id"] != channel_id)):
        raise ValueError("invalid upload receipt; reconcile before attempting another upload")
    return receipt


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
