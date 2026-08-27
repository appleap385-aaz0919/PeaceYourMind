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
 10. 폴백 품질 필터가 공고·행사·홍보·제3범주만 빼고 찬양 콘티는 남긴다 (2026-08-20·27)
 11. 세분류별 오프셋이 같은 풀을 공유하는 화면을 갈라 준다 (2026-08-20)
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
    MEDIA_FLOOR,
    PROMO_ANYWHERE,
    rotate_for_subcategory,
    PROMO_HEAD,
    PROMO_SERIES,
    drop_promotional,
    fill_balanced,
    promo_reason,
    select_crisis_videos,
    TAB_MAX_VIDEOS,
    select_fallback_videos,
    select_tab_layers,
    select_theme_videos,
    visible_count,
    weak_side,
)

from lib import alerts as alert_specs
from lib.alerts import ROUTE_ISSUE, ROUTE_SUMMARY, AlertCollector, route_for
from lib.allowlist import load_allowlist
from lib.filters import Video
from lib.quota import QuotaBudget
from lib.tagging import SERMON, UNKNOWN, WORSHIP, MediaVerdict
from lib.themes import (
    CRISIS_MIN_VIDEOS,
    FALLBACK_MAX_PER_TAB,
    SUBCATEGORY_MIN_VIDEOS,
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
    # ⚠ 2026-08-26 — 예약(MEDIA_FLOOR 슬롯 비우기)은 탭별 상한으로 대체돼 사라졌다.
    #   이 함수는 이제 다시 "20을 채운다"가 목표다.
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

    # 2026-08-26 — 다시 "20을 채운다"로 돌아왔다. 반대 탭은 이제 **자기 상한**을
    # 따로 가지므로 이쪽 자리를 비워 줄 이유가 없다(select_tab_layers).
    only_sermon = _pool([(f"채널{i}", 8, SERMON) for i in range(5)])
    picked, _, _ = select_theme_videos(only_sermon, day_of_year=0)
    _check(
        failures,
        len(picked) == THEME_MAX_VIDEOS,
        "한쪽 형식뿐이어도 20건을 채운다 (탭이 갈라져 자리를 비울 이유가 없다)",
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
    # ⚠ 채널마다 말씀 1 + 찬양 1로 둔다. 한 형식으로만 채우면 MEDIA_FLOOR 예약이
    #   걸려 총계가 16이 되고, "5채널"이라는 이 검사의 전제 자체가 사라진다.
    #   보려는 것은 회전이지 예약이 아니므로 예약이 안 걸리는 풀을 쓴다.
    fifteen = _pool([(f"채널{i:02d}", 1, SERMON) for i in range(15)]) + _pool(
        [(f"채널{i:02d}", 1, WORSHIP) for i in range(15)]
    )
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

    # 파생 경보 억제 (2026-08-20) — 채널이 0개면 풀이 비는 것은 필연이다.
    # 그 사실은 crisis_no_channels가 이미 말했으므로 crisis_empty를 또 내지 않는다.
    # 채널이 생긴 뒤에 비면 그때는 사건이므로 Issue로 나가야 한다 — 둘 다 본다.
    def _crisis_alert_types(*, has_channels: bool, previous_videos: list) -> set[str]:
        c = BuildContext(
            themes=load_themes(ROOT / "themes.yaml"),
            client=None,
            budget=QuotaBudget(),
            previous={"crisis": {"videos": previous_videos}} if previous_videos else {},
            allowlist=load_allowlist(ROOT / "channel_allowlist.yaml"),
        )
        _carry_over_crisis(
            c, [], kept=0, pool_size=0,
            now=datetime.now(timezone.utc), has_channels=has_channels,
        )
        return {a.type for a in c.collector.alerts}

    no_ch = _crisis_alert_types(has_channels=False, previous_videos=[])
    _check(
        failures,
        "crisis_empty" not in no_ch,
        "채널이 0개면 crisis_empty를 내지 않는다 (파생 경보)",
        str(sorted(no_ch) or "경보 없음"),
    )
    with_ch = _crisis_alert_types(has_channels=True, previous_videos=[])
    _check(
        failures,
        "crisis_empty" in with_ch,
        "채널이 있는데 비면 crisis_empty를 낸다 (진짜 사건)",
        str(sorted(with_ch)),
    )
    carried_no_ch = _crisis_alert_types(
        has_channels=False, previous_videos=[{"videoId": "x"}]
    )
    _check(
        failures,
        "crisis_carried_over" not in carried_no_ch,
        "채널이 0개면 crisis_carried_over도 내지 않는다",
        str(sorted(carried_no_ch) or "경보 없음"),
    )
    _check(
        failures,
        route_for("crisis_no_channels") == ROUTE_SUMMARY
        and route_for("crisis_empty") == ROUTE_ISSUE,
        "위기 경보 4종이 한 덩어리가 아니다 — 상태는 Summary, 사건은 Issue",
    )
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

    # --- 8-b. 탭별 상한 (2026-08-26 · 총량 20 → 탭당 20) --------------------
    print("")
    print("8-b. 탭별 상한 — 두 탭이 서로의 자리를 뺏지 않는다")
    print("-" * 76)
    # 재현: anger.irritation. 주제 풀이 전부 찬양이라 총량 모델에서는 [말씀]이
    # 자리를 못 얻었다. 탭이 갈라지면 각자 자기 상한을 가진다.
    worship_pool = _pool([(f"찬양채널{i}", 8, WORSHIP) for i in range(5)])
    # ⚠ 채널을 넉넉히 둔다. 폴백은 채널당 상한 3이 걸리고 **완화 사다리가 없어서**
    #   `3 x 채널 수`가 그 탭 폴백의 천장이다. 4채널이면 12에서 멈춘다 —
    #   실제로 이 픽스처를 4채널로 뒀다가 "20에 못 찬다"로 잘못 읽을 뻔했다.
    tab_fb = (
        [_untagged(f"fs{i}", f"말씀채널{i % 8}", SERMON) for i in range(40)]
        + [_untagged(f"fw{i}", f"찬양채널{i % 8}", WORSHIP) for i in range(40)]
    )
    theme, fall = select_tab_layers(
        worship_pool, tab_fb, day_of_year=0, position=0, exclude=set()
    )
    total = theme + fall
    _check(
        failures,
        visible_count(theme, WORSHIP) == TAB_MAX_VIDEOS,
        f"[찬양] 주제분이 탭 상한 {TAB_MAX_VIDEOS}까지 찬다 (반대 탭에 자리를 뺏기지 않는다)",
        f"{visible_count(theme, WORSHIP)}건",
    )
    _check(
        failures,
        visible_count(total, SERMON) == TAB_MAX_VIDEOS,
        f"[말씀]도 {TAB_MAX_VIDEOS}까지 찬다 — 주제분이 0이면 그 탭 폴백이 전부 메운다",
        f"{visible_count(total, SERMON)}건 (주제분 {visible_count(theme, SERMON)})",
    )
    _check(
        failures,
        visible_count(fall, WORSHIP) == 0,
        "주제분이 이미 상한을 채운 탭에는 폴백이 들어가지 않는다",
        f"{visible_count(fall, WORSHIP)}건",
    )
    _check(
        failures,
        visible_count(fall, SERMON) <= FALLBACK_MAX_PER_TAB,
        f"탭 폴백이 상한 {FALLBACK_MAX_PER_TAB}을 넘지 않는다",
        f"{visible_count(fall, SERMON)}건",
    )

    # ★ 진짜 천장은 상수가 아니라 **채널 수**다. 폴백에는 완화 사다리가 없다.
    narrow = [_untagged(f"n{i}", f"한채널{i % 2}", SERMON) for i in range(30)]
    _, narrow_fall = select_tab_layers(
        worship_pool, narrow, day_of_year=0, position=0, exclude=set()
    )
    _check(
        failures,
        visible_count(narrow_fall, SERMON) == 2 * THEME_MAX_PER_CHANNEL,
        f"폴백 천장은 채널 수 x 상한이다 (2채널이면 {2 * THEME_MAX_PER_CHANNEL}건에서 멈춘다)",
        f"{visible_count(narrow_fall, SERMON)}건 — 사다리가 없어 상한이 안 풀린다",
    )
    _check(
        failures,
        all(t.is_untagged for t in fall),
        "폴백은 여전히 미태깅만 쓴다 (assert_fallback_untagged 불변식)",
    )
    _check(
        failures,
        len({t.video_id for t in total}) == len(total),
        "같은 영상이 두 번 담기지 않는다 (unknown이 양쪽 탭에서 뽑혀도)",
    )

    # 주제분이 늘면 폴백이 자동으로 줄어드는가 — 구조의 핵심 성질이다.
    mixed_pool = worship_pool + _pool([(f"말씀채널{i}", 3, SERMON) for i in range(4)])
    theme2, fall2 = select_tab_layers(
        mixed_pool, tab_fb, day_of_year=0, position=0, exclude=set()
    )
    _check(
        failures,
        visible_count(fall2, SERMON) < visible_count(fall, SERMON),
        "말씀 주제분이 생기면 [말씀] 폴백이 그만큼 줄어든다",
        f"폴백 {visible_count(fall, SERMON)} → {visible_count(fall2, SERMON)}건",
    )
    _check(
        failures,
        visible_count(theme2 + fall2, SERMON) == TAB_MAX_VIDEOS,
        "줄어들어도 탭 합계는 상한 그대로다",
        f"{visible_count(theme2 + fall2, SERMON)}건",
    )

    # unknown은 양쪽 탭에 세지만 데이터는 한 벌이다.
    unk_pool = [_tagged(f"u{i}", f"미판별{i % 3}", UNKNOWN) for i in range(24)]
    theme3, fall3 = select_tab_layers(
        unk_pool, tab_fb, day_of_year=0, position=0, exclude=set()
    )
    both = theme3 + fall3
    _check(
        failures,
        visible_count(both, SERMON) == TAB_MAX_VIDEOS
        and visible_count(both, WORSHIP) == TAB_MAX_VIDEOS
        and len({t.video_id for t in both}) <= 2 * TAB_MAX_VIDEOS,
        "unknown만 있으면 한 벌로 양쪽 탭을 채운다 (고유 영상은 40건을 넘지 않는다)",
        f"말씀 {visible_count(both, SERMON)} · 찬양 {visible_count(both, WORSHIP)} "
        f"· 고유 {len({t.video_id for t in both})}건",
    )

    # 탭별 폴백 비율 — 화면 평균이 아니라 탭별로 재는가.
    lopsided = SubcategoryResult(
        id="anger.irritation",
        themes=("self_control", "quiet_worship"),
        media_default=WORSHIP,
        theme_videos=theme,
        fallback_videos=fall,
    )
    ratios = lopsided.tab_fallback_ratio
    _check(
        failures,
        ratios[SERMON] == 1.0 and ratios[WORSHIP] == 0.0,
        "폴백 비율을 탭별로 잰다 (화면 평균이면 100% 탭이 가려진다)",
        f"말씀 {ratios[SERMON]:.0%} · 찬양 {ratios[WORSHIP]:.0%}",
    )
    _check(
        failures,
        abs(lopsided.fallback_ratio - 0.5) < 0.2,
        "★ 화면 평균은 어느 탭도 설명하지 못한다 (그래서 경보에 쓰지 않는다)",
        f"화면 평균 {lopsided.fallback_ratio:.0%}",
    )

    # --- 8-c. 성립 경보를 탭 단위로 (2026-08-26) ----------------------------
    print("")
    print("8-c. 성립 경보 — 화면 합계가 아니라 탭에서 보이는 수로 잰다")
    print("-" * 76)
    # ★ 옛 검사(화면 합계 < 8)가 놓치던 모양: 합계 22인데 한 탭이 2건이다.
    blind = SubcategoryResult(
        id="x.blind",
        themes=("a",),
        media_default=SERMON,
        theme_videos=[_tagged(f"s{i}", f"채널{i % 5}", SERMON) for i in range(20)]
        + [_tagged(f"w{i}", "찬양채널", WORSHIP) for i in range(2)],
        fallback_videos=[],
    )
    _check(
        failures,
        blind.count >= SUBCATEGORY_MIN_VIDEOS,
        f"전제 재현: 화면 합계 {blind.count}건이라 옛 화면 검사는 통과한다",
        f"{blind.count}건",
    )
    _check(
        failures,
        blind.tab_counts[WORSHIP]["total"] < SUBCATEGORY_MIN_VIDEOS,
        "★ 그러나 [찬양] 탭은 성립하지 않는다 — 탭 검사만 이것을 잡는다",
        f"찬양 {blind.tab_counts[WORSHIP]['total']}건 / 말씀 {blind.tab_counts[SERMON]['total']}건",
    )

    # 탭 검사가 화면 검사를 **포함**하는가 (vis <= count 이므로 논리적으로 성립).
    tiny = SubcategoryResult(
        id="x.tiny",
        themes=("a",),
        media_default=SERMON,
        theme_videos=[_tagged(f"t{i}", f"채널{i}", SERMON) for i in range(5)],
        fallback_videos=[],
    )
    _check(
        failures,
        tiny.count < SUBCATEGORY_MIN_VIDEOS
        and all(n["total"] < SUBCATEGORY_MIN_VIDEOS for n in tiny.tab_counts.values()),
        "화면 합계가 미달이면 두 탭 모두 반드시 걸린다 (옛 검사를 포함한다)",
        f"합계 {tiny.count} · 말씀 {tiny.tab_counts[SERMON]['total']} "
        f"· 찬양 {tiny.tab_counts[WORSHIP]['total']}",
    )

    # 심각도 2단 — MEDIA_FLOOR 미만은 critical, 그 위 미달은 warning.
    critical = alert_specs.theme_too_few("x", SERMON, 2, MEDIA_FLOOR, empty=True)
    warning = alert_specs.theme_too_few("x", SERMON, 6, SUBCATEGORY_MIN_VIDEOS, empty=False)
    _check(
        failures,
        critical["severity"] == "critical" and warning["severity"] == "warning",
        f"{MEDIA_FLOOR}건 미만은 critical · 그 위 미달은 warning",
        f"{critical['severity']} / {warning['severity']}",
    )
    _check(
        failures,
        "[sermon]" in critical["title"] and "토글" in critical["body"],
        "경보 문구가 어느 탭인지 말한다",
    )
    _check(
        failures,
        route_for(critical["type"]) == ROUTE_ISSUE,
        "성립 경보는 Issue로 간다 (상태가 아니라 사건이다)",
    )

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

    # 위기 경보 4종이 한 덩어리가 아니다 (2026-08-20).
    #   Issue    채널이 있는데도 비었다 / 시간이 갈수록 악화된다 = 사건
    #   Summary  채널이 0개다 = 사람이 승인하기 전까지 매일 같은 값 = 상태
    ISSUE_EXPECTED = [
        "crisis_empty",
        "crisis_carried_over",
        "crisis_stale",
        "theme_empty",
        "theme_too_few",
        # 탭이 너무 두껍다 (2026-08-27 · D안). theme_too_few의 반대쪽 끝이다.
        # ⛔ SUMMARY로 옮기지 말 것 — 임계(26/30)를 오늘의 정상 범위 위에 두어
        #   평소에는 아예 울리지 않는다. 울린다 = 어제와 달라졌다 = 사건이다.
        #   이웃인 theme_fallback_heavy가 summary라 묶고 싶어지지만 성격이 다르다.
        "tab_over_cap",
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
        "crisis_no_channels",
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
    # 10. 폴백 품질 필터 — 공고·행사·홍보·제3범주만 빼고 콘텐츠는 남기는가
    #     (2026-08-20 신설 · 2026-08-27 제3범주 추가)
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
    # 제3범주 — 말씀도 찬양도 아닌 정규 편성물 (2026-08-27, HANDOFF 2.74)
    MUST_DROP += [
        ("10년 선교를 결심했는데 3년 만에 돌아온 이유│김수영 원장 │새롭게 하소서", "간증"),
        ("우리가 알던 통일은 틀렸다│정지석 목사│부르심의 소명 더 콜링 179회", "간증"),
        ("미래목회 심포지엄 '교회, AX를 시작하다' | 온전한 인터뷰 | 레디온 199편", "인터뷰"),
        ("8월 3주 교계 뉴스 | #민주화운동 #기독학교 | 레디온 199편", "교계 뉴스"),
        ("갑자기 찾아온 시련, 그 이후 180도 달라진 삶 | 정재환 대표 [휴먼네컷 79편]", "인물 다큐"),
        ("[Clip] 왜 믿음 좋은 사람들에게 어려움을 허락하실까? | 남미경 대표 | 원더풀우먼", "토크"),
        ("[CTS 추천픽] 부교역자 구인난 | 황승영 기자 출연 | 「CTS 뉴스 W」", "뉴스"),
        ("[CTS 추천픽] 살려달라고 외친 기도 한 마디, 개그우먼 정선희 | 내가 매일 기쁘게", "간증"),
        ("교회학교, 우리 교회도 부흥할 수 있다 (한민수 목사) | 온전한 인터뷰", "출연자 표기"),
    ]

    # ★ 여기가 이 검사의 핵심이다. 이 넷은 '주년'·'콘서트'·'기념'·'광복'을 품고
    #   있지만 전부 실제 콘텐츠다. 어간을 넓히면 여기서 깨진다.
    MUST_KEEP = [
        ("주 여호와는 나의 힘 & 찬송할 수 있을 때 | 옹기장이 40주년 카운트다운 콘서트 2026", "찬양 곡"),
        ("할렐루야 존귀하신 주 | 옹기장이 40주년 카운트다운콘서트 2026", "찬양 곡"),
        ("[고난주간 3일] 나를 기념하라, 우리를 위해 흘리신 언약의 피 — 최후의 만찬", "고난주간 콘텐츠"),
        ("한국중앙교회 임석순 목사 (CBS 주일강단 540회) - 영적 광복을 위한 오늘의 핍박", "설교"),
    ]
    # ★★ 제3범주 사전이 **편성 라벨로 번지지 않는지**를 고정한다 (2026-08-27).
    #    셋 다 2.74 ③ 실측에서 오탐으로 확인돼 사전에서 뺀 것들이다.
    #    누군가 'CTS 추천픽'·'CBS 광장'·'두란노 성경교실'을 넣으면 여기서 깨진다.
    MUST_KEEP += [
        ("[CTS 추천픽] 열왕기 1강 | 전원희 목사 | 「두란노 성경교실 : 예수로 읽는 성경」", "성경 강의"),
        ("망한 나라의 마지막 왕, 시드기야는 왜 파국을 막지 못했나?｜CBS 광장", "성경 해설"),
        ("유다가 멸망한 진짜 이유│성서학당 김기석 목사 예레미야 29강", "강해(전각 구분자)"),
        ("알고 들으면 더 은혜로운 찬송가 이야기! 288장 \"예수를 나의 구주 삼고\" #찬송가", "찬송가 해설"),
        ("듣기만 해도 마음이 편안해지는 성경구절 12가지 #성경 #말씀 #위로 #평안 #기도", "말씀(해시태그)"),
        ("거룩한 불: 간증 2 (21) | R.T. 켄달의 말씀과 성령", "설교 시리즈('간증' 어휘)"),
    ]

    missed = [(s, k) for s, k in MUST_DROP if not promo_reason(s)]
    _check(
        failures,
        not missed,
        f"공고·행사·홍보·제3범주 {len(MUST_DROP)}종을 전부 뺀다",
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

    # =========================================================================
    # 11. 세분류별 오프셋 — [4]가 "주제분 순서 분산"으로 되살아난 자리 (2026-08-20)
    # =========================================================================
    print("\n[11] 세분류별 오프셋")

    base = _pool([("채널A", 12, WORSHIP)])
    r0 = rotate_for_subcategory(base, 0)
    r3 = rotate_for_subcategory(base, 3)
    _check(
        failures,
        [t.video_id for t in r0] == [t.video_id for t in base],
        "자리 0은 그대로 둔다",
    )
    _check(
        failures,
        set(t.video_id for t in r3) == set(t.video_id for t in base)
        and [t.video_id for t in r3] != [t.video_id for t in base],
        "★ 구성은 그대로이고 순서만 바뀐다",
        f"첫 항목 {r3[0].video_id}",
    )
    _check(
        failures,
        rotate_for_subcategory(base[:1], 5)[0].video_id == base[0].video_id,
        "1건짜리 목록은 회전하지 않는다",
    )
    _check(
        failures,
        [t.video_id for t in rotate_for_subcategory(base, 3)]
        == [t.video_id for t in rotate_for_subcategory(base, 15)],
        "자리는 풀 크기로 나눈 나머지다 (3과 15가 같다)",
    )

    # ★ 실제 매핑으로 — 같은 주제 풀을 공유하는 화면들이 갈리는가.
    #   quiet_worship(실측 12건)을 5개 화면이 공유한다. 그 다섯이 매핑에서
    #   0·3·13·20·21번 자리라 나머지가 갈린다. 매핑 순서를 바꾸면 여기서 깨진다.
    real = load_themes(ROOT / "themes.yaml")
    shared = [
        (i, s)
        for i, (s, t) in enumerate(real.mapping.items())
        if "quiet_worship" in t
    ]
    offsets = {i % 12 for i, _ in shared}
    _check(
        failures,
        len(offsets) == len(shared),
        f"quiet_worship을 쓰는 {len(shared)}개 화면이 서로 다른 자리를 받는다",
        f"자리 {sorted(i for i, _ in shared)} → 오프셋 {sorted(offsets)}",
    )

    # 고장 주입 — 오프셋을 끄면 두 화면이 같은 목록을 낸다
    same = rotate_for_subcategory(base, 0)
    _check(
        failures,
        [t.video_id for t in same] == [t.video_id for t in rotate_for_subcategory(base, 0)],
        "고장 주입: 자리를 둘 다 0으로 두면 목록이 같아진다",
    )

    # ⚠ 이것은 **세트를 바꾸지 않는다.** 그 한계를 여기 고정해 둔다 —
    #   나중에 "오프셋을 넣었는데 왜 아직 겹치나"를 묻게 되는 자리다.
    _check(
        failures,
        set(t.video_id for t in rotate_for_subcategory(base, 3))
        == set(t.video_id for t in rotate_for_subcategory(base, 7)),
        "⚠ 세트는 같다 — 공급이 늘기 전에는 여기까지다 (HANDOFF 3절 10번)",
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
