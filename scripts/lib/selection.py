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
import re
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


# =============================================================================
# 폴백 품질 — 폴백에도 넣지 않는 것 (2026-08-20)
# =============================================================================
# 폴백은 "감정에 딱 맞지는 않아도 그 채널의 최근 영상"을 허용한 층이다
# (HANDOFF 2.14). 그런데 실측에서 그 범위 밖이 올라왔다 — 단원 모집 공고,
# 기념행사 중계, 채널 구독자 이벤트. **감정에 안 맞는 것과 콘텐츠가 아닌 것은
# 다르다.** 앞은 폴백이 감수하기로 한 것이고 뒤는 아니다.
#
# [왜 어휘 목록 하나로 하지 않았나 — 실측이 먼저 막았다]
#   '주년'·'콘서트'를 통째로 걸면 이런 것이 함께 사라진다.
#       "주 여호와는 나의 힘 & 찬송할 수 있을 때 | 옹기장이 40주년 카운트다운 콘서트"
#       "할렐루야 존귀하신 주 | 옹기장이 40주년 카운트다운콘서트 2026"
#   전부 실제 찬양 영상이고 40주년은 **어디서 찍었는가**일 뿐이다. 반대로
#       "극동방송 70주년 기념 호남권 전도대회 | FEBC 호남권 전도대회 2부 LIVE"
#   에서는 그것이 영상 자체다. 가르는 축은 어휘의 유무가 아니라 **머리가 무엇인가**다.
#
#   실측 (dist/titles.json 1,067건 · 미태깅 788건)
#       머리 기준 + 시리즈   제외 20건 · 정상 콘텐츠 손실 0건   ← 채택
#       전체 매칭            제외 28건 · 찬양 5건 + 설교 2건 손실
#
# ⚠ 이 사전을 늘릴 때는 `retag_titles.py --probe <어휘>`로 무엇이 걸리는지
#   눈으로 세고 나서 넣는다. 제목 blocklist가 정상 영상을 떨어뜨리는 쪽이 더 큰
#   위험이라는 판단은 HANDOFF 2.12절에서 이미 한 번 한 것이다.

# (a) 위치 무관 — 이 말이 있으면 영상이 아니라 공고·홍보다
PROMO_ANYWHERE = (
    "모집", "신입단원", "공고", "접수", "채용", "지원자격", "선발",
    "하이라이트", "예고편", "티저", "스케치", "홍보영상",
    "돌파기념", "구독자",
)
# (b) 제목 머리에만 — 트레일러(세로줄 뒤)에 있으면 촬영 장소·행사명일 뿐이다
PROMO_HEAD = (
    "주년", "축제", "전도대회", "총회", "음악회",
    "발대식", "페스티벌", "체육대회", "바자회", "헌당", "임직",
)
# (c) 시리즈 브랜드 — 트레일러에 있어도 뺀다. **사람이 지정한다.**
#     머리만으로 못 가르는 구간이다. CTS 광복 시리즈의 머리는 "독립유공자 26인
#     집안, 목회자 사모가 된 자녀들"이라 (b)에 안 걸리는데, 그렇다고 '광복'을
#     통째로 넣으면 "영적 광복을 위한 오늘의 핍박"(CBS 설교)을 잃는다.
#     ★ 이 경계는 [2] 곡명 사전이 생기면 자동으로 갈린다 — 머리가 곡명인지
#       판정할 수 있게 되기 때문이다. 그때 이 목록을 다시 볼 것.
PROMO_SERIES = ("광복 81주년",)

# 세로줄 뒤는 채널·예배·행사 이름이다 (retag_titles._TRAILER와 같은 규칙).
_TRAILER = re.compile(r"\s*[|｜│]\s*")


def promo_reason(title: str) -> str | None:
    """폴백에서 뺄 이유가 있으면 그 이유를, 없으면 None.

    **폴백 전용이다. 주제분에는 걸지 않는다** — 주제어가 걸린 영상은 그 나름의
    근거가 있고, 두 층은 판단 기준이 다르다. 실측에서도 제외 대상 20건은
    전부 미태깅이었다.
    """
    for word in PROMO_ANYWHERE:
        if word in title:
            return f"공고/홍보:{word}"
    head = _TRAILER.split(title)[0]
    for word in PROMO_HEAD:
        if word in head:
            return f"행사:{word}"
    for word in PROMO_SERIES:
        if word in title:
            return f"시리즈:{word}"
    return None


def drop_promotional(
    untagged: Sequence[TaggedVideo],
) -> tuple[list[TaggedVideo], list[tuple[str, TaggedVideo]]]:
    """폴백 후보에서 공고·행사·홍보를 뺀다. (남은 후보, 뺀 것+이유)를 돌려준다.

    ⚠ **뺀 자리를 되메우지 않는다.** 화면이 SUBCATEGORY_MIN_VIDEOS 미만이 되면
      그대로 두고 theme_too_few(critical)가 뜬다 — 쓰레기로 채우는 것보다 얇은
      편이 낫다는 판단이다(사용자 결정 2026-08-20). select_fallback_videos는
      풀에서 need만큼 뽑고 모자라면 적게 돌려주므로 되메우는 경로 자체가 없다.
      **여기서 뺀 것을 다시 넣는 코드를 만들지 말 것.**
    """
    kept: list[TaggedVideo] = []
    dropped: list[tuple[str, TaggedVideo]] = []
    for item in untagged:
        reason = promo_reason(item.video.title)
        if reason:
            dropped.append((reason, item))
        else:
            kept.append(item)
    return kept, dropped


# =============================================================================
# 세분류별 오프셋 (2026-08-20) — [4]가 다른 형태로 되살아난 자리다
# =============================================================================
# [4] 폴백 오프셋은 "폴백 겹침 해소"가 목적이었고 보류됐다 — 동일 5쌍 중
# 오프셋으로 풀리는 것이 0쌍이었기 때문이다(재측정 2.30절). 전부 **주제분이
# 같아서** 생긴 쌍이었다.
#
# 그래서 목적을 바꿔 되살렸다: **주제분 순서 분산.**
#   같은 주제 풀을 여러 화면이 공유할 때, 풀이 화면 정원보다 작으면 모든 화면이
#   풀 전체를 가져가 세트가 같아진다. 지금 quiet_worship(12건)을 세 화면이
#   그렇게 쓴다 — anger.irritation · exhaustion.tired · calm.ease.
#
#   ⚠ **이것은 세트를 바꾸지 않는다. 순서만 바꾼다.**
#     세트를 가르려면 화면당 몫을 12 → 4로 깎아야 하고, 그러면 폴백이 8건 는다.
#     사용자가 바로 알아채는 것은 스크롤 없이 보이는 첫 화면이므로, 주제분을
#     잃지 않으면서 첫 화면을 다르게 만드는 쪽을 골랐다(사용자 결정 2026-08-20).
#     스크롤하면 같은 12건이라는 한계는 남는다 — **그건 공급 문제이고
#     HANDOFF 3절 10번(채널 발굴)이 그 자리다.**


def rotate_for_subcategory(
    videos: Sequence[TaggedVideo], position: int
) -> list[TaggedVideo]:
    """세분류마다 시작점을 달리해 목록을 회전한다. **구성은 그대로다.**

    position은 themes.yaml mapping에서의 자리(0부터)다.

    ⚠ **세분류 id를 해시해서 쓰지 않는다.** 처음에 그렇게 했다가
      anger.irritation과 exhaustion.tired가 12로 나눈 나머지에서 **둘 다 4**로
      충돌해 아무것도 달라지지 않았다. 해시는 충돌을 막아 주지 않는다.
      매핑 순서를 쓰면 같은 풀을 공유하는 화면들이 연속된 자리에 있어
      나머지가 자연히 갈린다 — quiet_worship을 쓰는 다섯 화면이
      0·3·13·20·21번이고 풀 12건에서 0·3·1·8·9로 나뉜다.

    ⚠ 파이썬 내장 hash()도 쓰지 않는다 — PYTHONHASHSEED로 프로세스마다
      달라져 같은 입력이 매번 다른 결과를 낸다. 재현이 깨진다.
    """
    items = list(videos)
    if len(items) < 2:
        return items
    offset = position % len(items)
    return items[offset:] + items[:offset]


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
