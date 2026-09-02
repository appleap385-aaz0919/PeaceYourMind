#!/usr/bin/env python
"""구절 알림의 **실제 발송 시각**을 하루 한 줄씩 누적한다 — 관찰용.

    python scripts/collect_notify_log.py            어제~오늘을 훑어 없는 날만 채운다
    python scripts/collect_notify_log.py --show     지금까지 모인 것을 표로 본다

[왜 만들었나 — 2026-09-02]
    09-01은 42분, 09-02는 2분 늦게 왔다. 편차가 커서 두 점으로는 아무 결론이
    안 난다(HANDOFF 2.96 알림 지연 관찰). 며칠을 더 봐야 하는데 —

    ⚠ **이벤트 버퍼는 2.5일이면 돈다**(실측). 그날 안 찍으면 그날이 사라진다.
    ★ 그리고 **사람이 시켜서 찍는 방식은 잊힌다.** 2026-09-02 아침에 겪은 병이
      그것이다. "매일 찍겠습니다"는 미래에 사람이 기억해야 하는 설계이고,
      이 저장소에서 그 설계는 일곱 번 실패했다.
    → 작업 스케줄러가 부른다. 사람은 결론이 날 때 한 번 본다.

[⛔ 저장 위치가 저장소 밖인 이유]
    관찰 원자료는 **생성물이다.** 이 저장소는 dist/·app/public/krv/를 이미
    빼 두었다 — 생성물은 커밋하지 않는다는 태도가 있다.
    14일이면 커밋이 14개 늘고, 그만큼 git log가 시끄러워진다.
    ★ 판단에 쓰이는 것은 **결론**이지 원자료가 아니다. 결론만 HANDOFF에 남긴다.
    ⚠ 대가 — 다른 기기·다른 사람은 못 본다. 지금은 개발자 하나·기기 하나라
      그 대가가 0에 가깝다. ⛔ 팀이 되면 다시 볼 것.

[⚠ 못 찍은 날과 알림이 없던 날을 구분한다]
    기기가 안 붙어 있으면 그날은 잴 수 없다. 그것을 빈 줄로 남기면 나중에
    "그날은 알림이 안 왔다"로 읽힌다 — **없는 것과 모르는 것은 다르다.**
    그래서 상태를 명시한다: ok · no_device · no_event.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PACKAGE = "io.github.appleap385.peaceinmind"

# ⛔ 저장소 밖이다. 위 주석 참조.
OUT = Path(os.environ.get("PYM_OBS_DIR", r"D:/jaehyuk.myung/claude_demo/_obs"))
LOG = OUT / "notify_delay.tsv"

HEADER = "date\tscheduled\tfired\tdelay_min\tchannel\tsound\tstatus"

# adb는 PATH에 없다 (HANDOFF 3절 실행 환경).
ADB = os.environ.get(
    "PYM_ADB", r"D:/jaehyuk.myung/android/sdk/platform-tools/adb.exe"
)

_ENQUEUE = re.compile(
    r"^(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})\.\d+ .*notification_enqueue.*"
    + re.escape(PACKAGE)
    + r",(\d+),.*channel=(\w+)"
)
_PLAYER = re.compile(r"^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}):\d+ .*event:started")


def _run(args: list[str]) -> str:
    """adb를 부른다. 실패는 예외가 아니라 빈 문자열이다 — 호출부가 상태로 다룬다."""
    try:
        out = subprocess.run(
            args, capture_output=True, text=True, timeout=120, encoding="utf-8",
            errors="replace",
        )
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def device_online() -> bool:
    lines = _run([ADB, "devices"]).splitlines()[1:]
    return any(line.strip().endswith("\tdevice") for line in lines)


def fired_times() -> dict[str, tuple[str, str]]:
    """{ "MM-DD": (HH:MM:SS, channel) } — 이벤트 버퍼에 남아 있는 발송."""
    found: dict[str, tuple[str, str]] = {}
    for line in _run([ADB, "shell", "logcat", "-b", "events", "-d"]).splitlines():
        hit = _ENQUEUE.match(line.strip())
        if hit:
            month, day, clock, _id, channel = hit.groups()
            found[f"{month}-{day}"] = (clock, channel)
    return found


def sound_days() -> set[str]:
    """소리가 실제로 재생된 날. 오디오 플레이어의 event:started로 본다.

    ⚠ 이 앱의 알림인지까지는 가리지 못한다 — dumpsys audio는 패키지를 안 남긴다.
      같은 분에 발송이 있으면 그 소리로 본다(호출부에서 맞춘다).
    """
    days: set[str] = set()
    for line in _run([ADB, "shell", "dumpsys", "audio"]).splitlines():
        hit = _PLAYER.match(line.strip())
        if hit:
            month, day, hour, minute, _sec = hit.groups()
            days.add(f"{month}-{day} {hour}:{minute}")
    return days


def scheduled_hhmm() -> str:
    """예약 시각. ⚠ 앱 설정(IndexedDB)은 읽을 수 없어 기본값을 쓴다."""
    return os.environ.get("PYM_NOTIFY_TIME", "09:00")


def existing_dates() -> set[str]:
    if not LOG.exists():
        return set()
    return {
        line.split("\t", 1)[0]
        for line in LOG.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    }


def append(row: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text(HEADER + "\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")


def collect() -> int:
    have = existing_dates()
    today = date.today()
    # 어제와 오늘만 본다. 버퍼가 2.5일이라 그 이상은 어차피 없다.
    targets = [today - timedelta(days=1), today]

    if not device_online():
        # ⚠ 못 찍은 것을 **기록으로 남긴다.** 빈 날과 구분해야 한다.
        for day in targets:
            key = day.strftime("%m-%d")
            iso = day.isoformat()
            if iso not in have:
                append(f"{iso}\t{scheduled_hhmm()}\t-\t-\t-\t-\tno_device")
                print(f"{iso}  기기 미연결 — 기록으로 남겼다")
        return 0

    fired = fired_times()
    sounds = sound_days()
    wrote = 0
    for day in targets:
        iso = day.isoformat()
        if iso in have:
            continue
        key = day.strftime("%m-%d")
        if key not in fired:
            # ⚠ 오늘은 아직 안 왔을 수 있다. 그때는 적지 않는다 — 내일 다시 본다.
            if day == today:
                print(f"{iso}  아직 발송 없음 (오늘이다. 내일 다시 본다)")
                continue
            append(f"{iso}\t{scheduled_hhmm()}\t-\t-\t-\t-\tno_event")
            print(f"{iso}  버퍼에 없음 — 놓쳤거나 안 왔다")
            wrote += 1
            continue

        clock, channel = fired[key]
        want = datetime.strptime(f"{iso} {scheduled_hhmm()}", "%Y-%m-%d %H:%M")
        got = datetime.strptime(f"{iso} {clock}", "%Y-%m-%d %H:%M:%S")
        delay = round((got - want).total_seconds() / 60)
        sound = "O" if f"{key} {clock[:5]}" in sounds else "?"
        append(f"{iso}\t{scheduled_hhmm()}\t{clock}\t{delay}\t{channel}\t{sound}\tok")
        print(f"{iso}  {clock}  {delay}분 늦음  channel={channel}  소리={sound}")
        wrote += 1
    return wrote


def show() -> int:
    if not LOG.exists():
        print(f"아직 기록이 없다: {LOG}")
        return 1
    rows = [r.split("\t") for r in LOG.read_text(encoding="utf-8").splitlines() if r.strip()]
    for row in rows:
        print("  ".join(f"{cell:<12}" for cell in row))
    body = [r for r in rows[1:] if len(r) >= 7 and r[6] == "ok"]
    print()
    print(f"표본 {len(body)}개 / 기록 {len(rows) - 1}일")
    # ⛔ 결론은 여기서 내지 않는다. 14일을 채우고 사람이 본다 (HANDOFF 2.96).
    if len(body) < 14:
        print(f"⚠ 14일에 {14 - len(body)}일 모자란다 — 아직 결론을 적지 말 것")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="구절 알림 발송 시각 누적")
    parser.add_argument("--show", action="store_true", help="모인 기록을 본다")
    args = parser.parse_args(argv)
    if args.show:
        return show()
    collect()
    print(f"\n기록 파일: {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
