#!/usr/bin/env python3
"""verses.yaml -> verses.json (앱 번들용) 생성. API 소모 0.

    python scripts/gen_verses_json.py
    python scripts/gen_verses_json.py --dry-run     # 쓰지 않고 결과만 보여준다
    python scripts/gen_verses_json.py --out PATH

무엇을 하는가
    1. verses.yaml을 읽어 원문 대조 게이트를 다시 통과하는지 확인한다
       (verified: false가 하나라도 있으면 생성하지 않는다)
    2. 큐레이션 메타(note · verified · verified_by · verified_at)를 제거한다
    3. crisis를 최상위로 분리해 내보낸다 (PLAN.md 4.1 · 4.2)
    4. 개수·주제·태그를 단언한 뒤 JSON을 쓴다

왜 note를 빼는가
    note는 선정 근거와 검수 이력이다 — 사람이 읽는 큐레이션 자산이지
    앱이 쓰는 데이터가 아니다. 앱 번들에 넣으면 용량만 늘고, 내부 판단
    기록(예: "번영신학 오용이 많은 구절이다")이 사용자에게 노출된다.
    소스(verses.yaml)에는 그대로 남는다.

왜 crisis를 최상위로 분리하는가
    위기 구절은 감정 매핑을 타지 않는 별도 고정 큐레이션이다(PLAN.md 7절).
    PLAN 4.2가 videos.json에 정한 "crisis 최상위 분리 + 빌드 시 교차 검증
    단언"과 같은 구조다. 한 배열에 섞어 넣고 필드로 구분하면, 앱에서
    필터를 한 번 빠뜨리는 순간 위기 구절이 일반 화면에 뜬다.
    구조로 막으면 그 실수가 불가능해진다.

게이트 (하나라도 걸리면 파일을 쓰지 않는다)
    - verified: false 구절이 있다
    - 감정/위기 풀 분리가 깨졌다 (verify_verses.py와 같은 규칙)
    - 출력 개수가 입력 개수와 다르다 (생성 중 유실)
    - 출력 개수가 기대치와 다르다 (--expect-verses / --expect-crisis)
    - theme이 themes.yaml에 없다
    - emotion_tags가 themes.yaml mapping에 없는 세분류를 가리킨다
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from verify_verses import (  # noqa: E402
    CRISIS_PREFIX,
    CRISIS_THEME,
    check_crisis_separation,
)
from lib.krv_source import KrvBible, normalize_ws, parse_ref  # noqa: E402
from lib.verses_io import VersesFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VERSES_PATH = ROOT / "verses.yaml"
THEMES_PATH = ROOT / "themes.yaml"
KRV_PATH = ROOT / "data" / "krv" / "bible_1961_krv.json"
DEFAULT_OUT = ROOT / "app" / "src" / "data" / "verses.json"

# 앱 번들에 남기는 필드. 이 목록에 없는 것은 전부 제거된다.
APP_FIELDS = ("id", "ref", "text", "emotion_tags", "theme")
CRISIS_APP_FIELDS = ("id", "ref", "text")

# 기대 개수 — 현재 큐레이션 규모.
#
# 이 값을 두는 이유는 "생성이 조용히 줄어드는 것"을 막기 위해서다.
# 입출력 개수 비교(구조적 검사)는 유실을 잡지만, verses.yaml 자체가
# 잘못 편집돼 구절이 사라진 경우는 잡지 못한다 — 입력이 이미 줄었기 때문이다.
# 큐레이션을 늘리거나 줄일 때는 이 값도 함께 고친다.
#
# [2026-08-19~ 확장 중] 세분류당 10 → 10~15로 넓히는 작업이 진행 중이다
# (PLAN.md 3.2 · HANDOFF 2.24). 목표는 감정 305건이고 계열 단위로 나눠 올린다.
# **이 값을 부등호(>=)로 바꾸지 말 것** — 매 배치마다 손으로 고치는 마찰이
# "이번에 몇 건을 의도적으로 늘렸는가"를 확인시키는 장치다. 확장이 끝나면
# 최종값에서 다시 고정된다.
#   240  Phase 1 완료 시점
#   242  anxiety.worry +2 (눅 12:7 · 시 68:19)
#   245  anxiety.tension +2 (출 14:14 · 마 10:19) · restless +1 (전 3:1)
#   256  sadness.sorrow +5 · lonely +2 · loss +4
#   264  exhaustion.tired +3 · burnout +4 · listless +1
EXPECT_VERSES = 264
EXPECT_CRISIS = 10

EXIT_OK = 0
EXIT_FAILED = 1


class BuildError(RuntimeError):
    """생성 전 검사에서 걸렸다. 파일을 쓰지 않는다."""


def strip_entry(entry: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """앱이 쓰는 필드만 남기고 text의 공백을 정규화한다.

    text 정규화가 필요한 이유: verses.yaml은 폴디드 스칼라(`>`)로 본문을
    담는데, YAML은 그 값 끝에 개행을 붙이고 줄바꿈을 공백으로 편다.
    소스에서는 문제가 없지만(verify_verses.py도 정규화 후 비교한다)
    그대로 JSON에 넣으면 앱이 받는 문자열 끝에 "\\n"이 붙는다.

    normalize_ws는 연속 공백을 하나로 줄이고 양끝을 다듬을 뿐 글자를
    바꾸지 않는다 — 동일성유지권 관점에서 안전한 범위다. 정규화 결과가
    원문과 같은지는 assert_matches_source()가 다시 확인한다.

    필드 순서를 고정해 diff를 읽기 쉽게 한다.
    """
    out: dict[str, Any] = {}
    for key in fields:
        if key not in entry:
            continue
        out[key] = normalize_ws(str(entry[key])) if key == "text" else entry[key]
    return out


def assert_matches_source(bundle: dict[str, Any], bible: KrvBible) -> None:
    """앱에 나가는 본문이 개역한글 원문과 글자 단위로 같은지 최종 확인한다.

    verify_verses.py가 이미 같은 검사를 하지만, 여기서 다시 하는 이유는
    **검사 대상이 다르기 때문**이다. verify_verses는 verses.yaml의 값을 보고,
    이 함수는 JSON에 실제로 들어간 문자열을 본다. 그 사이에 strip_entry의
    정규화가 끼어 있다. 정규화가 본문을 건드리면 여기서 걸린다.
    """
    for entry in bundle["verses"] + bundle["crisis"]:
        parts = bible.verses_in_range(parse_ref(entry["ref"]))
        original = normalize_ws(" ".join(text for _, _, text in parts))
        if entry["text"] != original:
            raise BuildError(
                f"{entry['id']}: 번들 본문이 원문과 다르다\n"
                f"    원문: {original}\n"
                f"    번들: {entry['text']}"
            )


def load_theme_ids(path: Path) -> tuple[set[str], set[str]]:
    """themes.yaml에서 주제 id와 감정 세분류 id를 읽는다."""
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    themes = {str(t["id"]) for t in (raw.get("themes") or [])}
    subcategories = set(raw.get("mapping") or {})
    return themes, subcategories


def validate(
    verses_file: VersesFile,
    theme_ids: set[str],
    subcategory_ids: set[str],
    *,
    expect_verses: int,
    expect_crisis: int,
) -> list[str]:
    """생성 전 전수 검사. 걸린 사유를 전부 모아 돌려준다."""
    problems: list[str] = []

    unverified = [v["id"] for v in verses_file.entries if not v.get("verified")]
    if unverified:
        problems.append(
            f"verified: false 구절 {len(unverified)}건 — {', '.join(unverified[:5])}"
            + (" ..." if len(unverified) > 5 else "")
            + "  (검수를 통과하지 않은 구절은 앱에 넣지 않는다)"
        )

    problems.extend(check_crisis_separation(verses_file))

    if len(verses_file.verses) != expect_verses:
        problems.append(
            f"감정 풀 {len(verses_file.verses)}건 — 기대 {expect_verses}건과 다르다 "
            "(--expect-verses로 조정하거나 큐레이션을 확인할 것)"
        )
    if len(verses_file.crisis) != expect_crisis:
        problems.append(
            f"위기 풀 {len(verses_file.crisis)}건 — 기대 {expect_crisis}건과 다르다 "
            "(--expect-crisis로 조정하거나 큐레이션을 확인할 것)"
        )

    for verse in verses_file.verses:
        theme = verse.get("theme")
        if theme not in theme_ids:
            problems.append(f"{verse['id']}: themes.yaml에 없는 theme {theme!r}")
        for tag in verse.get("emotion_tags") or []:
            if tag not in subcategory_ids:
                problems.append(
                    f"{verse['id']}: themes.yaml mapping에 없는 세분류 {tag!r}"
                )

    empty = [v["id"] for v in verses_file.entries if not str(v.get("text", "")).strip()]
    if empty:
        problems.append(f"text가 빈 구절 {len(empty)}건 — {', '.join(empty[:5])}")

    return problems


def build(verses_file: VersesFile, theme_ids: set[str], now: datetime) -> dict[str, Any]:
    """앱 번들 구조를 만든다.

    themes는 실제로 쓰인 주제만 담는다 — 앱이 빈 주제 화면을 만들지 않도록.
    crisis_fixed는 감정 매핑을 타지 않으므로 여기 넣지 않는다.
    """
    used_themes = sorted({v["theme"] for v in verses_file.verses})
    return {
        "translation": verses_file.translation,
        "source_version": verses_file.version,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": "성경전서 개역한글판, 대한성서공회",
        "themes": used_themes,
        "verses": [strip_entry(v, APP_FIELDS) for v in verses_file.verses],
        "crisis": [strip_entry(v, CRISIS_APP_FIELDS) for v in verses_file.crisis],
    }


def assert_no_loss(bundle: dict[str, Any], verses_file: VersesFile) -> None:
    """생성 중 유실이 없었는지 확인한다.

    개수뿐 아니라 id 집합까지 본다 — 같은 수의 다른 구절이 나오는 결함은
    개수만으로는 잡히지 않는다.
    """
    for key, source in (("verses", verses_file.verses), ("crisis", verses_file.crisis)):
        built_ids = [e["id"] for e in bundle[key]]
        source_ids = [e["id"] for e in source]
        if built_ids != source_ids:
            raise BuildError(
                f"{key}: 생성 결과가 원본과 다르다 "
                f"(원본 {len(source_ids)}건, 생성 {len(built_ids)}건)"
            )

    leaked = sorted(
        key
        for entry in bundle["verses"] + bundle["crisis"]
        for key in entry
        if key not in set(APP_FIELDS)
    )
    if leaked:
        raise BuildError(f"앱 번들에 큐레이션 메타가 남았다: {sorted(set(leaked))}")

    for entry in bundle["crisis"]:
        if not entry["id"].startswith(CRISIS_PREFIX):
            raise BuildError(f"crisis 배열에 일반 id가 있다: {entry['id']}")
        if "emotion_tags" in entry or "theme" in entry:
            raise BuildError(f"crisis 항목에 감정 매핑 필드가 남았다: {entry['id']}")


def report(bundle: dict[str, Any], out: Path, payload: str, dry_run: bool) -> None:
    verses, crisis = bundle["verses"], bundle["crisis"]
    print("=" * 72)
    print("verses.json 생성" + ("  (--dry-run: 쓰지 않음)" if dry_run else ""))
    print("=" * 72)
    print(f"  번역본        {bundle['translation']}")
    print(f"  출처 표기     {bundle['attribution']}")
    print(f"  감정 풀       {len(verses):3}건")
    print(f"  위기 풀       {len(crisis):3}건  (최상위 분리, theme/emotion_tags 없음)")
    print(f"  합계          {len(verses) + len(crisis):3}건")
    print(f"  주제          {len(bundle['themes'])}개  {', '.join(bundle['themes'])}")
    print(f"  크기          {len(payload.encode('utf-8')):,} 바이트")
    print(f"  제거한 필드   note · verified · verified_by · verified_at")
    print(f"  본문          공백 정규화 후 원문 재대조 통과")
    print(f"  출력          {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="verses.yaml에서 앱 번들용 verses.json을 생성한다 (API 소모 0)."
    )
    parser.add_argument("--verses", type=Path, default=VERSES_PATH)
    parser.add_argument("--themes", type=Path, default=THEMES_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--krv", type=Path, default=KRV_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="검사와 생성만 하고 파일을 쓰지 않는다"
    )
    parser.add_argument("--expect-verses", type=int, default=EXPECT_VERSES)
    parser.add_argument("--expect-crisis", type=int, default=EXPECT_CRISIS)
    parser.add_argument(
        "--indent", type=int, default=0,
        help="JSON 들여쓰기 (기본 0 = 압축. 앱 번들이므로 크기를 우선한다)",
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        verses_file = VersesFile(args.verses)
        theme_ids, subcategory_ids = load_theme_ids(args.themes)

        problems = validate(
            verses_file,
            theme_ids,
            subcategory_ids,
            expect_verses=args.expect_verses,
            expect_crisis=args.expect_crisis,
        )
        if problems:
            print("=" * 72, file=sys.stderr)
            print(f"생성 중단 — 검사에서 {len(problems)}건이 걸렸다", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            for message in problems:
                print("  X " + message, file=sys.stderr)
            print("파일을 쓰지 않았다.", file=sys.stderr)
            return EXIT_FAILED

        bundle = build(verses_file, theme_ids, datetime.now(timezone.utc))
        assert_no_loss(bundle, verses_file)
        assert_matches_source(bundle, KrvBible(args.krv))

        payload = json.dumps(
            bundle,
            ensure_ascii=False,
            indent=args.indent or None,
            separators=(",", ":") if not args.indent else None,
        )
        report(bundle, args.out, payload, args.dry_run)

        if not args.dry_run:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(payload + "\n", encoding="utf-8", newline="\n")
            print()
            print("생성 완료. app/src/data/verses.json은 .gitignore 대상이다 —")
            print("단일 소스는 verses.yaml이고 이 파일은 매 빌드마다 새로 만든다.")
        return EXIT_OK

    except BuildError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except Exception as exc:  # noqa: BLE001
        print(f"생성 실패: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
