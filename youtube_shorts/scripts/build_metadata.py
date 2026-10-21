#!/usr/bin/env python3
"""Create YouTube title and description metadata from a daily verse manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ATTRIBUTION = "성경전서 개역한글판, 대한성서공회"
WEBSITE = "https://appleap385-aaz0919.github.io/PeaceYourMind/"
PLAY_STORE = "https://play.google.com/store/apps/details?id=io.github.appleap385.peaceinmind"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Defaults to metadata.json beside the manifest")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "draft":
        parser.error("Expected an untouched draft manifest")

    daily_cta = "구절이 포함된 장 전체를 이어 읽고, 마음에 맞는 말씀과 찬양 영상도 살펴보세요."
    description = "\n".join([
        f"{manifest['reference']} — {manifest['text'].strip()}",
        "",
        daily_cta,
        "앱과 웹사이트는 채널 프로필 링크에서 확인하세요.",
        "",
        f"웹사이트: {WEBSITE}",
        f"안드로이드 앱: {PLAY_STORE}",
        "",
        ATTRIBUTION,
    ])
    payload = {
        "date_kst": manifest["date_kst"],
        "verse_id": manifest["verse_id"],
        "title": f"오늘의 말씀 | {manifest['reference']} #Shorts",
        "description": description,
        "language": "ko",
        "tags": ["성경말씀", "오늘의말씀", "성경구절", "말씀쇼츠", "Peace in Mind", "Shorts"],
        "status": "ready",
    }
    output = args.output or args.manifest.with_name("metadata.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Reviewed metadata draft: {output}")


if __name__ == "__main__":
    main()
