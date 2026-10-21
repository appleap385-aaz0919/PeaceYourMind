#!/usr/bin/env python3
"""Authorize the channel owner once for YouTube Shorts uploads."""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_secret", type=Path,
                        help="OAuth desktop client JSON downloaded from Google Cloud")
    parser.add_argument("--token-output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "token.local.json")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(str(args.client_secret), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    args.token_output.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Local upload authorization saved to {args.token_output}")
    print("This file is ignored by Git. Do not send it or add it to the repository.")


if __name__ == "__main__":
    main()
