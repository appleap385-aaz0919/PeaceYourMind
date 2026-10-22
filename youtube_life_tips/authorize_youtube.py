"""Authorize this local folder for the separately selected life-tips channel."""

from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from youtube_auth import load_local_config, load_oauth_client, my_channels, save_token, state_path, post_form


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}
    expected_state = ""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        if state != self.expected_state:
            # Browsers/extensions can make unrelated requests to the callback
            # origin. Ignore them and keep listening for this run's OAuth state.
            self.send_response(204)
            self.end_headers()
            return
        CallbackHandler.result = {
            "code": query.get("code", [""])[0],
            "error": query.get("error", [""])[0],
        }
        CallbackHandler.ready.set()
        self.send_response(200 if CallbackHandler.result["code"] else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<p>인증이 완료되었습니다. 이 창을 닫으셔도 됩니다.</p>".encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-file", help="OAuth desktop client JSON; copied under state/")
    args = parser.parse_args()
    config = load_local_config()
    client_path = state_path(config, "oauth_client_file", "state/google_oauth_client.json")
    if args.client_file:
        candidate = Path(args.client_file).resolve()
        state_dir = (Path(__file__).resolve().parent / "state").resolve()
        if candidate != state_dir and state_dir not in candidate.parents:
            raise ValueError("OAuth client file must be inside youtube_life_tips/state")
        client_path = candidate
    token_path = state_path(config, "oauth_token_file", "state/youtube_token.json")
    client = load_oauth_client(client_path)

    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(24)

    CallbackHandler.result = {}
    CallbackHandler.ready = threading.Event()
    CallbackHandler.expected_state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler)
    # Consent can take several minutes. Poll repeatedly so unrelated requests
    # or callbacks from an older attempt do not end the current login flow.
    callback_deadline = time.monotonic() + 20 * 60
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    auth_query = urllib.parse.urlencode({
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"{client['auth_uri']}?{auth_query}"
    print("브라우저에서 생활꿀팁 채널에 사용할 Google 계정을 선택해 인증해 주세요.")
    print("인증 주소를 여는 중입니다. 토큰과 클라이언트 비밀값은 출력하지 않습니다.")
    print("이 PowerShell 창을 열어 두고, 방금 열린 인증 창에서 절차를 완료해 주세요 (최대 20분 대기).")
    if not webbrowser.open(auth_url):
        print(auth_url)
    try:
        while not CallbackHandler.ready.is_set():
            remaining = callback_deadline - time.monotonic()
            if remaining <= 0:
                break
            server.timeout = min(30, remaining)
            server.handle_request()
    finally:
        server.server_close()
    if not CallbackHandler.result.get("code"):
        error = CallbackHandler.result.get("error")
        if error:
            raise RuntimeError(f"OAuth was cancelled or denied by Google: {error}")
        raise RuntimeError("No matching Google OAuth callback arrived within 20 minutes")

    exchanged = post_form(client["token_uri"], {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "code": CallbackHandler.result["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    exchanged["expires_at"] = time.time() + int(exchanged.get("expires_in", 3600))
    channels = my_channels(exchanged["access_token"])
    save_token(token_path, exchanged)
    print("인증된 채널 목록:")
    for channel in channels:
        print(f"- {channel['title']}  (channel ID: {channel['id']})")
    target = config.get("youtube_channel_id", "")
    if target and target != "REPLACE_WITH_LIFE_TIPS_CHANNEL_ID":
        if not any(channel["id"] == target for channel in channels):
            raise RuntimeError("configured youtube_channel_id is not among the authenticated channels")
        print("설정된 생활꿀팁 채널과 일치합니다. 예약 작업에서 이 토큰을 사용할 수 있습니다.")
    else:
        print("state/config.local.json에 생활꿀팁 채널 ID를 지정해야 자동 게시가 활성화됩니다.")


if __name__ == "__main__":
    main()
