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
     — 제목 어휘가 동점이면 곡명 구조로 가른다. 개정 전에는 동점이 제목 증거를
       버리고 채널로 내려가 찬양 콘티 24건이 sermon이 됐다 (2026-08-24)
  4. themes.yaml 게이트 6종이 실제로 빌드를 세운다 (고장을 주입해 확인)
  5. 실제 themes.yaml이 전역 금지어를 태깅 사전에 쓰지 않는다
"""

from __future__ import annotations

import dataclasses
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
    is_conti_structure,
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
    # 4순위 — 양쪽 다 걸리고 곡명 구조도 아니면 길이로 넘어간다
    ("설교와 찬양이 함께하는 시간", 2400, "mixed", SERMON, "duration"),
    ("설교 후 찬양", 300, "mixed", WORSHIP, "duration"),
    #
    # --- 동점을 곡명 구조로 가른다 (2026-08-24, HANDOFF 2.43) ---------------
    # 실사용 제보 "말씀 탭에 찬양 영상이 계속 보인다"로 열렸다. 아래 세 건은
    # 전부 실측 제목이고, 개정 전에는 **채널 단계**에서 sermon으로 확정됐다.
    # 실측 1,067건 중 24건이 이 경로로 회복됐다(전부 sermon → worship).
    #
    # (가) 예배명이 sermon 어휘다 — "금요기도"는 때이지 형식이 아니다
    (
        "주를 기억합니다 + 아 하나님의 은혜로 + 하나님의 나라 진동치 않네"
        " + 주 예수 나의 산 소망 | 오륜교회 금요기도회 찬양 블레싱워십 (2026-08-14)",
        2400,
        "sermon",
        WORSHIP,
        "conti",
    ),
    # (나) 곡명 안의 "말씀"이 sermon 어휘다 — 곡명은 형식 증거가 아니다
    (
        "크신 내 주님 + 주의 약속하신 말씀 위에서 + 전능하신 나의 주 하나님은"
        " + 나의 믿음 주께 있네 | 오륜교회 주일 4부예배 찬양 하이프레이즈 (2026-08-02)",
        2400,
        "sermon",
        WORSHIP,
        "conti",
    ),
    # (다) 구분자가 /이고 형식 표지가 앞머리 대괄호에 있다
    (
        "[주일찬양] 휘문채플 / 26.07.19 / 주의 약속하신 말씀 위에 서 / 은혜 / 에벤에셀 하나님",
        2400,
        "sermon",
        WORSHIP,
        "conti",
    ),
    #
    # --- 곡명 구조가 삼키면 안 되는 정탐 (위 규칙의 가드) -------------------
    # (라) worship 어휘가 프로그램명("W워십")에서 왔다.
    #   ★ 2026-08-28 — 근거가 channel → **title**로 올라갔다. 판정은 그대로 sermon이다.
    #     단독 '워십'을 어휘에서 빼면서(HANDOFF 2.81) 동점이 아예 성립하지 않는다.
    #       전  sermon 3 + worship 1(워십) → 동점 → 곡명 1개라 가드 ①에 막힘
    #           → 장절 없음 → **채널**이 답했다
    #       후  sermon 3 + worship 0        → 1순위에서 바로 확정
    #     ⚠ 이 줄이 channel로 되돌아가면 '워십'이 어휘에 다시 들어온 것이다.
    (
        "[LIVE] W워십ㅣ굿티비(GOOD TV)와 함께 하는 꿈의교회 저녁예배"
        " _ 냄새는 감출 수 없다ㅣ김학중 목사 설교 잠언 강해 26/8/16",
        3600,
        "sermon",
        SERMON,
        "title",
    ),
    # (마) ★ /가 곡명 구분자가 아니라 메타데이터 구분자다 (실측 18건).
    #     곡명은 2개 이상으로 잡히지만 나머지 구간에 sermon만 남아 sermon이다.
    #     (가)~(다)와 **같은 채널**이 올리는 형식이라 이 가드가 없으면 함께 뒤집힌다.
    (
        "[사역자설교] 성경을 이루려 함이니라 / 마가복음 14:43-52 - 임대선 목사"
        " / 정의학 초원지기 | 2026.08.05",
        2400,
        "sermon",
        SERMON,
        "title",
    ),
    # (바) 설교 제목에 "찬양"이 들어간다 — 곡명 1개라 장절 신호가 살아난다
    (
        "[생명의 삶 큐티] 찬양의 이유, 영원한 인자하심 |시편 117:1~118:7| 김상수 목사 | 260714QT",
        900,
        "devotion",
        SERMON,
        "scripture",
    ),
    # 5순위 — 아무것도 안 걸리고 길이도 애매하면 unknown
    ("교회 소식 브리핑", 900, "mixed", UNKNOWN, "none"),
    # ★ 단독 '워십'은 형식 신호가 아니다 (2026-08-28 · HANDOFF 2.81).
    #   프로그램·예배 이름에서만 나타났다. 실측 10건 전부 그랬고 진짜 찬양은 0건이다.
    #   ⚠ 아래 둘은 41~54분 설교다. '워십'을 되살리면 여기서 먼저 깨진다.
    (
        "그의 마음을 따르는 사람 1 : 조용한 혁명┃한소망교회 최봉규 목사 [C채널] 한소망비전워십",
        3248, "sermon", SERMON, "channel",
    ),
    (
        "받은 은혜, 잃어버린 은혜!┃만나교회 김병삼 목사 [C채널] 만나워십",
        3091, "sermon", SERMON, "channel",
    ),
    # ⚠ 반대쪽 — '워십팀'·'워십밴드'는 남긴다. 이건 형식을 말한다
    ("주일 찬양 - 워십팀 인도", 1500, "mixed", WORSHIP, "title"),
    # ⚠ '워십'을 포함하되 다른 worship 어휘도 있으면 그대로 찬양이다 (실측 30건)
    ("빛으로 비추시네 + 온 땅의 주인 | 오륜교회 주일 5부예배 찬양 램넌트워십", 1500, "sermon", WORSHIP, "title"),
    # ★ 사각지대 경계를 고정한다 (2026-08-28 · sermon_min 1800 → 1200).
    #   이 세 줄이 임계를 지킨다 — 값을 바꾸면 여기서 먼저 깨진다.
    #   1200 미만은 여전히 unknown이고(사각지대는 600~1200으로 좁아졌다),
    #   1200 이상은 sermon이다. 20분대 강해가 풀린 자리가 이것이다.
    ("어느 쪽도 아닌 제목 A", 1199, "mixed", UNKNOWN, "none"),
    ("어느 쪽도 아닌 제목 B", 1200, "mixed", SERMON, "duration"),
    ("어느 쪽도 아닌 제목 C", 1500, "mixed", SERMON, "duration"),
    # 승인 목록에 없는 채널(content_type 미상)도 같은 경로를 탄다
    ("성경통독 창세기 1장", 1200, None, SERMON, "title"),
    #
    # --- 안 A 곡명 나열 (2026-08-28 · HANDOFF 2.89) ------------------------
    # ★ 사용자 신고 2건. 어휘가 하나도 안 걸려 길이 규칙까지 내려가 sermon이었다.
    #   ⚠ 근거가 songlist가 아니라 duration으로 되돌아가면 규칙이 꺼진 것이다.
    (
        "[사랑의교회] 예수 피를 힘입어/문들아 머리 들어라/나는 주만 높이리"
        "/나 주님의 기쁨 되기 원하네/그리스도의 계절",
        1248, "mixed", WORSHIP, "songlist",
    ),
    (
        "[사랑의교회] 두 손 들고/성령이여 내 영혼을/기뻐하며 승리의 노래 부르리"
        "/주께서 높은 보좌에/예배합니다",
        1226, "mixed", WORSHIP, "songlist",
    ),
    # unknown이던 것도 구제된다 (10~20분 사각지대)
    ("[사랑의교회] 주께서 높은 보좌에/두 손 들고/지극히 높으신 주", 723, "mixed", WORSHIP, "songlist"),
    #
    # ⛔ 임계는 3이다. 곡명 2개는 콘티로 보지 않는다 — 날짜·괄호가 잘려 가짜가 된다.
    ("[사랑의교회] 나 속죄함을 받은 후 / 모든 만물 다스리시는", 900, "mixed", UNKNOWN, "none"),
    #
    # ⛔ 가드 G1 — 나머지 구간에 sermon 어휘가 있으면 콘티가 아니다.
    ("[사역자설교] 가/나/다 | 우리들교회", 900, "mixed", SERMON, "title"),
    # ⛔ 가드 G2 — 곡명 자리에 장절이나 설교자 크레딧이 있으면 콘티가 아니다.
    #   (장절이 살아 있으므로 2순위가 답한다)
    ("[우리들] 가나다라 / 마가복음 14:43-52 / 마바사아", 900, "mixed", SERMON, "scripture"),
    #
    # ⚠ 자리 확인 — 동점 뒤이므로 **1순위가 이긴다.** 제목이 형식을 직접 말하면
    #   곡명 구조가 그것을 덮지 않는다. ⛔ 이 줄이 songlist로 바뀌면 규칙이
    #   1순위 앞으로 올라간 것이다 (근거 110건이 옮겨간다 — 올리지 말 것).
    ("주일 찬양대 특송 가/나/다/라", 900, "mixed", WORSHIP, "title"),
    #
    # --- 안 B 설교자 크레딧이 붙은 '찬양' (2026-08-28) ----------------------
    # ★ 사용자 신고 2건. '찬양' 하나가 1순위에서 worship을 확정하고 있었다.
    #   어휘를 빼면 3순위(채널)가 답한다 — 규칙을 앞에 놓지 않는 것이 이 안의 요점이다.
    (
        "수원은혜교회 황유석 목사 | 인생의 밤에 노래하게 하시는 하나님을 찬양합니다"
        " [C채널] 비전메시지",
        2035, "sermon", SERMON, "channel",
    ),
    (
        "빛의자녀교회 김형민 목사(빛의자녀 472회) - 무릎 꿇고 찬양하세요(샤인영성)",
        2084, "sermon", SERMON, "channel",
    ),
    # ⛔ 크레딧이 없으면 '찬양'은 그대로 형식 어휘다
    ("무릎 꿇고 찬양하세요", 2084, "sermon", WORSHIP, "title"),
    # ⛔ 교회명 없이 'OOO 목사'만 있으면 이 규칙이 아니다 (안 A′ 크레딧과 다른 형태)
    ("찬양의 자리로 - 홍길동 목사", 2084, "sermon", WORSHIP, "title"),
    # ⚠ '찬양' 말고 다른 worship 어휘는 그대로 센다. 실측 제목이고, 크레딧이 있어도
    #   '예배실황'은 남아 sermon('주일예배')과 동점이 된 뒤 채널이 답한다.
    #   ⛔ 이 줄이 sermon/title로 바뀌면 SERMON_TOPIC_WORDS가 늘어난 것이다.
    (
        "꿈의교회 김학중 목사(주일예배 실황 707회) - 멋지게 롱런하는 인생이 되려면",
        2746, "sermon", SERMON, "channel",
    ),
    #
    # --- 설교자 크레딧 (2026-08-28 · 안 A′ · HANDOFF 2.83) -----------------
    # ★ 두 줄은 **실측에서 판정이 바뀐 전부**다. 둘 다 길이 규칙이 찬양으로
    #   확정하던 설교이고, 이 신호가 그 앞에서 sermon을 준다.
    #   ⚠ 근거가 speaker가 아니라 duration으로 되돌아가면 신호가 꺼진 것이다.
    (
        "염려 대신 감사를 | 더하는교회 | 최민우 목사 | 더 기프트 #더기프트 #더하는교회 #최민우",
        180, "mixed", SERMON, "speaker",
    ),
    ("[사랑의교회] 하나님은 우리의 피난처 - 조성환 목사", 599, "mixed", SERMON, "speaker"),
    # 직함이 붙은 형태도 같은 구간이다 (사랑의교회 실측)
    ("[사랑의교회] 광야에서의 승리 - 윤대혁 후임목사", 599, "mixed", SERMON, "speaker"),
    ("[사랑의교회] 죄로부터의 해방 - 오정현 담임목사", 599, "mixed", SERMON, "speaker"),
    # 콜론 관행(연동교회)도 같다
    ("[아침 예배] 인간의 생명과 돼지의 생명 : 이성희 목사", 599, "mixed", SERMON, "speaker"),
    #
    # ⛔ 오탐 방어 — '목사'라는 **낱말**만으로는 걸리면 안 된다.
    #   구간이 통째로 "OOO 목사"가 아니면 크레딧이 아니다. 안 A(어휘)가
    #   정확도 40%였던 이유가 이것이다 (간증 프로그램 출연자가 목사다).
    ("김형민 목사가 전하는 오늘의 이야기", 900, "mixed", UNKNOWN, "none"),
    ("목사님과 함께 걷는 길", 900, "mixed", UNKNOWN, "none"),
    # 제목 어휘가 형식을 직접 말하면 크레딧이 그것을 덮지 않는다 (1순위가 앞이다)
    ("주일 찬양 콘티 | 홍길동 목사", 900, "mixed", WORSHIP, "title"),
    # 장절이 있으면 근거는 scripture다 — 크레딧은 그 뒤다
    ("복 있는 사람 | 시편 1:1-6 | 홍길동 목사", 900, "mixed", SERMON, "scripture"),
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
        # 2026-08-24 추가분 — 3차 발굴 후보의 실제 제목 관행 (HANDOFF 2.46)
        #   현재 코퍼스에서는 0건이라, 이 검사가 유일한 방어다.
        #   "0건이니 죽은 어휘"라며 지우면 여기서 걸린다.
        ("[CCM Playlist] 감사가 줄어들던 날에 | 피아노 찬양 | [4시간]", True),
        ("[미니뮤직 LIVE] 실시간 연주 찬양 | 테마= 주께 더 가까이", True),
        # ⛔ `주일찬양`은 검토하고 뺐다 — 적중 14건이지만 전부 회중 찬양 콘티다.
        #   넣으면 위 세 줄과 같은 이유로 joy_praise와 구분이 무너진다.
        ("[주일 BRANDNEW 찬양] 휘문채플 / 26.08.02 / 말씀하소서", False),
    ):
        hit = "quiet_worship" in {m.theme_id for m in tag_themes(title, themes)}
        _check(
            failures,
            hit is want,
            f"quiet_worship {'태깅' if want else '비태깅'}: {title[:38]}",
        )
    print("\n3-1. 채널명 접두어를 콘텐츠로 착각하지 않는다")
    print("-" * 76)
    # 2026-08-24 — 3차 발굴 1위 후보가 드러낸 오탐 유형 (HANDOFF 2.46).
    #   `쉼과 회복이 있는 교회`는 영상 1,994건 전부에 [쉼과회복]을 붙인다.
    #   그대로 두면 주일예배 라이브가 rest로 태깅돼 풀 0이 "메워진다".
    #
    # ★ 아래 뒤쪽 두 줄이 이 검사의 핵심이다. 대괄호를 **전부** 떼는 안은
    #   실측에서 태깅 118건을 잃었다([생명의 삶 큐티] 100 · [매일성경] 18,
    #   전부 daily_word). 브랜드인지 내용인지는 괄호 모양으로 갈리지 않는다.
    for title, channel, theme_id, want in (
        ("[쉼과회복] 주일예배 라이브 - 2026.08.23 (3부)", "쉼과 회복이 있는 교회", "rest", False),
        ("[쉼과회복] 수요 성경강좌 창세기 시리즈(8)", "쉼과 회복이 있는 교회", "renewal", False),
        # 채널명을 주지 않으면 예전과 똑같이 동작한다 (하위 호환)
        ("[쉼과회복] 주일예배 라이브 - 2026.08.23 (3부)", None, "rest", True),
        # 브랜드가 아니라 프로그램 이름이면 그대로 둔다 — daily_word 주력 공급
        ("[생명의 삶 큐티] 찬양의 이유, 영원한 인자하심", "CGN 생명의 삶", "daily_word", True),
        ("[매일성경]으로 하루를 시작하며 듣는 아침의 말씀", "CGN", "daily_word", True),
    ):
        hit = theme_id in {m.theme_id for m in tag_themes(title, themes, channel)}
        _check(
            failures,
            hit is want,
            f"{channel or '(채널명 없음)':14} {theme_id:11}"
            f" {'태깅' if want else '비태깅'}: {title[:34]}",
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

    # =========================================================================
    # 2026-08-20 — 태깅 오탐 4유형 (HANDOFF 2.29). 유형마다 메커니즘이 다르다.
    # =========================================================================
    # 실측 제목을 그대로 고정한다. 방어를 끄거나 느슨하게 하면 여기서 깨진다.
    print("\n3-2. 태깅 오탐 방어 4종")
    print("-" * 76)
    for title, theme_id, want, kind in (
        # [어절 경계] 정규화가 띄어쓰기를 지워 짧은 키워드가 우연히 걸린다
        ("인생의 지름길이 아닌 우회로는 견딜 수 없다면 l 원유경 목사", "trust", False, "어절경계"),
        ("[아침예배] 하나님의 지독한 사랑 (겔 29:17-21)_베이직교회", "trust", False, "어절경계"),
        ("[생명의 삶 큐티] 성령의 능력으로 전하는 하나님의 지혜", "trust", False, "어절경계"),
        ("강남중앙침례교회 최병락 목사(TV강단 42회) - 복 있는 사람", "renewal", False, "어절경계"),
        # [부정 문맥] 밝은 주제 + 방향을 뒤집는 어휘
        ("[아침예배] 불행을 기뻐하는 죄 (겔 25:1-17)_베이직교회", "joy_praise", False, "부정문맥"),
        ("[생명의 삶 큐티] 하나님 백성의 패망을 기뻐하는 죄", "joy_praise", False, "부정문맥"),
        # [고유명사] 키워드가 기관 이름 안에서만 걸렸다
        ("감사드림교회 차영아 목사(TV강단 32회) - 순종에 하늘의 문이 열립니다",
         "gratitude", False, "고유명사"),
        # [표면 일치] 사람이 지정한 (문맥어, 주제)
        ("최일관 목사 낮은담교회 새벽만나 \u201c안식일의 주인\u201d 누가복음 6:1-5",
         "rest", False, "표면일치"),
        # ★ 정탐은 살아 있어야 한다 — 방어가 과하면 여기서 깨진다
        ("[주일 BRANDNEW 찬양] 판교채플/ 말씀이 육신되어 / 주 나와 함께 하시니",
         "presence", True, "정탐:4음절은 어절을 넘어도 된다"),
        ("꿈의교회 저녁예배 설교 l 의지할 가족, 의지할 교회 l 김문겸 목사",
         "trust", True, "정탐:한 어절 안이면 걸린다"),
        ("나를 향한 주의 사랑 + 내 마음을 가득 채운 | 오륜교회", "love", True, "정탐:공백 키워드"),
        ("우리의 예배는 + 새 힘 얻으리 + 예수 사랑하심은 | 오륜교회", "strength", True, "정탐:공백 키워드"),
        ("감사와 관련된 기독교 명언 10가지 #감사 #말씀", "gratitude", True, "정탐:기관명이 아니다"),
        ("[생명의 삶 큐티] 고난을 인내하고 죄를 이기는 부활 소망", "hope", True, "정탐:hope는 밝은 계열이 아니다"),
    ):
        hit = theme_id in {m.theme_id for m in tag_themes(title, themes)}
        _check(failures, hit is want, f"[{kind}] {theme_id} {'있음' if want else '없음'}: {title[:34]}")

    # 고장 주입 1 — 어절 경계를 끄면 오탐이 되살아난다
    import lib.tagging as _tag

    saved = _tag.SHORT_KEYWORD_SYLLABLES
    try:
        _tag.SHORT_KEYWORD_SYLLABLES = 0
        back = "trust" in {m.theme_id for m in tag_themes("인생의 지름길이 아닌 우회로는", themes)}
        _check(failures, back, "고장 주입: 경계를 끄면 '인생의 지'가 다시 의지로 걸린다")
        # 고장 주입 2 — 전체 적용하면 정탐이 죽는다
        _tag.SHORT_KEYWORD_SYLLABLES = 99
        lost = "presence" not in {
            m.theme_id for m in tag_themes("판교채플 / 주 나와 함께 하시니", themes)
        }
        _check(failures, lost, "고장 주입: 전체 적용하면 '함께 하시니' 정탐이 죽는다")
    finally:
        _tag.SHORT_KEYWORD_SYLLABLES = saved
    _check(
        failures,
        "trust" not in {m.theme_id for m in tag_themes("인생의 지름길이 아닌 우회로는", themes)}
        and "presence" in {m.theme_id for m in tag_themes("판교채플 / 주 나와 함께 하시니", themes)},
        "고장을 되돌리면 둘 다 정상으로 돌아온다",
    )
    # 고장 주입 3 — hope를 밝은 계열에 넣으면 정상 콘텐츠를 잃는다
    saved_bright = _tag.BRIGHT_THEMES
    try:
        _tag.BRIGHT_THEMES = saved_bright + ("hope",)
        gone = "hope" not in {
            m.theme_id for m in tag_themes("고난을 인내하고 죄를 이기는 부활 소망", themes)
        }
        _check(failures, gone, "고장 주입: hope를 밝은 계열에 넣으면 부활 소망 설교를 잃는다")
    finally:
        _tag.BRIGHT_THEMES = saved_bright

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

    # 고장 주입 — 신호를 끄면 두 건이 **길이 규칙으로 되돌아간다**.
    # 이 확인이 없으면 "speaker로 나온다"가 우연인지 규칙 때문인지 알 수 없다.
    off = dataclasses.replace(themes, speaker_credit_signal=False)
    for title, seconds in (
        ("염려 대신 감사를 | 더하는교회 | 최민우 목사 | 더 기프트", 180),
        ("[사랑의교회] 하나님은 우리의 피난처 - 조성환 목사", 599),
    ):
        back = classify_media_type(title, seconds, "mixed", off)
        _check(
            failures,
            back.media_type == WORSHIP and back.reason == "duration",
            f"고장 주입: 크레딧을 끄면 길이 규칙이 다시 찬양으로 확정한다 — {title[:24]}",
            f"실제 {back.media_type}/{back.reason}",
        )
    # ⚠ 순서 확인 — 크레딧이 **길이 규칙보다 앞**이어야 효과가 있다.
    _check(
        failures,
        classify_media_type("어느 쪽도 아닌 제목 - 홍길동 목사", 300, "mixed", themes).reason
        == "speaker",
        "크레딧이 길이 규칙보다 앞에서 판정한다",
    )

    # ⚠⚠ 안 A의 확인되지 않은 취약점을 **여기서 고정한다** (2026-08-28 · 사용자 지시).
    #   두 가드가 모두 우리들교회의 **현재 제목 관행**에 기대고 있다 —
    #   '[사역자설교]' 접두사(G1)와 곡명 자리의 장절·목사 표기(G2).
    #   그 채널이 관행을 바꾸면 아래 7건이 한꺼번에 worship 오탐이 된다.
    #   ⛔ 이 목록을 지우지 말 것. 게이트가 실패하는 것이 조용히 오분류되는 것보다 낫다.
    WORSHIP_MUST_NOT = [
        "[사역자설교] 하나님의 율법을 따라 / 에스라 7:11-20 - 이성훈 목사 / 김형진 평원지기 | 2026.08.19",
        "[사역자설교] 이름을 기억하시는 하나님 / 에스라 2:1-35 - 김성우 목사 / 김미현 초원지기 | 2026.08.12",
        "[사역자설교] 성경을 이루려 함이니라 / 마가복음 14:43-52 - 임대선 목사 / 정의학 초원지기 | 2026.08.05",
        "[사역자설교] 나는 아니지요 / 마가복음 14:12-21 - 최대규 목사 / 차연실 평원지기 | 2026.07.29",
        "[사역자설교] 가장 큰 계명 / 마가복음 12:28-34 - 정정환 목사 / 박재석 초원지기 | 2026.07.22",
        "[사역자설교] 이런 일을 할 권위 / 마가복음 11:27-33 - 김정태 목사 / 정상호 초원지기 | 2026.07.15",
        "[사역자설교] 부끄러운 명단 / 에스라 10:18-44 - 박인용 목사 / 류명기 초원지기 | 2026.08.26",
    ]
    broke = [t for t in WORSHIP_MUST_NOT if is_conti_structure(t, themes)]
    _check(
        failures,
        not broke,
        f"⚠ 우리들교회 사역자설교 {len(WORSHIP_MUST_NOT)}건은 곡명 나열로 보지 않는다",
        f"{len(broke)}건이 콘티로 잡혔다 — {broke[:1]}",
    )
    # 가드를 하나씩 꺼서 **각각이 실제로 무엇을 막고 있는지** 확인한다.
    saved_min = _tag.CONTI_STRUCTURE_MIN_SONGS
    try:
        _tag.CONTI_STRUCTURE_MIN_SONGS = 2
        loosened = [t for t in WORSHIP_MUST_NOT if is_conti_structure(t, themes)]
        _check(
            failures,
            not loosened,
            "고장 주입: 임계를 2로 내려도 가드 둘이 남아 사역자설교를 막는다",
            f"{len(loosened)}건 뚫림",
        )
        # 임계 2에서 실제로 뚫리는 것 — 곡명 2개짜리가 콘티로 잡힌다.
        # ⚠ 가드는 이것을 못 막는다. 곡명 인식 자체가 느슨해지기 때문이다.
        _check(
            failures,
            is_conti_structure("[사랑의교회] 나 속죄함을 받은 후 / 모든 만물 다스리시는", themes),
            "고장 주입: 임계를 2로 내리면 곡명 2개짜리가 콘티로 잡힌다 (실측 오탐 25건의 문)",
        )
    finally:
        _tag.CONTI_STRUCTURE_MIN_SONGS = saved_min
    _check(
        failures,
        not is_conti_structure("[사랑의교회] 나 속죄함을 받은 후 / 모든 만물 다스리시는", themes),
        "고장을 되돌리면 곡명 2개짜리는 다시 콘티가 아니다",
    )
    # 진짜 콘티는 잡아야 한다 (위 방어가 정탐을 죽이지 않는지)
    CONTI_MUST = [
        "[사랑의교회] 예수 피를 힘입어/문들아 머리 들어라/나는 주만 높이리/나 주님의 기쁨 되기 원하네/그리스도의 계절",
        "[사랑의교회] 주께서 높은 보좌에/두 손 들고/지극히 높으신 주",
        "[사랑의교회] 찬송으로 보답할 수 없는/나 무엇과도 주님을/오직 예수 다른 이름은 없네",
    ]
    missed_conti = [t for t in CONTI_MUST if not is_conti_structure(t, themes)]
    _check(
        failures,
        not missed_conti,
        f"실제 콘티 {len(CONTI_MUST)}건은 곡명 나열로 잡는다",
        f"{len(missed_conti)}건 놓침",
    )

    # 안 B — 어휘를 좁히는 규칙이 **그 문맥에서만** 작동하는지
    _check(
        failures,
        _tag.has_church_speaker_credit("수원은혜교회 황유석 목사 | 인생의 밤에"),
        "설교자 크레딧('OOO교회 OOO 목사')을 인식한다",
    )
    for negative in ("무릎 꿇고 찬양하세요", "홍길동 목사 - 찬양의 자리로", "오륜교회 주일 찬양 헤세드"):
        _check(
            failures,
            not _tag.has_church_speaker_credit(negative),
            f"크레딧이 아닌 것을 크레딧으로 보지 않는다: {negative[:22]}",
        )
    _check(
        failures,
        _tag.SERMON_TOPIC_WORDS == ("찬양",),
        "⛔ 문맥에서 빼는 어휘는 '찬양' 하나뿐이다 — 늘리려면 오탐을 다시 재야 한다",
        str(_tag.SERMON_TOPIC_WORDS),
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
