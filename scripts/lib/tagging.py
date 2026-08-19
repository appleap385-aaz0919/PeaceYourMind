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
    return bool(needle) and needle in normalize(title)


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
    matches: list[ThemeMatch] = []
    for theme in themes.taggable:
        hits = matched_keywords(title, theme.title_keywords)
        if hits:
            matches.append(ThemeMatch(theme_id=theme.id, hits=hits))
    return tuple(matches)


def has_scripture_reference(title: str) -> bool:
    return bool(SCRIPTURE_RE.search(title))


def classify_media_type(
    title: str,
    duration_seconds: int,
    channel_content_type: str | None,
    themes: Themes,
) -> MediaVerdict:
    """말씀/찬양을 가린다 (themes.yaml 판별 우선순위 1~4 그대로).

        1. 채널 content_type이 sermon·worship·devotion이면 거기서 끝난다.
        2. mixed(또는 알 수 없음)면 제목 — 본문 장절이 있으면 sermon.
        3. 없으면 title_keywords로, **한쪽만 걸릴 때만** 확정한다.
        4. 양쪽 다 걸리거나 아무것도 안 걸리면 길이로 가린다.
        5. 그래도 못 가리면 unknown.

    unknown은 버리는 값이 아니다. 앱은 unknown을 **양쪽 토글 모두에 노출한다**
    (PLAN.md 3.4) — 판별 실패로 영상이 사라지는 것보다 낫고, unknown 비율이
    사전을 고칠 근거가 된다. 주제 태깅의 untagged와는 성격이 다르다.
    """
    direct = CHANNEL_CONTENT_TYPE_MAP.get(str(channel_content_type or "").strip())
    if direct:
        return MediaVerdict(direct, REASON_CHANNEL)

    if themes.scripture_reference_signal and has_scripture_reference(title):
        return MediaVerdict(SERMON, REASON_SCRIPTURE)

    hit_ids = [
        media.id
        for media in themes.media_types
        if matched_keywords(title, media.title_keywords)
    ]
    if len(hit_ids) == 1:
        return MediaVerdict(hit_ids[0], REASON_TITLE)

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
