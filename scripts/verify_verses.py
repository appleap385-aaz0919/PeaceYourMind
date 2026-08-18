#!/usr/bin/env python3
"""verses.yaml의 구절 본문을 개역한글 원문과 대조한다.

    python scripts/verify_verses.py            # 대조 + 일치 건 verified 갱신
    python scripts/verify_verses.py --check    # 대조만. 갱신하지 않는다 (CI 게이트)

왜 자동 수정을 하지 않는가
--------------------------
불일치는 자동으로 고치지 않는다. diff를 출력하고 verified: false로 남긴다.
사람이 보고 승인한 뒤에만 반영한다.

이유는 동일성유지권이면서, 동시에 **불일치의 원인이 두 가지**라서다.

    (a) text가 틀렸다               -> text를 원문으로 교체하면 된다
    (b) ref가 틀렸다 (절 경계 오류) -> text만 고치면 잘못된 구절이 박제된다

verses.yaml의 시편 46:1이 (b)였다. 초안이 46:1-2로 잡고 3절 끝을 2절에
이어붙였다. text만 원문으로 덮었다면 "1-2절이라 적힌 1절"이 남았을 것이다.
기계는 (a)와 (b)를 구분하지 못한다. 그래서 판단을 사람에게 남긴다.

--check가 실패하는 조건 (둘 중 하나라도 해당하면 종료 코드 1)
    1. 본문이 원문과 다른 구절이 있다
    2. verified: false 구절이 있다   <- 검수 없이 배포 불가
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.krv_source import KrvBible, RefError, normalize_ws, parse_ref  # noqa: E402
from lib.verses_io import VersesFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KRV_PATH = ROOT / "data" / "krv" / "bible_1961_krv.json"
VERSES_PATH = ROOT / "verses.yaml"

# verified_by에 남길 데이터 출처 식별자. 전문은 data/krv/SOURCE.md.
# 커밋을 박아두는 이유: 원문 데이터가 교체되면 판정 근거가 달라지므로,
# 어느 기준으로 통과한 검수인지가 구절마다 남아야 한다.
SOURCE_ID = "krv1961@bluesaurel/Korean-Bible-1961-KRV#65cdce8"

MATCH = "match"
MISMATCH = "mismatch"
REF_ERROR = "ref_error"


@dataclass
class Result:
    verse_id: str
    ref: str
    status: str
    was_verified: bool
    draft: str = ""
    original: str = ""
    detail: str = ""
    parts: list[tuple[int, int, str]] | None = None

    @property
    def ok(self) -> bool:
        return self.status == MATCH


def compare(verse: dict, bible: KrvBible) -> Result:
    verse_id = verse["id"]
    ref_text = verse["ref"]
    was_verified = bool(verse.get("verified"))
    draft = normalize_ws(verse.get("text", ""))

    try:
        ref = parse_ref(ref_text)
        parts = bible.verses_in_range(ref)
    except RefError as exc:
        return Result(verse_id, ref_text, REF_ERROR, was_verified,
                      draft=draft, detail=str(exc))

    original = normalize_ws(" ".join(text for _, _, text in parts))
    status = MATCH if draft == original else MISMATCH
    return Result(verse_id, ref_text, status, was_verified,
                  draft=draft, original=original, parts=parts)


# ---------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------
def first_difference(draft: str, original: str) -> int:
    limit = min(len(draft), len(original))
    for index in range(limit):
        if draft[index] != original[index]:
            return index
    return limit


def render_diff(result: Result) -> list[str]:
    """원문과 초안을 나란히 보여주고, 어긋나기 시작하는 지점을 짚어준다."""
    lines = [
        "  원문 : " + result.original,
        "  초안 : " + result.draft,
    ]

    position = first_difference(result.draft, result.original)
    window = 12
    left = max(0, position - window)
    lines.append(
        "  최초 불일치 {}자째   원문 ...{!r}   초안 ...{!r}".format(
            position,
            result.original[left:position + window],
            result.draft[left:position + window],
        )
    )

    if result.parts and len(result.parts) > 1:
        lines.append("  절 단위 원문:")
        for chapter, number, text in result.parts:
            lines.append("    {}:{}  {}".format(chapter, number, text))
    return lines


def report(results: list[Result], check_only: bool, updated: list[str]) -> None:
    matched = [r for r in results if r.status == MATCH]
    mismatched = [r for r in results if r.status == MISMATCH]
    ref_errors = [r for r in results if r.status == REF_ERROR]

    print("=" * 72)
    print("구절 본문 대조 - {}건".format(len(results)))
    print("기준 원문: {}".format(SOURCE_ID))
    print("모드: {}".format("--check (갱신 없음)" if check_only else "갱신"))
    print("=" * 72)

    if ref_errors:
        print()
        print("[ref 오류] {}건 - 참조를 해석할 수 없거나 원문에 없는 절이다".format(len(ref_errors)))
        print()
        for result in ref_errors:
            print("  X {:12} {}".format(result.verse_id, result.ref))
            print("    " + result.detail)
            if result.draft:
                print("    초안 : " + result.draft)
            print()

    if mismatched:
        print()
        print("[불일치] {}건 - 자동 수정하지 않는다. 사람이 판단한다.".format(len(mismatched)))
        print()
        for result in mismatched:
            flag = "   (!) 기존 verified: true" if result.was_verified else ""
            print("  X {:12} {}{}".format(result.verse_id, result.ref, flag))
            for line in render_diff(result):
                print(line)
            print()

    print()
    print("[요약]")
    print("  일치      {:3}건".format(len(matched)))
    print("  불일치    {:3}건".format(len(mismatched)))
    print("  ref 오류  {:3}건".format(len(ref_errors)))

    revalidated = [r for r in matched if r.was_verified]
    if revalidated:
        print("  (일치 중 기존 verified: true 재확인 {}건)".format(len(revalidated)))

    if updated:
        print()
        print("[갱신] verified: true로 표시 {}건".format(len(updated)))
        for verse_id in updated:
            print("  o " + verse_id)
    elif not check_only and not mismatched and not ref_errors:
        print()
        print("[갱신] 이미 전건 verified: true - 바꿀 것이 없다")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="verses.yaml의 구절 본문을 개역한글 원문과 대조한다.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="갱신 없이 검사만 한다. 불일치 또는 verified: false가 있으면 종료 코드 1 (CI 게이트)",
    )
    parser.add_argument("--verses", type=Path, default=VERSES_PATH, help="verses.yaml 경로")
    parser.add_argument("--krv", type=Path, default=KRV_PATH, help="개역한글 원문 JSON 경로")
    args = parser.parse_args()

    if not args.krv.exists():
        print("원문 데이터가 없다: {}".format(args.krv), file=sys.stderr)
        print("data/krv/SOURCE.md의 원본 URL에서 내려받고 sha256을 확인할 것.", file=sys.stderr)
        return 2

    bible = KrvBible(args.krv)
    verses_file = VersesFile(args.verses)

    if verses_file.translation != "krv1961":
        print(
            "경고: translation이 'krv1961'이 아니다 ({!r}). "
            "이 스크립트는 개역한글 원문으로만 대조한다.".format(verses_file.translation),
            file=sys.stderr,
        )

    results = [compare(verse, bible) for verse in verses_file.verses]

    updated: list[str] = []
    if not args.check:
        today = dt.date.today().isoformat()
        verified_by = "verify_verses.py({})".format(SOURCE_ID)
        by_id = {v["id"]: v for v in verses_file.verses}
        for result in results:
            if not result.ok:
                continue
            verse = by_id[result.verse_id]
            # 이미 verified: true인 구절은 건드리지 않는다.
            #
            # 이 스크립트가 아닌 방법으로 검수된 구절이 있다 — 1차분 6건은
            # 사람이 웹 원문(bible.com KRV + 대한성서공회)과 직접 대조했고,
            # verified_by에 그 이력이 남아 있다. 스크립트가 자기 이름으로
            # 덮으면 독립적으로 이뤄진 검증 기록이 사라진다.
            #
            # 재확인 자체는 여전히 일어난다. 대조는 전건에 대해 돌고,
            # 기존 verified: true가 원문과 어긋나면 리포트에 표시되고
            # --check가 실패한다. 갱신하지 않을 뿐 검사에서 빠지지 않는다.
            if verse.get("verified"):
                continue
            verses_file.mark_verified(result.verse_id, verified_by, today)
            updated.append(result.verse_id)
        if updated:
            verses_file.save()

    report(results, check_only=args.check, updated=updated)

    failed = [r for r in results if not r.ok]

    if args.check:
        # 갱신을 하지 않으므로 파일에 남아 있는 verified 값을 그대로 본다.
        unverified = [v["id"] for v in verses_file.verses if not v.get("verified")]
        if failed or unverified:
            print()
            print("=" * 72)
            if failed:
                print("게이트 실패: 본문이 원문과 다른 구절 {}건".format(len(failed)))
            if unverified:
                print("게이트 실패: verified: false 구절 {}건 - {}".format(
                    len(unverified), ", ".join(unverified)))
            print("검수를 통과하지 않은 구절이 있으면 배포하지 않는다.")
            print("=" * 72)
            return 1
        print()
        print("게이트 통과: 전건 원문 일치 + verified: true")
        return 0

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
