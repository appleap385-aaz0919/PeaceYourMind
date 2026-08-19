"""위기 풀 — 가장 먼저 확정되고, 미달이면 완화 대신 직전 결과를 유지한다.

**crisis_eligible 채널에서만 나온다** (PLAN.md 7절). 일반 풀보다 좁은 기준이며,
2026-08-18 승인 15건은 전부 false라 현재 이 풀은 비어 있다 — 앱은 상담 안내만
표시하고, 그것이 의도된 안전 동작이다.

먼저 확정하는 이유는 둘이다.
    1. 중단이 나도 안전 데이터는 갱신된 상태여야 한다
    2. 먼저 확정해야 일반 주제 후보에서 그 videoId를 뺄 수 있다 —
       상호 배타가 사후 검사가 아니라 구조로 보장된다
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from lib import alerts as alert_specs
from lib.report import iso, parse_iso
from lib.results import BuildContext, CrisisResult, TaggedVideo
from lib.selection import select_crisis_videos
from lib.themes import CRISIS_MIN_VIDEOS, CRISIS_STALE_DAYS

logger = logging.getLogger("build_videos")


def build_crisis(
    ctx: BuildContext, tagged: Sequence[TaggedVideo], now: datetime, day_of_year: int
) -> CrisisResult:
    """위기 화면 영상 풀. **crisis_eligible 채널에서만 나온다** (PLAN.md 7절).

    일반 풀보다 좁은 기준이다 — 정신건강 전문 사역·상담 사역 중심으로만
    crisis_eligible을 준다. 2026-08-18 승인 15건은 전부 false이므로 현재 이
    풀은 비어 있고, 앱은 상담 안내만 표시한다. **의도된 안전 동작이다.**

    주제 태깅을 타지 않는다. 위기 화면의 구절이 감정 매핑을 타지 않는 것과 같은
    이유이며(운영자 고정 큐레이션), themes.yaml의 crisis_fixed가 mapping에
    등장하면 로더가 빌드를 세운다.
    """
    eligible = set(ctx.allowlist.crisis_ids)
    if not eligible:
        logger.warning("crisis_eligible 채널이 0개 — 위기 풀을 새로 만들 원천이 없다")
        ctx.collector.add(**alert_specs.crisis_no_channels())

    pool = [t for t in tagged if t.video.channel_id in eligible]
    picked, cap, unlocked = select_crisis_videos(pool, day_of_year)

    if len(picked) >= CRISIS_MIN_VIDEOS:
        logger.info("위기 풀 갱신 — %d건 확보 (풀 %d건)", len(picked), len(pool))
        return CrisisResult(
            videos=[t.to_json() for t in picked],
            updated_at=iso(now),
            source="allowlist_crisis_eligible",
            carried_over=False,
            pool_size=len(pool),
            max_per_channel=cap,
            per_channel_unlocked=unlocked,
        )
    return _carry_over_crisis(ctx, tagged, len(picked), len(pool), now)


def _carry_over_crisis(
    ctx: BuildContext,
    tagged: Sequence[TaggedVideo],
    kept: int,
    pool_size: int,
    now: datetime,
) -> CrisisResult:
    """12건 미달 — 필터를 완화하지 않고 직전 결과를 유지한다.

    유지하더라도 생존 검증은 한다. 직전 결과의 videoId는 이미 이번 후보에
    포함돼 videos.list를 탔으므로, 살아남은 것만 tagged에 남아 있다.
    추가 API 호출이 없다 (FYM은 여기서 한 번 더 불렀다 — 후보 구성이 달랐다).
    """
    previous = ctx.previous.get("crisis") or {}
    previous_videos = previous.get("videos") or []
    logger.warning(
        "위기 확보량 %d건 < 최소 %d건 — 필터를 완화하지 않고 직전 결과를 유지한다",
        kept,
        CRISIS_MIN_VIDEOS,
    )
    if previous_videos:
        ctx.collector.add(**alert_specs.crisis_carried_over(kept, CRISIS_MIN_VIDEOS))

    if not previous_videos:
        logger.error("유지할 직전 결과도 없다 — 위기 화면은 상담 안내만 노출한다")
        ctx.collector.add(**alert_specs.crisis_empty())
        return CrisisResult(
            videos=[],
            updated_at=str(previous.get("updated_at") or iso(now)),
            source="none",
            carried_over=True,
            pool_size=pool_size,
        )

    alive_by_id = {t.video_id: t for t in tagged}
    order = [str(v["videoId"]) for v in previous_videos]
    alive = [alive_by_id[vid] for vid in order if vid in alive_by_id]
    logger.warning(
        "직전 결과 %d건 중 %d건 생존 — updated_at은 갱신하지 않는다", len(order), len(alive)
    )
    if not alive:
        ctx.collector.add(**alert_specs.crisis_empty())
    return CrisisResult(
        videos=[t.to_json() for t in alive],
        updated_at=str(previous.get("updated_at") or iso(now)),
        source=str(previous.get("source", "carried_over")),
        carried_over=True,
        pool_size=pool_size,
    )


def check_crisis_freshness(ctx: BuildContext, crisis: CrisisResult, now: datetime) -> int:
    updated = parse_iso(crisis.updated_at)
    if updated is None:
        return -1
    days = (now - updated).days
    if days >= CRISIS_STALE_DAYS and crisis.videos:
        logger.error("위기 풀이 %d일째 갱신되지 않았다", days)
        ctx.collector.add(
            **alert_specs.crisis_stale(crisis.updated_at, days, CRISIS_STALE_DAYS)
        )
    return days
