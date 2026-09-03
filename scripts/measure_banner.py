"""세 갈래의 배너 기하를 **한 번에** 잰다 (HANDOFF 2.118).

[왜 스크립트인가]
  갈래 A·B·C가 **하나의 식을 공유한다.** 갈래 B를 고치면 A·C가 함께 바뀐다 —
  실제로 X 식을 한 번 고쳤을 때 셋이 다 움직였다(2026-09-03). 손으로 셋을
  돌리면 빠뜨린다.

[기준 항등식]
  배너 아래끝 = 화면 바닥에서 **64dp**   ( = P + margin + (SDK>=35 ? I : 0) )
  위 여백 = 아래 여백 = **16dp** (BANNER_MARGIN)
  배경면 높이 = **82dp** (50 + 2m)

[⛔ 픽셀 허용치]
  배경면 색(#141E24) 판정에 허용치를 6으로 두면 배경면 **아래 그라디언트**가
  배경면으로 잡혀 아래 여백이 40dp로 나온다. 스스로 한 번 속았다 —
  **허용치는 2다.** 바꾸지 말 것.

쓰는 법
  python scripts/measure_banner.py                 # 붙어 있는 기기 전부
  python scripts/measure_banner.py R39N500G7YF     # 지정
⚠ 각 기기가 **결과 화면에 있고 배너가 채워진 상태**여야 한다. 이 스크립트는
  화면을 넘기지 않는다 — 재기만 한다.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ADB = r"D:/jaehyuk.myung/android/sdk/platform-tools/adb.exe"
BAND = (0x14, 0x1E, 0x24)  # T.ink — 배경면 색
TOL = 2  # ⛔ 6으로 올리지 말 것 (위 주석)
BANNER_H = 50
MARGIN = 16
EXPECT_BOTTOM_DP = 64


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, errors="replace").stdout


def devices() -> list[str]:
    out = sh(ADB, "devices")
    return [l.split("\t")[0] for l in out.splitlines()[1:] if "\tdevice" in l]


def density(serial: str) -> float:
    m = re.search(r"(\d+)", sh(ADB, "-s", serial, "shell", "wm", "density"))
    return int(m.group(1)) / 160 if m else 3.0


def screencap(serial: str, out: Path) -> None:
    p = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"], capture_output=True)
    out.write_bytes(p.stdout)


def runs(img, x: int, y0: int) -> list[tuple[str, int, int]]:
    def near(c):
        return all(abs(a - b) <= TOL for a, b in zip(c, BAND))

    out, cur = [], None
    for y in range(y0, img.height):
        k = "band" if near(img.getpixel((x, y))) else "other"
        if cur is None or cur[0] != k:
            if cur:
                out.append((cur[0], cur[1], y - 1))
            cur = (k, y)
    out.append((cur[0], cur[1], img.height - 1))
    return out


def measure(serial: str, tmp: Path) -> dict:
    from PIL import Image  # 늦게 부른다 — 없으면 여기서만 실패한다

    d = density(serial)
    png = tmp / f"band_{serial}.png"
    screencap(serial, png)
    img = Image.open(png).convert("RGB")
    x = img.width // 2
    seq = [r for r in runs(img, x, int(img.height * 0.55)) if (r[2] - r[1] + 1) / d >= 4]
    # band · other(배너) · band 세 덩어리를 뒤에서 찾는다
    for i in range(len(seq) - 3, -1, -1):
        a, b, c = seq[i], seq[i + 1], seq[i + 2]
        if a[0] == "band" and b[0] == "other" and c[0] == "band":
            h = lambda r: (r[2] - r[1] + 1) / d
            if abs(h(b) - BANNER_H) <= 3:
                return {
                    "serial": serial,
                    "dpr": d,
                    "위": round(h(a), 1),
                    "배너": round(h(b), 1),
                    "아래": round(h(c), 1),
                    "배경면": round(h(a) + h(b) + h(c), 1),
                    # ⚠ 배너의 아래끝이다 — 아래쪽 배경면 덩어리가 **시작하는** 자리.
                    #   c[2](배경면 아래끝)로 재면 48dp가 나와 기준과 어긋난다.
                    "배너아래끝dp": round((img.height - c[1]) / d, 1),
                    "배경면아래끝dp": round((img.height - c[2] - 1) / d, 1),
                    "png": str(png),
                }
    return {"serial": serial, "dpr": d, "err": "배경면·배너 덩어리를 못 찾았다 (결과 화면인가? 광고가 채워졌나?)", "png": str(png)}


def main() -> int:
    tmp = Path(__file__).resolve().parent.parent / ".measure"
    tmp.mkdir(exist_ok=True)
    targets = sys.argv[1:] or devices()
    if not targets:
        print("붙어 있는 기기가 없다")
        return 1
    bad = 0
    print(f"{'기기':<16}{'dpr':>5}{'위':>7}{'배너':>7}{'아래':>7}{'배경면':>8}{'배너아래끝':>11}  판정")
    for s in targets:
        r = measure(s, tmp)
        if "err" in r:
            print(f"{s:<16}{r['dpr']:>5}  {r['err']}")
            bad += 1
            continue
        ok = (
            abs(r["위"] - MARGIN) <= 1
            and abs(r["아래"] - MARGIN) <= 1
            and abs(r["배너아래끝dp"] - EXPECT_BOTTOM_DP) <= 2
        )
        bad += 0 if ok else 1
        print(
            f"{s:<16}{r['dpr']:>5}{r['위']:>7}{r['배너']:>7}{r['아래']:>7}"
            f"{r['배경면']:>8}{r['배너아래끝dp']:>11}  {'OK' if ok else '어긋남'}"
        )
    print()
    print(f"기준 — 위 {MARGIN} · 아래 {MARGIN} · 배경면 {BANNER_H + 2 * MARGIN} · 배너아래끝 {EXPECT_BOTTOM_DP}dp")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
