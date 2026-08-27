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
    FALLBACK_MAX_PER_TAB,
    PER_CHANNEL_STEPS,
    THEME_MAX_PER_CHANNEL,
    THEME_MAX_VIDEOS,
    THEME_MIN_VIDEOS,
)

logger = logging.getLogger("build_videos")

# 한 주제의 20슬롯을 형식별로 몇 건까지 먼저 확보할 것인가 (나머지는 남는 쪽이 채운다).
MEDIA_BALANCE_TARGET = THEME_MAX_VIDEOS // 2

# 반대 형식 바닥 — 토글 한쪽이 이 아래로 내려가지 않게 한다 (2026-08-25 신설).
#
# [왜 필요한가 — MEDIA_BALANCE_TARGET만으로는 못 막았다]
#   위 상수는 **주제 풀 안에서만** 동작한다. 풀에 그 형식이 아예 없으면 예약해도
#   채울 것이 없고, 부족분이 조용히 사라진 채 나머지 형식이 20슬롯을 다 가져갔다.
#   실측: anger.irritation·exhaustion.tired가 [말씀] 탭 0건. 두 화면 모두 주제가
#   self_control(영상 0건) + quiet_worship(어휘가 전부 찬양이라 말씀이 안 나온다)이다.
#
#   ⚠ **공급이 늘수록 나빠지는 구조였다.** 찬양 3곳 승인으로 quiet_worship 풀이
#     10 → 207이 되자 주제분만으로 20슬롯이 차서 폴백 층이 사라졌고, 폴백이 넣어
#     주던 unknown 3건이 [말씀] 탭의 유일한 재고였다 → 3건에서 0건이 됐다.
#
# [왜 4인가]
#   배포본 24화면의 **약한 쪽 건수 분포**에서 정했다 (2026-08-24 실측).
#       중앙값 6 · 1사분위 4 · 최소 0
#   4는 중앙값 아래라 건강한 화면을 건드리지 않는다 — 이 값 이상인 19개 화면은
#   아래 계산이 전부 0으로 지나간다. 실제로 슬롯을 내주는 화면은 5개뿐이다.
#   ⛔ 이 값을 키워서 "충분히 나오게" 만들려 하지 말 것. 그것은 폴백을 늘리는
#     것이고, 폴백은 감정에 맞춰 고른 영상이 아니다 — 정확도를 잃는다.
#     "비지 않게"는 여기서 풀고, "충분히"는 채널 발굴로 푼다 (HANDOFF 2.59).
#
# ★ 2026-08-26 탭별 상한으로 바뀌며 **역할이 좁아졌다.**
#   이제 각 탭을 TAB_MAX_VIDEOS까지 채우려 하므로 정상적으로는 바닥에 걸릴 일이 없다.
#   판정 기준도 "총 20 안에서 약한 쪽"이 아니라 **각 탭의 부족분**이다 —
#   select_tab_layers의 need가 곧 그 부족분이고, 언제나 MEDIA_FLOOR보다 크다.
#   ★ 2026-08-26 — **선정 로직에 관여하지 않는다. 경보 임계값이 유일한 쓰임이다.**
#     build_videos._evaluate_subcategory에서 theme_too_few의 심각도를 가른다:
#       탭 노출 < MEDIA_FLOOR          critical  "사실상 빈 탭"
#       탭 노출 < SUBCATEGORY_MIN(8)   warning   "목록 성립 불가"
#     전에는 logger.error로만 남아 아무도 보지 않았다 — 정식 경보로 올렸다(2.67).
MEDIA_FLOOR = 4


# 탭 하나가 보여 줄 최대 건수 (2026-08-26 — 화면 총량 20에서 탭별 20으로).
#
# [왜 바꿨나 — 두 탭이 서로의 자리를 뺏고 있었다]
#   총량이 20이면 찬양이 16일 때 말씀은 4밖에 못 가진다. 그런데 **사용자가 한 번에
#   보는 것은 한 탭**이다. 총량으로 묶을 이유가 없었다.
#
# ⚠ 2026-08-25에 같은 방향의 (b)안을 기각했는데 근거는 **선택 부담**이었다
#   (taxonomy content_policy).
#
# ⛔⛔ **정정 (2026-08-27 · HANDOFF 2.71 ⑥·2.72).**
#   여기 원래 "탭별 20은 한 번에 보는 목록을 20 이하로 유지하므로 그 결정을
#   어기지 않는다"고 적혀 있었다. **그 문장은 사실이 아니다.**
#
#   이 상수가 보장하는 것은 "한 탭이 20건 이하"가 아니라 **"각 패스의 기여가
#   20 이하"** 라는 다른 명제다. 두 패스(SERMON→WORSHIP)가 하나의 목록에 쌓고
#   unknown은 양쪽 탭에 보이므로, **뒷 패스가 담은 unknown이 앞 패스의 탭에도
#   나타나 20을 넘는다.** 사후 보정이 없다.
#
#     2026-08-26 실측   15개 탭이 21~24건 · 최대 24 · 앱은 자르지 않는다
#     구조적 상한        40 (뒷 패스의 20이 전부 unknown인 경우)
#
#   사용자 결정(2026-08-27): **초과를 허용하되 경보로 드러낸다(D안).** 24건 자체는
#   선택 부담을 유의미하게 늘리지 않고, 진짜 위험은 상한이 보장되지 않아 조용히
#   벌어지는 것이기 때문이다. 임계는 아래 TAB_OVER_* 참조.
#
# ⛔ 20으로 **정확히** 맞추는 길은 탭별 목록 분리(A안)뿐이다. 아래 두 안으로
#   부분 수정하지 말 것 — 둘 다 검토를 마치고 기각했다(2.72).
#     B  뒷 패스의 unknown 채택 억제 → unknown은 약한 탭을 메우는 값이라
#        조이면 주제분 0인 탭이 20을 못 채운다. **2.64가 푼 문제로 되돌아간다.**
#        게다가 찬양 탭만 고쳐지고 말씀 탭 초과는 남는다.
#     C  사후 절단 → 순환한다. unknown을 빼면 반대 탭도 하나 잃어 20 아래로
#        떨어질 수 있다. 단독으로 성립하지 않는다.
#
# ⚠ unknown은 양쪽 탭에 노출되므로 화면당 **고유** 영상은 20~40건이 된다.
#   두 탭 합계가 40을 넘는 것처럼 보이는 것은 중복 계산이지 데이터 중복이 아니다.
TAB_MAX_VIDEOS = THEME_MAX_VIDEOS

# 탭 노출이 이 값 이상이면 경보 (2026-08-27 · 사용자 결정 D안).
#
# [왜 20이 아니라 26/30인가 — 20 초과는 정상이고, '얼마나' 초과인지가 신호다]
#   TAB_MAX_VIDEOS 바로 위(21)에서 울리면 15개 탭이 매일 울린다. 그건 소음이지
#   신호가 아니다. 이 경보의 목적은 "초과를 잡는 것"이 아니라 **"오늘의 정상
#   범위를 벗어난 것을 잡는 것"** 이다.
#
#   [값의 근거 — 2026-08-26 실측과 구조적 상한 사이에서 잡았다]
#     의도치        20
#     오늘 최대     24  (초과분 4 · unknown 고유 273건 중 14건 = 5.1%)
#     구조적 상한   40
#
#     WARN 26   오늘 최대보다 2 위. 초과분이 4→6으로 **50% 늘 때** 울린다.
#               오늘 값으로는 울리지 않으므로 소음이 아니고, unknown이 눈에 띄게
#               늘면 울린다. 초과분은 곧 뒷 패스가 담은 unknown 수이므로
#               이 경보는 사실상 **unknown 급증 감지기**다.
#     CRIT 30   의도치의 1.5배이자 20과 40의 **정확한 중간**. 여기까지 오면
#               "탭당 20"이라는 말이 사실상 의미를 잃는다.
#
# ⚠ 이 값을 낮춰 "초과 자체"를 잡으려 하지 말 것. 초과는 D안이 **허용하기로 한
#   것**이다. 낮추면 매일 울리는 경보가 되어 아무도 안 보게 된다 — MEDIA_FLOOR가
#   logger.error로만 남아 아무도 안 보던 그 상태(2.67)를 반대 방향으로 재현한다.
TAB_OVER_WARN = 26
TAB_OVER_CRITICAL = 30


def visible_count(videos: Sequence[TaggedVideo], media_type: str) -> int:
    """토글 한쪽에 실제로 보이는 건수. **앱의 visibleVideos()와 같은 기준이다.**

    unknown은 양쪽 토글 모두에 노출되므로 양쪽에 센다(PLAN.md 3.4). 그래서
    말씀 합계 + 찬양 합계는 전체보다 클 수 있다 — 그게 정상이다.
    """
    return sum(1 for t in videos if t.media.media_type in (media_type, UNKNOWN))


def weak_side(videos: Sequence[TaggedVideo]) -> str:
    """토글 두 쪽 중 더 적게 보이는 쪽. 동수면 SERMON (결정적이어야 한다).

    ⚠ 양쪽이 **동시에** MEDIA_FLOOR 아래인 경우는 다루지 않는다. unknown이 양쪽에
      세어지므로 `말씀 + 찬양 >= 전체`이고, 둘 다 4 미만이려면 화면이 8건 미만이어야
      한다. 그것은 SUBCATEGORY_MIN_VIDEOS 경보가 이미 잡는 별개의 상태다.
    """
    return SERMON if visible_count(videos, SERMON) <= visible_count(videos, WORSHIP) else WORSHIP


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

# (d) 제3범주 프로그램 — **말씀도 찬양도 아닌 정규 편성물** (2026-08-27 · 사용자 결정)
#
#     [무엇을 빼는가]
#       간증·인터뷰·뉴스·다큐다. 방송사 채널(CBSJOY·CGN·CTS·극동방송)이 시리즈로
#       올리고 제목에 브랜드를 붙인다. 교회 채널에는 이런 것이 없다.
#       미태깅 81건 중 **64%가 이것이었고**(HANDOFF 2.73 ②), [말씀]을 눌러도
#       [찬양]을 눌러도 같은 인터뷰가 나오는 화면이 24개 중 19개였다(2.73 ③).
#
#     [왜 빼도 되는가 — 실측으로 확인했다 (2.74 ①)]
#       48/48 탭이 20건을 그대로 유지한다. 폴백 실효 천장은 후보 수가 아니라
#       **THEME_MAX_PER_CHANNEL(3) × 채널 수**라서, 57건을 빼도 채널이 21개
#       그대로면 천장이 안 움직인다. 한계점은 채널 10개 미만이다.
#       ⚠ 2.73 ⑦에 "빼면 주제분 0인 탭이 20을 못 채운다"고 적었던 것은 **오류다**
#         — 후보 수와 실효 재고를 혼동했다. 2.74에 정정 기록.
#
#     ⛔⛔ **항목을 추가할 때는 오탐 실측이 먼저다** (HANDOFF 2.14 원칙).
#       이 목록은 5일치 합집합 2,023건에서 재고 넣은 것이다. 하루치로 재면
#       안 되는 이유가 아래에 있다.
#
#     ⛔ **편성 라벨을 넣지 말 것.** 실측에서 걸러낸 세 가지다:
#         CTS 추천픽      라벨이다. 29건 안에 다큐·뉴스·간증과 함께
#                        **두란노 성경교실(성경 강의) 4건**이 섞여 있다
#         CBS 광장        6건 중 4건이 성경 인물 해설(시드기야·엘리야·안디옥)이다
#         두란노 성경교실   성경 강의다. 제3범주가 아니다
#       프로그램 **하나**를 가리키는 이름만 넣는다.
#
#     ※ '광복 81주년'·'위대한 유산'은 위 PROMO_SERIES가 이미 잡는다. 그래도
#       여기 두는 것은 그 시리즈가 끝나도 프로그램명은 남기 때문이다
#       (promo_reason은 먼저 걸린 이유를 돌려주므로 중복이 문제되지 않는다).
THIRD_PARTY_PROGRAMS = (
    "새롭게 하소서",      # CBSJOY 간증
    "부르심의 소명",      # CBSJOY 간증
    "온전한 인터뷰",      # CGN 인터뷰
    "레디온",            # CGN 교계 뉴스
    "휴먼네컷",          # CGN 인물 다큐
    "원더풀우먼",         # CTS 토크
    "CTS 뉴스 W",       # CTS 뉴스
    "내가 매일 기쁘게",    # CTS 간증
    "만나고 싶은 사람",    # 극동방송 인터뷰
    "광복 81주년",       # CTS 다큐 (PROMO_SERIES와 중복 — 위 ※ 참조)
    "위대한 유산",        # CTS 다큐
)

# (e) 괄호 안 인물 직함 — 인터뷰·간증 제목의 출연자 표기다.
#     실측 합집합 2,023건에서 3건뿐이지만 **오탐 0**이라 보조로 남긴다.
_THIRD_GUEST = re.compile(r"\([가-힣]{2,4}\s*(?:목사|교사|대표|권사|작가|기자|집사)\)")

# ⛔⛔ **기각된 신호 3종 — 되살리지 말 것** (2026-08-27 실측, HANDOFF 2.74 ③)
#   하루치(1,754건)로 재면 셋 다 오탐 0으로 보인다. 5일치 합집합(2,023건)에서 무너졌다.
#
#     S2 전각 구분자 '│'    32건 중 오탐 8 (25%)
#        잔여가 전부 CBSJOY 성서학당 예레미야 강해였다. '│'는 그 채널의 편집
#        습관이고 **같은 채널이 간증도 강해도 같은 문자를 쓴다.**
#     S4 인터뷰·간증 어휘    40건 중 오탐 ~6
#        '이야기'가 "찬송가 이야기"(찬양 해설)와 "거룩한 불: 간증"(R.T. 켄달
#        설교 시리즈)까지 잡는다.
#     S5 해시태그 3개 이상   15건 중 오탐 ~6
#        광주극동방송이 **말씀 콘텐츠에도 해시태그를 단다**
#        ("성경구절 12가지 #성경 #말씀 #위로").
#
#   ⛔ 특히 **구분자를 신호로 쓰지 말 것**(사용자 지시). 시각적으로 같은 세로
#     막대가 유니코드 4종으로 섞여 있다 — '|' U+007C 1,806회 · 'ㅣ' U+3163
#     (한글 자모!) 106회 · '│' U+2502 48회 · '｜' U+FF5C 6회.
#     콘텐츠 구조가 아니라 편집자의 타이핑 습관이다.

# 세로줄 뒤는 채널·예배·행사 이름이다 (retag_titles._TRAILER와 같은 규칙).
# ⚠ 'ㅣ'(U+3163 한글 자모)는 일부러 넣지 않았다 — 실측에서 이것만 쓰는 제목이
#   87건이지만 그 때문에 과다 제외되는 폴백 후보는 **0건**이다(2026-08-27 확인).
#   넣으려면 PROMO_HEAD 전체에 대해 오탐을 다시 재야 한다. 지금은 잠복 항목이다.
_TRAILER = re.compile(r"\s*[|｜│]\s*")


def promo_reason(title: str) -> str | None:
    """폴백에서 뺄 이유가 있으면 그 이유를, 없으면 None.

    [무엇을 빼는가 — 두 갈래다]
      공고/홍보 · 행사 · 시리즈   영상이 아니라 안내물이다 (2026-08-20)
      제3범주                    말씀도 찬양도 아닌 정규 편성물 (2026-08-27)
                                간증·인터뷰·뉴스·다큐. 위 (d)(e) 참조

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
    # 제3범주는 **마지막에** 본다 — 위 이유가 먼저 걸리면 그 이유를 남긴다.
    # 로그·리포트의 기존 분류가 바뀌지 않게 하려는 순서다.
    for word in THIRD_PARTY_PROGRAMS:
        if word in title:
            return f"제3범주:{word}"
    if _THIRD_GUEST.search(title):
        return "제3범주:출연자 표기"
    return None


def drop_promotional(
    untagged: Sequence[TaggedVideo],
) -> tuple[list[TaggedVideo], list[tuple[str, TaggedVideo]]]:
    """폴백 후보에서 공고·행사·홍보와 제3범주를 뺀다. (남은 후보, 뺀 것+이유)를 돌려준다.

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

    [2026-08-26 — 이 함수는 이제 **탭 하나**의 풀을 받는다]
      select_tab_layers가 형식으로 거른 풀(그 형식 + unknown)을 넘긴다. 그래서
      위 "말씀 10 / 찬양 10" 균형은 한 탭 안에서는 거의 의미가 없다 —
      반대 형식이 애초에 없기 때문이다. 남는 것은 **채널 분산과 상한 사다리**다.
      ⚠ 위기 풀 선정은 여전히 형식을 섞은 풀을 넘기므로 균형 코드는 살려 둔다.

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

    # ⛔ 2026-08-25에 여기 있던 "반대 형식 자리 예약"은 **걷어냈다**(2026-08-26).
    #   탭별 상한으로 바뀌어 select_tab_layers가 탭마다 따로 채우므로, 한쪽 형식이
    #   자리를 다 가져가는 상황 자체가 없어졌다.
    #   ⚠⚠ 되살리지 말 것 — 이 함수는 이제 **탭으로 걸러진 풀**을 받는다. 그 풀에는
    #     한 형식 + unknown만 있어 반대 형식이 구조적으로 0이다. 예약을 두면
    #     **모든 탭에서 무조건 4자리가 비어** 주제분이 이유 없이 줄어든다.
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
    target: str,
    need: int,
    day_of_year: int,
    *,
    exclude: set[str] | None = None,
) -> list[TaggedVideo]:
    """주제 태깅이 안 된 영상으로 화면의 남은 슬롯을 채운다 (PLAN.md 3.3 개정).

    [무엇을 담는가]
      target 형식 + unknown. unknown을 넣는 것은 **양쪽 토글 모두에 노출되는 값**이라
      어느 쪽에서도 빈 화면을 만들지 않기 때문이다(주제 태깅의 untagged와 다르다).

    [2026-08-25 — target을 인자로 받는다. 필터를 없앤 것이 아니다]
      전에는 화면의 media_default가 여기 박혀 있어, 찬양 기본 화면은 폴백으로도
      찬양만 받았다. 그러면 [말씀] 탭이 빈 화면을 벗어날 방법이 없다.
      호출부가 슬롯 그룹마다 목표 형식을 정해 두 번 부른다.
        형식 보장분   target = 약한 형식   (MEDIA_FLOOR까지만)
        개수 보충분   target = media_default
      **"아무거나 넣지 않는다"는 필터의 목적은 그대로 살아 있다** — 무엇이 목표인지만
      슬롯 그룹별로 달라진다.

    ★ 편집 결정 (2026-08-25, 사용자) — 찬양 기본 화면에 말씀 폴백을 넣어도 된다.
      media_default는 "먼저 보여준다"는 판단이지 "반대 형식을 안 보여준다"가 아니다.
      [말씀] 토글의 존재 자체가 그 증거이고, 사용자가 그것을 눌렀다는 것은 설교를
      보고 싶다고 명시한 것이다. 거기서 0건은 편집 의도가 아니라 그냥 빈 화면이다.
      토글이 갈라 주므로 찬양 목록에 말씀이 섞이지도 않는다(visibleVideos).
      ⚠ 반대 형식은 MEDIA_FLOOR까지만이다. 기본 형식이 16/20을 유지해 편집 의도가 남는다.

    [정렬은 주제분과 같은 규칙이다 — 최신순 + 채널 라운드로빈]
      채널 간 우열을 두지 않는다. 승인 채널은 전원 동등한 자격으로 목록에 있고
      (channel_allowlist.yaml), "태깅률이 낮은 채널"은 콘텐츠가 나빠서가 아니라
      제목 관행이 다를 뿐이다 — CGN 성경통독은 태깅률 0%지만 성경 통독 방송이다.
      순위를 매기면 그 관행 차이가 노출 차별이 된다.

    [상한은 호출부가 정한다]
      need는 호출부가 정한다(select_tab_layers). 상한은 FALLBACK_MAX_PER_TAB이고,
      2026-08-26부터 탭 상한과 같은 20이다 — 한 탭이 100% 폴백이 될 수 있다는
      뜻이며 사용자 결정이다(themes.py 주석).
    """
    if need <= 0:
        return []
    exclude = exclude or set()
    pool = [
        t
        for t in untagged
        if t.video_id not in exclude and t.media.media_type in (target, UNKNOWN)
    ]
    order = _channel_order(pool, day_of_year)
    used: Counter[str] = Counter()
    return _round_robin(pool, THEME_MAX_PER_CHANNEL, need, order, used)


def select_tab_layers(
    pool,
    untagged,
    day_of_year: int,
    position: int,
    *,
    exclude: set[str],
) -> tuple[list[TaggedVideo], list[TaggedVideo]]:
    """화면 하나를 **탭별로** 채운다 (2026-08-26 · 사용자 결정).

    [무엇이 달라졌나]
      전   주제분 20(형식 균형) → 남은 자리를 폴백.        **화면 총량 20**
      후   탭마다 주제분 → 그 탭의 부족분을 그 탭 폴백이.  **탭당 20**

      각 탭에서 **주제분을 먼저** 채우므로 주제분이 늘면 폴백이 자동으로 줄어든다.
      그 성질은 그대로다 — 바뀐 것은 "얼마까지 채우는가"의 단위뿐이다.

    [탭 풀을 어떻게 나누나]
      앱의 visibleVideos()와 같은 기준이다 — 그 형식 + unknown.
      ⚠ unknown은 양쪽 탭에 들어가므로 두 탭에서 같은 영상이 뽑힐 수 있다.
        최종 목록에는 **한 번만** 담고(seen), 부족분은 "지금까지 담은 것 중 이 탭에
        보이는 수"를 빼서 센다. 그래서 두 탭 합계가 40을 넘어 보여도 데이터는 한 벌이다.

    ⚠ 채널 상한·완화 사다리·회전은 select_theme_videos를 그대로 쓴다. 탭마다 따로
      부르므로 **한 채널이 말씀 3 + 찬양 3까지 가질 수 있다.** 전에는 used를 형식
      사이에 공유해 3이 상한이었다. 탭이 갈라진 이상 한 탭 안에서 3이면 충분하다 —
      사용자는 두 탭을 겹쳐 보지 않는다.

    ⚠ 순서가 결과를 바꾼다. SERMON을 먼저 돌리므로 unknown이 말씀 쪽에 먼저
      담기고, 찬양 탭은 그것을 이미 가진 채로 부족분을 센다. 형식 간 우열이 아니라
      **결정적이어야 해서** 고정한 순서다.
    """
    theme: list[TaggedVideo] = []
    fallback: list[TaggedVideo] = []
    seen: set[str] = set(exclude)

    for tab in (SERMON, WORSHIP):
        tab_pool = [t for t in pool if t.media.media_type in (tab, UNKNOWN)]
        picked, _, _ = select_theme_videos(tab_pool, day_of_year)
        picked = rotate_for_subcategory(picked, position)
        for tagged in picked[:TAB_MAX_VIDEOS]:
            if tagged.video_id in seen:
                continue
            theme.append(tagged)
            seen.add(tagged.video_id)

        # 이미 담긴 것 중 **이 탭에 보이는** 수를 뺀 만큼만 폴백으로 메운다.
        have = visible_count(theme, tab) + visible_count(fallback, tab)
        # 상한 둘은 지금 같은 값(20)이지만 뜻이 다르다 — 앞은 "탭이 보여 줄 최대",
        # 뒤는 "그중 폴백이 가져갈 수 있는 최대". 둘을 갈라 두면 나중에 폴백만
        # 조일 때 한 줄이면 된다.
        need = min(max(0, TAB_MAX_VIDEOS - have), FALLBACK_MAX_PER_TAB)
        for tagged in select_fallback_videos(
            untagged, tab, need, day_of_year, exclude=seen
        ):
            fallback.append(tagged)
            seen.add(tagged.video_id)

    return theme, fallback

