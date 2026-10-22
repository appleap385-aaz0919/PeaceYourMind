"""Small standard-library OAuth and YouTube API helpers for this project."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
CONFIG_PATH = STATE / "config.local.json"


def load_local_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError("state/config.local.json is missing; copy the example and set the life-tips channel ID")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def state_path(config: dict[str, Any], key: str, default: str) -> Path:
    value = str(config.get(key, default))
    path = (ROOT / value).resolve()
    if path != STATE.resolve() and STATE.resolve() not in path.parents:
        raise ValueError(f"{key} must point inside youtube_life_tips/state")
    return path


def load_oauth_client(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Google OAuth desktop client file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    details = payload.get("installed") or payload.get("web") or {}
    if not details.get("client_id") or not details.get("client_secret"):
        raise ValueError("OAuth client JSON does not contain client_id/client_secret")
    return {
        "client_id": details["client_id"],
        "client_secret": details["client_secret"],
        "auth_uri": details.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth"),
        "token_uri": details.get("token_uri", "https://oauth2.googleapis.com/token"),
    }


def post_form(url: str, values: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(values).encode("ascii")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"Google OAuth request failed ({exc.code}): {detail}") from exc


def save_token(path: Path, token: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2), encoding="utf-8")


def get_access_token(client: dict[str, str], token_path: Path) -> str:
    if not token_path.is_file():
        raise FileNotFoundError("YouTube OAuth token is missing; run authorize_youtube.py once")
    token = json.loads(token_path.read_text(encoding="utf-8"))
    if token.get("access_token") and float(token.get("expires_at", 0)) > time.time() + 90:
        return token["access_token"]
    refresh = token.get("refresh_token")
    if not refresh:
        raise ValueError("OAuth token has no refresh_token; run authorize_youtube.py again")
    refreshed = post_form(client["token_uri"], {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    })
    token.update(refreshed)
    token["refresh_token"] = refresh
    token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    save_token(token_path, token)
    return token["access_token"]


def api_json(url: str, access_token: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1500]
        raise RuntimeError(f"YouTube API request failed ({exc.code}): {detail}") from exc


def my_channels(access_token: str) -> list[dict[str, str]]:
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
    payload = api_json(url, access_token)
    return [
        {"id": item["id"], "title": item.get("snippet", {}).get("title", "")}
        for item in payload.get("items", [])
    ]
