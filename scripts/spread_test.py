#!/usr/bin/env python
"""선정 로직 검증 — 채널 분산 · 형식 균형 · 완화 사다리 · 위기 유지. 네트워크 없음.

    python scripts/spread_test.py

**드라이런으로는 검증되지 않는다.** DryRunClient의 합성 데이터는 채널마다
영상 수가 비슷해서 편중 상황 자체를 만들지 않는다. 여기서는 편중된 풀을
일부러 만들어 억제되는지 본다 (FYM spread_test.py와 같은 이유).

고정해 두는 것
  1. 채널당 상한이 **주제 단위로** 지켜진다 — 형식별로 두 번 순회해도
     한 채널이 3+3=6건을 가져가지 못한다
  2. 형식 균형이 실제로 한쪽을 살린다 — 균형이 없으면 사라졌을 찬양이 남는다
  3. 완화 사다리(3→4→5)와 상한 해제가 정해진 조건에서만 작동한다
  4. 채널 회전이 매일 다른 채널에 두 번째 슬롯을 준다
  5. 위기 풀 12건 미달이면 직전 결과를 유지하고, 그 과정에 API를 쓰지 않는다
  6. 승인이 취소된 채널의 영상이 직전 결과를 타고 살아남지 않는다
  7. 무결성 단언(상호 배타 · media_type)이 실제로 배포를 막는다
  8. 폴백이 미태깅·기본 형식·상한·채널 분산을 전부 지킨다
  9. 경보가 Issue/Summary로 올바르게 갈린다 (2026-08-19 정책)
 10. 폴백 품질 필터가 공고·행사·홍보만 빼고 찬양 콘티는 남긴다 (2026-08-20)
"""

from __future__ import annotations

import inspect
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timezone

from build_videos import (
    IntegrityError,
    build_subcategories,
    assert_disjoint,
    assert_fallback_untagged,
    assert_media_type_filled,
)
from lib.collect import enforce_allowlist
from lib.crisis import _carry_over_crisis
from lib.results import (
    BuildContext,
    CrisisResult,
    SubcategoryResult,
    TaggedVideo,
    ThemeResult,
)
from lib.selection import (
    PROMO_ANYWHERE,
    PROMO_HEAD,
    PROMO_SERIES,
    drop_promotional,
    fill_balanced,
    promo_reason,
    select_crisis_videos,
    select_fallback_videos,
    select_theme_videos,
)

from lib import alerts as alert_specs
from lib.alerts import ROUTE_ISSUE, ROUTE_SUMMARY, AlertCollector, route_for
from lib.allowlist import load_allowlist
from lib.filters import Video
from lib.quota import QuotaBudget
from lib.tagging import SERMON, UNKNOWN, WORSHIP, MediaVerdict
from lib.themes import (
    CRISIS_MIN_VIDEOS,
    THEME_MAX_PER_CHANNEL,
    THEME_MAX_VIDEOS,
    load_themes,
)

ROOT = Path(__file__).resolve().parents[1]
EXIT_OK, EXIT_FAIL = 0, 1


def _tagged(video_id: str, channel: str, media_type: str) -> TaggedVideo:
    video = Video(
        video_id=video_id,
        title=f"{channel} 영상 {video_id}",
        channel=channel,
        channel_id=f"UC_{channel}",
        published_at="2026-08-18T00:00:00Z",
        duration="PT20M",
        duration_seconds=1200,
        description="",
        tags=(),
        comments_disabled=False,
    )
    return TaggedVideo(
        video=video, themes=("comfort",), hits=("위로",), media=MediaVerdict(media_type, "title")
    )


def _tagged_untagged(
    video_id: str, channel: str, media_type: str, title: str
) -> TaggedVideo:
    """미태깅 영상 하나 — 폴백 후보다. 제목이 검사 대상이라 직접 받는다."""
    base = _tagged(video_id, channel, media_type)
    return replace(
        base, video=replace(base.video, title=title), themes=(), hits=()
    )


def _pool(spec: list[tuple[str, int, str]]) -> list[TaggedVideo]:
    """(채널, 건수, 형식) 목록을 그 순서 그대로 후보 풀로 만든다.

    앞에 적은 채널이 목록 앞쪽(=최신)이다. 편중은 한 채널이 앞을 쓸어담아
    생기므로 그 형태를 그대로 만든다.
    """
    pool: list[TaggedVideo] = []
    for channel, count, media_type in spec:
        for i in range(count):
            pool.append(_tagged(f"{channel}-{media_type}-{i}", channel, media_type))
    return pool


def _spread(picked: list[TaggedVideo]) -> Counter:
    return Counter(t.video.channel for t in picked)


def _media(picked: list[TaggedVideo]) -> Counter:
    return Counter(t.media.media_type for t in picked)


def _check(failures: list[str], ok: bool, label: str, detail: str = "") -> None:
    print(f"{'   ' if ok else 'X  '}{label}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    failures: list[str] = []
    cap0 = THEME_MAX_PER_CHANNEL
    print(f"주제당 상한 {THEME_MAX_VIDEOS}건 / 채널당 상한 사다리 {cap0}→{cap0+1}→{cap0+2}")

    # --- 1. 채널당 상한이 주제 단위로 지켜지는가 -----------------------------
    print("\n1. 채널 편중 억제 — 형식별로 두 번 순회해도 상한은 한 번만 센다")
    print("-" * 76)
    hog = _pool([("독식채널", 15, SERMON), ("독식채널", 15, WORSHIP)])
    others = _pool([(f"채널{i}", 2, SERMON) for i in range(10)])
    pool = hog + others

    naive = pool[:THEME_MAX_VIDEOS]
    _check(
        failures,
        _spread(naive)["독식채널"] == THEME_MAX_VIDEOS,
        "상한이 없으면 한 채널이 20건을 전부 가져간다 (전제 재현)",
        f"{_spread(naive)['독식채널']}건",
    )

    picked, cap, unlocked = select_theme_videos(pool, day_of_year=0)
    spread = _spread(picked)
    _check(
        failures,
        spread["독식채널"] <= cap0,
        f"독식 채널이 상한 {cap0} 이하로 억제된다",
        f"{spread['독식채널']}건 (상한 {cap})",
    )
    _check(
        failures,
        len(picked) == THEME_MAX_VIDEOS and not unlocked,
        "20건을 채우면서 상한을 풀지 않는다",
        f"{len(picked)}건",
    )

    # --- 2. 형식 균형 --------------------------------------------------------
    print("\n2. 형식 균형 — 소수 형식이 20슬롯 밖으로 밀리지 않는가")
    print("-" * 76)
    # 말씀이 목록 앞을 전부 차지하고 찬양이 뒤로 밀린 풀.
    lopsided = _pool([(f"말씀채널{i}", 5, SERMON) for i in range(6)]) + _pool(
        [(f"찬양채널{i}", 3, WORSHIP) for i in range(2)]
    )
    naive = lopsided[:THEME_MAX_VIDEOS]
    _check(
        failures,
        _media(naive)[WORSHIP] == 0,
        "균형이 없으면 찬양이 0건이 된다 (전제 재현)",
        f"말씀 {_media(naive)[SERMON]} / 찬양 {_media(naive)[WORSHIP]}",
    )
    picked, _, _ = select_theme_videos(lopsided, day_of_year=0)
    media = _media(picked)
    _check(
        failures,
        media[WORSHIP] == 6,
        "풀에 있던 찬양 6건이 전부 살아남는다",
        f"말씀 {media[SERMON]} / 찬양 {media[WORSHIP]}",
    )
    _check(failures, len(picked) == THEME_MAX_VIDEOS, "그러면서 20건을 채운다", f"{len(picked)}건")

    balanced = _pool([(f"채널{i}", 6, SERMON) for i in range(5)]) + _pool(
        [(f"채널{i}", 6, WORSHIP) for i in range(5)]
    )
    picked, _, _ = select_theme_videos(balanced, day_of_year=0)
    media = _media(picked)
    _check(
        failures,
        media[SERMON] == 10 and media[WORSHIP] == 10,
        "양쪽이 넉넉하면 10:10으로 나눈다",
        f"말씀 {media[SERMON]} / 찬양 {media[WORSHIP]}",
    )

    only_sermon = _pool([(f"채널{i}", 8, SERMON) for i in range(5)])
    picked, _, _ = select_theme_videos(only_sermon, day_of_year=0)
    _check(
        failures,
        len(picked) == THEME_MAX_VIDEOS,
        "한쪽 형식뿐이어도 20건을 채운다 (균형이 상한이 되지 않는다)",
        f"{len(picked)}건",
    )

    unknown_pool = _pool([(f"채널{i}", 8, UNKNOWN) for i in range(5)])
    picked, _, _ = select_theme_videos(unknown_pool, day_of_year=0)
    _check(
        failures,
        len(picked) == THEME_MAX_VIDEOS,
        "미판별만 있어도 20건을 채운다 (양쪽 토글에 노출되므로 버리지 않는다)",
        f"{len(picked)}건",
    )

    # --- 3. 완화 사다리와 상한 해제 -----------------------------------------
    print("\n3. 완화 사다리 · 상한 해제")
    print("-" * 76)
    five_channels = _pool([(f"채널{i}", 10, SERMON) for i in range(5)])
    picked, cap, unlocked = select_theme_videos(five_channels, day_of_year=0)
    _check(
        failures,
        cap == cap0 + 1 and len(picked) == THEME_MAX_VIDEOS and not unlocked,
        f"5채널이면 상한 {cap0}로 15건뿐 → {cap0+1}로 올려 20건",
        f"상한 {cap}, {len(picked)}건",
    )

    single = _pool([("단일채널", 30, SERMON)])
    picked, cap, unlocked = select_theme_videos(single, day_of_year=0)
    _check(
        failures,
        unlocked and len(picked) == THEME_MAX_VIDEOS,
        "한 채널뿐이고 하한도 못 채우면 상한을 해제한다",
        f"{len(picked)}건, 해제 {unlocked}",
    )

    shallow = _pool([("단일채널", 4, SERMON)])
    picked, cap, unlocked = select_theme_videos(shallow, day_of_year=0)
    _check(
        failures,
        not unlocked,
        "풀 자체가 얕으면 해제하지 않는다 (해제해도 늘지 않는다)",
        f"{len(picked)}건, 해제 {unlocked}",
    )

    # --- 4. 채널 회전 --------------------------------------------------------
    print("\n4. 채널 회전 — 두 번째 슬롯이 매일 다른 채널로 간다")
    print("-" * 76)
    # 15채널 × 2건. 상한 3이면 1바퀴(15) + 2바퀴 앞쪽 5개 = 20건이라
    # "두 번 뽑히는 채널 5개"가 날마다 달라져야 한다.
    fifteen = _pool([(f"채널{i:02d}", 2, SERMON) for i in range(15)])
    day0 = {c for c, n in _spread(fill_balanced(fifteen, cap0, 0)).items() if n == 2}
    day5 = {c for c, n in _spread(fill_balanced(fifteen, cap0, 5)).items() if n == 2}
    _check(failures, len(day0) == 5, "하루에 5채널만 2건을 갖는다", str(sorted(day0)))
    _check(failures, day0 != day5, "day가 바뀌면 그 5채널이 달라진다", str(sorted(day5)))
    union = day0 | day5
    _check(failures, len(union) > 5, "여러 날에 걸쳐 더 많은 채널이 두 번째 슬롯을 받는다",
           f"{len(union)}채널")

    # --- 5. 위기 풀 ----------------------------------------------------------
    print("\n5. 위기 풀 — 미달 시 직전 결과 유지 (API 소모 0)")
    print("-" * 76)
    crisis_pool = _pool([(f"위기채널{i}", 5, SERMON) for i in range(6)])
    picked, cap, unlocked = select_crisis_videos(crisis_pool, day_of_year=0)
    _check(
        failures,
        len(picked) == 20 and max(_spread(picked).values()) <= cap0 + 1,
        "위기 풀도 채널 분산으로 20건을 채운다",
        f"{len(picked)}건, 최다 {max(_spread(picked).values())}건, 상한 {cap}",
    )

    budget = QuotaBudget()
    previous_ids = [f"이전{i}" for i in range(14)]
    survivors = [_tagged(vid, "위기채널0", SERMON) for vid in previous_ids[:12]]
    ctx = BuildContext(
        themes=load_themes(ROOT / "themes.yaml"),
        client=None,  # 유지 경로는 API를 부르지 않는다 — 부르면 여기서 터진다
        budget=budget,
        previous={
            "crisis": {
                "updated_at": "2026-08-17T00:00:00Z",
                "source": "allowlist_crisis_eligible",
                "videos": [{"videoId": vid} for vid in previous_ids],
            }
        },
        allowlist=load_allowlist(ROOT / "channel_allowlist.yaml"),
    )
    result = _carry_over_crisis(ctx, survivors, kept=3, pool_size=3, now=datetime.now(timezone.utc))
    _check(
        failures,
        result.carried_over and len(result.videos) == 12,
        f"{CRISIS_MIN_VIDEOS}건 미달이면 직전 결과 중 생존분을 유지한다",
        f"{len(result.videos)}건",
    )
    _check(
        failures,
        result.updated_at == "2026-08-17T00:00:00Z",
        "updated_at을 갱신하지 않는다 (신선도 경보가 이어져야 한다)",
        result.updated_at,
    )
    _check(failures, budget.spent == 0, "유지 경로에서 쿼터를 쓰지 않는다", f"{budget.spent} units")
    types = {a.type for a in ctx.collector.alerts}
    _check(failures, "crisis_carried_over" in types, "경보를 남긴다", str(sorted(types)))

    empty_ctx = BuildContext(
        themes=ctx.themes,
        client=None,
        budget=QuotaBudget(),
        previous={},
        allowlist=ctx.allowlist,
    )
    empty = _carry_over_crisis(empty_ctx, [], kept=0, pool_size=0, now=datetime.now(timezone.utc))
    _check(
        failures,
        empty.videos == [] and "crisis_empty" in {a.type for a in empty_ctx.collector.alerts},
        "유지할 직전 결과도 없으면 0건 + crisis_empty 경보",
    )

    # --- 6. 승인 목록 밖 채널 배제 ------------------------------------------
    print("\n6. 승인이 취소된 채널의 영상은 직전 결과를 타고 살아남지 못한다")
    print("-" * 76)
    approved = ctx.allowlist.channels[0]
    # 하나는 실제 승인 채널 ID로, 하나는 목록에 없는 ID로 둔다.
    # 둘 다 필터를 통과한 상태 — 여기서 갈리는 것은 승인 여부뿐이다.
    survivor = replace(
        _tagged("살아남을영상", approved.channel_name, SERMON).video,
        channel_id=approved.channel_id,
    )
    removed = _tagged("사라질영상", "승인취소된채널", SERMON).video
    survivors, dropped = enforce_allowlist(ctx, [survivor, removed])
    _check(
        failures,
        dropped == 1 and [v.video_id for v in survivors] == ["살아남을영상"],
        "allowlist에서 빠진 채널의 영상이 제외된다",
        f"생존 {len(survivors)}건 / 제외 {dropped}건",
    )

    # --- 7. 배포 전 무결성 단언 ---------------------------------------------
    print("\n7. 무결성 단언 — 고장을 주입해 실제로 배포를 막는지 본다")
    print("-" * 76)
    shared = _tagged("겹치는영상", "채널A", SERMON)
    theme = ThemeResult(
        id="comfort",
        label="위로",
        picked=[shared],
        pool_size=1,
        max_per_channel=cap0,
        per_channel_unlocked=False,
    )
    crisis = CrisisResult(
        videos=[shared.to_json()],
        updated_at="2026-08-19T00:00:00Z",
        source="test",
        carried_over=False,
    )
    try:
        assert_disjoint([theme], crisis)
        caught = ""
    except IntegrityError as exc:
        caught = str(exc)
    _check(failures, "겹치는영상" in caught, "crisis와 주제가 같은 영상을 가지면 배포를 막는다",
           caught.splitlines()[0][:60] if caught else "예외 없음")

    broken = ThemeResult(
        id="comfort",
        label="위로",
        picked=[
            TaggedVideo(
                video=shared.video,
                themes=("comfort",),
                hits=(),
                media=MediaVerdict("podcast", "title"),  # 사전에 없는 형식
            )
        ],
        pool_size=1,
        max_per_channel=cap0,
        per_channel_unlocked=False,
    )
    try:
        assert_media_type_filled([broken])
        caught = ""
    except IntegrityError as exc:
        caught = str(exc)
    _check(
        failures,
        "media_type" in caught,
        "media_type이 sermon/worship/unknown이 아니면 배포를 막는다",
        caught.splitlines()[0][:60] if caught else "예외 없음",
    )
    assert_media_type_filled([theme])  # 정상 경로는 통과해야 한다
    _check(failures, True, "정상 목록은 그대로 통과한다")

    # --- 8. 폴백 (주제 태깅 실패분으로 화면 채우기) --------------------------
    print("\n8. 폴백 — 미태깅 영상만, 기본 형식만, 상한 안에서")
    print("-" * 76)

    def _untagged(video_id, channel, media_type):
        t = _tagged(video_id, channel, media_type)
        return TaggedVideo(video=t.video, themes=(), hits=(), media=t.media)

    fb_pool = (
        [_untagged(f"w{c}-{i}", f"찬양채널{c}", WORSHIP) for c in range(6) for i in range(4)]
        + [_untagged(f"s{i}", "말씀채널", SERMON) for i in range(10)]
        + [_untagged(f"u{i}", "미판별채널", UNKNOWN) for i in range(4)]
    )
    picked = select_fallback_videos(fb_pool, WORSHIP, 12, day_of_year=0)
    _check(failures, len(picked) == 12, "요청한 만큼만 채운다", f"{len(picked)}건")
    _check(
        failures,
        all(t.media.media_type in (WORSHIP, UNKNOWN) for t in picked),
        "기본 형식과 unknown만 들어간다 (반대 형식은 제외)",
        str(sorted({t.media.media_type for t in picked})),
    )
    _check(
        failures,
        max(_spread(picked).values()) <= cap0,
        f"폴백에도 채널당 상한 {cap0}이 걸린다",
        f"최다 {max(_spread(picked).values())}건",
    )
    _check(
        failures,
        all(t.is_untagged for t in picked),
        "태깅된 영상은 절대 폴백으로 들어가지 않는다",
    )

    tagged_in_pool = fb_pool + [_tagged("태깅됨", "찬양채널0", WORSHIP)]
    picked2 = select_fallback_videos(tagged_in_pool, WORSHIP, 12, day_of_year=0)
    _check(
        failures,
        "태깅됨" not in {t.video_id for t in picked2},
        "풀에 태깅분이 섞여 있어도 걸러낸다",
    )

    excluded = select_fallback_videos(
        fb_pool, WORSHIP, 12, day_of_year=0, exclude={t.video_id for t in picked}
    )
    _check(
        failures,
        not ({t.video_id for t in excluded} & {t.video_id for t in picked}),
        "exclude에 넣은 영상은 다시 나오지 않는다 (위기 풀·주제분 중복 방지)",
    )
    _check(failures, not select_fallback_videos(fb_pool, WORSHIP, 0, 0), "need가 0이면 빈 목록")

    sub = SubcategoryResult(
        id="anger.irritation",
        themes=("self_control", "quiet_worship"),
        media_default=WORSHIP,
        theme_videos=[_tagged("주제1", "채널A", WORSHIP)],
        fallback_videos=picked[:11],
    )
    _check(failures, sub.count == 12, "주제분 + 폴백이 화면 건수다", f"{sub.count}건")
    _check(
        failures,
        abs(sub.fallback_ratio - 11 / 12) < 1e-9,
        "폴백 비율이 경보 판정 기준이다",
        f"{sub.fallback_ratio:.0%}",
    )
    videos = sub.videos
    _check(
        failures,
        videos[0]["source"] == "theme" and videos[-1]["source"] == "fallback",
        "출력 순서는 주제분 먼저, 폴백 뒤 (근거의 강도 순)",
    )
    _check(
        failures,
        all("source" in v for v in videos),
        "모든 영상에 source가 붙는다 — 앱이 두 층을 섞지 않기 위한 근거다",
    )

    try:
        assert_fallback_untagged(
            [
                SubcategoryResult(
                    id="x",
                    themes=("a",),
                    media_default=WORSHIP,
                    theme_videos=[],
                    fallback_videos=[_tagged("태깅된영상", "채널A", WORSHIP)],
                )
            ]
        )
        caught = ""
    except IntegrityError as exc:
        caught = str(exc)
    _check(
        failures,
        "태깅된영상" in caught,
        "폴백에 태깅분이 섞이면 배포를 막는다",
        caught.splitlines()[0][:56] if caught else "예외 없음",
    )

    # --- 9. 경보 라우팅 (2026-08-19 정책) ------------------------------------
    print("\n9. 경보 라우팅 — 사건은 Issue로, 상태는 Summary로")
    print("-" * 76)

    ISSUE_EXPECTED = [
        "crisis_empty",
        "crisis_carried_over",
        "crisis_stale",
        "crisis_no_channels",
        "theme_empty",
        "theme_too_few",
        "channel_zero_yield",
        "channel_dead",
        "allowlist_undersized",
        "allowlist_empty",
        "allowlist_placeholders",
        "channel_review_overdue",
    ]
    SUMMARY_EXPECTED = [
        "theme_low_yield",
        "media_type_gap",
        "theme_fallback_heavy",
        "untagged_high",
    ]
    for alert_type in ISSUE_EXPECTED:
        _check(
            failures,
            route_for(alert_type) == ROUTE_ISSUE,
            f"Issue로 간다: {alert_type}",
            route_for(alert_type),
        )
    for alert_type in SUMMARY_EXPECTED:
        _check(
            failures,
            route_for(alert_type) == ROUTE_SUMMARY,
            f"Summary에만 남는다: {alert_type}",
            route_for(alert_type),
        )

    # 경보 정의와 라우팅표가 어긋나면 조용히 Issue가 새거나 사라진다.
    # alerts.py에 있는 모든 생성기가 둘 중 한쪽에 반드시 분류되는지 본다.
    generators = [
        name
        for name in dir(alert_specs)
        if not name.startswith("_")
        and inspect.isfunction(getattr(alert_specs, name))
        and getattr(alert_specs, name).__module__ == alert_specs.__name__
        and name != "route_for"
    ]
    unclassified = [
        g for g in generators if g not in ISSUE_EXPECTED and g not in SUMMARY_EXPECTED
    ]
    _check(
        failures,
        not unclassified,
        "모든 경보 생성기가 라우팅표에 있다",
        ", ".join(unclassified) or "-",
    )

    collector = AlertCollector()
    collector.add(**alert_specs.crisis_empty())
    collector.add(**alert_specs.theme_low_yield("comfort", 3, 15))
    _check(
        failures,
        len(collector.issues) == 1 and len(collector.diagnostics) == 1,
        "수집기가 두 갈래를 나눠 준다",
        f"issue {len(collector.issues)} / summary {len(collector.diagnostics)}",
    )
    _check(
        failures,
        all("route" in a.to_json() for a in collector.alerts),
        "리포트 JSON에 route가 실린다 (워크플로가 이 값으로 가른다)",
    )

    # =========================================================================
    # 10. 폴백 품질 필터 — 공고·행사·홍보만 빼고 콘텐츠는 남기는가 (2026-08-20)
    # =========================================================================
    # 실측 제목을 그대로 고정한다. 사전을 손볼 때 여기서 먼저 깨져야 한다.
    print("\n[10] 폴백 품질 필터")

    MUST_DROP = [
        ("광주극동방송 어린이합창단 신입단원 모집 '2026전도대회 호남권연합찬양'", "모집 공고"),
        ("옹터뷰(28기 신입단원모집 특별인터뷰)", "모집 홍보"),
        ("📍호남권 전도를 통해 이어진 구원의 순간들 | 전도대회 하이라이트", "홍보"),
        ("구독자2만명돌파기념!! 옹기장이가 쏜다 생방송", "채널 이벤트"),
        ("✔극동방송 70주년 기념 호남권 전도대회 | FEBC 호남권 전도대회 2부 LIVE", "행사 중계"),
        ("[생방송] 2026 나라사랑축제 (익산)", "행사 중계"),
        ("[LIVE] 2025 극동방송 총회 및 성탄 공개방송", "행사 중계"),
        ("옹기장이 28기 향상음악회", "행사"),
        (
            "[CTS 추천픽] 독립유공자 26인 집안, 목회자 사모가 된 자녀들"
            " | 🇰🇷 광복 81주년,믿음으로 지켜낸 대한민국의 독립 이야기",
            "기념일 시리즈",
        ),
    ]
    # ★ 여기가 이 검사의 핵심이다. 이 넷은 '주년'·'콘서트'·'기념'·'광복'을 품고
    #   있지만 전부 실제 콘텐츠다. 어간을 넓히면 여기서 깨진다.
    MUST_KEEP = [
        ("주 여호와는 나의 힘 & 찬송할 수 있을 때 | 옹기장이 40주년 카운트다운 콘서트 2026", "찬양 곡"),
        ("할렐루야 존귀하신 주 | 옹기장이 40주년 카운트다운콘서트 2026", "찬양 곡"),
        ("[고난주간 3일] 나를 기념하라, 우리를 위해 흘리신 언약의 피 — 최후의 만찬", "고난주간 콘텐츠"),
        ("한국중앙교회 임석순 목사 (CBS 주일강단 540회) - 영적 광복을 위한 오늘의 핍박", "설교"),
    ]

    missed = [(s, k) for s, k in MUST_DROP if not promo_reason(s)]
    _check(
        failures,
        not missed,
        f"공고·행사·홍보 {len(MUST_DROP)}종을 전부 뺀다",
        "; ".join(k for _, k in missed) or "-",
    )
    lost = [(s, k) for s, k in MUST_KEEP if promo_reason(s)]
    _check(
        failures,
        not lost,
        f"행사장에서 찍힌 콘텐츠 {len(MUST_KEEP)}종은 남긴다",
        "; ".join(f"{k}: {promo_reason(s)}" for s, k in lost) or "-",
    )

    # 머리/트레일러 구분이 실제로 작동하는가 — 같은 어휘, 다른 자리
    _check(
        failures,
        promo_reason("극동방송 70주년 기념 대회 | FEBC LIVE") is not None
        and promo_reason("할렐루야 | 옹기장이 40주년 콘서트") is None,
        "같은 '주년'이라도 머리에 있을 때만 뺀다",
    )

    # 폴백 전용이다 — 주제분에는 걸지 않는다는 것을 호출 구조로 고정한다
    src = inspect.getsource(build_subcategories)
    body = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    _check(
        failures,
        body.count("drop_promotional") == 1 and "is_untagged" in body,
        "미태깅(=폴백 후보)에만 적용한다",
    )

    # 되메우지 않는다 — 풀을 줄이면 결과도 줄어야 한다
    promo_pool = [
        _tagged_untagged(f"promo-{i}", "채널A", WORSHIP, "어린이합창단 신입단원 모집 안내")
        for i in range(10)
    ]
    clean_pool = [
        _tagged_untagged(f"ok-{i}", "채널A", WORSHIP, f"주 은혜라 {i}") for i in range(3)
    ]
    kept, dropped = drop_promotional(promo_pool + clean_pool)
    picked = select_fallback_videos(kept, WORSHIP, 12, day_of_year=1)
    _check(
        failures,
        len(dropped) == 10 and len(picked) == 3,
        "뺀 자리를 되메우지 않는다 — 후보가 없으면 그만큼 적게 나간다",
        f"제외 {len(dropped)} · 확보 {len(picked)}/12",
    )

    # 고장 주입 — 어휘를 넓히면 찬양 콘티가 걸리는 것을 실제로 확인한다
    import lib.selection as _sel

    saved = _sel.PROMO_ANYWHERE
    try:
        _sel.PROMO_ANYWHERE = saved + ("주년",)
        broke = [s for s, _ in MUST_KEEP if _sel.promo_reason(s)]
        _check(
            failures,
            len(broke) >= 2,
            "고장 주입: '주년'을 위치 무관으로 옮기면 찬양 콘티가 걸린다",
            f"{len(broke)}건 걸림",
        )
    finally:
        _sel.PROMO_ANYWHERE = saved
    _check(
        failures,
        not [s for s, _ in MUST_KEEP if promo_reason(s)],
        "고장을 되돌리면 다시 통과한다",
    )

    print("\n" + "=" * 76)
    if failures:
        print(f"실패 {len(failures)}건:")
        for f in failures:
            print(f"  - {f}")
        return EXIT_FAIL
    print("전부 통과")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
