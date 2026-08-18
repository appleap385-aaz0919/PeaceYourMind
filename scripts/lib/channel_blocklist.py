"""channel_blocklist.yaml 로더 — 채널 단위 차단 목록.

**PYM에서 이 목록은 2차 안전망이다** (channel_blocklist.yaml 헤더 참조).
FYM은 검색으로 영상을 모았기에 블록리스트가 주 방어선 중 하나였지만,
PYM은 전면 화이트리스트라 승인되지 않은 채널은 애초에 수집되지 않는다.

그럼에도 두는 이유:
    - 승인된 채널이 나중에 성격이 바뀔 수 있다 (운영자 교체, 노선 변경)
    - 같은 단체가 채널을 여럿 운영하며 일부만 성격이 다를 수 있다
    - allowlist·blocklist가 충돌하면 **blocklist가 이긴다** — 화이트리스트가
      필터 면제권이 아니라는 원칙을 구조로 유지한다

여기에 채널이 쌓인다면 그것은 allowlist 승인 기준이 새고 있다는 신호다.
대개의 올바른 조치는 이 파일에 추가하는 것이 아니라 allowlist에서 빼는 것이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = ("channel_id", "channel_name", "added_at", "added_by", "reason")


class ChannelBlocklistError(ValueError):
    """channel_blocklist.yaml 구조 오류."""


@dataclass(frozen=True)
class BlockedChannel:
    channel_id: str
    channel_name: str
    added_at: str
    added_by: str
    reason: str


@dataclass(frozen=True)
class ChannelBlocklist:
    channels: tuple[BlockedChannel, ...]
    path: Path

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(c.channel_id for c in self.channels)

    @property
    def by_id(self) -> dict[str, BlockedChannel]:
        return {c.channel_id: c for c in self.channels}

    @property
    def size(self) -> int:
        return len(self.channels)


def load_channel_blocklist(path: Path) -> ChannelBlocklist:
    """차단 목록을 읽는다. 파일이 없으면 빈 목록으로 진행한다.

    파일 부재를 예외로 만들지 않는 이유: 이 목록은 안전망이지 필수 장치가 아니다.
    없다고 배치를 세우면, 정작 필요한 blocklist·길이 필터까지 함께 멈춘다.
    """
    if not path.exists():
        return ChannelBlocklist(channels=(), path=path)

    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    entries = raw.get("channels") or []
    if not isinstance(entries, list):
        raise ChannelBlocklistError(f"{path}: channels는 목록이어야 한다")

    channels: list[BlockedChannel] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ChannelBlocklistError(f"{path}: channels[{index}]가 매핑이 아니다")
        # None을 문자열로 만들지 않고 판정한다 — YAML에서 값을 비운 키는
        # 빈 문자열이 아니라 None이라, str(None) == "None"이 truthy가 된다.
        # (lib/allowlist.py의 _is_blank 주석 참조 — FYM에서 이식하며 고친 결함)
        missing = [
            f for f in REQUIRED_FIELDS
            if entry.get(f) is None or not str(entry.get(f)).strip()
        ]
        if missing:
            raise ChannelBlocklistError(
                f"{path}: channels[{index}]({entry.get('channel_id', '?')})에 "
                f"필수 필드 누락 — {', '.join(missing)}"
            )
        channels.append(
            BlockedChannel(
                channel_id=str(entry["channel_id"]).strip(),
                channel_name=str(entry["channel_name"]).strip(),
                added_at=str(entry["added_at"]).strip(),
                added_by=str(entry["added_by"]).strip(),
                reason=" ".join(str(entry["reason"]).split()),
            )
        )
    return ChannelBlocklist(channels=tuple(channels), path=path)
