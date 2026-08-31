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
from lib.krv_source import (  # noqa: E402
    BOOK_KEYS,
    KrvBible,
    RefError,
    normalize_ws,
    parse_ref,
)
from lib.verses_io import VersesFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VERSES_PATH = ROOT / "verses.yaml"
THEMES_PATH = ROOT / "themes.yaml"
KRV_PATH = ROOT / "data" / "krv" / "bible_1961_krv.json"
DEFAULT_OUT = ROOT / "app" / "src" / "data" / "verses.json"

# 앱 번들에 남기는 필드. 이 목록에 없는 것은 전부 제거된다.
# notify는 **제외된 구절에만** 있다(notify: false). 없으면 알림 대상이라는 뜻이고,
# 앱은 `verse.notify !== false`로 읽는다. 빠진 값을 기본값으로 쓰는 이 형태가
# 293건 중 23건에만 표시를 남겨 번들도 작고 diff도 읽힌다.
# ⚠ notify_note는 여기 없다 — note와 같은 큐레이션 메타이고 앱이 쓰지 않는다.
APP_FIELDS = ("id", "ref", "text", "emotion_tags", "theme", "notify")
# read_from은 여기 없다 — 큐레이션 입력이고, 결과는 read.from에 이미 반영된다
CRISIS_APP_FIELDS = ("id", "ref", "text")

# verses.yaml에 없고 여기서 계산해 붙이는 필드.
#
# read = {"book": 영문책키, "chapter": 장, "from": 끝 절 + 1}
#   "이어서 읽기" 탭이 열 장과 시작 절이다. app/public/krv/<book>/<chapter>.json이
#   그 장의 본문이고, gen_krv_chapters.py가 같은 소스에서 함께 만든다.
#
# ★ 왜 앱에서 ref를 파싱하지 않고 여기서 붙이는가
#   krv_source.parse_ref는 66권의 한글 정식명·약어 사전을 들고 있다. 그것을 JS로
#   옮기면 그 순간 **두 번째 구현**이 되고, 두 구현이 어긋나면 화면이 엉뚱한 장을
#   연다. 이 저장소는 그 비용을 이미 안다 — normalize가 앱(JS)과 배치(Python)에
#   양쪽으로 있어서 normalize.parity.test.js가 문자 단위 일치를 지키고 있다.
#   파싱을 빌드 타임에 끝내면 이식도 패리티 테스트도 필요 없다.
#
# ⚠ from은 **장의 끝을 넘을 수 있다.** 인용 구절이 그 장의 마지막 절인 경우가
#   289건 중 20건이고(롬 8:38-39는 로마서 8장의 마지막이라 from=40이지만 39절이
#   끝이다), 그 처리는 앱의 페이지 규칙이 맡는다(chapters.js pageFor).
#   여기서 미리 자르지 않는 이유는 이 필드의 뜻이 "인용한 다음 절"이기 때문이다 —
#   자르는 순간 뜻이 "시작 절"로 바뀌고, 그러면 페이지 크기(4절)라는 화면의
#   판단이 데이터 생성기로 새어 들어온다.
COMPUTED_FIELDS = ("read",)

# 이어서 읽기 한 페이지 절 수. app/src/lib/chapters.js의 PAGE_SIZE와 같아야 한다.
# ⚠ 두 값이 어긋나면 아래 게이트가 검사하는 범위와 사용자가 보는 범위가 달라진다.
READ_PAGE_SIZE = 4

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
#   275  anger.irritation +2 · unfair +5 · rage +2 · frustration.suppressed +2
#   279  frustration.stuck +2 · blocked +2
#   288  joy.grateful +5 · proud +1 · delight +3
#   293  flutter 2 · calm.ease 1 · boredom.novelty 2
#   289  ★ 재검토로 4건 제외 — 마 10:19 · 요 11:6 · 전 5:12 · 시 103:10
#        (채택하면서 note에 위험을 적어 두고 넘어간 유형. verses.yaml 제외 목록)
#   286  ★ 장 문맥 재검토로 3건 제외 — 시 88:1-2 · 시 143:4 · 시 1:2
#        (2026-08-20 '이어서 읽기' 신설 축. verses.yaml excluded 참조)
EXPECT_VERSES = 293
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

    problems.extend(check_notify_pool(verses_file))

    return problems


# 아침 알림이 고를 수 있는 구절 수. 시편 전체와 notify: false를 뺀 나머지다.
# ⚠ 큐레이션이 늘면 이 값도 늘어야 한다 — 게이트가 알려 주면 그때 함께 올린다.
EXPECT_NOTIFY_POOL = 107


def check_notify_pool(verses_file: VersesFile) -> list[str]:
    """알림 풀이 설계대로 남는지 본다 (2026-08-31).

    [왜 게이트인가]
      알림 구절은 **화면과 다른 기준**으로 걸러진다. 시편 전체를 빼고(1인칭
      고백이 감정을 넘겨짚는다) 서사·탄식 등 23건을 더 뺀다. 이 규칙은 코드가
      아니라 데이터에 있으므로, 큐레이션을 손대다 풀이 조용히 비거나 넘칠 수
      있다. 여기서 세어 두면 그날 바로 걸린다.

    ⛔ 위기 풀(crisis)은 애초에 세지 않는다 — 알림이 그 배열을 읽지 않는다.
    """
    problems: list[str] = []
    flagged = [v["id"] for v in verses_file.verses if v.get("notify") is False]
    no_reason = [
        v["id"] for v in verses_file.verses
        if v.get("notify") is False and not str(v.get("notify_note", "")).strip()
    ]
    if no_reason:
        problems.append(
            f"notify: false인데 notify_note가 없는 구절 {len(no_reason)}건 — "
            f"{', '.join(no_reason[:5])}  (왜 뺐는지 남기지 않으면 되살릴 수 없다)"
        )

    pool = [
        v for v in verses_file.verses
        if v.get("notify") is not False and not str(v["ref"]).startswith("시편 ")
    ]
    if len(pool) != EXPECT_NOTIFY_POOL:
        problems.append(
            f"알림 풀 {len(pool)}건 — 기대 {EXPECT_NOTIFY_POOL}건과 다르다 "
            f"(시편 제외 · notify: false {len(flagged)}건 제외). "
            "큐레이션이 늘었다면 EXPECT_NOTIFY_POOL을 함께 올릴 것"
        )
    return problems


def read_pointer(verse: dict[str, Any]) -> dict[str, Any]:
    """구절 하나의 "이어서 읽기" 시작점을 계산한다.

    범위형 ref(롬 8:38-39)는 **끝 절** 기준이다 — 인용한 마지막 절 다음부터
    이어 읽는 것이 이 기능의 뜻이다. 장을 넘는 범위(시 42:5-43:1)는 시작 장을
    쓴다. 이어서 읽기가 장 경계를 넘지 않으므로 열 수 있는 장은 시작 장뿐이고,
    끝 장을 가리키면 사용자가 읽던 구절이 없는 장이 열린다.

    [read_from — 큐레이션이 시작 절을 지정한다 (2026-08-20)]
      기본은 위 규칙이지만, 그렇게 열면 화면과 어긋나는 본문이 나오는 구절이
      있다. 그때 verses.yaml에 read_from을 적어 **장 안의 다른 자리**로 연다.
        계 21:5   기본이면 8절(불못 명단)이 첫 페이지에 온다 → 1절부터 연다
        사 66:13  기본이면 16절("살륙 당할 자가 많으리니") → 10절부터 연다
      앱은 이 값을 그대로 쓴다. 장 마지막 절이라 열 것이 없을 때 장 처음부터
      여는 분기를 이미 갖고 있어(chapters.js initialCursor) **앱 변경이 없다.**

    ⚠ read_from은 예외이지 기본이 아니다. 쓰는 곳마다 근거를 주석에 적는다 —
      "인용한 다음 절부터"라는 약속을 깨는 값이라, 근거 없이 늘어나면
      이어서 읽기가 무엇을 여는지 아무도 예측할 수 없게 된다.
    """
    parsed = parse_ref(verse["ref"])
    default = parsed.end[1] + 1 if parsed.end[0] == parsed.start[0] else 1
    return {
        "book": parsed.book_key,
        "chapter": parsed.start[0],
        "from": int(verse.get("read_from") or default),
    }


def first_page_verses(pointer: dict[str, Any], bible: KrvBible) -> list[int]:
    """이어서 읽기 첫 페이지에 실제로 뜨는 절 번호.

    **앱(chapters.js)의 규칙을 그대로 옮긴 것이다.** 두 곳이 어긋나면 이 게이트가
    검사하는 화면과 사용자가 보는 화면이 달라진다.
      · 인용이 장의 마지막이면 장 처음부터
      · 남은 절이 한 페이지보다 적으면 장 끝에 맞춰 뒤로 당긴다
    ⚠ 합본 구간(같은 본문이 연속 복제된 곳)은 앱이 한 단위로 묶어 그리므로
      실제로는 더 뒤까지 보인다. 여기서는 절 번호로만 세어 **더 좁게** 본다 —
      게이트가 놓치는 쪽이 아니라 조이는 쪽으로 틀리게 둔다.
    """
    verses = bible.chapter_verses(pointer["book"], pointer["chapter"])
    total = len(verses)
    start = pointer["from"]
    if start > total:
        start = 1
    elif total - start + 1 < READ_PAGE_SIZE:
        start = max(1, total - READ_PAGE_SIZE + 1)
    return list(range(start, min(start + READ_PAGE_SIZE, total + 1)))


def load_excluded(path: Path) -> list[dict[str, Any]]:
    """verses.yaml의 구조화 제외 색인을 읽는다."""
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return list(raw.get("excluded") or [])


def check_exclusion_index(path: Path, excluded: list[dict[str, Any]]) -> list[str]:
    """① 제외 색인의 모든 ref가 파일 어딘가의 주석에 언급되는가.

    색인은 ref와 사유 분류만 갖는다. "왜 뺐는가"는 [제외 기록] 주석에 있고
    그것이 이 저장소의 판단 자산이다. 근거 없는 제외가 색인에만 생기면
    다음 사람이 이유를 알 수 없으므로 여기서 막는다.

    ⚠ 역방향은 검사하지 않는다. 주석에서 ref를 기계로 뽑으면 오탐이 난다 —
      실측에서 41건이 뽑혔는데 실제 제외는 13건이었다(제외 기록 산문이 수록
      구절 자신을 자주 언급한다). 거짓 실패가 쌓이면 사람이 게이트를 끈다.
    """
    text = path.read_text(encoding="utf-8")
    problems = []
    for item in excluded:
        ref = str(item.get("ref", "")).strip()
        if not ref:
            problems.append("excluded 항목에 ref가 없다")
            continue
        # 주석은 약어를 쓰고("시 1:3") 색인은 정식명을 쓴다("시편 1:3").
        # 같은 절을 가리키는 모든 표기를 만들어 대조한다 — 표기 차이로 거짓
        # 실패가 나면 사람이 게이트를 끄게 되고, 그러면 게이트가 없는 것과 같다.
        try:
            parsed = parse_ref(ref)
        except RefError as exc:
            problems.append(f"제외 색인의 ref를 해석할 수 없다: {ref!r} ({exc})")
            continue
        names = [k for k, v in BOOK_KEYS.items() if v == parsed.book_key]
        tail = "%d:%d" % (parsed.start[0], parsed.start[1])
        forms = ["%s %s" % (n, tail) for n in names] + ["%s%s" % (n, tail) for n in names]
        # 색인 줄 자신이 1회 잡히므로, 주석에 있으려면 2회 이상이어야 한다
        if sum(text.count(f) for f in forms) < 2:
            problems.append(
                f"제외 색인 {ref!r}의 근거 서술이 주석에 없다 — "
                "[제외 기록]에 왜 뺐는지 적을 것"
            )
    return problems


def check_reader_first_page(
    bundle: dict[str, Any], excluded: list[dict[str, Any]], bible: KrvBible
) -> list[str]:
    """② 수록 구절의 "이어서 읽기 첫 페이지"에 제외한 절이 들어오는가.

    ★ 이 게이트가 있는 이유는 실제 사고다 (2026-08-20).
      시 1:3을 번영신학으로 빼고 렘 17:7-8로 대체했는데, 시 1:2를 수록한 탓에
      이어서 읽기 **첫 페이지 첫 줄**에 시 1:3이 다시 떴다. 제외 작업 자체가
      무효화된 것이다. 전수 조사에서 이런 재노출이 13건이었다.

    첫 페이지만 본다. 그 자리는 탭을 열면 **무조건** 보이고 선택이 아니다.
    장 뒤쪽은 사용자가 [다음]을 눌러 능동적으로 간 결과라 note에 기록만 한다
    (판정 기준 2층 — HANDOFF 2.38).
    """
    blocked: set[tuple[str, int, int]] = set()
    for item in excluded:
        try:
            ref = parse_ref(str(item["ref"]))
        except RefError as exc:
            return [f"제외 색인의 ref를 해석할 수 없다: {item.get('ref')!r} ({exc})"]
        for chapter in range(ref.start[0], ref.end[0] + 1):
            lo = ref.start[1] if chapter == ref.start[0] else 1
            hi = ref.end[1] if chapter == ref.end[0] else 999
            for number in range(lo, hi + 1):
                blocked.add((ref.book_key, chapter, number))

    problems = []
    for entry in bundle["verses"]:
        pointer = entry["read"]
        for number in first_page_verses(pointer, bible):
            key = (pointer["book"], pointer["chapter"], number)
            if key in blocked:
                problems.append(
                    f"{entry['id']} ({entry['ref']}): 이어서 읽기 첫 페이지 "
                    f"{number}절이 제외 구절이다 — read_from으로 다른 자리를 열거나 "
                    "이 구절을 빼야 한다"
                )
    return problems


def build(verses_file: VersesFile, theme_ids: set[str], now: datetime) -> dict[str, Any]:
    """앱 번들 구조를 만든다.

    themes는 실제로 쓰인 주제만 담는다 — 앱이 빈 주제 화면을 만들지 않도록.
    crisis_fixed는 감정 매핑을 타지 않으므로 여기 넣지 않는다.

    ★ read는 감정 풀에만 붙인다 — 위기 풀에는 붙이지 않는다.
      위기 화면에는 "이어서 읽기"가 없다. 위기 구절의 앞뒤에 무엇이 있는지
      통제할 수 없기 때문이다. 그런데 데이터에 시작점이 들어 있으면 그 화면을
      만드는 일이 **한 줄짜리 실수**로 가능해진다. 위기 풀을 최상위로 분리한
      것과 같은 판단이다(PLAN.md 4.2) — 구조로 막으면 그 실수가 불가능해진다.
      assert_no_loss가 위기 항목에 read가 섞이지 않았는지 다시 확인한다.
    """
    used_themes = sorted({v["theme"] for v in verses_file.verses})

    verses = []
    for verse in verses_file.verses:
        entry = strip_entry(verse, APP_FIELDS)
        entry["read"] = read_pointer(verse)
        verses.append(entry)

    return {
        "translation": verses_file.translation,
        "source_version": verses_file.version,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": "성경전서 개역한글판, 대한성서공회",
        "themes": used_themes,
        "verses": verses,
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

    # 감정 풀과 위기 풀을 **각자의 허용 목록으로** 본다.
    #
    # 전에는 둘 다 APP_FIELDS로 봤다. 위기 항목의 허용 필드가 더 좁은데도
    # 넓은 목록으로 검사한 것이라, 위기 항목에 theme이 섞여도 이 자리에서는
    # 걸리지 않았다(아래 별도 검사가 그것만 따로 잡고 있었다).
    # read가 생기면서 그 느슨함이 실제 위험이 됐다 — 위기 항목에 read가 붙는
    # 것이 정확히 막아야 할 일이다. 목록을 갈라 두면 앞으로 추가되는 필드도
    # 자동으로 같은 보호를 받는다.
    allowed = {
        "verses": set(APP_FIELDS) | set(COMPUTED_FIELDS),
        "crisis": set(CRISIS_APP_FIELDS),
    }
    for key, permitted in allowed.items():
        leaked = sorted({field for entry in bundle[key] for field in entry} - permitted)
        if leaked:
            raise BuildError(f"{key}에 허용되지 않은 필드가 남았다: {leaked}")

    for entry in bundle["crisis"]:
        if not entry["id"].startswith(CRISIS_PREFIX):
            raise BuildError(f"crisis 배열에 일반 id가 있다: {entry['id']}")
        if "emotion_tags" in entry or "theme" in entry:
            raise BuildError(f"crisis 항목에 감정 매핑 필드가 남았다: {entry['id']}")
        if "read" in entry:
            raise BuildError(
                f"crisis 항목에 이어서 읽기 시작점이 붙었다: {entry['id']} — "
                "위기 구절의 앞뒤는 통제할 수 없어 그 화면에는 이 기능을 두지 않는다"
            )

    for entry in bundle["verses"]:
        pointer = entry.get("read")
        if not pointer or not all(k in pointer for k in ("book", "chapter", "from")):
            raise BuildError(f"{entry['id']}: read 시작점이 없거나 불완전하다")


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
    print(f"  이어서 읽기   시작 절 지정 {sum(1 for v in verses if v['read'])and sum(1 for v in verses)}건 중 "
          f"{sum(1 for v in verses if v['read']['from'] == 1)}건이 장 처음부터 · 제외 색인 게이트 통과")
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
        bible = KrvBible(args.krv)
        assert_matches_source(bundle, bible)

        # 제외 색인 게이트 2종 (verses.yaml excluded 주석 참조)
        excluded = load_excluded(args.verses)
        gate = check_exclusion_index(args.verses, excluded)
        gate += check_reader_first_page(bundle, excluded, bible)
        if gate:
            raise BuildError(
                "제외 색인 게이트 {}건{}    ".format(len(gate), "\n")
                + "{}    ".format("\n").join(gate)
            )

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
