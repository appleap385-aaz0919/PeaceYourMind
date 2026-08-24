#!/usr/bin/env python
"""HANDOFF.md의 규모 수치를 **실측해서 채운다** — 네트워크·API 호출 없음.

    python scripts/stats.py            실측값을 표로 출력한다
    python scripts/stats.py --write    HANDOFF.md의 표시 구간을 갱신한다
    python scripts/stats.py --check    문서와 실측이 다르면 종료 코드 1  ← 게이트

[왜 만들었나 — 2026-08-24]
    같은 수치가 HANDOFF 1절과 3절에 손으로 두 번 적혀 있었고, 갈라졌다.

        장 본문   1절 174개 장 4,283절 · 3절 178개 장      실측 178개 장 4,442절
        앱 테스트  1절 105건(+Phase 3줄 61건) · 3절 110건   실측 110건
        구절      양쪽 다 "293 (감정 283 + 위기 10)"        실측 감정 293 + 위기 10 = 303

    구절은 **양쪽이 똑같이 틀렸다.** 한쪽을 고치고 다른 쪽을 잊은 것이 아니라,
    한 번 잘못 적힌 값이 복사돼 두 곳에 남은 것이다. 어느 쪽이 최신인지
    문서만 봐서는 가릴 수 없었고, 그래서 "3절이 최신으로 보인다"는 추정이 나왔다.
    **추정이 필요했다는 것 자체가 결함이다.**

[그래서 여기서 정하는 것과 정하지 않는 것을 가른다]
    여기서 정한다       저장소 파일만 읽으면 언제나 같은 답이 나오는 것
                       (구절·장·어휘·채널·테스트 수)
    여기서 정하지 않는다  코퍼스에 따라 매일 달라지는 것
                       (주제별 풀 크기 · 폴백 비율 · 총 노출)
                       이런 값은 **적는 순간 낡는다.** 문서에는 숫자 대신
                       측정 명령과 "언제 어느 코퍼스로 쟀는지"를 남긴다.
                       근거는 HANDOFF 2.42절(retag --screens의 유효 범위)이다.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.allowlist import MIN_ALLOWLIST_SIZE, load_allowlist  # noqa: E402
from lib.channel_blocklist import load_channel_blocklist  # noqa: E402
from lib.krv_source import KrvBible, parse_ref  # noqa: E402
from lib.reviewed_out import load_reviewed_out  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "HANDOFF.md"
APP_TEST_DIR = ROOT / "app" / "test"
EXIT_OK, EXIT_FAIL = 0, 1

BEGIN = "<!-- STATS:BEGIN 규모 -->"
END = "<!-- STATS:END -->"
NOTE = "<!-- scripts/stats.py --write 로 생성한다. 손으로 고치지 말 것. -->"

# 파이썬 게이트 — 이 목록이 곧 "게이트 N종"의 근거다.
PY_GATES = (
    "verify_verses.py --check",
    "fill_verses.py --verify",
    "tagging_test.py",
    "spread_test.py",
    "messages_test.py",
)
# 줄 첫머리의 test( 만 센다. node:test 러너는 중첩 호출을 따로 세지 않으므로
# 이 방식이 러너의 집계와 같다 (2026-08-24 대조: 정적 110 = 러너 110).
_APP_TEST = re.compile(r"^\s*test\(", re.MULTILINE)


def _is_psalm(ref: str) -> bool:
    return ref.startswith("시편")


def measure() -> dict[str, Any]:
    """저장소 파일만 읽어 규모를 잰다. 같은 커밋이면 언제나 같은 답이다."""
    raw = yaml.safe_load((ROOT / "verses.yaml").read_text(encoding="utf-8"))
    emotion, crisis = raw["verses"], raw["crisis"]
    every = emotion + crisis

    bible = KrvBible(ROOT / "data" / "krv" / "bible_1961_krv.json")
    chapters: dict[tuple[str, int], int] = {}
    for verse in emotion:  # 장 본문은 감정 풀에서만 뽑는다 (gen_krv_chapters.py 참조)
        ref = parse_ref(verse["ref"])
        key = (ref.book_key, ref.start[0])
        chapters[key] = len(bible.chapter_verses(ref.book_key, ref.start[0]))

    themes = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    theme_kw = sum(len(t.get("title_keywords") or []) for t in themes["themes"])
    media_kw = sum(len(m.get("title_keywords") or []) for m in themes["media_types"])

    taxonomy = yaml.safe_load((ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))
    subs = [s for c in taxonomy["categories"] for s in (c.get("subcategories") or [])]
    emotion_kw = sum(len(s.get("keywords") or []) for s in subs)

    allowlist = load_allowlist(ROOT / "channel_allowlist.yaml")
    blocklist = load_channel_blocklist(ROOT / "channel_blocklist.yaml")
    reviewed = load_reviewed_out(ROOT / "channel_reviewed_out.yaml")

    app_tests = sum(
        len(_APP_TEST.findall(path.read_text(encoding="utf-8")))
        for path in sorted(APP_TEST_DIR.glob("*.test.js"))
    )

    return {
        "emotion": len(emotion),
        "crisis": len(crisis),
        "verses": len(every),
        "excluded": len(raw.get("excluded") or []),
        # 시편 비율은 **감정 풀 기준**이다 — 2.39·2.41절의 장르 분포 논의가
        # 감정 화면을 대상으로 하고, 위기 풀은 화면 구성이 다르기 때문이다.
        "psalms": sum(1 for v in emotion if _is_psalm(v["ref"])),
        "read_from": sum(1 for v in every if v.get("read_from")),
        "chapters": len(chapters),
        "chapter_verses": sum(chapters.values()),
        "books": len({book for book, _ in chapters}),
        "themes": len(themes["themes"]),
        "theme_kw": theme_kw,
        "media_kw": media_kw,
        "categories": len(taxonomy["categories"]),
        "subcategories": len(subs),
        "emotion_kw": emotion_kw,
        "allowlist": allowlist.size,
        "blocklist": len(blocklist.channels),
        "reviewed_out": len(reviewed.channels),
        "py_gates": len(PY_GATES),
        "app_tests": app_tests,
    }


def render(m: dict[str, Any]) -> str:
    """HANDOFF에 넣을 블록. 서식의 정의는 여기 한 곳뿐이다."""
    psalm_rate = m["psalms"] / m["emotion"] * 100
    room = m["allowlist"] - MIN_ALLOWLIST_SIZE
    tail = (
        " = MIN_ALLOWLIST_SIZE (한 건만 빠져도 경보)"
        if room == 0
        else f" (하한 {MIN_ALLOWLIST_SIZE}까지 여유 {room})"
    )
    lines = [
        BEGIN,
        NOTE,
        "```",
        f"구절       {m['verses']}  = 감정 {m['emotion']} + 위기 {m['crisis']}",
        f"           감정 중 시편 {m['psalms']} ({psalm_rate:.1f}%)"
        f" · 비시편 {m['emotion'] - m['psalms']}",
        f"           read_from 지정 {m['read_from']}건"
        f" · 검토 후 제외 {m['excluded']}건",
        f"장 본문     {m['chapters']}개 장 {m['chapter_verses']:,}절 ({m['books']}권)"
        " — 감정 구절이 닿는 장만",
        "           app/public/krv/ · .gitignore 대상 · 매 빌드 재생성",
        f"주제       {m['themes']}개 · 제목 어휘 {m['theme_kw']}"
        f" · 형식 어휘 {m['media_kw']}",
        f"감정 분류   대분류 {m['categories']} · 세분류 {m['subcategories']}"
        f" · 키워드 {m['emotion_kw']}",
        f"채널       allowlist {m['allowlist']}{tail}",
        f"           blocklist {m['blocklist']} · reviewed_out {m['reviewed_out']}",
        f"게이트      파이썬 {m['py_gates']}종 + 앱 {m['app_tests']}건",
        "```",
        END,
    ]
    return "\n".join(lines)


# 표지는 **줄 전체**일 때만 인정한다.
#   2026-08-24: 2.43절 본문이 표지 문자열을 인용했더니 파서가 그것을 구간 시작으로
#   잡아 문서 90줄을 통째로 삼켰다. 문서가 자기 표지를 설명하는 것은 정상이므로
#   파서 쪽을 조인다. 회귀는 --check가 잡는다 — HANDOFF 2.43절이 지금도 표지를
#   본문에서 인용하고 있어서, 이 정규식이 느슨해지면 --check가 바로 깨진다.
_BEGIN_LINE = re.compile(rf"^{re.escape(BEGIN)}$", re.MULTILINE)
_END_LINE = re.compile(rf"^{re.escape(END)}$", re.MULTILINE)


def _regions(text: str) -> list[tuple[int, int]]:
    """표시 구간을 전부 찾는다. 여러 곳에 같은 블록을 둘 수 있다."""
    spans, at = [], 0
    while True:
        begin = _BEGIN_LINE.search(text, at)
        if not begin:
            return spans
        end = _END_LINE.search(text, begin.end())
        if not end:
            raise ValueError(f"{BEGIN} 뒤에 {END} 줄이 없다")
        spans.append((begin.start(), end.end()))
        at = end.end()


def _apply(text: str, block: str) -> str:
    for start, stop in reversed(_regions(text)):
        text = text[:start] + block + text[stop:]
    return text


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="HANDOFF 규모 수치 실측")
    parser.add_argument("--write", action="store_true", help="HANDOFF.md를 갱신한다")
    parser.add_argument("--check", action="store_true", help="다르면 종료 코드 1")
    args = parser.parse_args(argv)

    block = render(measure())
    if not (args.write or args.check):
        print(block)
        return EXIT_OK

    text = HANDOFF.read_text(encoding="utf-8")
    spans = _regions(text)
    if not spans:
        print(f"{HANDOFF.name}에 {BEGIN} 구간이 없다", file=sys.stderr)
        return EXIT_FAIL

    updated = _apply(text, block)
    if args.write:
        if updated == text:
            print(f"{HANDOFF.name} 변경 없음 — 이미 실측과 같다 (구간 {len(spans)}개)")
        else:
            HANDOFF.write_text(updated, encoding="utf-8")
            print(f"{HANDOFF.name} 갱신 — 구간 {len(spans)}개")
        return EXIT_OK

    if updated != text:
        print("문서의 규모 수치가 실측과 다르다.", file=sys.stderr)
        print("  python scripts/stats.py --write  로 맞춘다.", file=sys.stderr)
        print("\n[실측]")
        print(block)
        return EXIT_FAIL

    print(f"규모 수치 일치 — 구간 {len(spans)}개")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
