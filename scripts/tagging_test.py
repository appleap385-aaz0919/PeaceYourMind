#!/usr/bin/env python
"""주제 태깅 · media_type 판별 · themes.yaml 게이트 검증 — 네트워크 호출 없음.

    python scripts/tagging_test.py

**드라이런으로는 검증되지 않는 것을 여기서 본다.** 드라이런의 합성 제목은
사전에서 만들어낸 것이라 당연히 걸린다(build_videos.dry_run_titles 주석).
판별 규칙의 정오는 손으로 쓴 제목으로 봐야 한다.

고정해 두는 것
  1. 본문 장절 패턴이 실제 설교 제목을 잡고, 일상어를 잡지 않는다
     — 1음절 약어("행"·"사")가 "여행 12장"·"감사 3가지"에 걸리던 유형
  2. 영문 키워드가 단어 경계로만 걸린다 (themes.yaml이 QT에 요구한 것)
  3. media_type 판별이 themes.yaml 우선순위(제목 → 장절 → 채널 → 길이)를 따른다
     — 채널이 1순위였을 때 찬양 81건이 sermon으로 판정되던 회귀 방지
  4. themes.yaml 게이트 6종이 실제로 빌드를 세운다 (고장을 주입해 확인)
  5. 실제 themes.yaml이 전역 금지어를 태깅 사전에 쓰지 않는다
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.tagging import (
    SERMON,
    UNKNOWN,
    WORSHIP,
    classify_media_type,
    has_scripture_reference,
    matches_keyword,
    tag_themes,
    visible_counts,
)
from lib.themes import FORBIDDEN_KEYWORDS, ThemesError, load_themes

ROOT = Path(__file__).resolve().parents[1]
THEMES_PATH = ROOT / "themes.yaml"
EXIT_OK, EXIT_FAIL = 0, 1


def _check(failures: list[str], ok: bool, label: str, detail: str = "") -> None:
    print(f"{'   ' if ok else 'X  '}{label}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def _load_broken(mutate) -> str:
    """themes.yaml을 고장 내서 로더가 거부하는지 본다. 거부 메시지를 돌려준다."""
    raw = yaml.safe_load(THEMES_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "themes.broken.yaml"
        broken.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        try:
            load_themes(broken)
        except ThemesError as exc:
            return str(exc)
    return ""


# --- 1. 본문 장절 패턴 -------------------------------------------------------

SCRIPTURE_YES = [
    "주일예배 | 요한복음 3:16 - 하나님이 세상을 이처럼 사랑하사",
    "에스겔 40장 새 성전",
    "[강해] 누가복음 8:19-21",
    "시편 23편 여호와는 나의 목자시니",
    "요 3:16 묵상",
    "롬 8:28 모든 것이 합력하여",
]
SCRIPTURE_NO = [
    "여행 12장 브이로그",  # 사도행전 약어 "행"이 단어 안에 있다
    "감사 3가지 이유",  # 이사야 약어 "사"가 단어 안에 있다
    "2026년 신년 특별 새벽기도",  # 숫자만 있고 장절 표지가 없다
    "찬양 콘티 모음 40곡",
    "우리 교회 소식",
]

# --- 3. media_type 판별 -----------------------------------------------------
#   (제목, 길이(초), 채널 content_type, 기대 media_type, 기대 근거)
#
# 2026-08-19 개정된 우선순위를 고정한다: 제목 → 장절 → 채널 → 길이.
# 개정 전에는 채널이 1순위였고, 그 탓에 sermon 채널이 올린 찬양 81건이
# sermon으로 판정됐다(실측). 아래 첫 두 건이 그 회귀를 막는 자리다.
MEDIA_CASES = [
    # 1순위 — 제목이 형식을 말하면 채널 성격을 이긴다
    ("찬양 메들리 1시간", 3600, "sermon", WORSHIP, "title"),
    ("주일예배 설교 - 잃어버린 아들", 3600, "worship", SERMON, "title"),
    # 실측 사례: 찬양 콘티의 곡명이 시편이다. 장절보다 제목이 앞이라 찬양으로 남는다
    (
        "시편 92편 + 주 이름 찬양 + 나의 기도하는 것보다 | 주일 2부예배 찬양 헤세드",
        1200,
        "sermon",
        WORSHIP,
        "title",
    ),
    # 2순위 — 제목이 형식을 말하지 않으면 본문 장절이 sermon 신호다
    ("[주일] 요한복음 3:16 - 하나님이 세상을 이처럼", 300, "mixed", SERMON, "scripture"),
    # 3순위 — 제목도 장절도 없으면 채널 성격이 기본값이다
    ("교회 소식", 1200, "sermon", SERMON, "channel"),
    ("이번 주 안내", 1200, "worship", WORSHIP, "channel"),
    ("오늘 하루", 1200, "devotion", SERMON, "channel"),  # devotion은 sermon으로 본다
    # 4순위 — 양쪽 다 걸리면 제목으로 정하지 않고 길이로 넘어간다
    ("설교와 찬양이 함께하는 시간", 2400, "mixed", SERMON, "duration"),
    ("설교 후 찬양", 300, "mixed", WORSHIP, "duration"),
    # 5순위 — 아무것도 안 걸리고 길이도 애매하면 unknown
    ("교회 소식 브리핑", 900, "mixed", UNKNOWN, "none"),
    # 승인 목록에 없는 채널(content_type 미상)도 같은 경로를 탄다
    ("성경통독 창세기 1장", 1200, None, SERMON, "title"),
]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    failures: list[str] = []
    themes = load_themes(THEMES_PATH)

    print("\n1. 본문 장절 패턴 (sermon의 최강 신호)")
    print("-" * 76)
    for title in SCRIPTURE_YES:
        _check(failures, has_scripture_reference(title), f"장절 인식: {title}")
    for title in SCRIPTURE_NO:
        _check(failures, not has_scripture_reference(title), f"장절 아님: {title}")

    print("\n2. 키워드 매칭 — 한글은 부분, 영문은 단어 경계")
    print("-" * 76)
    _check(failures, matches_keyword("새 힘을 주시는 하나님", "새 힘"), "한글 띄어쓰기 무시")
    _check(failures, matches_keyword("마음이무거울때", "마음이 무거"), "붙여쓴 제목도 매칭")
    _check(failures, matches_keyword("오늘의 QT 나눔", "QT"), "영문 키워드 매칭")
    _check(
        failures,
        not matches_keyword("Worship Equipment 리뷰", "QT"),
        "영문 키워드가 단어 안에서는 안 걸린다",
    )
    _check(failures, matches_keyword("CCM 워십 라이브", "CCM"), "영문 3자 매칭")

    print("\n3. 주제 태깅")
    print("-" * 76)
    tags = {m.theme_id for m in tag_themes("두려워하지 말라 - 평강의 하나님", themes)}
    _check(failures, "peace" in tags, "peace 태깅", str(sorted(tags)))
    multi = {m.theme_id for m in tag_themes("절망 속에 임하는 위로", themes)}
    _check(failures, {"hope", "comfort"} <= multi, "복수 태깅 허용", str(sorted(multi)))
    _check(failures, not tag_themes("청년부 수련회 하이라이트", themes), "미태깅은 빈 결과")

    # 2026-08-19 사전 보강에서 내린 판단을 고정한다 (HANDOFF 2.17).
    # love는 "사랑받음"이지 "사랑함"이 아니다. 어간을 "사랑하"까지 줄이면
    # 방향이 반대인 곡("우리가 주를 더욱 사랑하고")까지 들어온다 — 실측 9건 중
    # 4건이 그랬다. 그래서 **주어를 하나님으로 묶는 표지**만 키워드로 둔다.
    # 나중에 "활용형을 줄이면 더 많이 잡힌다"며 되돌리는 것을 여기서 막는다.
    for title, want in (
        ("예수 사랑하심을 + 위대하신 주", True),
        ("끝까지 사랑하셨어요 (요한복음 13:1)", True),
        ("주의 인자하신 그 사랑이", True),
        ("사랑한다 말하시네", True),
        ("우리가 주를 더욱 사랑하고 / 주님의 선하심", False),
        ("그러므로 사랑하자 | 새노래배우기", False),
    ):
        hit = "love" in {m.theme_id for m in tag_themes(title, themes)}
        _check(
            failures,
            hit is want,
            f"love {'태깅' if want else '비태깅'}: {title[:34]}",
        )

    # 어미가 갈려 빗나가던 활용형 — 어간으로 줄여 잡기로 한 것들이다.
    for title, theme_id in (
        ("보라 너희는 두려워 말고", "peace"),
        ("주 안에서 기뻐해", "joy_praise"),
        ("송축해 내 영혼", "joy_praise"),
        ("구원으로 인도하는", "guidance"),
        ("주 신실하심 놀라워", "trust"),
        ("주님의 선하심", "gratitude"),
    ):
        hit = theme_id in {m.theme_id for m in tag_themes(title, themes)}
        _check(failures, hit, f"{theme_id} 활용형 태깅: {title}")
    # 2026-08-20 — quiet_worship 어휘 개정을 고정한다 (HANDOFF 2.28).
    #   개정 전 6종(잔잔한 찬양·조용한 찬양·묵상 찬양·피아노 찬양·CCM 피아노·
    #   새벽 찬양)은 실측 1,067건에 **한 건도 걸리지 않았다.** 검색창에 칠 말이지
    #   교회가 제목에 쓰는 말이 아니었다. 실제 어휘로 갈아 12건을 잡는다.
    for title, want in (
        ("2026/08/16(주일) 꿈의교회, 희망의 찬양대_거룩하시다", True),
        ("8-1. 내 삶의 이유라 | Anointing Instrumental Series Vol.8", True),
        ("어노인팅 연주곡 시리즈 Vol.8 - 소망 (Hope) 전곡", True),
        ("[CCM PIANO] 훈계로 다스려주소서 피아노ver.", True),
        # ⛔ 여기부터가 이 검사의 핵심이다. 물량이 아쉽다고 `워십`·`찬양`을
        #   넣으면 이 셋이 들어온다 — 전부 고조된 예배 찬양 콘티다.
        #   intent가 "조용한 찬양·연주"인데 일반 찬양까지 받으면 joy_praise와
        #   구분이 사라지고 주제 집합 분리 작업과 충돌한다.
        ("주의 아름다움은 말로 다 | 오륜교회 금요기도회 찬양 하이프레이즈", False),
        ("문들아 머리 들어라 + 날마다 | 오륜교회 주일 5부예배 찬양 램넌트워십", False),
        ("[주일찬양] 휘문채플 / 주님 뜻대로 살기로 했네", False),
    ):
        hit = "quiet_worship" in {m.theme_id for m in tag_themes(title, themes)}
        _check(
            failures,
            hit is want,
            f"quiet_worship {'태깅' if want else '비태깅'}: {title[:38]}",
        )
    # 검색어를 되돌리지 않았는가 — 죽은 어휘가 다시 들어오면 여기서 걸린다
    qw = next(t for t in themes.taggable if t.id == "quiet_worship")
    revived = [k for k in ("잔잔한 찬양", "조용한 찬양", "CCM 피아노", "새벽 찬양") if k in qw.title_keywords]
    _check(
        failures,
        not revived,
        "검색어 유물을 되살리지 않았다",
        ", ".join(revived) or "-",
    )

    crisis_tagged = tag_themes("위기 상담 안내", themes)
    _check(
        failures,
        all(m.theme_id != "crisis_fixed" for m in crisis_tagged),
        "crisis_fixed는 제목 태깅 대상이 아니다",
    )

    print("\n4. media_type 판별 우선순위")
    print("-" * 76)
    for title, seconds, content_type, expected, reason in MEDIA_CASES:
        verdict = classify_media_type(title, seconds, content_type, themes)
        _check(
            failures,
            verdict.media_type == expected and verdict.reason == reason,
            f"{content_type or '(미상)':8} {title[:28]:30} → {expected}/{reason}",
            f"실제 {verdict.media_type}/{verdict.reason}",
        )

    print("\n5. unknown은 양쪽 토글에 노출된다")
    print("-" * 76)
    counts = visible_counts([SERMON, SERMON, WORSHIP, UNKNOWN])
    _check(
        failures,
        counts == {SERMON: 3, WORSHIP: 2},
        "unknown 1건이 양쪽에 더해진다",
        str(counts),
    )

    print("\n6. themes.yaml 게이트 — 고장을 주입해 실제 차단을 확인한다")
    print("-" * 76)

    def add_forbidden(raw: dict[str, Any]) -> None:
        raw["themes"][0]["title_keywords"].append("치유")

    def crisis_in_mapping(raw: dict[str, Any]) -> None:
        raw["mapping"]["anxiety.worry"] = ["crisis_fixed"]

    def unknown_theme(raw: dict[str, Any]) -> None:
        raw["mapping"]["anxiety.worry"] = ["없는주제"]

    def defaults_mismatch(raw: dict[str, Any]) -> None:
        raw["media_defaults"].pop("anxiety.worry")

    def bad_default_value(raw: dict[str, Any]) -> None:
        raw["media_defaults"]["anxiety.worry"] = "podcast"

    def overlapping_duration(raw: dict[str, Any]) -> None:
        raw["duration_signal"]["worship_max_seconds"] = 3600

    gates = [
        ("전역 금지어가 태깅 사전에 들어감", add_forbidden, "금지어"),
        ("crisis_fixed가 mapping에 등장", crisis_in_mapping, "crisis_fixed"),
        ("정의되지 않은 주제 참조", unknown_theme, "정의되지 않은"),
        ("media_defaults 세분류 누락", defaults_mismatch, "집합이 다르다"),
        ("media_defaults 값이 media_types 밖", bad_default_value, "media_types에 없다"),
        ("duration_signal 구간 겹침", overlapping_duration, "겹친다"),
    ]
    for label, mutate, needle in gates:
        message = _load_broken(mutate)
        hit = next((line.strip() for line in message.splitlines() if needle in line), "")
        _check(failures, bool(hit), f"차단: {label}", hit[:70])

    # media_types 사전에는 금지어 규칙을 적용하지 않는다 (themes.yaml 명시).
    # "말씀"은 sermon 사전에 실제로 들어 있고, 그것이 옳다.
    def forbidden_in_media_types(raw: dict[str, Any]) -> None:
        raw["media_types"][0]["title_keywords"].append("간증")

    _check(
        failures,
        _load_broken(forbidden_in_media_types) == "",
        "media_types 사전에는 금지어 규칙을 적용하지 않는다",
    )

    print("\n7. 실제 themes.yaml 상태")
    print("-" * 76)
    offenders = [
        f"{t.id}:{k}"
        for t in themes.themes
        for k in t.title_keywords
        if any(w in k for w in FORBIDDEN_KEYWORDS)
    ]
    _check(failures, not offenders, "태깅 사전에 전역 금지어 없음", ", ".join(offenders))
    empty = [t.id for t in themes.taggable if not t.title_keywords]
    _check(failures, not empty, "태깅 대상 주제에 키워드가 모두 있다", ", ".join(empty))

    print("\n" + "=" * 76)
    if failures:
        print(f"실패 {len(failures)}건:")
        for f in failures:
            print(f"  - {f}")
        return EXIT_FAIL
    print("전부 통과")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
