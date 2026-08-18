"""YouTube Data API v3 쿼터 회계.

[비용표] https://developers.google.com/youtube/v3/determine_quota_cost
    search.list         100 units   ← 이것만 비싸다. 호출 횟수가 곧 비용이다.
    videos.list           1 unit    (id를 50개까지 묶어 1회 호출)
    channels.list         1 unit    (id를 50개까지 묶어 1회 호출)
    playlistItems.list    1 unit    (재생목록 1개당 1회 호출)

[일일 한도] 10,000 units — 태평양 시간 자정에 리셋된다.
    그래서 워크플로 cron은 PT 자정 직후로 잡는다.

[하루 예산 — PLAN.md 6절 확정치]
    channels.list  화이트리스트 50채널 → uploads 재생목록 ID  (50개당 1회) =   1
    playlistItems  채널별 최근 업로드 1~2페이지                            =  50~100
    videos.list    길이·공개상태·지역 확인 (50건 묶음)                     =  10~20
    ----------------------------------------------------------------------
    일일 배치 합계                                                        ≈ 150
    후보 발굴 suggest_channels.py (월 1회, 이때만 search 사용)             ≈ 661

[PYM은 일상 배치에서 search.list를 쓰지 않는다 — 이것이 FYM과의 결정적 차이다]
    FYM은 감정 세분류마다 검색어를 돌려 하루 7,900을 썼다.
    PYM은 전면 화이트리스트라(PLAN.md 5절) 승인 채널의 uploads 재생목록만
    순회한다. 채널당 1 unit이므로 채널을 50개로 늘려도 배치는 200을 넘지 않는다.

    이 구조가 안전의 근거이기도 하다. 검색을 하지 않으면 이단 채널이
    검색 결과로 유입될 경로 자체가 없다 — 목록 밖의 채널은 서비스에 존재하지 않는다.

[하지 말 것]
    search.list(channelId=...)로 화이트리스트 채널을 뒤지면 채널당 100 units다.
    50채널이면 5,000 units로 예산이 붕괴하고, 위 안전 근거도 함께 무너진다.
    channels.list → uploads 재생목록 → playlistItems.list 경로는 채널당 1 unit이고,
    결과도 "그 채널의 최신 업로드"라 검색보다 정확하다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

DAILY_LIMIT = 10_000

# 한도 10,000을 그대로 쓰지 않는다. 수동 재실행·검증 여유분 200을 남긴다.
#
# PYM은 일일 배치가 ~150이라 이 값에 닿을 일이 거의 없다. 그래도 낮추지 않는 것은
# 하드캡이 "정상 소모의 상한"이 아니라 "폭주를 멈추는 벽"이기 때문이다.
# 페이지네이션 버그로 playlistItems를 무한히 도는 사고에서 이 값이 마지막 방어선이 된다.
DEFAULT_HARD_CAP = 9_800

COST: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
}


class QuotaExceeded(RuntimeError):
    """쿼터 하드캡 초과.

    재시도해도 같은 결과이므로 워크플로는 이 예외로 끝난 실행을 재시도하지 않는다
    (build_videos.py는 종료 코드 2로 구분해 알린다).
    """


@dataclass
class QuotaBudget:
    """실행 중 실제 소모량을 세고, 하드캡을 넘으려는 호출을 미리 막는다."""

    hard_cap: int = DEFAULT_HARD_CAP
    spent: int = 0
    calls: Counter[str] = field(default_factory=Counter)

    def charge(self, endpoint: str, calls: int = 1) -> None:
        """호출 직전에 비용을 청구한다. 넘치면 호출하지 않고 예외를 던진다."""
        if endpoint not in COST:
            raise KeyError(f"비용표에 없는 엔드포인트: {endpoint}")
        cost = COST[endpoint] * calls
        if self.spent + cost > self.hard_cap:
            raise QuotaExceeded(
                f"하드캡 {self.hard_cap:,} 초과 — 현재 {self.spent:,} + "
                f"{endpoint} {cost:,} = {self.spent + cost:,}. "
                "부분 결과를 쓰지 않고 중단한다."
            )
        self.spent += cost
        self.calls[endpoint] += calls

    @property
    def remaining(self) -> int:
        return max(0, self.hard_cap - self.spent)

    def report_lines(self) -> list[str]:
        lines = ["실제 소모 쿼터", "-" * 52]
        for endpoint, count in sorted(self.calls.items()):
            units = COST[endpoint] * count
            lines.append(f"  {endpoint:<20} {count:>5}회  {units:>6,} units")
        lines.append("-" * 52)
        lines.append(
            f"  {'합계':<20} {'':>5}    {self.spent:>6,} units "
            f"(하드캡 {self.hard_cap:,}, 잔여 {self.remaining:,})"
        )
        return lines


@dataclass(frozen=True)
class QuotaEstimate:
    """실행 전 예상 소모량. 하드캡을 넘으면 API를 한 번도 부르지 않고 중단한다."""

    rows: tuple[tuple[str, str, int, int], ...]  # (항목, 엔드포인트, 호출 수, units)

    @property
    def total(self) -> int:
        return sum(row[3] for row in self.rows)

    def table(self, hard_cap: int) -> str:
        lines = ["", "예상 쿼터 소모량 (실행 전 산정)", "=" * 64]
        lines.append(f"  {'항목':<30}{'호출':>8}{'units':>12}")
        lines.append("-" * 64)
        for label, _endpoint, calls, units in self.rows:
            lines.append(f"  {label:<30}{calls:>8,}{units:>12,}")
        lines.append("-" * 64)
        margin = hard_cap - self.total
        verdict = "OK" if margin >= 0 else "초과 — 중단"
        lines.append(f"  {'합계':<30}{'':>8}{self.total:>12,}")
        lines.append(
            f"  하드캡 {hard_cap:,} / 일일 한도 {DAILY_LIMIT:,} "
            f"→ 여유 {margin:,} units [{verdict}]"
        )
        lines.append("=" * 64)
        return "\n".join(lines)


def build_estimate(
    *,
    allowlist_channels: int,
    uploads_pages_per_channel: int = 2,
    expected_video_ids: int,
) -> QuotaEstimate:
    """일일 배치의 예상 소모량 표를 만든다 (보수적 상한 기준).

    FYM의 같은 함수에 있던 category_search_calls / crisis_search_calls 인자를
    없앴다. PYM 일상 배치는 search.list를 부르지 않는다 — 인자를 남겨두면
    언젠가 누군가 값을 넣게 되고, 그 순간 전면 화이트리스트 전제가 깨진다.
    """
    videos_calls = -(-expected_video_ids // 50)  # 올림 나눗셈
    channels_calls = -(-allowlist_channels // 50) if allowlist_channels else 0
    playlist_calls = allowlist_channels * uploads_pages_per_channel
    rows = (
        (
            "화이트리스트 채널 조회",
            "channels.list",
            channels_calls,
            channels_calls * COST["channels.list"],
        ),
        (
            "채널별 최근 업로드",
            "playlistItems.list",
            playlist_calls,
            playlist_calls * COST["playlistItems.list"],
        ),
        (
            "영상 검증 (삭제·비공개·길이)",
            "videos.list",
            videos_calls,
            videos_calls * COST["videos.list"],
        ),
    )
    return QuotaEstimate(rows=rows)
