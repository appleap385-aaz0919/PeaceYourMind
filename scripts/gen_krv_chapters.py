#!/usr/bin/env python3
"""구절이 닿는 장의 원문만 app/public/krv/로 뽑는다 ("이어서 읽기" 탭용). API 소모 0.

    python scripts/gen_krv_chapters.py
    python scripts/gen_krv_chapters.py --dry-run   # 쓰지 않고 결과만 보여준다

무엇을 만드는가
    app/public/krv/<영문책키>/<장>.json  — 장 하나가 파일 하나다
    {"book":"Psalms","chapter":130,"title":"시편 130편","verses":["...","..."]}

왜 전문을 넣지 않는가 — 실측으로 갈렸다 (2026-08-20)
    전문 66권을 앱 번들에 넣으면      gzip +1,254,618  (앱 전체의 12.8배)
    닿는 장 174개를 번들에 넣으면     gzip   +165,904  (1.7배)
    장 단위로 따로 받으면             gzip 장당 1,234(중앙값) · 최대 4,616
    번들에 넣는 두 안은 **탭을 한 번도 열지 않는 사용자가 비용을 전부 낸다.**
    그래서 장 단위 원격을 택했다 (HANDOFF 설계안 결정 B).

    ⚠ 책 단위로 묶는 안은 검토하고 버렸다. 감정 구절 289건 중 시편이 166건(57%)이고
      시편 청크 하나가 gzip 47,944다 — 절반 이상의 경우에 48KB를 받는 꼴이라
      장 단위보다 나쁘다.

왜 data/가 아니라 app/public/인가
    data/ 하위는 배치(build.yml)의 영역이고 **매일 바뀐다.** 원문은 바뀌지 않고
    앱과 함께 배포되는 불변 자산이라 성격이 다르다. app/public/은 vite가
    app/dist/로 그대로 옮기고 deploy-app.yml이 gh-pages 루트에 올린다.
    service worker는 /data/가 아닌 같은 오리진 요청을 캐시하므로 한 번 연 장은
    오프라인에서도 열린다 (sw.js의 /krv/ 분기).

왜 감정 풀에서만 뽑는가
    위기 화면에는 이 탭이 없다 — 위기 구절의 앞뒤에 무엇이 있는지 통제할 수
    없기 때문이다(PLAN.md 7절과 같은 이유). 그래서 위기 풀은 여기서 읽지 않는다.
    (결과적으로 위기 구절이 쓰는 장은 감정 풀이 쓰는 장의 부분집합이라 파일은
    어차피 존재하지만, **그 파일을 만드는 근거가 위기 풀이어서는 안 된다.**
    큐레이션이 바뀌어 그 포함 관계가 깨져도 이 스크립트는 달라지지 않는다.)

게이트 (하나라도 걸리면 파일을 쓰지 않는다)
    - 감정 구절의 ref를 해석할 수 없다
    - 장의 절 번호가 1..N 연속이 아니다 (앱이 배열 인덱스를 절 번호로 쓴다)
    - 뽑은 본문이 원문과 글자 단위로 다르다
    - 감정 구절이 닿는 장 중 만들어지지 않은 것이 있다
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.krv_source import KrvBible, RefError, parse_ref  # noqa: E402
from lib.verses_io import VersesFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VERSES_PATH = ROOT / "verses.yaml"
KRV_PATH = ROOT / "data" / "krv" / "bible_1961_krv.json"
DEFAULT_OUT = ROOT / "app" / "public" / "krv"

# 시편만 '편'을 쓴다. 나머지 65권은 '장'이다.
#
# 화면 머리에 뜨는 문자열("시편 130편")을 여기서 만들어 넣는다. 앱에 한글
# 책 이름과 단위 규칙을 다시 두지 않기 위해서다 — parse_ref의 66권 사전을
# JS로 옮기면 그 순간 **두 번째 구현**이 되고, 이 저장소는 그 비용을 이미
# 안다(normalize.parity.test.js가 존재하는 이유).
CHAPTER_UNIT_EXCEPTIONS = {"Psalms": "편"}
DEFAULT_CHAPTER_UNIT = "장"

EXIT_OK = 0
EXIT_FAILED = 1


class BuildError(RuntimeError):
    """생성 전 검사에서 걸렸다. 파일을 쓰지 않는다."""


def chapter_title(book_ko: str, book_key: str, chapter: int) -> str:
    unit = CHAPTER_UNIT_EXCEPTIONS.get(book_key, DEFAULT_CHAPTER_UNIT)
    return f"{book_ko} {chapter}{unit}"


def touched_chapters(verses_file: VersesFile) -> dict[tuple[str, int], str]:
    """감정 구절이 닿는 장을 모은다 -> {(영문책키, 장): 한글책이름}.

    범위형 ref(롬 8:38-39)와 장을 넘는 범위(시 42:5-43:1) 모두 시작 장만
    본다. **이어서 읽기는 장 경계를 넘지 않기 때문이다**(설계안 4절) —
    시작 장 하나면 그 구절이 열 수 있는 본문 전부가 된다.

    ⚠ 끝 장을 함께 모으고 싶어지면 먼저 4절의 판단을 다시 읽을 것.
      장 경계를 넘지 않는 이유는 용량이 아니라 "통제할 수 없는 본문이
      이어진다"이고, 파일을 더 만든다고 해결되지 않는다.
    """
    out: dict[tuple[str, int], str] = {}
    errors: list[str] = []
    for verse in verses_file.verses:
        try:
            ref = parse_ref(verse["ref"])
        except RefError as exc:
            errors.append(f"{verse['id']}: {exc}")
            continue
        out[(ref.book_key, ref.start[0])] = ref.book_ko
    if errors:
        raise BuildError("ref를 해석할 수 없는 구절이 있다:\n    " + "\n    ".join(errors))
    return out


def build_chapter(
    bible: KrvBible, book_key: str, book_ko: str, chapter: int
) -> dict[str, Any]:
    """장 하나를 앱이 받을 구조로 만든다.

    verses는 절 번호 순서의 본문 배열이다. **인덱스 + 1이 절 번호**라는
    약속을 앱이 그대로 쓰므로, 아래에서 1..N 연속을 단언한다. 번호를 배열에
    함께 넣지 않는 이유는 174개 파일에 걸쳐 순수한 낭비이기 때문이다.
    """
    verses = bible.chapter_verses(book_key, chapter)
    numbers = [number for number, _ in verses]
    if numbers != list(range(1, len(numbers) + 1)):
        raise BuildError(
            f"{book_ko} {chapter}: 절 번호가 1..{len(numbers)} 연속이 아니다 "
            f"({numbers[:5]}...) — 앱이 배열 인덱스를 절 번호로 쓰므로 어긋난다"
        )
    return {
        "book": book_key,
        "chapter": chapter,
        "title": chapter_title(book_ko, book_key, chapter),
        "verses": [text for _, text in verses],
    }


def assert_matches_source(payload: dict[str, Any], bible: KrvBible) -> None:
    """파일에 들어간 본문이 원문과 글자 단위로 같은지 확인한다.

    **정규화조차 하지 않는다.** verses.json 쪽은 폴디드 스칼라를 거치느라
    공백 정규화가 필요하지만, 여기는 원문 JSON에서 곧장 옮기는 경로라
    한 글자도 달라질 자리가 없다. 그러니 완전 일치로 본다 — 느슨하게
    비교하면 이 검사가 잡을 수 있는 유일한 결함(복사 중 훼손)을 놓친다.
    """
    book_key, chapter = payload["book"], payload["chapter"]
    original = [text for _, text in bible.chapter_verses(book_key, chapter)]
    if payload["verses"] != original:
        raise BuildError(f"{payload['title']}: 뽑은 본문이 원문과 다르다")


def merged_runs(verses: list[str]) -> list[tuple[int, int]]:
    """연속으로 같은 본문이 반복되는 구간을 (시작절, 끝절)로 돌려준다.

    개역한글은 여러 절을 나누지 않고 합쳐 싣는 구간이 있고, 원문 데이터는
    절 수(31,102)를 맞추려고 그 합본 본문을 각 절 번호에 똑같이 복제한다
    (krv_source.verses_in_range의 방어 주석 참조). 지금까지는 그런 ref가
    거부돼 화면에 나온 적이 없지만, **장 전체를 그리면 막을 것이 없다.**

    여기서는 보고만 한다 — 묶어 그리는 것은 앱(chapters.js)의 일이다.
    이 함수는 "그런 장이 몇 개인지"를 리포트에 띄워, 큐레이션이 바뀌어
    새 장이 들어왔을 때 사람이 알아차리게 하는 용도다.

    ⚠ 비연속 반복은 여기 잡히지 않으며 잡아서도 안 된다. 시편 46:7과 46:11,
      시편 107:8·15·21·31은 **후렴**이다 — 원문이 의도적으로 반복한다.
      판별은 절 번호가 붙어 있는가 하나로 갈린다.
    """
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(verses):
        end = index
        while end + 1 < len(verses) and verses[end + 1] == verses[index]:
            end += 1
        if end > index:
            runs.append((index + 1, end + 1))
        index = end + 1
    return runs


def write_all(
    chapters: dict[tuple[str, int], dict[str, Any]], out: Path, dry_run: bool
) -> int:
    """장 파일을 쓰고, 더 이상 필요 없는 파일을 지운다.

    지우는 쪽이 중요하다 — 큐레이션에서 구절이 빠지면 그 장은 아무도 열 수
    없는데 파일만 배포에 남는다. 생성물 디렉터리를 통째로 다시 만드는 것이
    가장 확실하다(.gitignore 대상이므로 사람이 넣어 둔 것이 섞일 자리가 없다).
    """
    if dry_run:
        return 0
    if out.exists():
        shutil.rmtree(out)
    written = 0
    for (book_key, chapter), payload in sorted(chapters.items()):
        target = out / book_key / f"{chapter}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written += 1
    return written


def report(
    chapters: dict[tuple[str, int], dict[str, Any]],
    out: Path,
    dry_run: bool,
) -> None:
    payloads = list(chapters.values())
    sizes = [
        len(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        for p in payloads
    ]
    books = Counter(key[0] for key in chapters)
    merged = [(p["title"], merged_runs(p["verses"])) for p in payloads]
    merged = [(title, runs) for title, runs in merged if runs]

    print("=" * 72)
    print("krv 장 원문 생성" + ("  (--dry-run: 쓰지 않음)" if dry_run else ""))
    print("=" * 72)
    print(f"  장            {len(chapters)}개  ({len(books)}권)")
    print(f"  절            {sum(len(p['verses']) for p in payloads):,}건")
    print(f"  파일 크기     합계 {sum(sizes):,} · 중앙값 {sorted(sizes)[len(sizes) // 2]:,} "
          f"· 최대 {max(sizes):,} 바이트 (비압축)")
    print(f"  본문          원문과 글자 단위 일치 확인")
    print(f"  출력          {out}")
    print()
    print(f"  합본 구간이 있는 장 {len(merged)}개 — 앱이 절 번호를 묶어 한 번만 그린다")
    for title, runs in merged:
        spans = " · ".join(f"{a}-{b}" for a, b in runs)
        print(f"    {title}  {spans}")
    if len(merged) != 2:
        print()
        print("  ⚠ 합본 구간이 있는 장이 2개가 아니다. 큐레이션이 바뀌었다면 정상이지만,")
        print("    chapters.test.js의 고정 목록도 함께 갱신할 것.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="구절이 닿는 장의 원문을 app/public/krv/로 뽑는다 (API 소모 0)."
    )
    parser.add_argument("--verses", type=Path, default=VERSES_PATH)
    parser.add_argument("--krv", type=Path, default=KRV_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--dry-run", action="store_true", help="검사와 생성만 하고 파일을 쓰지 않는다"
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        verses_file = VersesFile(args.verses)
        bible = KrvBible(args.krv)

        wanted = touched_chapters(verses_file)
        chapters: dict[tuple[str, int], dict[str, Any]] = {}
        for (book_key, chapter), book_ko in wanted.items():
            payload = build_chapter(bible, book_key, book_ko, chapter)
            assert_matches_source(payload, bible)
            chapters[(book_key, chapter)] = payload

        missing = sorted(key for key in wanted if key not in chapters)
        if missing:
            raise BuildError(f"만들어지지 않은 장이 있다: {missing}")

        report(chapters, args.out, args.dry_run)
        written = write_all(chapters, args.out, args.dry_run)
        if not args.dry_run:
            print()
            print(f"생성 완료 — {written}개 파일. app/public/krv/는 .gitignore 대상이다.")
            print("단일 소스는 data/krv/bible_1961_krv.json이고 매 빌드마다 새로 만든다.")
        return EXIT_OK

    except BuildError as exc:
        print("=" * 72, file=sys.stderr)
        print("생성 중단", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print("  X " + str(exc), file=sys.stderr)
        print("파일을 쓰지 않았다.", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
