"""수집 — 승인 채널의 업로드 재생목록에서 후보 videoId를 모은다.

**PYM 배치에서 영상이 들어오는 유일한 경로다.** search.list를 부르지 않으므로
목록 밖의 채널은 서비스에 존재하지 않는다 (PLAN.md 5절).

여기서 하는 일은 셋이다.
    1. 승인 채널 → uploads 재생목록 → 최근 업로드 videoId
    2. 직전 결과의 videoId를 후보 뒤에 붙여 풀 깊이를 유지
    3. 필터를 통과한 영상 중 **승인 목록 밖 채널의 것을 최종적으로 배제**
       (2번이 있는 한 1번만으로는 화이트리스트가 보장되지 않는다)
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from typing import Any

from lib import alerts as alert_specs
from lib.filters import Video, dedupe
from lib.results import BuildContext, ChannelYield

logger = logging.getLogger("build_videos")

# 채널당 읽어올 최근 업로드 수. 50건이 1페이지 = 1 unit이다 (PLAN.md 6절 "1~2페이지").
#
# 100으로 잡은 이유: 승인 목록에 쇼츠 비중이 높은 채널이 있다
# (CTS·CBSJOY·극동방송·ANOINTING — 발굴 표본 10건 중 절반 이상이 3분 미만).
# 50건만 읽으면 그런 채널의 잔존이 한 자릿수로 떨어져 "목록에 있으나 실질적으로
# 없는 채널"이 된다. 채널당 1 unit을 더 쓰는 쪽이 길이 필터를 푸는 것보다 낫다.
DEFAULT_UPLOADS_PER_CHANNEL = 100


def collect_uploads(
    ctx: BuildContext, uploads_per_channel: int
) -> tuple[list[str], dict[str, list[str]]]:
    """승인 채널의 최근 업로드 videoId를 모은다.

    경로는 channels.list → uploads 재생목록 → playlistItems.list다.
    search.list(channelId)는 채널당 100 units라 쓰지 않는다 — 채널 50개면
    5,000 units로 예산이 붕괴하고, 검색을 쓰지 않는다는 안전 근거도 함께 무너진다.

    응답에 없는 채널은 삭제·비공개·차단 중 하나다. PYM은 전면 화이트리스트라
    그 채널의 영상이 그날 통째로 0건이 되므로 critical 경보를 낸다.
    """
    channels = ctx.allowlist.channels
    if not channels:
        logger.error("승인 채널이 없다 — 수집할 대상이 없다")
        ctx.collector.add(**alert_specs.allowlist_empty())
        return [], {}

    # 표를 승인 목록 전체로 먼저 깔아 둔다. 응답이 없는 채널을 표에서 빼면
    # "오늘 0건이었다"는 사실이 리포트에서 사라진다 — 그것이 가장 봐야 할 행이다.
    for channel in channels:
        ctx.yields[channel.channel_id] = ChannelYield(
            channel_id=channel.channel_id,
            name=channel.channel_name,
            content_type=channel.content_type,
        )

    items = ctx.client.channels([c.channel_id for c in channels])
    uploads: dict[str, str] = {}
    for item in items:
        playlist = (
            (item.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
        )
        if playlist:
            uploads[str(item["id"])] = str(playlist)

    for channel in channels:
        if channel.channel_id not in uploads:
            logger.error(
                "채널 응답 없음 — %s (%s). 오늘 이 채널의 영상은 0건이다",
                channel.channel_name,
                channel.channel_id,
            )
            ctx.collector.add(
                **alert_specs.channel_dead(channel.channel_id, channel.channel_name)
            )

    by_channel: dict[str, list[str]] = {}
    ordered: list[str] = []
    for channel in channels:
        playlist = uploads.get(channel.channel_id)
        if not playlist:
            continue
        video_ids = ctx.client.playlist_items(playlist, uploads_per_channel)
        by_channel[channel.channel_id] = video_ids
        ordered.extend(video_ids)
        ctx.yields[channel.channel_id].collected = len(video_ids)
        logger.info(
            "  %-22s %3d건 수집 (%s)", channel.channel_name, len(video_ids), channel.content_type
        )

    logger.info(
        "수집 완료 — %d채널 / 영상 %d건 (중복 제거 전)", len(by_channel), len(ordered)
    )
    return ordered, by_channel


def previous_video_ids(previous: dict[str, Any]) -> list[str]:
    """직전 결과의 videoId — 후보 뒤에 붙여 풀 깊이를 유지한다.

    직전 결과를 섞는 이유는 FYM과 다르다. FYM은 매일 검색어가 로테이션돼
    후보 자체가 달라졌지만, PYM의 후보는 "최근 N건"이라 업로드가 뜸한 채널의
    영상이 창 밖으로 밀려나면 그대로 사라진다. 직전 결과를 후보에 넣으면
    그 영상이 계속 검증을 받으면서 풀에 남는다.

    **재검증은 그대로 한다** — 후보에 넣는다는 것은 videos.list를 다시 탄다는
    뜻이고, 삭제·비공개가 되면 거기서 걸러진다. 필터 완화가 아니다.

    [두 스키마를 모두 읽는다]
      2026-08-19 폴백 도입으로 videos.json의 목록 키가 `themes`에서
      `subcategories`로 바뀌었다(PLAN.md 4.2). 개정 직후 한 번은 **직전 파일이
      옛 스키마**이므로, 새 키만 읽으면 그날 직전 결과가 통째로 유실된다.
      한 줄 차이로 풀이 얕아지는 종류의 사고라 두 키를 다 본다.
    """
    ids: list[str] = []
    for group in ("subcategories", "themes"):
        for entry in previous.get(group, []):
            ids.extend(str(v["videoId"]) for v in entry.get("videos", []))
    ids.extend(str(v["videoId"]) for v in (previous.get("crisis") or {}).get("videos", []))
    return dedupe(ids)


def enforce_allowlist(ctx: BuildContext, kept: Sequence[Video]) -> tuple[list[Video], int]:
    """승인 목록에 없는 채널의 영상을 최종 풀에서 뺀다.

    **수집 경로만 믿지 않는다.** 오늘 수집한 영상은 당연히 승인 채널의 것이지만,
    후보에는 직전 결과가 섞여 있다. 어제 승인돼 있던 채널이 오늘 목록에서
    빠졌다면(성격 변화·폐쇄·승인 철회) 그 채널의 영상은 **직전 결과를 타고
    계속 살아남는다.** 승인을 취소했는데 영상이 안 사라지는 것은 전면
    화이트리스트라는 전제가 깨지는 것이다.

    channel_blocklist는 필터 단계에서 이미 걸러졌다. 이건 다른 경우다 —
    "막은 채널"이 아니라 "이제 승인되지 않은 채널"이고, 대개의 올바른 조치가
    blocklist 추가가 아니라 allowlist 제거이므로(channel_blocklist.yaml 헤더)
    제거만으로 실제 제거가 되어야 한다.
    """
    active = set(ctx.allowlist.active_ids)
    survivors = [v for v in kept if v.channel_id in active]
    dropped = len(kept) - len(survivors)
    if dropped:
        names = Counter(v.channel for v in kept if v.channel_id not in active)
        logger.warning(
            "승인 목록 밖 채널의 영상 %d건을 제외했다 (직전 결과에서 넘어온 것) — %s",
            dropped,
            ", ".join(f"{name} {n}건" for name, n in names.most_common()),
        )
    return survivors, dropped
