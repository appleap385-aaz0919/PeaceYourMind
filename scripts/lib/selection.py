"""선정 — 채널 분산과 형식 균형으로 주제별 목록을 고른다. API를 부르지 않는다.

두 가지를 동시에 지켜야 한다.
    채널 분산   한 채널이 목록을 독식하지 못하게 (FYM 승계, 상한 3 + 라운드로빈)
    형식 균형   말씀/찬양 한쪽이 0건이 되지 않게 (PYM 고유, PLAN.md 3.4)

둘은 서로 당긴다 — 형식별로 나눠 뽑으면 채널 상한이 두 번 적용될 위험이 있고,
채널만 보면 형식이 한쪽으로 쏠린다. 그래서 상한 계수(used)를 형식 순회 사이에
공유하고, 순회 순서를 "적게 뽑힌 채널 먼저"로 둔다.

검증은 scripts/spread_test.py가 편중된 풀을 만들어 한다 — 드라이런의 합성
데이터는 채널마다 고르게 분포해 편중 상황 자체를 만들지 못한다.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

from lib.results import TaggedVideo
from lib.tagging import SERMON, UNKNOWN, WORSHIP
from lib.themes import (
    CRISIS_MAX_VIDEOS,
    CRISIS_MIN_VIDEOS,
    PER_CHANNEL_STEPS,
    THEME_MAX_PER_CHANNEL,
    THEME_MAX_VIDEOS,
    THEME_MIN_VIDEOS,
)

logger = logging.getLogger("build_videos")

# 한 주제의 20슬롯을 형식별로 몇 건까지 먼저 확보할 것인가 (나머지는 남는 쪽이 채운다).
MEDIA_BALANCE_TARGET = THEME_MAX_VIDEOS // 2


def per_channel_ladder() -> tuple[int, ...]:
    """채널당 상한 사다리 (3 → 4 → 5). 목표를 못 채울 때만 한 단계씩 올린다."""
    return tuple(THEME_MAX_PER_CHANNEL + i for i in range(PER_CHANNEL_STEPS))


def _channel_order(videos: Sequence[TaggedVideo], day_of_year: int) -> list[str]:
    """순회할 채널 순서 — 등장 순서(=최신순)를 하루 단위로 회전시킨다.

    **PYM에서는 회전이 옳다.** FYM 일반 카테고리에서 회전을 뺐던 이유는
    거기서 채널 목록이 '검색 관련성 순위로 늘어선 50~80개'였고 슬롯이 20개뿐이라,
    회전이 "관련성 상위 채널을 통째로 건너뛰기"가 됐기 때문이다(_rotate 주석).

    PYM의 채널 목록은 그것과 다르다.
      · 사람이 승인한 15개다. 관련성 순위가 아니라 전원이 동등한 자격을 갖는다.
      · 슬롯(20) > 채널(15)이라 회전은 "전원이 돌아가며 들어온다"가 된다.
      · 그런데 상한 3 × 15채널 = 45 > 20이라 **뒤쪽 채널은 2번째 바퀴에 못 든다.**
        순서가 고정이면 같은 채널이 매일 같은 자리에서 밀린다.
    즉 FYM 위기 카테고리와 같은 상황이고, 거기서 회전이 하던 일을 여기서 한다.
    """
    seen: list[str] = []
    for tagged in videos:
        if tagged.video.channel_id not in seen:
            seen.append(tagged.video.channel_id)
    if not seen:
        return []
    start = day_of_year % len(seen)
    return seen[start:] + seen[:start]


def _round_robin(
    videos: Sequence[TaggedVideo],
    cap: int,
    limit: int,
    order: Sequence[str],
    used: Counter[str],
) -> list[TaggedVideo]:
    """채널을 한 바퀴씩 돌며 1건씩, 채널당 cap건까지 limit건이 찰 때까지 채운다.

    used는 **호출 사이에 공유된다.** 형식 균형 때문에 이 함수를 한 주제에서
    여러 번 부르는데, 상한이 호출마다 초기화되면 한 채널이 말씀 3건 + 찬양 3건으로
    6건을 가져간다. 상한은 주제 단위여야 한다.

    매 바퀴 **지금까지 적게 뽑힌 채널부터** 돈다(동률은 회전 순서). 이 정렬이
    없으면 앞선 호출에서 이미 1건씩 받은 채널이 다음 호출에서도 앞자리를 지켜,
    뒤쪽 채널이 한 건도 못 들어오는 일이 생긴다.
      실측(15채널 × 2건, 말씀만 있는 풀): 정렬 없이는 앞 10채널이 2건씩 20슬롯을
      다 가져가고 **뒤 5채널이 0건**이었다. 정렬을 넣으면 5채널 2건 + 10채널 1건이 된다.
      승인 채널 전원이 목록에 들어오게 하는 것이 회전을 넣은 이유이므로,
      한 호출 안에서만 공평한 것으로는 부족하다.
    """
    by_channel: dict[str, list[TaggedVideo]] = {}
    for tagged in videos:
        by_channel.setdefault(tagged.video.channel_id, []).append(tagged)

    position = {channel_id: i for i, channel_id in enumerate(order)}
    picked: list[TaggedVideo] = []
    progressed = True
    while len(picked) < limit and progressed:
        progressed = False
        for channel_id in sorted(order, key=lambda c: (used[c], position[c])):
            if len(picked) >= limit:
                break
            if used[channel_id] >= cap:
                continue
            queue = by_channel.get(channel_id)
            if not queue:
                continue
            picked.append(queue.pop(0))
            used[channel_id] += 1
            progressed = True
    return picked


def fill_balanced(
    pool: Sequence[TaggedVideo], cap: int, day_of_year: int
) -> list[TaggedVideo]:
    """한 주제의 슬롯을 형식별로 나눠 채운다 (말씀 10 / 찬양 10 → 남는 쪽이 나머지).

    [왜 균형을 맞추는가]
      앱은 영상 목록 위의 [말씀]/[찬양] 토글로 이 목록을 거른다(PLAN.md 3.4).
      한 주제의 20건이 전부 말씀이면 찬양 토글은 빈 화면이 된다. 풀에 찬양이
      있었는데 상한·순서 때문에 20건 밖으로 밀린 것이라면 그건 데이터가 아니라
      선정의 결함이다.

      unknown은 별도 몫을 두지 않는다. 양쪽 토글 모두에 노출되므로 어느 쪽의
      빈 화면도 만들지 않기 때문이다. 남은 슬롯을 채우는 3차 순회에서 들어온다.

    [순서]
      선정은 라운드로빈(채널 분산)으로 하고, **출력 순서는 최신순으로 되돌린다.**
      선정 순서 그대로 내보내면 목록 앞쪽에 말씀이 뭉치는데, 토글로 걸러 보는
      화면에서는 그 뭉침이 의미가 없고 최신순이 사용자에게 읽히는 순서다.
    """
    order = _channel_order(pool, day_of_year)
    used: Counter[str] = Counter()

    picked: list[TaggedVideo] = []
    for media_type in (SERMON, WORSHIP):
        group = [t for t in pool if t.media.media_type == media_type]
        picked.extend(_round_robin(group, cap, MEDIA_BALANCE_TARGET, order, used))

    taken = {t.video_id for t in picked}
    rest = [t for t in pool if t.video_id not in taken]
    picked.extend(_round_robin(rest, cap, THEME_MAX_VIDEOS - len(picked), order, used))

    rank = {t.video_id: i for i, t in enumerate(pool)}
    picked.sort(key=lambda t: rank.get(t.video_id, len(rank)))
    return picked


def select_theme_videos(
    pool: Sequence[TaggedVideo], day_of_year: int
) -> tuple[list[TaggedVideo], int, bool]:
    """주제 하나의 최종 목록을 고른다.

    완화 순서 (FYM 승계)
      1. 기본 상한(3)으로 20건이 차면 그대로 쓴다 — 분산이 개수보다 우선이다.
      2. 못 채우면 4, 5로 한 단계씩 올린다.
      3. 마지막 단계로도 하한(15)에 못 미치는데 **상한만 풀면 채울 수 있는**
         경우에만 상한을 해제한다. 풀 자체가 얕아서 미달인 경우에는 해제해도
         늘지 않으므로 하지 않는다 — min(하한, 확보 가능량)과 비교하는 이유다.

    반환: (선정 목록, 실제 적용된 상한, 상한 해제 여부)
    """
    ladder = per_channel_ladder()
    for cap in ladder:
        picked = fill_balanced(pool, cap, day_of_year)
        if len(picked) >= THEME_MAX_VIDEOS:
            return picked, cap, False

    last = ladder[-1]
    picked = fill_balanced(pool, last, day_of_year)
    reachable = min(THEME_MIN_VIDEOS, len(pool))
    if len(picked) < reachable:
        return list(pool[:THEME_MAX_VIDEOS]), last, True
    return picked, last, False


def select_crisis_videos(
    pool: Sequence[TaggedVideo], day_of_year: int
) -> tuple[list[TaggedVideo], int, bool]:
    """위기 풀 선정 — 일반 주제와 같은 라운드로빈이되 형식 균형은 두지 않는다.

    위기 화면에는 [말씀]/[찬양] 토글이 없다. 형식 선택은 감정 화면의 기능이고,
    위기 화면은 상담 안내가 최상단인 단일 목록이다(PLAN.md 7절).
    """
    ladder = per_channel_ladder()
    order = _channel_order(pool, day_of_year)
    for cap in ladder:
        used: Counter[str] = Counter()
        picked = _round_robin(pool, cap, CRISIS_MAX_VIDEOS, order, used)
        if len(picked) >= CRISIS_MAX_VIDEOS:
            return picked, cap, False

    last = ladder[-1]
    used = Counter()
    picked = _round_robin(pool, last, CRISIS_MAX_VIDEOS, order, used)
    if len(picked) < CRISIS_MIN_VIDEOS <= len(pool):
        logger.warning(
            "채널당 상한 %d로는 %d건뿐이라 최소 %d건을 못 채운다 — 상한을 해제한다",
            last,
            len(picked),
            CRISIS_MIN_VIDEOS,
        )
        return list(pool[:CRISIS_MAX_VIDEOS]), last, True
    return picked, last, False


def select_fallback_videos(
    untagged: Sequence[TaggedVideo],
    media_default: str,
    need: int,
    day_of_year: int,
    *,
    exclude: set[str] | None = None,
) -> list[TaggedVideo]:
    """주제 태깅이 안 된 영상으로 화면의 남은 슬롯을 채운다 (PLAN.md 3.3 개정).

    [무엇을 담는가]
      그 세분류의 기본 형식(media_defaults) + unknown. unknown을 넣는 것은
      **양쪽 토글 모두에 노출되는 값**이라 어느 쪽에서도 빈 화면을 만들지 않기
      때문이다(주제 태깅의 untagged와 다르다).

    [정렬은 주제분과 같은 규칙이다 — 최신순 + 채널 라운드로빈]
      채널 간 우열을 두지 않는다. 승인 채널은 전원 동등한 자격으로 목록에 있고
      (channel_allowlist.yaml), "태깅률이 낮은 채널"은 콘텐츠가 나빠서가 아니라
      제목 관행이 다를 뿐이다 — CGN 성경통독은 태깅률 0%지만 성경 통독 방송이다.
      순위를 매기면 그 관행 차이가 노출 차별이 된다.

    [상한은 호출부가 정한다]
      need = min(빈 슬롯, FALLBACK_MAX_PER_SUBCATEGORY). 폴백이 화면을 다 덮지
      못하게 막는 것은 정책이고(20슬롯 중 최대 12), 그 판단은 세분류를 아는
      호출부에 있다.
    """
    if need <= 0:
        return []
    exclude = exclude or set()
    pool = [
        t
        for t in untagged
        if t.video_id not in exclude and t.media.media_type in (media_default, UNKNOWN)
    ]
    order = _channel_order(pool, day_of_year)
    used: Counter[str] = Counter()
    return _round_robin(pool, THEME_MAX_PER_CHANNEL, need, order, used)
