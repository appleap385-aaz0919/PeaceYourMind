#!/usr/bin/env python3
"""Select a verified, non-crisis PYM verse deterministically for a KST date."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "verses.yaml"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "work"
TIMEZONE = ZoneInfo("Asia/Seoul")
ATTRIBUTION = "성경전서 개역한글판, 대한성서공회"


def target_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(TIMEZONE).date()


def load_verses(source: Path) -> list[dict]:
    with source.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("verses.yaml must be a mapping")

    # Crisis verses are deliberately excluded: a daily promotional Short must
    # never draw from the app's separately curated crisis content.
    pool = data.get("verses")
    if not isinstance(pool, list) or not pool:
        raise ValueError("verses.yaml has no regular verses")
    eligible = [
        item
        for item in pool
        if isinstance(item, dict)
        and item.get("verified") is True
        and all(isinstance(item.get(key), str) and item[key].strip() for key in ("id", "ref", "text"))
        # The requested daily format is one biblical verse, never a range.
        and re.search(r":\d+$", item["ref"].strip()) is not None
    ]
    if not eligible:
        raise ValueError("No verified regular verses are available")
    return eligible


def make_manifest(day: date, verses: list[dict]) -> dict:
    # Consecutive dates select consecutive entries, so the single-verse pool is
    # exhausted before any verse repeats. YAML order remains the editorial order.
    selected = verses[(day.toordinal() - 1) % len(verses)]
    return {
        "date_kst": day.isoformat(),
        "verse_id": selected["id"],
        "reference": selected["ref"],
        "text": selected["text"].strip(),
        "translation": ATTRIBUTION,
        "cta": "이 구절이 담긴 장을 이어 읽고, 마음에 맞는 말씀과 찬양 영상도 만나보세요.",
        "profile_cta": "Peace in Mind 앱과 웹사이트는 채널 프로필 링크에서 확인하세요.",
        "profile_links": {
            "website": "https://appleap385-aaz0919.github.io/PeaceYourMind/",
            "android": "https://play.google.com/store/apps/details?id=io.github.appleap385.peaceinmind",
        },
        "status": "draft",
        "publish_blockers": ["configure Google Cloud TTS and channel-owner OAuth"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="KST calendar date, YYYY-MM-DD (defaults to today)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    day = target_date(args.date)
    verses = load_verses(args.source)
    manifest = make_manifest(day, verses)
    target = args.output_dir / f"{day.isoformat()}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Draft manifest: {target}")
    print(f"{manifest['reference']} · {manifest['verse_id']} · {len(verses)} verified verses · KST {day}")


if __name__ == "__main__":
    main()
