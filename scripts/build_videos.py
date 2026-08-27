#!/usr/bin/env python
"""videos.json 생성 배치 (PLAN.md Phase 2).

승인 채널의 업로드를 순회해 영상을 모으고, 제목으로 **주제**와 **형식**을 가려
정적 배포용 videos.json을 만든다. FYM build_videos.py의 골격을 그대로 쓰되
수집부를 통째로 바꿨다.

    FYM  감정 세분류마다 검색 → 카테고리별 영상 목록      일 7,900 units
    PYM  승인 채널의 uploads 재생목록 순회 → 주제 태깅    일 ~60 units

**search.list를 부르지 않는다.** 이것이 쿼터 절감책이자 안전 장치다 —
검색을 하지 않으면 이단 채널이 검색 결과로 유입될 경로 자체가 없다
(PLAN.md 5절, lib/quota.py 상단).

실행 원칙 (FYM 승계 + PYM 고유)
  1. 위기 풀을 먼저 확정한다. 중단이 나도 안전 데이터는 갱신된 상태여야 하고,
     먼저 확정해야 일반 주제에서 그 videoId를 제외해 상호 배타가 구조로 보장된다.
  2. 실행 전 예상 쿼터를 산정해 하드캡을 넘으면 API를 한 번도 부르지 않고 멈춘다.
  3. 중단 시 원자성 — 부분 결과를 절대 쓰지 않는다. tmp → os.replace.
  4. 위기 확보량이 12건 미만이면 필터를 완화하지 않고 직전 결과를 유지한다.
  5. 주제별 선정은 채널 라운드로빈 + 채널당 상한 3 (사다리 3→4→5).
  6. **형식 균형** — 한 주제의 20슬롯을 말씀/찬양이 나눠 갖는다. 한쪽이 0이 되면
     앱의 토글이 빈 화면을 내므로, 풀에 양쪽이 있는데 선정에서 한쪽이 사라지는
     일이 없게 한다 (PLAN.md 3.4·4.2).

FYM과 다른 구조 하나 — **videos.list를 한 번만 돈다.**
    FYM은 카테고리마다 검색 결과가 달라 카테고리별로 videos.list를 불렀다.
    PYM의 후보는 채널 업로드 하나뿐이고 주제는 그 뒤에 제목으로 가른다.
    그래서 검증은 전체 후보에 대해 한 번만 하고, 태깅은 API 없이 그 결과 위에서 한다.

종료 코드
  0  성공
  1  일반 오류 — 워크플로가 1회만 재시도한다
  2  쿼터 관련 중단 — 재시도해도 같은 결과이므로 재시도하지 않는다

이 파일은 **오케스트레이션과 CLI**다. 단계별 로직은 lib에 있다.

    lib/collect.py     승인 채널 → uploads → 후보 videoId, 승인 목록 밖 배제
    lib/filters.py     videos.list 응답 검증·필터
    lib/tagging.py     제목 → 주제 / media_type 판별
    lib/selection.py   채널 분산 + 형식 균형 선정
    lib/crisis.py      위기 풀 (먼저 확정, 미달 시 직전 결과 유지)
    lib/report.py      videos.json · version.json · build_report.json 기록
    lib/results.py     위 모듈들이 주고받는 자료형

사용 예
  python scripts/build_videos.py --dry-run
  python scripts/build_videos.py --previous _previous/data/videos.json --out-dir dist
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import alerts as alert_specs
from lib.actions_status import batch_succeeded_on
from lib.allowlist import MIN_ALLOWLIST_SIZE, REVIEW_OVERDUE_DAYS, Allowlist, load_allowlist
from lib.channel_blocklist import load_channel_blocklist
from lib.collect import (
    DEFAULT_UPLOADS_PER_CHANNEL,
    collect_uploads,
    enforce_allowlist,
    previous_video_ids,
)
from lib.crisis import build_crisis, check_crisis_freshness
from lib.filters import Video, apply_filters, dedupe
from lib.quota import DEFAULT_HARD_CAP, QuotaBudget, QuotaExceeded, build_estimate
from lib.quota_log import (
    DAILY_CEILING,
    DEFAULT_LOG,
    QuotaBudgetExceeded,
    check as check_daily_quota,
    record as record_quota,
    table as quota_table,
)
from lib.report import iso, load_previous, write_outputs, write_title_dump
from lib.results import (
    BuildContext,
    CrisisResult,
    SubcategoryResult,
    TaggedVideo,
    ThemeResult,
)
from lib.selection import (
    MEDIA_FLOOR,
    TAB_OVER_CRITICAL,
    TAB_OVER_WARN,
    drop_promotional,
    select_tab_layers,
    # build_themes()가 주제별 진단·경보를 낼 때 쓴다(아래 271행 부근).
    # 화면 구성은 select_tab_layers가 하지만 그 안에서도 이 함수를 부른다.
    # ⚠ 2026-08-26 "영상 상한을 탭별로"(4702779)에서 이 줄이 빠져 배치가
    #   NameError로 죽었다. 임포트를 정리할 때 build_themes를 함께 볼 것.
    select_theme_videos,
)
from lib.taxonomy import load_subcategory_ids
from lib.tagging import SERMON, UNKNOWN, WORSHIP, classify_media_type, tag_themes
from lib.themes import (
    FALLBACK_HEAVY_RATIO,
    MIN_DURATION_SECONDS,
    SUBCATEGORY_MIN_VIDEOS,
    THEME_MAX_VIDEOS,
    THEME_MIN_VIDEOS,
    Themes,
    load_themes,
)
from lib.youtube import Client, DryRunClient, YouTubeClient

logger = logging.getLogger("build_videos")

# --only에서 위기 풀을 가리키는 토큰. 주제 id 공간과 겹치지 않는다.
CRISIS_SELECTOR = "crisis"

# 미태깅 비율이 이보다 높으면 경보. 주제 사전의 구멍이거나 채널 성격 불일치 신호다.
UNTAGGED_ALERT_RATIO = 0.7

# 폴백에서 뺀 공고·행사·홍보를 로그에 몇 건까지 보일 것인가.
PROMO_LOG_SAMPLE = 8

EXIT_OK = 0
EXIT_RETRYABLE = 1
EXIT_QUOTA = 2


class IntegrityError(RuntimeError):
    """산출물 무결성 위반. 배포하지 않는다."""


class SelectionError(ValueError):
    """--only에 알 수 없는 주제가 지정됐다."""


# =============================================================================
# 태깅 — 제목으로 주제와 형식을 가린다 (API 0)
# =============================================================================


def tag_pool(ctx: BuildContext, kept: Sequence[Video]) -> list[TaggedVideo]:
    """필터를 통과한 영상에 주제와 media_type을 붙인다.

    채널 content_type은 media_type 판별 1순위다(themes.yaml). 승인 목록에 없는
    채널이 여기 올 일은 없지만(전면 화이트리스트), 왔다면 mixed와 같은 경로로
    보내 제목·길이로 판정한다 — 알 수 없는 값을 sermon/worship 어느 쪽으로도
    단정하지 않는다.
    """
    tagged: list[TaggedVideo] = []
    for video in kept:
        channel = ctx.channel(video.channel_id)
        matches = tag_themes(video.title, ctx.themes, video.channel)
        media = classify_media_type(
            video.title,
            video.duration_seconds,
            channel.content_type if channel else None,
            ctx.themes,
        )
        tagged.append(
            TaggedVideo(
                video=video,
                themes=tuple(m.theme_id for m in matches),
                hits=tuple(h for m in matches for h in m.hits),
                media=media,
            )
        )
    return tagged


def _untagged_sample(untagged: Sequence[TaggedVideo], per_channel: int = 5) -> list[str]:
    """미태깅 제목 표본 — **채널마다 골고루** 뽑는다.

    앞에서부터 15건을 자르면 첫 채널의 제목만 담긴다(2026-08-19 첫 실측이
    정확히 그랬다 — 822건 중 표본 15건이 전부 오륜교회였다). 사전의 구멍을
    보려면 채널마다 어떤 제목이 안 걸리는지를 봐야 하므로 채널별로 잘라 담는다.
    """
    picked: list[str] = []
    seen: Counter[str] = Counter()
    for item in untagged:
        channel = item.video.channel
        if seen[channel] >= per_channel:
            continue
        seen[channel] += 1
        picked.append(f"[{channel}] {item.video.title}")
    return picked


def summarize_tagging(ctx: BuildContext, tagged: Sequence[TaggedVideo]) -> dict[str, Any]:
    """태깅 결과를 리포트용으로 집계하고, 필요하면 경보를 낸다.

    미태깅은 결함이 아니라 정상 동작이다(themes.yaml [채널 승인과 콘텐츠 태깅은
    별개다]). 다만 **어느 채널에 몰려 있는가**가 중요하다 — 특정 채널에 쏠려
    있으면 주제 사전이 아니라 그 채널의 승인 근거를 다시 봐야 한다.
    """
    untagged = [t for t in tagged if t.is_untagged]
    _, promo_dropped = drop_promotional(untagged)
    by_channel = Counter(t.video.channel for t in untagged)
    ratio = len(untagged) / len(tagged) if tagged else 0.0

    media_counts = Counter(t.media.media_type for t in tagged)
    reason_counts = Counter(t.media.reason for t in tagged)
    multi = sum(1 for t in tagged if len(t.themes) > 1)

    logger.info(
        "태깅 — 확보 %d건 중 태깅 %d건 / 미태깅 %d건 (%.0f%%), 복수 태깅 %d건",
        len(tagged),
        len(tagged) - len(untagged),
        len(untagged),
        ratio * 100,
        multi,
    )
    logger.info(
        "형식 — 말씀 %d / 찬양 %d / 미판별 %d  (판정근거 %s)",
        media_counts.get(SERMON, 0),
        media_counts.get(WORSHIP, 0),
        media_counts.get(UNKNOWN, 0),
        ", ".join(f"{k}:{v}" for k, v in sorted(reason_counts.items())),
    )

    if tagged and ratio >= UNTAGGED_ALERT_RATIO:
        logger.warning("미태깅 비율 %.0f%% — 주제 사전 또는 채널 성격을 확인할 것", ratio * 100)
        ctx.collector.add(**alert_specs.untagged_high(ratio, len(untagged), len(tagged)))

    return {
        "kept": len(tagged),
        "tagged": len(tagged) - len(untagged),
        "untagged": len(untagged),
        "untagged_ratio": round(ratio, 3),
        "multi_theme": multi,
        "untagged_by_channel": dict(by_channel.most_common()),
        "untagged_sample": _untagged_sample(untagged),
        # 폴백 후보에서 뺀 것 — 미태깅 중 공고·행사·홍보
        # (lib/selection.promo_reason). 매일 몇 건이 걸리는지 보이지 않으면
        # 사전이 과하게 잡기 시작해도 알 수 없다.
        "fallback_excluded": len(promo_dropped),
        "fallback_excluded_sample": [
            f"[{reason}] {item.video.title}" for reason, item in promo_dropped[:15]
        ],
        "media_types": {k: media_counts.get(k, 0) for k in (SERMON, WORSHIP, UNKNOWN)},
        "media_reasons": dict(sorted(reason_counts.items())),
    }


# =============================================================================
# 주제별 목록 — 선정 규칙 자체는 lib/selection.py에 있다
# =============================================================================


def build_themes(
    ctx: BuildContext,
    tagged: Sequence[TaggedVideo],
    exclude: set[str],
    day_of_year: int,
    selected_ids: Sequence[str],
) -> list[ThemeResult]:
    """주제별 목록을 만든다. 위기 videoId는 후보 단계에서 제외한다."""
    previous_ids = {
        vid
        for theme in ctx.previous.get("themes", [])
        for vid in (str(v["videoId"]) for v in theme.get("videos", []))
    }
    wanted = set(selected_ids)
    results: list[ThemeResult] = []

    for theme in ctx.themes.taggable:
        if theme.id not in wanted:
            continue
        matched = [t for t in tagged if theme.id in t.themes]
        pool = [t for t in matched if t.video_id not in exclude]
        excluded = len(matched) - len(pool)
        picked, cap, unlocked = select_theme_videos(pool, day_of_year)
        from_previous = sum(1 for t in picked if t.video_id in previous_ids)

        result = ThemeResult(
            id=theme.id,
            label=theme.label,
            picked=picked,
            pool_size=len(pool),
            max_per_channel=cap,
            per_channel_unlocked=unlocked,
            from_previous=from_previous,
            excluded_by_crisis=excluded,
        )
        _log_theme(result)
        _evaluate_theme(ctx, result)
        results.append(result)

    return results


def _log_theme(result: ThemeResult) -> None:
    spread = result.channel_spread
    top = f"{next(iter(spread.values()))}/{len(result.picked)}" if spread else "0/0"
    media = result.media_counts
    logger.info(
        "%-16s %2d건 (풀 %3d) | 말씀 %2d 찬양 %2d 미판별 %2d | %d채널(최다 %s), 상한 %d%s"
        " | 직전 유입 %d",
        result.id,
        len(result.picked),
        result.pool_size,
        media[SERMON],
        media[WORSHIP],
        media[UNKNOWN],
        len(spread),
        top,
        result.max_per_channel,
        " 해제" if result.per_channel_unlocked else "",
        result.from_previous,
    )


def _evaluate_theme(ctx: BuildContext, result: ThemeResult) -> None:
    if not result.picked:
        logger.error("%s 영상 0건 — 이 주제가 붙은 감정 화면이 빈다", result.id)
        ctx.collector.add(**alert_specs.theme_empty(result.id))
        return

    if len(result.picked) < THEME_MIN_VIDEOS:
        logger.warning(
            "%s 확보량 %d건 < 하한 %d건", result.id, len(result.picked), THEME_MIN_VIDEOS
        )
        ctx.collector.add(
            **alert_specs.theme_low_yield(result.id, len(result.picked), THEME_MIN_VIDEOS)
        )

    # 토글 기준으로 본다 — unknown은 양쪽에 노출되므로 한쪽이 0이 되는 것은
    # "그 형식의 영상도 unknown도 없다"는 뜻이다. 그때만 빈 화면이 나온다.
    visible = result.visible
    for side, other in ((SERMON, WORSHIP), (WORSHIP, SERMON)):
        if visible[side] == 0 and visible[other] > 0:
            logger.warning("%s %s 0건 — 토글을 눌러도 빈 화면이 된다", result.id, side)
            ctx.collector.add(
                **alert_specs.media_type_gap(result.id, side, other, len(result.picked))
            )




# =============================================================================
# 세분류 화면 — 주제분 + 폴백 2층 (PLAN.md 3.3 개정)
# =============================================================================


def build_subcategories(
    ctx: BuildContext,
    tagged: Sequence[TaggedVideo],
    exclude: set[str],
    day_of_year: int,
) -> list[SubcategoryResult]:
    """감정 세분류마다 실제 화면에 나갈 목록을 만든다.

    [왜 주제별 목록만으로는 부족한가]
      주제(theme)는 화면을 채우는 재료이고 화면은 세분류에 붙는다. 조합을 앱에
      맡기면 배치가 "이 화면이 몇 건 나가는가"를 모른다 — 화면 성립 여부
      (SUBCATEGORY_MIN_VIDEOS)와 폴백 비율을 판정할 수 없다. 그래서 배치가
      세분류 단위까지 조립한다.

    [2층 구조]
      1층 주제 태깅분  매핑 주제에 걸린 영상. 근거가 분명하다
      2층 폴백        어느 주제에도 안 걸린 영상을 형식(media_defaults)으로 채운다
                     상한 12/20 — 화면 전체가 폴백으로 덮이지 않게 한다

      실측(2026-08-19): 1,069건 중 제목이 주제를 말하는 것은 CGN 생명의 삶
      100건뿐이었다. 나머지는 설교 문장·곡목·프로그램 브랜드다. 미태깅을 버리면
      24개 화면 중 20개가 목표 미달이고 1개는 0건이 된다. 폴백은 그것을 메운다.
    """
    results: list[SubcategoryResult] = []
    untagged, promo_dropped = drop_promotional([t for t in tagged if t.is_untagged])
    if promo_dropped:
        logger.info(
            "폴백 후보에서 공고·행사·홍보·제3범주 %d건 제외 — 남은 후보 %d건",
            len(promo_dropped),
            len(untagged),
        )
        for reason, item in promo_dropped[:PROMO_LOG_SAMPLE]:
            logger.info("  제외 [%s] %s", reason, item.video.title[:70])

    for position, (sub, theme_ids) in enumerate(ctx.themes.mapping.items()):
        pool = [
            t
            for t in tagged
            if t.video_id not in exclude and any(x in t.themes for x in theme_ids)
        ]
        # 탭별로 채운다 — 주제분 먼저, 부족분을 그 탭의 폴백이 (2026-08-26).
        # 회전(rotate_for_subcategory)은 select_tab_layers 안에서 탭마다 걸린다.
        media_default = ctx.themes.media_default(sub) or SERMON
        picked, fallback = select_tab_layers(
            pool, untagged, day_of_year, position, exclude=exclude
        )

        result = SubcategoryResult(
            id=sub,
            themes=tuple(theme_ids),
            media_default=media_default,
            theme_videos=picked,
            fallback_videos=fallback,
        )
        _log_subcategory(result)
        _evaluate_subcategory(ctx, result)
        results.append(result)

    filled = sum(1 for r in results if r.count == THEME_MAX_VIDEOS)
    logger.info(
        "세분류 %d개 — 목표 달성 %d개 / 총 노출 %d건 (주제분 %d + 폴백 %d)",
        len(results),
        filled,
        sum(r.count for r in results),
        sum(len(r.theme_videos) for r in results),
        sum(len(r.fallback_videos) for r in results),
    )
    return results


def _log_subcategory(r: SubcategoryResult) -> None:
    logger.info(
        "%-22s %-7s 주제 %2d + 폴백 %2d = %2d건 (폴백 %3.0f%%) | 말씀 %2d 찬양 %2d 미판별 %2d",
        r.id,
        r.media_default,
        len(r.theme_videos),
        len(r.fallback_videos),
        r.count,
        r.fallback_ratio * 100,
        r.media_counts[SERMON],
        r.media_counts[WORSHIP],
        r.media_counts[UNKNOWN],
    )


def _evaluate_subcategory(ctx: BuildContext, r: SubcategoryResult) -> None:
    """화면 단위 경보 2종. 주제 단위 경보(theme_*)와 층이 다르다.

    주제 경보  "이 주제 풀이 얇다"          → 사전·채널 진단용
    화면 경보  "이 화면이 성립하지 않는다"    → 사용자가 실제로 겪는 상태
    """
    # ⚠⚠ 성립 여부도 **탭별로** 잰다 (2026-08-26). 화면 합계는 사용자가 보는 것이
    #   아니다 — 말씀 20 · 찬양 2인 화면은 합계 22로 옛 기준을 통과하지만 찬양 쪽
    #   사용자에게는 빈 화면이다.
    #   ★ 탭 검사가 화면 검사를 **포함한다** (vis <= count) — 놓치는 것이 없다.
    for side, n in r.tab_counts.items():
        if n["total"] >= SUBCATEGORY_MIN_VIDEOS:
            continue
        empty = n["total"] < MEDIA_FLOOR
        logger.error(
            "%s [%s] %d건 < %d건 — %s",
            r.id,
            side,
            n["total"],
            MEDIA_FLOOR if empty else SUBCATEGORY_MIN_VIDEOS,
            "사실상 빈 탭이다" if empty else "목록으로 성립하지 않는다",
        )
        ctx.collector.add(
            **alert_specs.theme_too_few(
                r.id,
                side,
                n["total"],
                MEDIA_FLOOR if empty else SUBCATEGORY_MIN_VIDEOS,
                empty=empty,
            )
        )

    # ⚠⚠ 반대쪽 끝 — 탭이 **너무 두꺼운** 경우다 (2026-08-27 · 사용자 결정 D안).
    #   TAB_MAX_VIDEOS(20)는 "한 탭이 20건 이하"를 보장하지 않는다. 보장하는 것은
    #   "각 패스의 기여가 20 이하"이고, 뒷 패스가 담은 unknown이 앞 패스의 탭에도
    #   보여 20을 넘는다(2026-08-26 실측 최대 24 · 구조적 상한 40).
    #   초과는 **허용하기로 했다.** 조용히 40까지 벌어지는 것만 막는다.
    #   임계 근거는 selection.py의 TAB_OVER_* 주석에 있다.
    for side, n in r.tab_counts.items():
        if n["total"] < TAB_OVER_WARN:
            continue
        severe = n["total"] >= TAB_OVER_CRITICAL
        logger.warning(
            "%s [%s] %d건 — 탭 노출이 임계 %d건을 넘었다 (의도 상한 20). "
            "unknown 급증을 의심할 것",
            r.id,
            side,
            n["total"],
            TAB_OVER_CRITICAL if severe else TAB_OVER_WARN,
        )
        ctx.collector.add(
            **alert_specs.tab_over_cap(
                r.id,
                side,
                n["total"],
                TAB_OVER_CRITICAL if severe else TAB_OVER_WARN,
                severe=severe,
            )
        )

    # ⚠⚠ 폴백 비율은 **탭별로** 잰다 (2026-08-26). 화면 평균으로 두면 한 탭이
    #   100% 폴백이어도 반대 탭에 가려진다 — 탭별 상한 이후 두 탭의 구성이 크게
    #   갈리므로 평균은 어느 쪽도 설명하지 못한다.
    counts = r.tab_counts
    for side, ratio in r.tab_fallback_ratio.items():
        if ratio <= FALLBACK_HEAVY_RATIO:
            continue
        n = counts[side]
        logger.warning(
            "%s [%s] 폴백 %.0f%% (%d/%d) — 주제 사전·채널이 이 감정을 못 받치고 있다",
            r.id,
            side,
            ratio * 100,
            n["fallback"],
            n["total"],
        )
        ctx.collector.add(
            **alert_specs.theme_fallback_heavy(
                f"{r.id} [{side}]", ratio, n["fallback"], n["total"]
            )
        )


# =============================================================================
# 무결성 검증 — 통과해야만 기록한다
# =============================================================================


def assert_disjoint(themes: Sequence[ThemeResult], crisis: CrisisResult | None) -> None:
    """crisis와 주제 목록이 videoId를 공유하지 않는지 단언한다 (PLAN.md 4.2).

    위기 풀을 먼저 확정하고 주제 후보에서 제외했으므로 정상적으로는 통과한다.
    여기서 걸린다면 제외 로직이 깨진 것이므로 배포하지 않는다.
    """
    if crisis is None:
        logger.warning("위기 풀을 실행하지 않아 상호 배타 검증을 건너뛴다")
        return
    crisis_ids = crisis.video_ids
    for theme in themes:
        overlap = {v["videoId"] for v in theme.videos} & crisis_ids
        if overlap:
            raise IntegrityError(
                f"crisis와 {theme.id}가 videoId를 공유한다: {sorted(overlap)}. 배포를 중단한다."
            )
    logger.info(
        "무결성 검증 통과 — crisis %d건과 주제 %d건이 서로소",
        len(crisis_ids),
        sum(len(t.picked) for t in themes),
    )


def assert_media_type_filled(themes: Sequence[ThemeResult]) -> None:
    """모든 영상에 media_type이 채워졌는지 단언한다.

    앱의 토글이 이 필드로 거른다. 비어 있는 영상은 어느 토글에도 안 잡혀
    **조용히 사라진다** — 판별 실패(unknown)와 필드 누락은 결과가 전혀 다르다.
    """
    valid = {SERMON, WORSHIP, UNKNOWN}
    for theme in themes:
        for video in theme.videos:
            if video.get("media_type") not in valid:
                raise IntegrityError(
                    f"{theme.id}의 {video.get('videoId')}에 media_type이 없다 "
                    f"({video.get('media_type')!r}). 앱 토글에서 사라지므로 배포하지 않는다."
                )


def assert_fallback_untagged(subcategories: Sequence[SubcategoryResult]) -> None:
    """폴백에 주제 태깅분이 섞이지 않았는지 단언한다.

    두 층은 근거의 강도가 다르다. 폴백에 태깅된 영상이 섞이면 `source` 필드가
    거짓말을 하게 되고, 앱이 "이 감정에 맞춰 고른 영상 / 이 채널의 최근 영상"으로
    나눠 보여줄 수 없다. 그 구분이 무너지는 순간 사용자는 화면 전체를 의심한다.
    """
    for sub in subcategories:
        tainted = [t.video_id for t in sub.fallback_videos if not t.is_untagged]
        if tainted:
            raise IntegrityError(
                f"{sub.id}의 폴백에 주제 태깅분이 섞였다: {sorted(tainted)}. "
                "source 구분이 무너지므로 배포하지 않는다."
            )
        overlap = {t.video_id for t in sub.theme_videos} & {
            t.video_id for t in sub.fallback_videos
        }
        if overlap:
            raise IntegrityError(
                f"{sub.id}에서 같은 영상이 두 층에 모두 있다: {sorted(overlap)}"
            )


# =============================================================================
# 진입점
# =============================================================================


def resolve_selection(
    themes: Themes, only: str | None
) -> tuple[list[str], bool, list[str] | None]:
    """--only 인자를 (실행할 주제 id, 위기 실행 여부, 원본 선택 목록)으로 푼다."""
    taggable = [t.id for t in themes.taggable]
    if not only:
        return taggable, True, None

    requested = [token.strip() for token in only.split(",") if token.strip()]
    known = set(taggable)
    unknown = [t for t in requested if t != CRISIS_SELECTOR and t not in known]
    if unknown:
        raise SelectionError(
            f"알 수 없는 주제: {', '.join(unknown)}\n"
            f"사용 가능한 값: {CRISIS_SELECTOR}, " + ", ".join(taggable)
        )
    run_crisis = CRISIS_SELECTOR in requested
    selected = [t for t in taggable if t in set(requested)]
    return selected, run_crisis, requested


def preflight(
    allowlist: Allowlist,
    previous: dict[str, Any],
    uploads_per_channel: int,
    hard_cap: int,
) -> int:
    """실행 전 예상 쿼터를 산정해 표로 출력하고 총량을 반환한다."""
    channels = allowlist.size
    pages = max(1, -(-uploads_per_channel // 50))
    expected_ids = channels * uploads_per_channel + len(previous_video_ids(previous))
    estimate = build_estimate(
        allowlist_channels=channels,
        uploads_pages_per_channel=pages,
        expected_video_ids=expected_ids,
    )
    print(estimate.table(hard_cap))
    return estimate.total


def dry_run_titles(themes: Themes) -> list[str]:
    """드라이런용 합성 제목. 주제·형식 판별 경로가 실제로 실행되게 만든다.

    ⚠ 이것은 판별 규칙의 **검증이 아니다.** 사전에서 만든 제목이라 당연히 걸린다.
      규칙의 정오는 scripts/tagging_test.py가 손으로 쓴 제목으로 본다.
      여기서 보는 것은 파이프라인이다 — 태깅→선정→형식 균형→리포트가 실제
      데이터 모양에서 끝까지 도는지, 리포트 숫자가 말이 되는지.

    어느 주제에도 걸리지 않는 제목을 일부러 섞는다. untagged 경로도 매일 도는
    경로이고, 그 비율이 리포트의 핵심 지표이기 때문이다.
    """
    titles: list[str] = []
    for theme in themes.taggable:
        keyword = theme.title_keywords[0] if theme.title_keywords else theme.label
        titles.append(f"주일예배 | 요한복음 3:16 — {keyword}")
        titles.append(f"{keyword} | 잔잔한 피아노 찬양 모음")
        titles.append(f"{keyword}에 대하여")
    # 이 넷은 어느 주제에도 안 걸려 폴백 후보로 떨어진다. 그중 **둘은 폴백
    # 품질 필터에도 걸리게** 두었다 — 뒤의 둘(스케치·하이라이트)이 그것이다.
    # 덕분에 드라이런이 필터의 양쪽 분기를 모두 태운다: 걸러지는 것과 남는 것.
    # ⚠ 여기 제목을 바꿀 때 그 균형을 깨지 말 것. 넷이 전부 통과하면 필터가
    #   꺼져 있어도 드라이런이 아무 말을 하지 않는다.
    titles.extend(
        [
            "교회 소식 브리핑",  # 남는다
            "성탄 축하 행사 스케치",  # 폴백 필터에 걸린다
            "선교 보고 영상",  # 남는다
            "청년부 수련회 하이라이트",  # 폴백 필터에 걸린다
        ]
    )
    return titles


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="videos.json 생성 배치 (PYM Phase 2)")
    parser.add_argument("--themes", type=Path, default=root / "themes.yaml")
    parser.add_argument("--taxonomy", type=Path, default=root / "taxonomy.yaml")
    parser.add_argument("--allowlist", type=Path, default=root / "channel_allowlist.yaml")
    parser.add_argument(
        "--channel-blocklist", type=Path, default=root / "channel_blocklist.yaml"
    )
    parser.add_argument("--out-dir", type=Path, default=root / "dist")
    parser.add_argument(
        "--previous", type=Path, default=None, help="직전 배치의 videos.json 경로"
    )
    parser.add_argument(
        "--uploads-per-channel",
        type=int,
        default=DEFAULT_UPLOADS_PER_CHANNEL,
        help=f"채널당 읽을 최근 업로드 수 (기본 {DEFAULT_UPLOADS_PER_CHANNEL}, 50건당 1 unit)",
    )
    parser.add_argument("--hard-cap", type=int, default=DEFAULT_HARD_CAP)
    parser.add_argument(
        "--day-of-year", type=int, default=None, help="채널 회전 위상 (검증용)"
    )
    parser.add_argument(
        "--only",
        default=None,
        metavar="ID,ID,...",
        help=(
            "지정한 주제만 실행한다 (예: comfort,crisis). "
            "산출물은 videos.partial.json으로 나가며 배포 대상이 아니다. "
            "⚠ FYM과 달리 쿼터는 줄지 않는다 — 수집이 주제 단위가 아니라 채널 단위라 "
            "어느 주제를 고르든 같은 영상을 받아온다. 태깅·선정 결과만 좁혀 본다."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="API를 호출하지 않고 전 과정을 검증한다"
    )
    parser.add_argument(
        "--dump-titles",
        action="store_true",
        help=(
            "필터를 통과한 영상 전량의 제목·채널·길이를 titles.json으로 떨군다 "
            "(태깅 성공 여부 무관). 태깅 전략을 분석할 때 이 파일이 있으면 "
            "API를 다시 쓰지 않아도 된다. 커밋 대상이 아니다."
        ),
    )
    parser.add_argument(
        "--quota-log",
        type=Path,
        default=root / DEFAULT_LOG,
        help=f"일일 소모 기록 파일 (기본 {DEFAULT_LOG}, 커밋하지 않는다)",
    )
    parser.add_argument("--daily-ceiling", type=int, default=DAILY_CEILING)
    parser.add_argument(
        "--no-quota-log", action="store_true", help="일일 누적 검사·기록을 건너뛴다"
    )
    parser.add_argument(
        "--no-reserve-actions-batch",
        dest="reserve_actions_batch",
        action="store_false",
        help="Actions 배치 몫(하루 2회분)을 미리 빼두지 않는다",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def make_client(args: argparse.Namespace, themes: Themes, budget: QuotaBudget) -> Client:
    if args.dry_run:
        logger.info("드라이런 — API를 호출하지 않는다 (쿼터 소모 0)")
        # blocklist_pool은 DryRunClient가 '걸러져야 할 제목'을 만들 때 쓰는 용어다.
        # PYM에는 제목 용어 사전이 없어(lib/filters.py 상단) 실제로 걸러지지 않는다.
        # 안전 용어를 넣으면 리포트에서 "자살이 들어간 제목이 통과했다"로 읽혀
        # 필터 고장으로 오해되므로, 상태를 그대로 말하는 문자열을 넣는다.
        return DryRunClient(
            budget, ["제목용어사전-없음"], title_pool=dry_run_titles(themes)
        )
    return YouTubeClient(os.environ.get("YOUTUBE_API_KEY", ""), budget)


def run(args: argparse.Namespace, spent_box: dict[str, Any] | None = None) -> int:
    now = datetime.now(timezone.utc)
    day_of_year = args.day_of_year if args.day_of_year is not None else now.timetuple().tm_yday

    # taxonomy.yaml이 이식되면 themes.yaml 검증 1번(mapping ↔ 세분류 대조)이 켜진다.
    # 감정 체계와 주제 매핑이 어긋난 채로 배치가 도는 것을 여기서 막는다.
    themes = load_themes(args.themes, taxonomy_ids=load_subcategory_ids(args.taxonomy))
    allowlist = load_allowlist(args.allowlist)
    blocklist = load_channel_blocklist(args.channel_blocklist)
    previous = load_previous(args.previous)

    selected, run_crisis, only = resolve_selection(themes, args.only)
    if only is not None:
        logger.warning("=" * 68)
        logger.warning("부분 실행 — 지정된 %d개 항목만 처리한다: %s", len(only), ", ".join(only))
        logger.warning("산출물은 videos.partial.json이며 version.json을 만들지 않는다.")
        if not run_crisis:
            logger.warning("위기 풀을 건너뛰므로 주제 후보에서 위기 videoId를 제외하지 않는다.")
        logger.warning("=" * 68)

    logger.info(
        "주제 %d/%d개 / 위기 %s / 승인 채널 %d개(예시 %d) / 채널당 업로드 %d건 / day=%d",
        len(selected),
        len(themes.taggable),
        "실행" if run_crisis else "건너뜀",
        allowlist.size,
        len(allowlist.placeholders),
        args.uploads_per_channel,
        day_of_year,
    )

    estimated = preflight(allowlist, previous, args.uploads_per_channel, args.hard_cap)
    if estimated > args.hard_cap:
        logger.error(
            "예상 소모량 %d units가 하드캡 %d를 넘는다 — API를 호출하지 않고 중단한다",
            estimated,
            args.hard_cap,
        )
        return EXIT_QUOTA

    if not args.dry_run and not args.no_quota_log:
        try:
            usage, reserve = check_daily_quota(
                args.quota_log,
                estimated,
                ceiling=args.daily_ceiling,
                reserve_actions_batch=args.reserve_actions_batch,
                batch_probe=batch_succeeded_on,
            )
        except QuotaBudgetExceeded as exc:
            logger.error("%s", exc)
            logger.error(
                "그날 이미 쓴 양을 포함한 판단이다. 정말 실행하려면 --no-quota-log, "
                "Actions 배치 예약을 빼려면 --no-reserve-actions-batch."
            )
            return EXIT_QUOTA
        print(quota_table(usage, estimated, reserve, args.daily_ceiling))

    budget = QuotaBudget(hard_cap=args.hard_cap)
    if spent_box is not None:
        spent_box["budget"] = budget

    ctx = BuildContext(
        themes=themes,
        client=make_client(args, themes, budget),
        budget=budget,
        previous=previous,
        allowlist=allowlist,
        blocked_channel_ids=blocklist.ids,
    )
    if blocklist.size:
        logger.info(
            "차단 채널 %d개 적용 — %s",
            blocklist.size,
            ", ".join(c.channel_name for c in blocklist.channels),
        )
    logger.info(
        "제목 용어 blocklist 없음 — 채널 화이트리스트와 길이·쇼츠 필터로만 거른다 "
        "(lib/filters.py 상단, Phase 3 taxonomy 이식에서 연결)"
    )
    _collect_allowlist_alerts(ctx, allowlist)

    # 1) 수집 — 승인 채널의 업로드
    collected, by_channel = collect_uploads(ctx, args.uploads_per_channel)
    carried = previous_video_ids(previous)
    candidates = dedupe(collected + carried)
    logger.info(
        "후보 %d건 (수집 %d + 직전 %d, 중복 제거 후)",
        len(candidates),
        len(collected),
        len(carried),
    )

    # 2) 검증·필터 — videos.list 한 번만 돈다
    items = ctx.client.videos(candidates)
    kept, stats = apply_filters(
        items,
        min_seconds=MIN_DURATION_SECONDS,
        blocked_channel_ids=ctx.blocked_channel_ids,
    )
    logger.info("필터 결과 — %s", stats.summary())
    kept, off_allowlist = enforce_allowlist(ctx, kept)

    # 3) 태깅 (API 0)
    tagged = tag_pool(ctx, kept)
    _record_channel_yields(ctx, by_channel, tagged)
    tagging_report = summarize_tagging(ctx, tagged)
    tagging_report["dropped_off_allowlist"] = off_allowlist
    if args.dump_titles:
        write_title_dump(args.out_dir, iso(now), tagged, dry_run=args.dry_run)

    # 4) 위기 풀 먼저 확정 — 그 videoId를 주제 후보에서 뺀다
    crisis = build_crisis(ctx, tagged, now, day_of_year) if run_crisis else None
    crisis_age = check_crisis_freshness(ctx, crisis, now) if crisis else -1

    # 5) 주제별 선정 — 진단 단위다 (사전·채널이 어느 주제를 못 받치는지 본다)
    exclude = crisis.video_ids if crisis else set()
    theme_results = build_themes(ctx, tagged, exclude, day_of_year, selected)

    # 6) 세분류 화면 조립 — 사용자가 실제로 보는 단위 (주제분 + 폴백)
    subcategories = build_subcategories(ctx, tagged, exclude, day_of_year)
    _record_selected(ctx, theme_results, subcategories)

    # 7) 무결성 검증 후에만 기록한다
    assert_disjoint(theme_results, crisis)
    assert_media_type_filled(theme_results)
    assert_fallback_untagged(subcategories)
    write_outputs(
        args.out_dir,
        iso(now),
        theme_results,
        subcategories,
        crisis,
        ctx,
        dry_run=args.dry_run,
        crisis_age_days=crisis_age,
        tagging=tagging_report,
        filter_stats=stats,
        only=only,
    )

    _log_channel_yields(ctx)
    print("\n".join(ctx.budget.report_lines()))
    _log_alert_summary(ctx)
    return EXIT_OK


def _record_channel_yields(
    ctx: BuildContext, by_channel: dict[str, list[str]], tagged: Sequence[TaggedVideo]
) -> None:
    """채널별 잔존 건수를 센다. **수집한 것만 센다.**

    직전 결과에서 되살아난 영상까지 섞으면 "오늘 이 채널이 실제로 공급한 양"이
    흐려진다. 채널이 죽었는지 보려는 표이므로 오늘 창(uploads N건) 안의 것만 본다.
    """
    tagged_by_id = {t.video_id: t for t in tagged}
    for channel_id, video_ids in by_channel.items():
        entry = ctx.yields.get(channel_id)
        if entry is None:
            continue
        survivors = [tagged_by_id[v] for v in video_ids if v in tagged_by_id]
        entry.kept = len(survivors)
        entry.tagged = sum(1 for t in survivors if not t.is_untagged)
        if entry.collected and entry.kept == 0:
            logger.warning(
                "%s — 수집 %d건이 필터를 하나도 통과하지 못했다", entry.name, entry.collected
            )
            ctx.collector.add(
                **alert_specs.channel_zero_yield(channel_id, entry.name, entry.collected)
            )


def _record_selected(
    ctx: BuildContext,
    themes: Sequence[ThemeResult],
    subcategories: Sequence[SubcategoryResult] = (),
) -> None:
    """최종 목록에 실린 영상 수를 채널별로 센다 (중복은 한 번만).

    한 영상이 여러 주제·여러 세분류에 실리므로 videoId로 먼저 접는다 — 접지
    않으면 "100건 수집한 채널이 300건 선정됐다"는 읽을 수 없는 표가 된다.
    폴백으로만 나간 영상도 화면에 노출되므로 함께 센다.
    """
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    picked_all = [t for theme in themes for t in theme.picked]
    picked_all += [
        t for sub in subcategories for t in (*sub.theme_videos, *sub.fallback_videos)
    ]
    for tagged in picked_all:
        if tagged.video_id in seen:
            continue
        seen.add(tagged.video_id)
        counts[tagged.video.channel_id] += 1
    for channel_id, count in counts.items():
        entry = ctx.yields.get(channel_id)
        if entry is not None:
            entry.selected = count


def _log_channel_yields(ctx: BuildContext) -> None:
    if not ctx.yields:
        return
    logger.info("채널별 기여 (수집 → 필터 잔존 → 태깅 → 선정)")
    logger.info("-" * 72)
    for entry in ctx.yields.values():
        flag = "  ← 잔존 0" if entry.collected and entry.kept == 0 else ""
        logger.info(
            "  %-22s %-8s %4d → %4d → %4d → %4d%s",
            entry.name[:22],
            entry.content_type,
            entry.collected,
            entry.kept,
            entry.tagged,
            entry.selected,
            flag,
        )


def _collect_allowlist_alerts(ctx: BuildContext, allowlist: Allowlist) -> None:
    if allowlist.placeholders:
        logger.warning(
            "화이트리스트에 예시 항목 %d건이 남아 있어 건너뛴다", len(allowlist.placeholders)
        )
        ctx.collector.add(**alert_specs.allowlist_placeholders(len(allowlist.placeholders)))
    if allowlist.is_undersized:
        logger.warning("승인 채널 %d개 < 최소 %d개", allowlist.size, MIN_ALLOWLIST_SIZE)
        ctx.collector.add(
            **alert_specs.allowlist_undersized(allowlist.size, MIN_ALLOWLIST_SIZE)
        )
    today = datetime.now(timezone.utc).date()
    for channel in allowlist.channels:
        days = channel.days_since_review(today)
        if days is not None and days > REVIEW_OVERDUE_DAYS:
            ctx.collector.add(
                **alert_specs.channel_review_overdue(
                    channel.channel_id, channel.channel_name, days
                )
            )


def _log_alert_summary(ctx: BuildContext) -> None:
    if not len(ctx.collector):
        logger.info("경보 없음")
        return
    logger.warning("경보 %d건:", len(ctx.collector))
    for alert in ctx.collector.alerts:
        logger.warning("  [%s] %s", alert.severity, alert.title)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return _run_and_record(args)
    except QuotaExceeded as exc:
        logger.error("쿼터 중단: %s", exc)
        logger.error("부분 결과를 쓰지 않았다 — 직전 videos.json이 그대로 유지된다")
        return EXIT_QUOTA
    except SelectionError as exc:
        logger.error("%s", exc)
        return EXIT_RETRYABLE
    except IntegrityError as exc:
        logger.error("무결성 검증 실패: %s", exc)
        logger.error("배포하지 않는다")
        return EXIT_RETRYABLE
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 부분 결과를 남기지 않는다
        logger.exception("배치 실패: %s", exc)
        logger.error("부분 결과를 쓰지 않았다 — 직전 videos.json이 그대로 유지된다")
        return EXIT_RETRYABLE


def _run_and_record(args: argparse.Namespace) -> int:
    """실행 결과와 무관하게 실제 소모량을 기록한다 (중단된 실행도 쿼터를 썼다)."""
    spent_box: dict[str, Any] = {}
    exit_code = EXIT_RETRYABLE
    try:
        exit_code = run(args, spent_box)
        return exit_code
    finally:
        budget = spent_box.get("budget")
        spent = budget.spent if budget is not None else 0
        if not args.dry_run and not args.no_quota_log and spent > 0:
            usage = record_quota(
                args.quota_log,
                script="build_videos",
                units=spent,
                exit_code=exit_code,
                only=args.only.split(",") if args.only else None,
                dry_run=args.dry_run,
            )
            logger.info(
                "쿼터 기록 — 이번 %s units, 오늘(PT %s) 누적 %s units",
                f"{spent:,}",
                usage.date,
                f"{usage.spent:,}",
            )


def _setup_logging(verbose: bool) -> None:
    # Windows 콘솔(cp949)에서 한글·기호가 깨지지 않도록 UTF-8로 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
