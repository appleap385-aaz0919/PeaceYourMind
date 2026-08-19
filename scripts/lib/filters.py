"""영상 필터 — videos.list 응답을 검증하고 걸러낸다 (FYM 이식).

필터 순서에는 이유가 있다.
    1) 이용 불가(삭제·비공개·처리 중)  ← 애초에 노출 자체가 불가능
    2) 국내 차단
    3) 3분 미만 (쇼츠 포함)
    4) 차단 채널 — 제목과 무관하게 채널로 거른다 (channel_blocklist.yaml)
    5) 제목 용어 blocklist — **PYM에서는 비어 있다.** 아래 참조

[PYM에는 제목 용어 blocklist 사전이 없다 — 빈 것이 현재의 설계다]
    FYM은 검색으로 영상을 모았으므로 제목 필터가 주 방어선 중 하나였고
    taxonomy.yaml에 tier_a/b/c 사전이 있었다. PYM은 전면 화이트리스트라
    (PLAN.md 5절) 승인되지 않은 채널의 영상은 애초에 후보에 들어오지 않는다.
    사전을 급하게 만들면 정상 채널의 영상을 떨어뜨리는 쪽이 더 큰 위험이라
    suggest_channels.py도 같은 판단으로 사전 대신 "성격 신호어 표시"를 골랐다.

    그래도 tiers 인자를 남겨 둔 이유: Phase 3에서 FYM taxonomy.yaml을 이식하면
    그 사전이 그대로 들어올 자리다. 호출부에서 넘기기만 하면 되고, 그때
    이 파일은 고칠 것이 없다. 지금은 비어 있다는 사실을 배치가 로그로 말한다.

정확한 길이 판정은 videos.list의 contentDetails.duration으로 한다.
PYM은 search를 쓰지 않으므로 FYM에 있던 videoDuration 파라미터 논의는 해당 없다.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from lib.normalize import matched_terms

_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

_SHORTS_MARKERS = ("#shorts", "#short", "#쇼츠")

KOREA_REGION = "KR"


def blocklist_text(snippet: Mapping[str, Any]) -> str:
    """blocklist 매칭 대상 텍스트를 뽑는다 — **제목만** 본다 (FYM 교훈).

    설명란·태그를 보지 않는 이유는 FYM에서 실증됐다. 설명란에는 해시태그·링크·
    채널 소개·타임스탬프·상담 안내가 뒤섞여 있어, 자살예방 상담전화를 성실히
    적어둔 채널이 오히려 걸러지는 정반대 결과가 구조적으로 나온다.

    **주제 태깅도 같은 이유로 제목만 본다** (PLAN.md 3.3). 매칭 범위를 이 함수
    한 곳에 두어, 필터와 태깅이 서로 다른 텍스트를 보는 일이 생기지 않게 한다.
    """
    return str(snippet.get("title", ""))


@dataclass(frozen=True)
class Video:
    """videos.json에 실릴 영상 1건 (+ 필터·태깅 판단에 쓰는 부가 정보)."""

    video_id: str
    title: str
    channel: str
    channel_id: str
    published_at: str
    duration: str
    duration_seconds: int
    description: str
    tags: tuple[str, ...]
    comments_disabled: bool

    def to_json(self, media_type: str | None = None) -> dict[str, str]:
        """PLAN.md 4.2 스키마. 썸네일 URL은 videoId로 조립하므로 넣지 않는다.

        media_type은 앱의 [말씀]/[찬양] 토글이 쓰는 필드다(PLAN.md 3.4).
        판별 결과가 없으면 필드를 빼지 않고 "unknown"을 채운다 — 앱이 필드
        존재 여부로 분기하지 않게 한다.
        """
        payload = {
            "videoId": self.video_id,
            "title": self.title,
            "channel": self.channel,
            "publishedAt": self.published_at,
            "duration": self.duration,
        }
        if media_type is not None:
            payload["media_type"] = media_type
        return payload

    @property
    def blocklist_text(self) -> str:
        return blocklist_text({"title": self.title})

    @property
    def shorts_marker_text(self) -> str:
        """쇼츠 표기 탐지 대상: 제목 + 설명 + 태그.

        blocklist·태깅과 달리 여기서는 설명·태그를 계속 본다.
        #shorts는 업로더가 형식을 스스로 밝힌 표기라 오탐 여지가 없고,
        제목에는 안 붙이고 설명에만 넣는 채널이 흔하다.
        """
        return " ".join((self.title, self.description, " ".join(self.tags)))


@dataclass
class FilterStats:
    """단계별 제거 건수. 과다 필터링을 사람이 판단할 수 있게 남긴다."""

    considered: int = 0
    dropped_unavailable: int = 0
    dropped_region: int = 0
    dropped_short: int = 0
    dropped_shorts_tag: int = 0
    dropped_blocked_channel: int = 0
    blocked_channels: Counter[str] = field(default_factory=Counter)
    entered_blocklist: int = 0
    dropped_by_tier: Counter[str] = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)
    kept: int = 0

    @property
    def dropped_blocklist(self) -> int:
        return sum(self.dropped_by_tier.values())

    @property
    def blocklist_drop_ratio(self) -> float:
        if self.entered_blocklist <= 0:
            return 0.0
        return self.dropped_blocklist / self.entered_blocklist

    def is_overfiltered(self, threshold: float = 0.5) -> bool:
        return self.entered_blocklist > 0 and self.blocklist_drop_ratio >= threshold

    def summary(self) -> str:
        tiers = ", ".join(f"{k}:{v}" for k, v in sorted(self.dropped_by_tier.items())) or "0"
        return (
            f"후보 {self.considered} → 확보 {self.kept} "
            f"(이용불가 {self.dropped_unavailable}, 국내차단 {self.dropped_region}, "
            f"3분미만 {self.dropped_short}, 쇼츠표기 {self.dropped_shorts_tag}, "
            f"차단채널 {self.dropped_blocked_channel}, "
            f"blocklist {self.dropped_blocklist} [{tiers}])"
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "considered": self.considered,
            "kept": self.kept,
            "dropped_unavailable": self.dropped_unavailable,
            "dropped_region": self.dropped_region,
            "dropped_short": self.dropped_short,
            "dropped_shorts_tag": self.dropped_shorts_tag,
            "dropped_blocked_channel": self.dropped_blocked_channel,
            "blocked_channels": dict(self.blocked_channels),
            "dropped_blocklist": self.dropped_blocklist,
            "dropped_by_tier": dict(self.dropped_by_tier),
            "blocklist_drop_ratio": round(self.blocklist_drop_ratio, 3),
            "blocked_samples": self.samples[:5],
        }


def parse_duration(iso: str) -> int:
    """ISO 8601 duration → 초. 파싱 실패는 0을 반환해 '3분 미만'으로 걸러지게 한다."""
    if not iso:
        return 0
    match = _DURATION.match(iso)
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86_400
        + parts["hours"] * 3_600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def build_video(item: Mapping[str, Any]) -> Video | None:
    """videos.list 항목 → Video. 노출 불가 상태면 None."""
    status = item.get("status") or {}
    if status.get("privacyStatus") != "public":
        return None
    if status.get("uploadStatus") not in (None, "processed"):
        return None

    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    duration = str(content.get("duration", ""))

    return Video(
        video_id=str(item.get("id", "")),
        title=str(snippet.get("title", "")),
        channel=str(snippet.get("channelTitle", "")),
        channel_id=str(snippet.get("channelId", "")),
        published_at=str(snippet.get("publishedAt", "")),
        duration=duration,
        duration_seconds=parse_duration(duration),
        description=str(snippet.get("description", "")),
        tags=tuple(str(t) for t in (snippet.get("tags") or [])),
        comments_disabled="commentCount" not in stats,
    )


def _is_region_blocked(item: Mapping[str, Any]) -> bool:
    restriction = (item.get("contentDetails") or {}).get("regionRestriction") or {}
    blocked = restriction.get("blocked") or []
    allowed = restriction.get("allowed")
    if KOREA_REGION in blocked:
        return True
    return bool(allowed) and KOREA_REGION not in allowed


def _has_shorts_marker(video: Video) -> bool:
    text = video.shorts_marker_text.lower()
    return any(marker in text for marker in _SHORTS_MARKERS)


def apply_filters(
    items: Iterable[Mapping[str, Any]],
    tiers: Mapping[str, Sequence[str]] | None = None,
    *,
    min_seconds: int,
    blocked_channel_ids: frozenset[str] | set[str] | None = None,
) -> tuple[list[Video], FilterStats]:
    """videos.list 응답에 필터를 적용한다.

    tiers는 제목 용어 blocklist 계층이다. PYM은 현재 넘기지 않는다(모듈 주석 참조).
    None이면 blocklist 단계가 통째로 통과가 되며, entered_blocklist는 그대로
    세어 리포트에 남는다 — "검사를 안 했다"와 "검사했는데 안 걸렸다"를
    구분하지 못하게 만들지 않기 위해 dropped_by_tier가 비는 쪽으로 남긴다.

    blocked_channel_ids는 channel_blocklist.yaml에서 온다. 제목 검사보다 먼저 본다 —
    채널이 걸리면 제목이 무엇이든 결과가 같고, 어느 쪽에 걸렸는지 리포트에서
    구분되어야 "제목 필터를 고쳐야 하나"를 헷갈리지 않는다.
    """
    tiers = tiers or {}
    blocked_ids = blocked_channel_ids or frozenset()
    stats = FilterStats()
    kept: list[Video] = []

    for item in items:
        stats.considered += 1

        video = build_video(item)
        if video is None:
            stats.dropped_unavailable += 1
            continue
        if _is_region_blocked(item):
            stats.dropped_region += 1
            continue
        if video.duration_seconds < min_seconds:
            stats.dropped_short += 1
            continue
        if _has_shorts_marker(video):
            stats.dropped_shorts_tag += 1
            continue
        if video.channel_id in blocked_ids:
            stats.dropped_blocked_channel += 1
            stats.blocked_channels[video.channel] += 1
            continue

        stats.entered_blocklist += 1
        blocked_tier, hits = _blocklist_verdict(video, tiers)
        if blocked_tier:
            stats.dropped_by_tier[blocked_tier] += 1
            if len(stats.samples) < 20:
                stats.samples.append(f"[{blocked_tier}] {video.title} ← {', '.join(hits)}")
            continue

        kept.append(video)

    stats.kept = len(kept)
    return kept, stats


def _blocklist_verdict(
    video: Video, tiers: Mapping[str, Sequence[str]]
) -> tuple[str | None, list[str]]:
    text = video.blocklist_text
    for tier_name, terms in tiers.items():
        hits = matched_terms(text, terms)
        if hits:
            return tier_name, hits
    return None, []


def dedupe(video_ids: Iterable[str]) -> list[str]:
    """순서를 보존하며 중복 videoId를 제거한다.

    PYM에서 이 순서는 검색 관련도가 아니라 **채널 순회 + 업로드 최신순**이다.
    같은 영상이 두 채널의 재생목록에 나타나는 일은 없지만, 직전 결과를 후보 뒤에
    붙일 때 겹치므로 여전히 필요하다.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for vid in video_ids:
        if vid and vid not in seen:
            seen.add(vid)
            ordered.append(vid)
    return ordered
