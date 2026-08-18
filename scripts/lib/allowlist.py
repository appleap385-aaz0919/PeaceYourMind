"""channel_allowlist.yaml 로더.

**PYM에서 이 파일은 유일한 영상 출처다.** FYM에서는 위기 카테고리에만 적용됐지만
PYM은 전면 화이트리스트라(PLAN.md 5절) 여기 없는 채널은 서비스에 존재하지 않는다.
변경은 PR로만 한다.

FYM 로더와 다른 점 — 필수 필드가 늘었다
    affiliation            소속 (교단명 / 교회명(교단) / "초교파(법인명)")
    affiliation_verified   정체를 무엇으로 확인했는지
    content_type           주력 콘텐츠 (sermon / worship / devotion / mixed)

    앞의 둘은 PYM 신규 필드다. 승인 기준 1(정체 확인)·2(이단 배제)를 통과한
    근거가 데이터에 남아야 하기 때문이다. 이단 배제는 자동 점검이 판단할 수
    없는 항목이라, 사람이 무엇을 보고 승인했는지가 유일한 감사 흔적이 된다.
    비어 있으면 로더가 실패한다 — 근거 없는 승인을 구조로 막는다.

    content_type은 배치가 주제 태깅 통계를 갈래별로 리포트하는 데 쓴다.

선택 필드
    crisis_eligible  true인 채널만 위기 풀 수집 대상이 된다 (기본 false).
                     위기 풀은 일반보다 좁다 — 정신건강 전문 사역·상담 사역
                     채널 중심으로만 true를 준다 (PLAN.md 7절).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

# PLAN.md 5.2 / channel_allowlist.yaml 헤더에서 확정된 임계값
MIN_ALLOWLIST_SIZE = 15  # 이보다 줄면 allowlist_undersized 경보
REVIEW_OVERDUE_DAYS = 120  # last_reviewed_at 초과 시 재검토 Issue
NO_UPLOAD_DAYS = 90  # 최근 업로드가 없으면 Issue
MIN_BLOCKLIST_PASS_RATE = 0.5  # 통과율이 이보다 낮으면 채널 성향 변화 신호

# 스캐폴드 예시 항목. 실제 채널로 교체될 때까지 배치가 건너뛴다.
PLACEHOLDER_PREFIX = "UC_EXAMPLE"

CONTENT_TYPES = ("sermon", "worship", "devotion", "mixed")

REQUIRED_FIELDS = (
    "channel_id",
    "channel_name",
    "affiliation",
    "affiliation_verified",
    "content_type",
    "added_at",
    "last_reviewed_at",
    "reviewed_by",
    "note",
)


class AllowlistError(ValueError):
    """channel_allowlist.yaml 구조 오류."""


@dataclass(frozen=True)
class AllowlistChannel:
    channel_id: str
    channel_name: str
    affiliation: str
    affiliation_verified: str
    content_type: str
    added_at: str
    last_reviewed_at: str
    reviewed_by: str
    note: str
    crisis_eligible: bool = False

    @property
    def is_placeholder(self) -> bool:
        return self.channel_id.startswith(PLACEHOLDER_PREFIX)

    def days_since_review(self, today: date) -> int | None:
        reviewed = _parse_date(self.last_reviewed_at)
        if reviewed is None:
            return None
        return (today - reviewed).days


@dataclass(frozen=True)
class Allowlist:
    channels: tuple[AllowlistChannel, ...]
    placeholders: tuple[AllowlistChannel, ...]
    path: Path

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(c.channel_id for c in self.channels)

    @property
    def crisis_ids(self) -> tuple[str, ...]:
        return tuple(c.channel_id for c in self.channels if c.crisis_eligible)

    @property
    def size(self) -> int:
        return len(self.channels)

    @property
    def is_undersized(self) -> bool:
        return self.size < MIN_ALLOWLIST_SIZE


def load_allowlist(path: Path) -> Allowlist:
    """화이트리스트를 읽는다. 파일이 없거나 비어 있으면 빈 목록으로 진행한다.

    **비어 있는 것을 예외로 만들지 않는다.** Phase 0이 끝나기 전에는 정상
    상태이고, suggest_channels.py는 바로 그 빈 목록을 채우려고 도는 도구다.
    배치(build_videos.py)는 다르다 — 목록이 비면 수집할 것이 없으므로
    호출부에서 경보를 낸다.
    """
    if not path.exists():
        return Allowlist(channels=(), placeholders=(), path=path)

    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    entries = raw.get("channels") or []
    if not isinstance(entries, list):
        raise AllowlistError(f"{path}: channels는 목록이어야 한다")

    active: list[AllowlistChannel] = []
    placeholders: list[AllowlistChannel] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        channel = _parse_channel(entry, index, path)
        if channel.channel_id in seen:
            raise AllowlistError(f"{path}: 채널 ID 중복 — {channel.channel_id}")
        seen.add(channel.channel_id)
        (placeholders if channel.is_placeholder else active).append(channel)

    return Allowlist(
        channels=tuple(active), placeholders=tuple(placeholders), path=path
    )


def _is_blank(value: Any) -> bool:
    """비어 있는가 — None을 문자열로 만들지 않고 판정한다.

    **FYM 로더에서 이식하며 고친 결함이다.**
    원본은 `not str(entry.get(f, "")).strip()`으로 검사했는데, YAML에서
    값을 비운 키(`affiliation:`)는 빈 문자열이 아니라 None으로 파싱된다.
    그러면 str(None) == "None"이라 truthy가 되어 **빈 필드가 통과한다.**

    suggest_channels.py가 내보내는 붙여넣기용 블록이 정확히 이 형태다
    (affiliation을 비운 채 TODO 주석을 달아 내보낸다). 즉 이 결함이 있으면
    "채우지 않으면 배치가 돌지 않는다"는 설계가 그대로 무력화된다 —
    승인 근거 없는 채널이 조용히 수집 대상이 된다.
    """
    return value is None or not str(value).strip()


def _parse_channel(entry: Any, index: int, path: Path) -> AllowlistChannel:
    if not isinstance(entry, dict):
        raise AllowlistError(f"{path}: channels[{index}]가 매핑이 아니다")

    missing = [f for f in REQUIRED_FIELDS if _is_blank(entry.get(f))]
    if missing:
        raise AllowlistError(
            f"{path}: channels[{index}]({entry.get('channel_id', '?')})에 "
            f"필수 필드 누락 — {', '.join(missing)}. "
            "affiliation·affiliation_verified는 승인 기준 1·2를 통과한 근거다. "
            "비워둘 수 없다."
        )

    channel_id = str(entry["channel_id"]).strip()
    if not channel_id.startswith("UC") or len(channel_id) != 24:
        raise AllowlistError(
            f"{path}: channels[{index}] channel_id가 형식에 맞지 않는다 — "
            f"{channel_id!r} (UC로 시작하는 24자여야 한다. 핸들·URL 불가)"
        )

    content_type = str(entry["content_type"]).strip()
    if content_type not in CONTENT_TYPES:
        raise AllowlistError(
            f"{path}: channels[{index}]({channel_id}) content_type이 "
            f"{content_type!r} — {' / '.join(CONTENT_TYPES)} 중 하나여야 한다"
        )

    return AllowlistChannel(
        channel_id=channel_id,
        channel_name=str(entry["channel_name"]).strip(),
        affiliation=str(entry["affiliation"]).strip(),
        affiliation_verified=str(entry["affiliation_verified"]).strip(),
        content_type=content_type,
        added_at=str(entry["added_at"]).strip(),
        last_reviewed_at=str(entry["last_reviewed_at"]).strip(),
        reviewed_by=str(entry["reviewed_by"]).strip(),
        note=str(entry["note"]).strip(),
        crisis_eligible=bool(entry.get("crisis_eligible", False)),
    )


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
