"""제목 태깅 — 주제(theme)와 형식(media_type)을 가린다. **API를 부르지 않는다.**

두 축은 서로 다른 질문에 답한다 (themes.yaml media_type 절).
    theme       이 영상을 어느 감정 화면에 붙일 것인가   comfort · rest · guidance ...
    media_type  그 응답을 어떤 형식으로 받을 것인가       말씀 / 찬양
한 영상은 둘 다 갖는다. 사전도 따로 두며, 섞으면 둘 다 망가진다.

[제목만 본다]
    설명란·태그는 보지 않는다 (PLAN.md 3.3, FYM 교훈). 대상 텍스트는
    lib/filters.py의 blocklist_text() 한 곳에서만 정한다.

[키워드 매칭 규칙 — 한글과 영문이 다르다]
    한글 키워드  normalize() 후 부분 매칭. 띄어쓰기·문장부호·반복을 접어서
                 "새 힘"이 "새힘을 주시는"에 걸리게 한다. themes.yaml의
                 키워드 설계 원칙 2·3("짧은 키워드는 일상어를 삼킨다",
                 "한글은 음절 단위다")이 이 매칭을 전제로 쓰여 있다.
    영문 키워드  단어 경계 매칭. themes.yaml이 "QT"에 대해 명시적으로 요구한 것이다
                 ('영문 2자 — 대소문자 정규화 후 단어 경계 매칭으로만').
                 normalize()는 문장부호를 지우므로 부분 매칭을 쓰면 "qt"가
                 엉뚱한 영문 제목 안에서 걸린다.
                 ⚠ 대신 "Q.T." 표기는 놓친다 — 점이 경계가 되어 q와 t로 갈린다.
                   오탐과 미탐 중 미탐을 고른 것이고, themes.yaml의 요구가 그쪽이다.

[본문 장절 패턴이 sermon의 가장 강한 신호다]
    책 이름은 lib/krv_source.py의 BOOK_KEYS를 재사용한다 — 사전을 두 벌 두지 않는다
    (themes.yaml scripture_reference_signal 주석).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from lib.krv_source import BOOK_KEYS
from lib.normalize import normalize
from lib.themes import Themes

# media_type 판정값. themes.yaml media_types의 id와 같아야 하며,
# unknown만 여기서 정의한다 (사전이 없는 "판별 실패" 상태이기 때문).
SERMON = "sermon"
WORSHIP = "worship"
UNKNOWN = "unknown"

# 채널 content_type → media_type 직행표 (themes.yaml 판별 우선순위 1).
#   devotion(큐티·묵상)은 sermon으로 본다 — 말씀 해설이기 때문이다.
#   mixed는 여기 없다. 제목으로 가려야 하는 대상이 정확히 그쪽이다.
CHANNEL_CONTENT_TYPE_MAP = {
    "sermon": SERMON,
    "worship": WORSHIP,
    "devotion": SERMON,
}

# 판정 근거 — 리포트에 남겨 "사전을 고쳐야 하나"를 사람이 판단할 수 있게 한다.
REASON_CHANNEL = "channel"
REASON_SCRIPTURE = "scripture"
REASON_TITLE = "title"
# 동점을 곡명 구조로 갈랐다 — 아래 split_conti 참조.
REASON_CONTI = "conti"
REASON_DURATION = "duration"
REASON_NONE = "none"


def _scripture_pattern() -> re.Pattern[str]:
    """본문 장절 패턴 — "요한복음 3:16" · "에스겔 40장" · "시편 23편" · "요 3:16".

    두 가지 방어가 들어 있다.

    1. 앞 글자가 한글이면 매칭하지 않는다 (`(?<![가-힣])`).
       BOOK_KEYS에는 1음절 약어가 많다(행·요·사·시…). 방어가 없으면
       "여행 12장"의 "행 12장"이 사도행전으로 잡힌다.
    2. 숫자 뒤에 장절 표지가 반드시 와야 한다 (`:`·`장`·`편` 또는 범위 하이픈).
       숫자만 허용하면 "감사 3가지 이유"의 "사 3"이 이사야로 잡힌다.

    이 두 조건을 다 만족하는 제목은 실제로 본문을 밝힌 설교·강해다.
    찬양 제목에는 장절이 거의 붙지 않아 변별력이 높다.
    """
    books = sorted(BOOK_KEYS, key=len, reverse=True)  # 긴 이름 우선 (요한복음 > 요)
    alternation = "|".join(re.escape(b) for b in books)
    return re.compile(
        r"(?<![가-힣])(?:" + alternation + r")\s*\d{1,3}\s*(?::|장|편|[-~]\s*\d)"
    )


SCRIPTURE_RE = _scripture_pattern()

# 영문 키워드용 — 영문·숫자에 둘러싸이지 않은 위치에서만 맞춘다.
_ASCII_ONLY = re.compile(r"^[a-zA-Z0-9]+$")

# =============================================================================
# 오탐 방어 4종 (2026-08-20) — 유형마다 메커니즘이 다르다
# =============================================================================
# 실측(dist/titles.json 1,067건)에서 태깅 오탐이 네 유형으로 갈렸고, **전역 규칙
# 하나로는 하나밖에 못 잡는다**는 것이 확인됐다. 그래서 넷을 따로 둔다.
#
#   어절 경계   "인생의 지름길" → 의지    아래 SHORT_KEYWORD_SYLLABLES
#   부정 문맥   "불행을 기뻐하는 죄"      아래 NEGATIVE_CONTEXT + BRIGHT_THEMES
#   고유명사    "감사드림교회"            아래 ORG_SUFFIXES
#   표면 일치   "안식일의 주인" → rest    아래 SURFACE_EXCLUSIONS (사람이 지정)
#
# ⚠ **여기는 배치 전용이다.** app/src/lib/classify.js의 입력 분류와 섞지 말 것 —
#   그쪽은 normalize가 scripts/lib/normalize.py와 문자 단위로 같아야 하는 제약이
#   있어 비용이 완전히 다르다(HANDOFF 4.7이 둘을 한 덩어리로 묶어 뒀는데,
#   2026-08-20에 갈랐다). 제목 태깅은 그 제약을 받지 않는다.

# [어절 경계] 이 음절 수 이하의 한글 키워드는 어절을 넘어 매칭되지 않는다.
#   정규화가 띄어쓰기를 지우므로 짧은 키워드가 어절 경계를 넘어 우연히 걸린다.
#     "인생의 지름길"     → 인생의지름길   → `의지`  ✗
#     "하나님의 지혜"      → 하나님의지혜   → `의지`  ✗
#     "TV강단 42회 복 있는" → 42회복있는     → `회복`  ✗
#   실측: 경계를 넘는 매칭 25건 중 **2음절 키워드가 만든 4건이 전부 오탐**이었다.
#
#   ⛔ 이 값을 3 이상으로 올리지 말 것. 4음절 `함께하시`가 "주 나와 함께 하시니"를
#     잡는 것은 **정탐**이다(한국어 띄어쓰기 관행 차이). 전체 적용하면 25건 중
#     19건이 `그 사랑`·`주의 사랑`·`새 힘` 같은 **공백 포함 키워드의 정탐**이라
#     통째로 사라진다. 2음절에만 걸어야 오탐 4건만 정확히 걸러진다.
SHORT_KEYWORD_SYLLABLES = 2

# [부정 문맥] 방향을 뒤집는 어휘. 밝은 계열 주제에만 적용한다.
#   HANDOFF 4.5가 "주제마다 exclude_keywords를 다는 것보다 전역 규칙 하나가
#   단순하다"고 남긴 대안이다. 실측 2건을 잡고 정상 콘텐츠는 막지 않았다
#   (밝은 주제 태깅 41건 중 2건만 막힌다).
NEGATIVE_CONTEXT = (
    "죄", "심판", "멸망", "패망", "저주", "진노", "재앙", "불행", "형벌", "징계",
)
# 이 주제만 막는다. hope·patience는 "고난을 인내하고 죄를 이기는 부활 소망"처럼
# 부정 어휘와 함께 오는 것이 정상이라 뺐다 — 막으면 정상 콘텐츠를 잃는다.
BRIGHT_THEMES = ("joy_praise", "gratitude")

# [고유명사] 이 말로 끝나는 어절은 기관 이름이다. 그 안에서만 걸린 키워드는 버린다.
#   "감사드림교회 차영아 목사 - 순종에 하늘의 문이 열립니다" → gratitude ✗
#   내용은 순종 설교인데 교회 **이름**에서 `감사`가 걸렸다.
ORG_SUFFIXES = (
    "교회", "선교회", "선교단", "기도원", "방송", "센터", "교구", "신학교", "재단",
)
_TOKEN = re.compile(r"[^\s|｜│/+]+")

# [표면 일치] 기계가 못 가르는 것 — **사람이 지정한다.**
#   (문맥어, 주제) — 제목에 그 말이 있으면 그 주제를 붙이지 않는다.
#   "안식일의 주인"(누가복음 6:1-5)은 안식일 **규례**를 다루는 신학 설교다.
#   글자는 `안식`이 맞지만 지친 사람이 찾는 쉼이 아니다. 뜻을 봐야 갈리므로
#   폴백 시리즈 지정(lib/selection.PROMO_SERIES)과 같은 방식으로 사람이 적는다.
#   ⚠ 늘리기 전에 retag_titles.py --probe로 무엇이 걸리는지 눈으로 셀 것.
SURFACE_EXCLUSIONS = (
    ("안식일", "rest"),
)


def _syllables(keyword: str) -> int:
    return len([c for c in keyword if not c.isspace()])


def _normalized_with_gaps(text: str) -> tuple[str, list[bool]]:
    """정규화 문자열과 "이 글자 앞에 원문 공백이 있었는가" 배열.

    normalize()를 다시 구현하지 않는다 — 공백 위치만 따로 들고 다닌다.
    반복 축약은 어절 **안에서** 일어나므로 경계 판정에 영향을 주지 않는다.
    """
    kept: list[str] = []
    gap: list[bool] = []
    pending = False
    for ch in text.lower():
        if ch.isspace():
            pending = True
            continue
        if not (ch.isalnum() or ch == "_"):
            continue  # 문장부호는 정규화가 지운다. 경계로도 보지 않는다
        kept.append(ch)
        gap.append(pending)
        pending = False
    return "".join(kept), gap


def _crosses_word_gap(title: str, keyword: str) -> bool:
    """이 키워드가 **어절 경계를 넘어야만** 걸리는가."""
    haystack, gap = _normalized_with_gaps(title)
    needle = normalize(keyword)
    if not needle:
        return False
    start = 0
    found = False
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            break
        found = True
        if not any(gap[p] for p in range(i + 1, i + len(needle))):
            return False  # 경계를 안 넘는 자리가 하나라도 있으면 정상 매칭이다
        start = i + 1
    return found


@dataclass(frozen=True)
class ThemeMatch:
    theme_id: str
    hits: tuple[str, ...]


@dataclass(frozen=True)
class MediaVerdict:
    media_type: str
    reason: str

    @property
    def is_known(self) -> bool:
        return self.media_type != UNKNOWN


def matches_keyword(title: str, keyword: str) -> bool:
    """제목이 키워드를 포함하는가 (한글=부분 매칭 / 영문=단어 경계)."""
    if not title or not keyword:
        return False
    if _ASCII_ONLY.match(keyword):
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
        )
        return bool(pattern.search(title.lower()))
    needle = normalize(keyword)
    if not needle or needle not in normalize(title):
        return False
    # 짧은 한글 키워드는 어절을 넘어 걸리지 않는다 (SHORT_KEYWORD_SYLLABLES 주석 참조)
    if " " not in keyword and _syllables(keyword) <= SHORT_KEYWORD_SYLLABLES:
        return not _crosses_word_gap(title, keyword)
    return True


def _only_inside_org_name(title: str, keyword: str) -> bool:
    """이 키워드가 **기관 이름 안에서만** 걸렸는가 (ORG_SUFFIXES 주석 참조)."""
    if " " in keyword:
        return False
    needle = normalize(keyword)
    if not needle:
        return False
    holders = [t for t in _TOKEN.findall(title) if needle in normalize(t)]
    if not holders:
        return False
    return all(t.endswith(s) for t in holders for s in [next(
        (x for x in ORG_SUFFIXES if t.endswith(x)), "\x00")])


def matched_keywords(title: str, keywords: Iterable[str]) -> tuple[str, ...]:
    """걸린 키워드를 전부 돌려준다 — 왜 태깅됐는지 리포트에 남기기 위해서다."""
    return tuple(k for k in keywords if matches_keyword(title, k))


def tag_themes(title: str, themes: Themes) -> tuple[ThemeMatch, ...]:
    """제목을 주제로 태깅한다. 걸리는 주제가 없으면 빈 튜플(=untagged).

    **복수 태깅을 허용한다.** 한 영상이 comfort와 hope에 동시에 걸리면 양쪽
    풀에 들어간다. 주제 풀이 얇은 상태에서 한쪽을 임의로 버릴 이유가 없고,
    themes.yaml의 매핑도 세분류마다 주제를 2~3개씩 겹쳐 쓰도록 짜여 있다.

    위기 전용 주제(crisis_fixed)는 대상에서 빠진다 — Themes.taggable 참조.
    """
    negative = any(word in title for word in NEGATIVE_CONTEXT)
    matches: list[ThemeMatch] = []
    for theme in themes.taggable:
        # [부정 문맥] "불행을 기뻐하는 죄"는 joy_praise가 아니다
        if negative and theme.id in BRIGHT_THEMES:
            continue
        # [표면 일치] 사람이 지정한 (문맥어, 주제) 쌍
        if any(w in title and theme.id == tid for w, tid in SURFACE_EXCLUSIONS):
            continue
        hits = tuple(
            k for k in matched_keywords(title, theme.title_keywords)
            if not _only_inside_org_name(title, k)  # [고유명사]
        )
        if hits:
            matches.append(ThemeMatch(theme_id=theme.id, hits=hits))
    return tuple(matches)


def has_scripture_reference(title: str) -> bool:
    return bool(SCRIPTURE_RE.search(title))


# --- 콘티 제목 분해 --------------------------------------------------------
#
# 찬양 콘티 제목은 곡명을 +·/로 이어붙인 목록이다.
#   오륜교회   "성도여 다 함께 + Jehovah + 하나님의 부르심 | 오륜교회 금요기도회 찬양"
#   낮은담교회 "[주일찬양] 휘문채플 / 26.08.16 / 주님 뜻대로 살기로 했네 / …"
# 두 관행이 달라 +와 / 를 모두 구분자로 본다.
#
# ⚠ 이 분해는 **형식 판별(classify_media_type)의 동점 구간에서도 쓴다.**
#   2026-08-24 이전에는 --songs 통계 전용이었고 "여기서 무엇을 빼든 태깅
#   결과는 달라지지 않는다"고 적혀 있었다. 그 말은 이제 틀리다 — _NOT_A_SONG를
#   고치면 동점 판정이 움직인다.
_SONG_SPLIT = re.compile(r"\s*[+/]\s*")
# 세로줄 뒤는 채널·예배 이름이라 곡명이 아니다.
_TRAILER = re.compile(r"\s*[|｜]\s*")
# 조각 앞머리의 대괄호 표지 — "[주일찬양] 휘문채플"의 앞부분.
_LEADING_TAG = re.compile(r"^\s*[\[(][^\])]{0,24}[\])]\s*")
# 곡명이 아닌 조각.
#   날짜      26.08.16 · 2026 · 08
#   브랜드    휘문채플 · 판교채플 (낮은담교회 예배 장소)
#   부스러기  "Chord)" 처럼 괄호가 깨진 조각, 한글이 없는 짧은 토막
_NOT_A_SONG = re.compile(
    r"^(?:\d{1,4}(?:[.\-/]\d{1,2}){0,2}\(?[^)]{0,4}\)?|"
    r"[가-힣]{0,3}채플|후렴|[^가-힣]{0,12})$"
)

# 콘티로 인정하는 최소 곡명 수. 1이면 콘티가 아니다 — 아래 split_conti 주석 참조.
CONTI_MIN_SONGS = 2


def split_conti(title: str) -> tuple[list[str], str]:
    """제목을 (곡명, 그 외)로 가른다.

    "그 외"는 앞머리 대괄호 표지 + 곡명이 아닌 조각 + 세로줄 뒤 전부다.
    형식을 말하는 어휘는 거의 언제나 이쪽에 있다("… | 오륜교회 금요기도회 찬양 헤세드").
    """
    segments = _TRAILER.split(title)
    head, rest = segments[0], list(segments[1:])
    songs: list[str] = []
    for chunk in _SONG_SPLIT.split(head):
        tag = _LEADING_TAG.match(chunk)
        if tag:
            rest.append(tag.group(0))
            chunk = _LEADING_TAG.sub("", chunk)
        chunk = chunk.strip()
        if not chunk:
            continue
        (rest if _NOT_A_SONG.match(chunk) else songs).append(chunk)
    return songs, " ".join(rest)


def song_names(title: str) -> list[str]:
    """콘티 제목의 곡명만 돌려준다 (retag_titles.py --songs가 쓴다)."""
    return split_conti(title)[0]


def _break_media_tie(title: str, themes: Themes) -> str | None:
    """제목 어휘가 양쪽 다 걸렸을 때 곡명 구조로 가른다. 못 가르면 None.

    [왜 필요한가 — 2026-08-24 실사용 제보로 열렸다]
      "말씀 탭에 찬양 영상이 계속 보인다."
      원인은 동점이었다. 제목에 "찬양"이 명시된 콘티인데도

        곡명 안의 말씀   "주의 약속하신 말씀 위에서" · "말씀하소서" · "말씀이 육신 되어"
        예배명           "금요기도회" · "저녁예배"

      가 sermon 어휘로 함께 걸려 동점이 됐고, 동점은 제목 증거를 통째로 버리고
      장절·채널·길이로 내려간다. 그 아래 단계는 전부 sermon 쪽으로 기운다
      (오륜교회·꿈의교회가 sermon 채널이고, 콘티는 대개 30분을 넘는다).
      **"제목이 채널보다 앞"이라는 2026-08-19 개정이 동점 구간에서만 무효였다.**
      실측 1,067건 중 동점 31건, 그중 22건이 찬양 콘티였다.

    [곡명은 형식 증거가 아니다]
      곡명은 가사 제목이지 "이 영상이 무엇인가"가 아니다. 그래서 곡명 구간을
      빼고 나머지(앞머리 표지 + 세로줄 뒤)에서만 형식 어휘를 다시 센다.

    [곡명 2개 미만이면 손대지 않는다 — 이 가드가 정탐을 지킨다]
      실측에서 걸러진 것들:
        "[LIVE] W워십ㅣ… 저녁예배 _ 냄새는 감출 수 없다ㅣ김학중 목사 설교 잠언 강해"
        "[사역자설교] 울림 웬즈데이 워십 | 사무엘하 19:31-39 - 최대규 목사"
        "[생명의 삶 큐티] 찬양의 이유, 영원한 인자하심 |시편 117:1~118:7| 김상수 목사"
      셋 다 **실제 설교**이고 worship 어휘는 프로그램명·설교 제목에서 왔다.
      곡명이 1개라 여기서 그대로 통과하고 기존 순서를 탄다.

      ⚠ 곡명 2개 이상이라고 콘티인 것은 아니다. 우리들교회 사역자설교 제목은
        "[사역자설교] 제목 / 마가복음 14:43-52 - 임대선 목사 / 정의학 초원지기"
        처럼 /를 메타데이터 구분자로 쓴다 (실측 18건). 그래서 곡명 수만으로
        worship을 주지 않고, **나머지 구간에 worship 어휘가 남을 때만** 준다.
        위 18건은 나머지 구간에 sermon("설교")만 남아 sermon으로 확정된다.
    """
    songs, rest = split_conti(title)
    if len(songs) < CONTI_MIN_SONGS:
        return None
    hit_ids = [
        media.id
        for media in themes.media_types
        if matched_keywords(rest, media.title_keywords)
    ]
    if len(hit_ids) == 1:
        return hit_ids[0]
    # 나머지 구간에서도 동점이면(예: "금요기도회 찬양") 곡명 나열 구조가 증거다.
    # 아무것도 안 남았을 때는 판정하지 않는다 — 근거 없이 한쪽을 주지 않는다.
    return WORSHIP if WORSHIP in hit_ids else None


def classify_media_type(
    title: str,
    duration_seconds: int,
    channel_content_type: str | None,
    themes: Themes,
) -> MediaVerdict:
    """말씀/찬양을 가린다 (themes.yaml 판별 우선순위).

        1. 제목 어휘 — **한쪽만** 걸릴 때 확정한다
        1.5 양쪽 다 걸리면(동점) 곡명 구조로 한 번 더 가른다 — _break_media_tie
        2. 본문 장절 — 있으면 sermon
        3. 채널 content_type — sermon·worship·devotion이면 그대로
        4. 길이 — 30분↑ sermon / 10분↓ worship
        5. 그래도 못 가리면 unknown

    [2026-08-19 개정 — 제목이 채널보다 앞이다. 실측으로 뒤집혔다.]
      개정 전에는 채널 content_type이 1순위였고, 전용 채널은 거기서 끝났다.
      설계 의도는 "전용 채널은 제목을 볼 필요가 없다"였는데, 실제 데이터에서
      **전용 채널이 반대 형식의 영상을 대량으로 올린다.**

        오륜교회(sermon)   주일 각 부 예배 찬양 콘티 55건을 올린다
        우리들교회(sermon)  찬양 26건
        꿈의교회(sermon)    찬양 14건
        → 1,069건 중 81건이 찬양인데 sermon으로 판정됐다. 앱에서 [찬양] 토글을
          누르면 이 81건이 통째로 사라진다.

      채널 성격은 "그 채널이 주로 무엇을 올리는가"이지 "이 영상이 무엇인가"가
      아니다. 제목이 형식을 직접 말할 때는 그쪽이 더 구체적인 증거다.

    [장절보다도 제목이 앞인 이유 — 3건이지만 방향이 분명하다]
      "시편 92편 + 주 이름 찬양 + 나의 기도하는 것보다 | 주일 2부예배 찬양 헤세드"
      찬양 콘티의 **곡명이 시편**인 경우다. 장절을 먼저 보면 설교가 된다.
      제목에 형식 어휘("찬양")가 명시된 이상 그것이 우선한다.

    [2026-08-24 추가 — 동점 구간에서 위 개정이 무효였다]
      "제목이 채널보다 앞"은 **제목이 한쪽만 말할 때만** 적용됐다. 양쪽이 걸리면
      제목 증거를 통째로 버리고 장절·채널·길이로 내려갔고, 그 아래는 전부
      sermon 쪽으로 기운다. 실사용 제보("말씀 탭에 찬양 영상이 계속 보인다")로
      드러났고, 실측 1,067건 중 동점 31건 가운데 22건이 찬양 콘티였다.
      19건은 unknown이라 **양쪽 토글에 노출**되고 있었다.
      근거는 _break_media_tie에 적었다.

    unknown은 버리는 값이 아니다. 앱은 unknown을 **양쪽 토글 모두에 노출한다**
    (PLAN.md 3.4) — 판별 실패로 영상이 사라지는 것보다 낫고, unknown 비율이
    사전을 고칠 근거가 된다. 주제 태깅의 untagged와는 성격이 다르다.
    """
    hit_ids = [
        media.id
        for media in themes.media_types
        if matched_keywords(title, media.title_keywords)
    ]
    if len(hit_ids) == 1:
        return MediaVerdict(hit_ids[0], REASON_TITLE)

    if len(hit_ids) > 1:
        broken = _break_media_tie(title, themes)
        if broken:
            return MediaVerdict(broken, REASON_CONTI)

    if themes.scripture_reference_signal and has_scripture_reference(title):
        return MediaVerdict(SERMON, REASON_SCRIPTURE)

    direct = CHANNEL_CONTENT_TYPE_MAP.get(str(channel_content_type or "").strip())
    if direct:
        return MediaVerdict(direct, REASON_CHANNEL)

    signal = themes.duration_signal
    if duration_seconds >= signal.sermon_min_seconds:
        return MediaVerdict(SERMON, REASON_DURATION)
    if 0 < duration_seconds <= signal.worship_max_seconds:
        return MediaVerdict(WORSHIP, REASON_DURATION)

    return MediaVerdict(UNKNOWN, REASON_NONE)


def sides_for(media_type: str) -> tuple[str, ...]:
    """이 영상이 어느 토글에 보이는가 — unknown은 양쪽 다.

    리포트에서 "말씀 토글을 눌렀을 때 실제로 보일 건수"를 세는 데 쓴다.
    주제×media_type 분포를 원자료(sermon/worship/unknown)로만 남기면,
    unknown이 양쪽에 노출된다는 사실이 리포트를 읽는 사람에게서 사라진다.
    """
    if media_type == UNKNOWN:
        return (SERMON, WORSHIP)
    return (media_type,)


def visible_counts(media_types: Sequence[str]) -> dict[str, int]:
    """토글별로 실제 보이는 건수 (unknown은 양쪽에 더해진다)."""
    counts = {SERMON: 0, WORSHIP: 0}
    for media_type in media_types:
        for side in sides_for(media_type):
            counts[side] += 1
    return counts
