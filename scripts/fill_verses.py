#!/usr/bin/env python3
"""verses.yaml의 빈 text를 개역한글 원문에서 추출해 채운다.

    python scripts/fill_verses.py             # text가 빈 구절만 채운다
    python scripts/fill_verses.py --dry-run   # 무엇을 채울지 보여주기만
    python scripts/fill_verses.py --verify    # 채워진 구절의 추출 경로를 검증

왜 타이핑하지 않고 추출하는가
-----------------------------
1차분 30건 중 **8건(27%)이 본문 오류**였고 전부 기억에 의존해 쓴 초안에서 나왔다.

    셀프 리뷰(표본 6건)  3건 — "이제" 누락 / 절 경계 오류 / "알찌어다"->"알지어다"
    스크립트 대조(24건)  5건 — 쉼표 / "저가" 추가 / 띄어쓰기 2 / "하시니라" 누락

유형이 쉼표·띄어쓰기·조사·옛 표기처럼 눈으로 읽어서는 걸리지 않는 층위에
몰려 있다. 사람이 한 번 더 보는 것으로는 이 오류율이 내려가지 않는다.
반면 추출한 문자열은 정의상 원문과 같다 — 오류가 원천 차단된다.

그래서 2차분부터 선정은 ref까지만 하고 text는 이 스크립트가 채운다.
verify_verses.py의 역할도 바뀐다: 검출기가 아니라 **안전망**이 된다.
추출 경로가 깨졌을 때(잘못된 ref, 파싱 결함, 데이터 교체)만 울린다.

지키는 것 두 가지
-----------------
1. **이미 채워진 text를 덮어쓰지 않는다.** 1차분 30건은 검수를 마쳤고 일부는
   사람이 웹 원문과 대조한 이력이 있다. 빈 것만 채운다.
2. **폴디드 스칼라(`>`) 형식을 유지한다.** 기존 구절과 같은 폭으로 접어
   diff가 읽히게 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.krv_source import KrvBible, RefError, normalize_ws, parse_ref  # noqa: E402
from lib.verses_io import VersesFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KRV_PATH = ROOT / "data" / "krv" / "bible_1961_krv.json"
VERSES_PATH = ROOT / "verses.yaml"

# 접기 폭 — 들여쓰기 6칸을 포함한 라인 전체 길이 기준.
# 1차분 실측: 본문 라인 57개의 길이가 43~46에 몰려 있고 최빈값이 43이다.
# 46을 상한으로 두면 기존 구절과 같은 결이 된다.
WRAP_WIDTH = 46
INDENT = 6


def fold(text: str) -> list[str]:
    """본문을 어절 단위로 접는다. 들여쓰기는 붙이지 않는다(호출부 담당).

    한 어절이 폭을 넘으면 그 줄만 넘치게 둔다 — 어절을 쪼개면 본문이
    바뀌는 것과 같아서다. YAML 폴디드 스칼라는 줄바꿈을 공백 하나로
    되돌리므로, 어디서 접든 값 자체는 변하지 않는다.
    """
    budget = WRAP_WIDTH - INDENT
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= budget:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def extract(verse: dict, bible: KrvBible) -> str:
    """ref가 가리키는 원문을 그대로 이어붙여 돌려준다."""
    ref = parse_ref(verse["ref"])
    parts = bible.verses_in_range(ref)
    return normalize_ws(" ".join(text for _, _, text in parts))


# ---------------------------------------------------------------------
# 모드
# ---------------------------------------------------------------------
def run_verify(verses_file: VersesFile, bible: KrvBible) -> int:
    """채워진 구절에 대해 추출 경로가 현재 text를 재현하는지 확인한다.

    추출이 옳다면 '지금 추출한 값'과 '이미 검수된 text'가 같아야 한다.
    다르면 추출 경로(ref 파싱·범위 조회·이어붙이기) 어딘가가 틀린 것이다.
    """
    targets = [v for v in verses_file.verses if not verses_file.text_is_empty(v["id"])]

    print("=" * 72)
    print("추출 경로 검증 - 채워진 구절 {}건".format(len(targets)))
    print("=" * 72)

    matched: list[str] = []
    failed: list[tuple[str, str, str, str]] = []

    for verse in targets:
        stored = normalize_ws(str(verse.get("text", "")))
        try:
            extracted = extract(verse, bible)
        except RefError as exc:
            failed.append((verse["id"], verse["ref"], "ref 오류: " + str(exc), stored))
            continue

        if extracted == stored:
            # 접기가 값을 바꾸지 않는지도 함께 본다.
            refolded = normalize_ws(" ".join(fold(extracted)))
            if refolded != extracted:
                failed.append((verse["id"], verse["ref"], "접기가 값을 바꿨다", stored))
            else:
                matched.append(verse["id"])
        else:
            failed.append((verse["id"], verse["ref"], extracted, stored))

    if failed:
        print()
        for verse_id, ref, extracted, stored in failed:
            print("  X {:12} {}".format(verse_id, ref))
            print("    추출 : " + extracted)
            print("    현재 : " + stored)
            print()

    print()
    print("[요약]")
    print("  일치    {:3}건".format(len(matched)))
    print("  불일치  {:3}건".format(len(failed)))

    if failed:
        print()
        print("=" * 72)
        print("추출 경로 검증 실패 - 이 상태로 2차분을 채우면 안 된다")
        print("=" * 72)
        return 1

    print()
    print("추출 경로 검증 통과: {}/{} 전건 일치".format(len(matched), len(targets)))
    print("추출한 본문이 검수 완료된 본문을 그대로 재현한다.")
    return 0


def run_fill(verses_file: VersesFile, bible: KrvBible, dry_run: bool) -> int:
    targets = [v for v in verses_file.verses if verses_file.text_is_empty(v["id"])]

    print("=" * 72)
    print("빈 text 채우기 - 대상 {}건 / 전체 {}건".format(len(targets), len(verses_file.verses)))
    print("모드: {}".format("--dry-run (쓰지 않음)" if dry_run else "쓰기"))
    print("=" * 72)

    if not targets:
        print()
        print("채울 구절이 없다. 모든 구절의 text가 이미 채워져 있다.")
        print("(이미 채워진 text는 덮어쓰지 않는다 - 검수 이력을 지키기 위해서다)")
        return 0

    filled: list[str] = []
    errors: list[tuple[str, str, str]] = []

    for verse in targets:
        verse_id = verse["id"]
        try:
            extracted = extract(verse, bible)
        except RefError as exc:
            errors.append((verse_id, verse["ref"], str(exc)))
            continue

        folded = fold(extracted)
        print()
        print("  + {:12} {}".format(verse_id, verse["ref"]))
        for line in folded:
            print("      " + line)

        if not dry_run:
            verses_file.set_text(verse_id, folded)
        filled.append(verse_id)

    if errors:
        print()
        print("[ref 오류] {}건 - 채우지 않았다".format(len(errors)))
        print()
        for verse_id, ref, detail in errors:
            print("  X {:12} {}".format(verse_id, ref))
            print("    " + detail)
            print()

    if filled and not dry_run:
        verses_file.save()

    print()
    print("[요약]")
    print("  채움     {:3}건{}".format(len(filled), " (dry-run: 쓰지 않음)" if dry_run else ""))
    print("  ref 오류 {:3}건".format(len(errors)))

    if not dry_run and filled:
        print()
        print("다음: python scripts/verify_verses.py")
        print("  추출한 본문이므로 통과하는 것이 정상이다. 실패하면 ref를 의심할 것.")

    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="verses.yaml의 빈 text를 개역한글 원문에서 추출해 채운다.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="무엇을 채울지 보여주기만 하고 파일을 쓰지 않는다",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="채워진 구절에 대해 추출 경로가 현재 text를 재현하는지 검증한다 (쓰지 않음)",
    )
    parser.add_argument("--verses", type=Path, default=VERSES_PATH, help="verses.yaml 경로")
    parser.add_argument("--krv", type=Path, default=KRV_PATH, help="개역한글 원문 JSON 경로")
    args = parser.parse_args()

    if args.verify and args.dry_run:
        print("--verify와 --dry-run은 함께 쓸 수 없다.", file=sys.stderr)
        return 2

    if not args.krv.exists():
        print("원문 데이터가 없다: {}".format(args.krv), file=sys.stderr)
        print("data/krv/SOURCE.md의 원본 URL에서 내려받고 sha256을 확인할 것.", file=sys.stderr)
        return 2

    bible = KrvBible(args.krv)
    verses_file = VersesFile(args.verses)

    if verses_file.translation != "krv1961":
        print(
            "경고: translation이 'krv1961'이 아니다 ({!r}). "
            "이 스크립트는 개역한글 원문에서만 추출한다.".format(verses_file.translation),
            file=sys.stderr,
        )

    if args.verify:
        return run_verify(verses_file, bible)
    return run_fill(verses_file, bible, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
