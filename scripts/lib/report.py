"""산출물 기록 — videos.json · version.json · build_report.json.

**모든 처리가 끝난 뒤에만 호출된다.** 중단 시 부분 결과를 남기지 않는 것이
배치의 실행 원칙 3이고, 그 원칙이 지켜지는 자리가 여기다 (tmp → os.replace).

이름을 가르는 규칙도 여기 있다 — 드라이런은 `videos.dry-run.json`,
부분 실행(--only)은 `videos.partial.json`. 둘 다 실제 배포 파일을 덮지 않는다
(FYM에서 드라이런이 661 units짜리 결과를 덮은 사고의 교훈).

build_report.json은 **사람이 읽는 파일이다.** 채널별 기여, 주제별 형식 분포,
경보가 여기 모인다.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.filters import FilterStats
from lib.results import (
    BuildContext,
    CrisisResult,
    SubcategoryResult,
    TaggedVideo,
    ThemeResult,
)

logger = logging.getLogger("build_videos")


def write_outputs(
    out_dir: Path,
    version: str,
    themes: Sequence[ThemeResult],
    subcategories: Sequence[SubcategoryResult],
    crisis: CrisisResult | None,
    ctx: BuildContext,
    *,
    dry_run: bool,
    crisis_age_days: int,
    tagging: dict[str, Any],
    filter_stats: FilterStats,
    only: list[str] | None = None,
) -> None:
    """모든 처리가 끝난 뒤에만 호출된다 (부분 결과 방지).

    --only 부분 실행의 산출물은 videos.partial.json으로, 드라이런은
    videos.dry-run.json으로 이름을 갈라 실제 배포 파일을 덮지 않는다.
    (FYM에서 드라이런이 661 units짜리 결과를 덮은 사고의 교훈)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = only is not None

    videos_json: dict[str, Any] = {"version": version}
    if partial:
        videos_json["partial"] = True
        videos_json["only"] = only
    # 앱이 받는 단위는 **세분류 화면**이다 (PLAN.md 4.2, 2026-08-19 개정).
    #
    # 개정 전에는 주제(theme)별 목록을 내보내고 세분류→주제 조합을 앱에 맡겼다.
    # 폴백이 들어오면서 그 구조로는 안 된다 — 폴백은 세분류의 media_defaults에
    # 달려 있고, 화면이 몇 건 나가는지도 세분류 단위로만 정해진다.
    # 주제별 집계는 build_report.json에 남긴다(진단용이지 앱이 쓰는 값이 아니다).
    videos_json["subcategories"] = [s.to_json() for s in subcategories]
    if crisis is not None:
        videos_json["crisis"] = {
            "updated_at": crisis.updated_at,
            "source": crisis.source,
            "videos": crisis.videos,
        }

    report_json = {
        "version": version,
        "dry_run": dry_run,
        "partial": partial,
        "only": only,
        "allowlist_size": ctx.allowlist.size,
        "blocked_channels": sorted(ctx.blocked_channel_ids),
        "quota_spent": ctx.budget.spent,
        "quota_calls": dict(ctx.budget.calls),
        "filters": filter_stats.to_json(),
        "tagging": tagging,
        "channels": [y.to_json() for y in ctx.yields.values()],
        "crisis": None
        if crisis is None
        else {
            "count": len(crisis.videos),
            "carried_over": crisis.carried_over,
            "updated_at": crisis.updated_at,
            "age_days": crisis_age_days,
            "pool_size": crisis.pool_size,
            "max_per_channel": crisis.max_per_channel,
            "per_channel_unlocked": crisis.per_channel_unlocked,
            "channel_spread": crisis.channel_spread,
        },
        "subcategories": [
            {
                "id": s.id,
                "themes": list(s.themes),
                "media_default": s.media_default,
                "count": s.count,
                "from_theme": len(s.theme_videos),
                "from_fallback": len(s.fallback_videos),
                "fallback_ratio": round(s.fallback_ratio, 3),
                "media_types": s.media_counts,
                "visible_by_toggle": s.visible,
                "channel_spread": s.channel_spread,
            }
            for s in subcategories
        ],
        "themes": [
            {
                "id": t.id,
                "count": len(t.picked),
                "pool_size": t.pool_size,
                "surplus": max(0, t.pool_size - len(t.picked)),
                "from_previous": t.from_previous,
                "excluded_by_crisis": t.excluded_by_crisis,
                "max_per_channel": t.max_per_channel,
                "per_channel_unlocked": t.per_channel_unlocked,
                "media_types": t.media_counts,
                "visible_by_toggle": t.visible,
                "channel_spread": t.channel_spread,
            }
            for t in themes
        ],
        "alerts": ctx.collector.to_json(),
    }

    if partial:
        atomic_write(out_dir / "videos.partial.json", videos_json)
        atomic_write(out_dir / "build_report.partial.json", report_json)
        logger.warning(
            "부분 실행 산출물 — %s/videos.partial.json (version.json 미생성, 배포 대상 아님)",
            out_dir,
        )
        return

    suffix = ".dry-run" if dry_run else ""
    atomic_write(out_dir / f"videos{suffix}.json", videos_json)
    atomic_write(
        out_dir / f"version{suffix}.json",
        {
            "version": version,
            "crisis_updated_at": crisis.updated_at if crisis else None,
        },
    )
    atomic_write(out_dir / f"build_report{suffix}.json", report_json)
    if dry_run:
        logger.warning(
            "드라이런 산출물 — %s/videos.dry-run.json (실제 파일은 건드리지 않았다)", out_dir
        )
    else:
        logger.info("산출물 기록 완료 — %s", out_dir)


def atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def load_previous(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        logger.warning("직전 videos.json이 없다 — 최초 실행으로 진행한다")
        return {}
    try:
        with path.open(encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("직전 videos.json을 읽지 못했다 (%s) — 최초 실행으로 진행한다", exc)
        return {}
    logger.info(
        "직전 결과 로드 — version=%s, 목록 %d개, 위기 %d건",
        data.get("version"),
        len(data.get("subcategories") or data.get("themes", [])),
        len((data.get("crisis") or {}).get("videos", [])),
    )
    return data


def write_title_dump(
    out_dir: Path,
    version: str,
    tagged: Sequence[TaggedVideo],
    *,
    dry_run: bool,
) -> Path:
    """필터를 통과한 영상 **전량**의 제목·채널·길이를 떨군다 (--dump-titles).

    태깅 성공 여부와 무관하게 전건을 담는다. 미태깅 영상의 제목이야말로
    보려는 대상이기 때문이다 — 배치 리포트의 `untagged_sample`은 채널당 5건이라
    사전의 구멍을 세는 데는 못 쓴다.

    **이 파일이 있으면 이후 태깅 전략 분석이 전부 API 0으로 된다.**
    2026-08-19 첫 실측에서 미태깅 822건의 제목이 어디에도 남지 않아,
    "장절이 몇 건에 있는가" 같은 기본적인 질문에 답하려면 61 units를 다시
    써야 했다. 그 왕복을 없애려고 만든 옵션이다.

    산출물은 커밋하지 않는다(.gitignore `titles*.json`) — 원자료이고 매 실행
    바뀌며, 배포에 나가는 파일이 아니다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".dry-run" if dry_run else ""
    path = out_dir / f"titles{suffix}.json"
    payload = {
        "version": version,
        "count": len(tagged),
        "note": "필터 통과 전량. themes가 빈 배열이면 미태깅이다.",
        "videos": [
            {
                "videoId": t.video.video_id,
                "title": t.video.title,
                "channel": t.video.channel,
                "channelId": t.video.channel_id,
                "publishedAt": t.video.published_at,
                "duration": t.video.duration,
                "durationSeconds": t.video.duration_seconds,
                "themes": list(t.themes),
                "hits": list(t.hits),
                "mediaType": t.media.media_type,
                "mediaReason": t.media.reason,
            }
            for t in tagged
        ],
    }
    atomic_write(path, payload)
    logger.info("제목 덤프 %d건 기록 — %s (커밋 대상 아님)", len(tagged), path)
    return path
