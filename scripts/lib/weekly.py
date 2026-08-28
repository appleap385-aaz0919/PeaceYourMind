"""주간 진단을 **이번 실행에서 돌릴 것인가**를 정한다. API·네트워크 없음.

[왜 따로 뺐나 — 2026-08-28]
  판정이 워크플로 안의 인라인 JS였고 `new Date().getUTCDay() !== 1` 한 줄이었다.
  **실행 시각으로 월요일을 판정하면 배치 지연에 무너진다.**

    2026-08-27  09:30Z 예약 → 19:55Z 시작 (10시간 25분 지연, HANDOFF 2.78)

  월요일 09:30Z 실행이 14시간 30분 이상 밀리면 UTC 화요일이 되어 게이트에 걸리고,
  **주간 진단과 기준선 갱신이 통째로 건너뛰어진다.** 실패도 로그도 남지 않는다.
  그 주의 악화 판정이 사라지고, 기준선이 안 밀려 다음 주는 2주 전과 비교한다.

  파이썬으로 옮긴 이유는 **게이트가 검사할 수 있게** 하기 위해서다 —
  spread_test [12]가 지연·중복·누락 세 경우를 전부 고정한다.

[무엇을 기준으로 판정하는가 — 두 축이다]
  1. **예약 발동 시각**(실행 시각이 아니다). cron이 09:30Z이면 "실행 시각 이전의
     가장 가까운 09:30Z"가 이번 회차의 발동 시점이다. 10시간을 밀려도 그 값은
     안 변한다. 24시간 미만의 지연을 전부 흡수한다.
  2. **기준선 이후 경과일**. 1번만으로는 GitHub이 월요일 회차를 **통째로 흘려보낸**
     경우(2026-08-27 21:30Z 슬롯이 실제로 그랬다)를 못 잡는다. 경과일이
     STALE_DAYS를 넘으면 요일과 무관하게 돌려 **그 주를 건너뛰지 않게** 한다.

⚠ 두 축이 반대 방향의 실패를 각각 막는다. 하나만 두지 말 것.
    예약 발동 시각 없이 경과일만 → 요일이 표류한다
    경과일 없이 예약 발동 시각만 → 회차가 통째로 빠지면 2주 전과 비교하게 된다
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# 주간 기준선의 기준 요일. datetime.weekday() 기준이라 0 = 월요일.
ANCHOR_WEEKDAY = 0

# 같은 회차가 두 번 돌아 기준선을 두 번 덮어쓰는 것을 막는 하한.
# 정상 간격은 7일이므로 6일이면 여유가 충분하고, 같은 날 재실행은 확실히 막힌다.
MIN_GAP_DAYS = 6

# 월요일 회차를 통째로 놓쳤을 때 다음 실행이 이어받는 상한.
# 8일인 이유: 정상 경로는 7.0일 언저리(지연을 더해도 7.5일 내외)라 오발동하지
# 않고, 월요일을 놓치면 화요일에 정확히 8.0일이 되어 바로 잡힌다.
STALE_DAYS = 8

WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


@dataclass(frozen=True)
class WeeklyDecision:
    due: bool
    reason: str
    occurrence: datetime  # 이번 회차의 **예약** 발동 시각
    elapsed_days: float | None  # 기준선 이후 경과일 (기준선이 없으면 None)

    @property
    def summary(self) -> str:
        occ = f"{self.occurrence:%Y-%m-%d %H:%M}Z({WEEKDAY_KO[self.occurrence.weekday()]})"
        gap = "-" if self.elapsed_days is None else f"{self.elapsed_days:.1f}일"
        return f"예약 발동 {occ} · 기준선 이후 {gap} → {'실행' if self.due else '건너뜀'} ({self.reason})"


def parse_cron_hhmm(cron: str) -> tuple[int, int]:
    """"30 9 * * *" → (9, 30). 워크플로의 cron과 어긋나지 않게 문자열에서 읽는다."""
    parts = cron.split()
    if len(parts) < 2:
        raise ValueError(f"cron 형식을 읽을 수 없다: {cron!r}")
    return int(parts[1]), int(parts[0])


def scheduled_occurrence(now: datetime, hour: int, minute: int) -> datetime:
    """실행 시각 이전의 가장 가까운 예약 시점. **지연에 흔들리지 않는 값이다.**"""
    occ = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if occ > now:
        occ -= timedelta(days=1)
    return occ


def weekly_due(
    now: datetime,
    baseline_version: str | None,
    *,
    cron: str = "30 9 * * *",
) -> WeeklyDecision:
    """이번 실행에서 주간 진단·기준선 갱신을 할 것인가.

    ⚠ **이 한 번의 판정을 두 스텝이 공유해야 한다.** 각자 계산하면 어긋나고,
      어긋나면 비교는 했는데 기준선이 안 밀리거나(매주 같은 주와 비교) 비교 없이
      기준선만 밀린다(악화를 영영 못 봄). 워크플로가 출력값 하나로 묶는 이유다.
    """
    hour, minute = parse_cron_hhmm(cron)
    occ = scheduled_occurrence(now, hour, minute)

    if not baseline_version:
        return WeeklyDecision(True, "기준선이 없다 — 이번 값을 첫 기준선으로 삼는다", occ, None)

    try:
        base = datetime.fromisoformat(baseline_version.replace("Z", "+00:00"))
    except ValueError:
        return WeeklyDecision(True, f"기준선 시각을 읽을 수 없다({baseline_version!r}) — 다시 세운다", occ, None)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    elapsed = (now - base).total_seconds() / 86400.0

    if occ.weekday() == ANCHOR_WEEKDAY:
        if elapsed >= MIN_GAP_DAYS:
            return WeeklyDecision(True, "예약 발동일이 월요일이다", occ, elapsed)
        return WeeklyDecision(
            False, f"월요일이지만 기준선이 {elapsed:.1f}일 전이라 중복이다", occ, elapsed
        )

    if elapsed >= STALE_DAYS:
        return WeeklyDecision(
            True, f"월요일 회차를 놓쳤다 — 기준선이 {elapsed:.1f}일 전이다(안전망)", occ, elapsed
        )

    return WeeklyDecision(
        False, f"예약 발동일이 {WEEKDAY_KO[occ.weekday()]}요일이다", occ, elapsed
    )
