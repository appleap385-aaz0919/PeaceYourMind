"""themes.yaml 로더 — 주제 24개 · 감정 매핑 · media_type 사전.

FYM의 `lib/taxonomy.py`에 해당하지만 담는 것이 다르다.
    FYM taxonomy.yaml   감정 체계 + 검색어 + blocklist 계층
    PYM themes.yaml     주제 정의 + 감정→주제 매핑 + media_type 사전

**검색어가 없다.** PYM 배치는 search.list를 부르지 않기 때문이다(PLAN.md 5절).
그래서 이 로더에는 rotated_queries·crisis_queries에 해당하는 것이 없고,
대신 제목 태깅에 쓰는 title_keywords가 그 자리를 차지한다.

[빌드 시 검증 6종 — themes.yaml 말미가 정의한 것을 그대로 구현한다]
    1. mapping의 세분류 id가 taxonomy에 존재한다 (역방향도)
       → taxonomy.yaml은 Phase 3(앱 이식)에서 들어온다. 그전에는 건너뛴다.
         건너뛴 사실을 조용히 넘기지 않고 로그로 남긴다.
    2. mapping이 참조하는 주제가 themes에 정의되어 있다
    3. crisis_fixed는 mapping 어디에도 없다
    4. 전역 금지어가 themes[].title_keywords에 없다
       ※ media_types[].title_keywords에는 적용하지 않는다 — 용도가 다르다.
         (themes.yaml의 media_type 절 주석 참조. 두 사전을 섞으면 둘 다 망가진다.)
    5. media_defaults의 세분류 id 집합이 mapping과 정확히 같다
    6. media_defaults의 값이 media_types에 정의된 id뿐이다

검증은 로더에서 한다 — 배치·테스트·앞으로 만들 도구가 전부 이 경로를 지나므로
"검증을 부르는 것을 잊는" 실패 모드가 생기지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 위기 전용 주제. 감정 매핑을 타지 않고 운영자 고정 큐레이션만 쓴다 (PLAN.md 7절).
CRISIS_THEME_ID = "crisis_fixed"

# 전역 금지어 (themes.yaml 헤더 [전역 주의]). 태깅 사전에 들어가면 빌드를 세운다.
# media_types 사전에는 적용하지 않는다 — 아래 validate() 주석 참조.
FORBIDDEN_KEYWORDS = ("은혜", "치유", "축복", "간증", "기적", "기도응답")

# --- 선정 정책 (PLAN.md 4.2) -------------------------------------------------
# themes.yaml이 아니라 코드에 두는 이유: themes.yaml은 큐레이션 문서다.
# 주제·매핑·어휘 판단이 주석과 함께 들어 있고 사람이 읽고 고치는 파일이라,
# 배치 튜닝 상수를 섞으면 두 종류의 변경이 같은 파일에서 뒤엉킨다.
THEME_MIN_VIDEOS = 15  # 주제당 목표 하한 — 미달이면 경보
THEME_MAX_VIDEOS = 20  # 주제당 목표 상한
THEME_MAX_PER_CHANNEL = 3  # 채널당 상한 (FYM 승계 — 한 채널이 목록을 독식하지 못하게)
PER_CHANNEL_STEPS = 3  # 못 채울 때 상한을 올리는 단계 수 (3 → 4 → 5)

CRISIS_MIN_VIDEOS = 12  # 미달이면 필터를 완화하지 않고 직전 결과를 유지한다
CRISIS_MAX_VIDEOS = 20
CRISIS_STALE_DAYS = 3  # crisis.updated_at이 이보다 오래되면 경보

MIN_DURATION_SECONDS = 180  # 3분 미만 제외 (쇼츠가 여기에 포함되어 걸러진다)
# 상한은 두지 않는다 — 설교는 30분 이상이 흔하다 (PLAN.md 10절 확정).

EXPECTED_THEMES = 24
EXPECTED_SUBCATEGORIES = 24


class ThemesError(ValueError):
    """themes.yaml 구조 오류. 배치를 시작하지 않는다."""


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    intent: str
    title_keywords: tuple[str, ...]
    caution: str

    @property
    def is_crisis(self) -> bool:
        return self.id == CRISIS_THEME_ID


@dataclass(frozen=True)
class MediaType:
    id: str
    label: str
    intent: str
    title_keywords: tuple[str, ...]
    caution: str


@dataclass(frozen=True)
class DurationSignal:
    """길이 신호 — 보조 판정. 제목으로 갈리지 않을 때만 쓴다."""

    sermon_min_seconds: int
    worship_max_seconds: int


@dataclass(frozen=True)
class Themes:
    version: str
    themes: tuple[Theme, ...]
    mapping: dict[str, tuple[str, ...]]
    media_types: tuple[MediaType, ...]
    media_defaults: dict[str, str]
    duration_signal: DurationSignal
    scripture_reference_signal: bool
    path: Path

    @property
    def by_id(self) -> dict[str, Theme]:
        return {t.id: t for t in self.themes}

    @property
    def taggable(self) -> tuple[Theme, ...]:
        """제목 태깅 대상 주제. 위기 전용 주제는 빠진다.

        crisis_fixed는 title_keywords가 비어 있어 어차피 아무것도 걸리지 않지만,
        "비어 있어서 안 걸린다"에 기대지 않고 목록에서 빼둔다. 나중에 누가
        키워드를 채워 넣더라도 위기 풀이 제목 태깅으로 오염되지 않는다.
        """
        return tuple(t for t in self.themes if not t.is_crisis)

    @property
    def media_type_ids(self) -> tuple[str, ...]:
        return tuple(m.id for m in self.media_types)

    def media_default(self, subcategory: str) -> str | None:
        return self.media_defaults.get(subcategory)


def load_themes(path: Path, *, taxonomy_ids: set[str] | None = None) -> Themes:
    """themes.yaml을 읽고 검증까지 끝낸 객체를 돌려준다."""
    if not path.exists():
        raise ThemesError(f"{path}가 없다 — 주제 체계 없이는 태깅할 수 없다")

    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    if not isinstance(raw, dict):
        raise ThemesError(f"{path}: 최상위가 매핑이 아니다")

    themes = tuple(_parse_theme(e, i, path) for i, e in enumerate(_seq(raw, "themes", path)))
    media_types = tuple(
        _parse_media_type(e, i, path) for i, e in enumerate(_seq(raw, "media_types", path))
    )
    mapping = _parse_mapping(raw.get("mapping"), path)
    media_defaults = _parse_media_defaults(raw.get("media_defaults"), path)
    duration = _parse_duration_signal(raw.get("duration_signal"), path)

    parsed = Themes(
        version=str(raw.get("version", "")),
        themes=themes,
        mapping=mapping,
        media_types=media_types,
        media_defaults=media_defaults,
        duration_signal=duration,
        scripture_reference_signal=bool(raw.get("scripture_reference_signal", False)),
        path=path,
    )
    validate(parsed, taxonomy_ids=taxonomy_ids)
    return parsed


def validate(t: Themes, *, taxonomy_ids: set[str] | None = None) -> None:
    """themes.yaml 말미의 빌드 검증 6종. 하나라도 어긋나면 배치를 세운다."""
    problems: list[str] = []

    ids = [theme.id for theme in t.themes]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"주제 id 중복 — {', '.join(duplicates)}")

    # 1. mapping 세분류 id ↔ taxonomy
    if taxonomy_ids is None:
        logger.info(
            "검증 1 건너뜀 — taxonomy.yaml이 아직 없다 (Phase 3 앱 이식에서 들어온다). "
            "mapping 세분류 %d개는 그때 전수 대조한다",
            len(t.mapping),
        )
    else:
        unknown = sorted(set(t.mapping) - taxonomy_ids)
        missing = sorted(taxonomy_ids - set(t.mapping))
        if unknown:
            problems.append(f"mapping에 taxonomy에 없는 세분류 — {', '.join(unknown)}")
        if missing:
            problems.append(f"mapping에서 빠진 세분류 — {', '.join(missing)}")

    # 2. mapping이 참조하는 주제가 정의돼 있는가
    defined = set(ids)
    for sub, theme_ids in sorted(t.mapping.items()):
        unknown_themes = [x for x in theme_ids if x not in defined]
        if unknown_themes:
            problems.append(f"{sub}가 정의되지 않은 주제를 참조 — {', '.join(unknown_themes)}")

    # 3. crisis_fixed는 mapping 어디에도 없다
    #    위기 화면은 감정 매핑을 타지 않는다(PLAN.md 7절). 매핑에 등장하는 순간
    #    일반 감정 화면이 위기 풀을 끌어다 쓰게 되므로 구조로 막는다.
    tainted = sorted(sub for sub, ids_ in t.mapping.items() if CRISIS_THEME_ID in ids_)
    if tainted:
        problems.append(
            f"{CRISIS_THEME_ID}가 mapping에 등장한다 — {', '.join(tainted)} "
            "(위기 풀은 감정 매핑을 타지 않는다)"
        )

    # 4. 전역 금지어가 주제 태깅 사전에 없는가 (media_types에는 적용하지 않는다)
    for theme in t.themes:
        for keyword in theme.title_keywords:
            hits = [w for w in FORBIDDEN_KEYWORDS if w in keyword]
            if hits:
                problems.append(
                    f"{theme.id}.title_keywords에 전역 금지어 — {keyword!r} ← {', '.join(hits)}"
                )

    # 5·6. media_defaults 집합과 값
    if set(t.media_defaults) != set(t.mapping):
        only_defaults = sorted(set(t.media_defaults) - set(t.mapping))
        only_mapping = sorted(set(t.mapping) - set(t.media_defaults))
        problems.append(
            "media_defaults와 mapping의 세분류 집합이 다르다 — "
            f"defaults에만 {only_defaults or '없음'} / mapping에만 {only_mapping or '없음'}"
        )
    valid_media = set(t.media_type_ids)
    bad_values = sorted(
        f"{sub}={value}" for sub, value in t.media_defaults.items() if value not in valid_media
    )
    if bad_values:
        problems.append(
            f"media_defaults 값이 media_types에 없다 — {', '.join(bad_values)} "
            f"(가능한 값: {', '.join(sorted(valid_media))})"
        )

    if problems:
        raise ThemesError(
            f"{t.path} 검증 실패 {len(problems)}건:\n  " + "\n  ".join(problems)
        )

    logger.info(
        "themes.yaml 검증 통과 — 주제 %d개(태깅 대상 %d), 매핑 %d개, media_type %d종",
        len(t.themes),
        len(t.taggable),
        len(t.mapping),
        len(t.media_types),
    )


# --- 파싱 --------------------------------------------------------------------


def _seq(raw: dict[str, Any], key: str, path: Path) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ThemesError(f"{path}: {key}는 비어 있지 않은 목록이어야 한다")
    return value


def _parse_theme(entry: Any, index: int, path: Path) -> Theme:
    if not isinstance(entry, dict):
        raise ThemesError(f"{path}: themes[{index}]가 매핑이 아니다")
    theme_id = str(entry.get("id", "")).strip()
    if not theme_id:
        raise ThemesError(f"{path}: themes[{index}]에 id가 없다")
    return Theme(
        id=theme_id,
        label=str(entry.get("label", "")).strip(),
        intent=" ".join(str(entry.get("intent", "")).split()),
        title_keywords=_keywords(entry.get("title_keywords"), f"themes[{index}]", path),
        caution=" ".join(str(entry.get("caution", "")).split()),
    )


def _parse_media_type(entry: Any, index: int, path: Path) -> MediaType:
    if not isinstance(entry, dict):
        raise ThemesError(f"{path}: media_types[{index}]가 매핑이 아니다")
    media_id = str(entry.get("id", "")).strip()
    if not media_id:
        raise ThemesError(f"{path}: media_types[{index}]에 id가 없다")
    keywords = _keywords(entry.get("title_keywords"), f"media_types[{index}]", path)
    if not keywords:
        raise ThemesError(f"{path}: media_types[{index}]({media_id})에 title_keywords가 없다")
    return MediaType(
        id=media_id,
        label=str(entry.get("label", "")).strip(),
        intent=" ".join(str(entry.get("intent", "")).split()),
        title_keywords=keywords,
        caution=" ".join(str(entry.get("caution", "")).split()),
    )


def _keywords(value: Any, where: str, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ThemesError(f"{path}: {where}.title_keywords는 목록이어야 한다")
    words = tuple(str(v).strip() for v in value if str(v).strip())
    blanks = len(value) - len(words)
    if blanks:
        raise ThemesError(f"{path}: {where}.title_keywords에 빈 항목 {blanks}건")
    return words


def _parse_mapping(value: Any, path: Path) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict) or not value:
        raise ThemesError(f"{path}: mapping은 비어 있지 않은 매핑이어야 한다")
    parsed: dict[str, tuple[str, ...]] = {}
    for sub, theme_ids in value.items():
        if not isinstance(theme_ids, list) or not theme_ids:
            raise ThemesError(f"{path}: mapping[{sub}]는 비어 있지 않은 목록이어야 한다")
        parsed[str(sub).strip()] = tuple(str(t).strip() for t in theme_ids)
    return parsed


def _parse_media_defaults(value: Any, path: Path) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ThemesError(f"{path}: media_defaults는 비어 있지 않은 매핑이어야 한다")
    return {str(k).strip(): str(v).strip() for k, v in value.items()}


def _parse_duration_signal(value: Any, path: Path) -> DurationSignal:
    if not isinstance(value, dict):
        raise ThemesError(f"{path}: duration_signal이 매핑이 아니다")
    try:
        sermon_min = int(value["sermon_min_seconds"])
        worship_max = int(value["worship_max_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ThemesError(
            f"{path}: duration_signal에 sermon_min_seconds·worship_max_seconds가 필요하다"
        ) from exc
    if worship_max >= sermon_min:
        # 두 구간이 겹치면 같은 길이가 양쪽 신호에 걸린다.
        raise ThemesError(
            f"{path}: duration_signal 구간이 겹친다 — "
            f"worship_max({worship_max}) >= sermon_min({sermon_min})"
        )
    return DurationSignal(sermon_min_seconds=sermon_min, worship_max_seconds=worship_max)
