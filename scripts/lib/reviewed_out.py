"""channel_reviewed_out.yaml 로더 — 검토를 마치고 제외한 채널 기록.

allowlist·blocklist와 성격이 다르다.

    allowlist     "이 채널만 쓴다"          배치가 읽는다
    blocklist     "이 채널은 쓰지 않는다"    배치가 읽는다
    reviewed_out  "이 채널은 이미 검토했다"  suggest_channels.py만 읽는다

**배치는 이 파일을 보지 않는다.** 화이트리스트에 없으면 애초에 수집되지
않으므로 볼 이유가 없다. 이 파일은 차단 장치가 아니라 작업 기록이며,
같은 조사를 반복하지 않기 위한 것이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = (
    "channel_id",
    "channel_name",
    "criterion",
    "reason",
    "reviewed_at",
    "reviewed_by",
)


class ReviewedOutError(ValueError):
    """channel_reviewed_out.yaml 구조 오류."""


@dataclass(frozen=True)
class ReviewedOutChannel:
    channel_id: str
    channel_name: str
    criterion: str
    reason: str
    reviewed_at: str
    reviewed_by: str
    recheckable: bool = False
    recheck_condition: str = ""

    @property
    def summary(self) -> str:
        """검토 시트 한 줄 표시용."""
        tag = "재검토 가능" if self.recheckable else "영구"
        return f"기준 {self.criterion} / {tag} / {self.reviewed_at}"


@dataclass(frozen=True)
class ReviewedOut:
    channels: tuple[ReviewedOutChannel, ...]
    path: Path

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(c.channel_id for c in self.channels)

    @property
    def by_id(self) -> dict[str, ReviewedOutChannel]:
        return {c.channel_id: c for c in self.channels}

    @property
    def size(self) -> int:
        return len(self.channels)


def load_reviewed_out(path: Path) -> ReviewedOut:
    """기록을 읽는다. 파일이 없으면 빈 목록으로 진행한다.

    파일 부재를 예외로 만들지 않는 이유: 이 기록이 없어도 발굴은 돌아간다.
    없으면 이전에 제외한 채널이 다시 상위에 올라올 뿐이고, 그건 불편이지
    오류가 아니다.
    """
    if not path.exists():
        return ReviewedOut(channels=(), path=path)

    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    entries = raw.get("channels") or []
    if not isinstance(entries, list):
        raise ReviewedOutError(f"{path}: channels는 목록이어야 한다")

    channels: list[ReviewedOutChannel] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ReviewedOutError(f"{path}: channels[{index}]가 매핑이 아니다")
        # None을 문자열로 만들지 않고 판정한다 (lib/allowlist.py의 _is_blank 참조)
        missing = [
            f
            for f in REQUIRED_FIELDS
            if entry.get(f) is None or not str(entry.get(f)).strip()
        ]
        if missing:
            raise ReviewedOutError(
                f"{path}: channels[{index}]({entry.get('channel_id', '?')})에 "
                f"필수 필드 누락 — {', '.join(missing)}. "
                "제외 근거가 없으면 기록의 의미가 없다."
            )
        channel_id = str(entry["channel_id"]).strip()
        if channel_id in seen:
            raise ReviewedOutError(f"{path}: 채널 ID 중복 — {channel_id}")
        seen.add(channel_id)
        channels.append(
            ReviewedOutChannel(
                channel_id=channel_id,
                channel_name=str(entry["channel_name"]).strip(),
                criterion=str(entry["criterion"]).strip(),
                reason=" ".join(str(entry["reason"]).split()),
                reviewed_at=str(entry["reviewed_at"]).strip(),
                reviewed_by=str(entry["reviewed_by"]).strip(),
                recheckable=bool(entry.get("recheckable", False)),
                recheck_condition=" ".join(
                    str(entry.get("recheck_condition") or "").split()
                ),
            )
        )
    return ReviewedOut(channels=tuple(channels), path=path)
