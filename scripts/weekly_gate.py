#!/usr/bin/env python
"""주간 진단을 이번 실행에서 돌릴지 판정해 워크플로에 넘긴다. API 호출 0.

    python scripts/weekly_gate.py

  GITHUB_OUTPUT       due=true|false        두 스텝이 **같은 값**을 쓴다
  GITHUB_STEP_SUMMARY 판정 근거 한 줄        건너뛴 경우에도 남긴다

⚠ **건너뛴 것을 조용히 넘기지 않는 것이 이 스크립트의 절반이다.** 전에는
  인라인 JS가 `core.info`만 남겨 로그를 펼쳐야 보였다. 지연으로 주간 진단이
  통째로 빠져도 아무 흔적이 없었다(HANDOFF 2.78 ②).

판정 규칙은 lib/weekly.py에 있고 spread_test [12]가 고정한다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.weekly import weekly_due

BASELINE = Path(os.environ.get("WEEKLY_BASELINE", "_previous/data/diagnostics.weekly.json"))
DEFAULT_CRON = "30 9 * * *"


def baseline_version(path: Path) -> str | None:
    """기준선 스냅샷이 언제 만들어졌는가. 없거나 깨졌으면 None."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def emit(name: str, value: str) -> None:
    target = os.environ.get(name)
    if target:
        with open(target, "a", encoding="utf-8") as fp:
            fp.write(value + "\n")


def main() -> int:
    cron = os.environ.get("SCHEDULE") or DEFAULT_CRON
    decision = weekly_due(datetime.now(timezone.utc), baseline_version(BASELINE), cron=cron)

    print(decision.summary)
    emit("GITHUB_OUTPUT", f"due={'true' if decision.due else 'false'}")
    # 건너뛴 경우에도 남긴다 — 흔적 없이 사라지는 것이 이 장치가 막으려는 것이다.
    emit("GITHUB_STEP_SUMMARY", f"- **주간 진단**: {decision.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
