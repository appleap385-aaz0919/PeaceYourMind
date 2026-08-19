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
from lib.results import BuildContext, CrisisResult, ThemeResult

logger = logging.getLogger("build_videos")


def write_outputs(
    out_dir: Path,
    version: str,
    themes: Sequence[ThemeResult],
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
    videos_json["themes"] = [t.to_json() for t in themes]
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
        "직전 결과 로드 — version=%s, 주제 %d개, 위기 %d건",
        data.get("version"),
        len(data.get("themes", [])),
        len((data.get("crisis") or {}).get("videos", [])),
    )
    return data
