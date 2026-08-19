"""배치 산출물의 자료형 — 채널 기여 · 태깅된 영상 · 주제 결과 · 위기 결과 · 실행 맥락.

여기 모인 것은 전부 **데이터와 그 표현**이고 로직은 없다.
수집(collect) · 선정(selection) · 위기(crisis) · 리포트(report) 모듈이 전부
이 자료형을 주고받으므로, 한곳에 두어야 순환 의존이 생기지 않는다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from lib.allowlist import Allowlist, AllowlistChannel
from lib.alerts import AlertCollector
from lib.filters import Video
from lib.quota import QuotaBudget
from lib.tagging import SERMON, UNKNOWN, WORSHIP, MediaVerdict, visible_counts
from lib.themes import Themes
from lib.youtube import Client


@dataclass
class ChannelYield:
    """채널 하나가 이번 배치에 실제로 기여한 양.

    **이 표가 이번 Phase의 요구 산출물이다** (HANDOFF 3절).
    수집 건수가 아니라 필터 후 잔존을 봐야 한다 — 잔존이 0인 채널은 승인 목록에
    있으나 서비스에는 없는 채널이고, 유효 채널 수가 최소 기준 아래로 떨어진 것과
    같은 의미이기 때문이다.
    """

    channel_id: str
    name: str
    content_type: str
    collected: int = 0
    kept: int = 0
    tagged: int = 0
    selected: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "content_type": self.content_type,
            "collected": self.collected,
            "kept": self.kept,
            "tagged": self.tagged,
            "selected": self.selected,
        }


@dataclass
class TaggedVideo:
    """필터를 통과한 영상 1건 + 태깅 결과."""

    video: Video
    themes: tuple[str, ...]
    hits: tuple[str, ...]
    media: MediaVerdict

    @property
    def video_id(self) -> str:
        return self.video.video_id

    @property
    def is_untagged(self) -> bool:
        return not self.themes

    def to_json(self) -> dict[str, str]:
        return self.video.to_json(media_type=self.media.media_type)


@dataclass
class ThemeResult:
    id: str
    label: str
    picked: list[TaggedVideo]
    pool_size: int
    max_per_channel: int
    per_channel_unlocked: bool
    from_previous: int = 0
    excluded_by_crisis: int = 0

    @property
    def videos(self) -> list[dict[str, str]]:
        return [t.to_json() for t in self.picked]

    @property
    def media_counts(self) -> dict[str, int]:
        counts = Counter(t.media.media_type for t in self.picked)
        return {k: counts.get(k, 0) for k in (SERMON, WORSHIP, UNKNOWN)}

    @property
    def visible(self) -> dict[str, int]:
        """토글별로 실제 보이는 건수 (unknown은 양쪽에 노출된다)."""
        return visible_counts([t.media.media_type for t in self.picked])

    @property
    def channel_spread(self) -> dict[str, int]:
        return dict(Counter(t.video.channel for t in self.picked).most_common())

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "videos": self.videos}


@dataclass
class CrisisResult:
    videos: list[dict[str, str]]
    updated_at: str
    source: str
    carried_over: bool
    pool_size: int = 0
    max_per_channel: int | None = None
    per_channel_unlocked: bool = False

    @property
    def video_ids(self) -> set[str]:
        return {v["videoId"] for v in self.videos}

    @property
    def channel_spread(self) -> dict[str, int]:
        return dict(Counter(v["channel"] for v in self.videos).most_common())


@dataclass
class BuildContext:
    themes: Themes
    client: Client
    budget: QuotaBudget
    previous: dict[str, Any]
    allowlist: Allowlist
    blocked_channel_ids: frozenset[str] = frozenset()
    collector: AlertCollector = field(default_factory=AlertCollector)
    yields: dict[str, ChannelYield] = field(default_factory=dict)

    _index: dict[str, AllowlistChannel] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # 영상마다 부르는 조회라 매번 dict를 다시 만들지 않는다 (수백~수천 건).
        self._index = {c.channel_id: c for c in self.allowlist.channels}

    def channel(self, channel_id: str) -> AllowlistChannel | None:
        return self._index.get(channel_id)
