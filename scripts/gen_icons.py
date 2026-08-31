#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""아이콘 생성기 — 웹 아이콘 · 안드로이드 런처 아이콘 · 스플래시를 한 곳에서 만든다.

[왜 생성물인가 — 2026-08-31 복원]
  아이콘은 오랫동안 **손으로 만든 자산**이었다. icon.svg 머리말이 "gen_icons.py가
  생성한다"고 적어 두었는데 그 스크립트가 저장소에 없었다(커밋된 적이 없다).
  그래서 색을 바꾸거나 크기를 추가하려면 아무도 다시 뽑을 수 없었다.

  ⛔ 색을 여기에 적지 않는다. app/src/theme.js에서 읽는다.
    두 곳에 적으면 반드시 갈라지고, 갈라져도 아무도 모른다.

[모양 — 03-c "끊긴 원 · 숨" (2026-08-31 확정)]
  자정 그라데이션 위에 호흡하는 빛, 그 둘레에 위쪽이 90° 열린 얇은 원.
  원을 닫지 않은 것은 "들이쉬는 중"으로 읽히게 하려는 것이고, 입력 화면의
  .orb(10초 주기 호흡)와 같은 결이다.
  ⚠ 48dp 실측에서 획 82 대 틈 32(대비 49)로 틈이 살아 있다. 닫힌 원과
    구분되지 않으면 이 도형을 쓸 이유가 없으므로 그 수치가 근거다.
  ⛔ 십자가를 넣지 않는다 — 이 앱은 "마음"을 먼저 말한다.

[adaptive icon 구성 — 안 ㄱ]
  background  #0B1216 단색 (values/ic_launcher_background.xml)
  foreground  빛 + 끊긴 원만. 투명 배경 위, 중앙 66dp 안
  런처의 시차(parallax)가 전경만 움직이므로 **빛만 흔들린다** — 호흡과 맞는다.
  ⚠ 위쪽 자주(#221A28) 기울기는 전경에서 사라진다. 그것을 감수한 선택이다.

실행:  python scripts/gen_icons.py          (그리고 --check 로 대조만)
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    sys.exit("Pillow가 필요합니다:  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
THEME_JS = ROOT / "app" / "src" / "theme.js"
WEB_ICONS = ROOT / "app" / "public" / "icons"
RES = ROOT / "app" / "android" / "app" / "src" / "main" / "res"

# --- 기하 — 512 단위 캔버스가 108dp다 ---------------------------------------
CANVAS = 512
DP = CANVAS / 108.0                 # 1dp = 4.7407 단위
SAFE_R = 66 / 2 * DP                # 66dp 안전 원 = 156.4
VISIBLE = 72 * DP                   # 72dp 가시 사각 = 341.3

GLOW_R = 152                        # 빛의 반지름
GLOW_A = 0.95                       # 빛의 세기
GLOW_FALLOFF = 2.2                  # (1-t)^2.2 감쇠

RING_R = 124                        # 원의 반지름 (중심선)
RING_W = 13                         # 선 굵기
RING_A = 0.76                       # 불투명도
RING_GAP = 90                       # 위쪽 틈 (도)

SUPER = 4.0                         # 스퀴클 초타원 지수
MASTER = 1024                       # 마스터 렌더 해상도. 전부 여기서 줄인다


def theme_colors() -> dict[str, tuple[int, int, int]]:
    """theme.js의 색 토큰을 읽는다. **여기가 유일한 출처다.**"""
    src = THEME_JS.read_text(encoding="utf-8")
    found = dict(re.findall(r'(\w+):\s*"(#[0-9A-Fa-f]{6})"', src))
    need = ("plum", "ink", "inkDeep", "jade")
    missing = [k for k in need if k not in found]
    if missing:
        sys.exit("theme.js에서 색을 찾지 못했습니다: %s" % ", ".join(missing))
    return {k: tuple(int(found[k][i:i + 2], 16) for i in (1, 3, 5)) for k in need}


C = theme_colors()
PLUM, INK, INKDEEP, JADE = C["plum"], C["ink"], C["inkDeep"], C["jade"]


def _lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(w: int, h: int, cx: float, cy: float, radius: float) -> Image.Image:
    """앱 배경과 같은 그라데이션 — 위쪽 자주에서 바깥 검정으로.

    큰 이미지는 1/4로 계산한 뒤 늘린다. 그라데이션은 부드러워 손실이 없고,
    스플래시(1920x1280)를 픽셀마다 도는 것을 피한다.
    """
    step = 4 if max(w, h) > 600 else 1
    sw, sh = max(1, w // step), max(1, h // step)
    img = Image.new("RGB", (sw, sh))
    px = img.load()
    for y in range(sh):
        for x in range(sw):
            t = min(1.0, math.hypot(x * step - cx, y * step - cy) / radius)
            px[x, y] = _lerp(PLUM, INK, t / 0.45) if t < 0.45 else _lerp(INK, INKDEEP, (t - 0.45) / 0.55)
    return img if step == 1 else img.resize((w, h), Image.BICUBIC)


def glow_mask(size: int, cx: float, cy: float, radius: float, strength: float) -> Image.Image:
    """호흡하는 빛의 알파. SVG의 다단 stop과 같은 (1-t)^2.2 곡선이다."""
    m = Image.new("L", (size, size), 0)
    px = m.load()
    for y in range(size):
        for x in range(size):
            t = math.hypot(x - cx, y - cy) / radius
            if t >= 1.0:
                continue
            px[x, y] = int(255 * ((1 - t) ** GLOW_FALLOFF) * strength)
    return m


def draw_mark(img: Image.Image, scale: float) -> None:
    """빛과 끊긴 원을 그린다. scale은 512 단위 대비 배율."""
    size = img.size[0]
    c = size / 2.0

    light = glow_mask(size, c, c, GLOW_R * scale, GLOW_A)
    img.paste(Image.new("RGB", (size, size), JADE), (0, 0), light)

    # 끊긴 원 — PIL 각도계는 3시가 0°, 시계 방향. 위쪽은 270°.
    layer = Image.new("L", (size, size), 0)
    r = RING_R * scale
    start = 270 + RING_GAP / 2
    ImageDraw.Draw(layer).arc(
        [c - r, c - r, c + r, c + r],
        start, start + (360 - RING_GAP),
        fill=255, width=max(1, round(RING_W * scale)),
    )
    layer = layer.point(lambda v: int(v * RING_A))
    img.paste(Image.new("RGB", (size, size), JADE), (0, 0), layer)


def master_full() -> Image.Image:
    """배경까지 있는 완성본 (웹 아이콘 · 레거시 런처 아이콘용)."""
    scale = MASTER / CANVAS
    img = gradient(MASTER, MASTER, MASTER / 2, 0, 1.15 * MASTER)
    draw_mark(img, scale)
    return img


def master_foreground() -> Image.Image:
    """투명 배경 위의 전경만 (adaptive icon용). 배경은 단색이 따로 깔린다."""
    scale = MASTER / CANVAS
    size = MASTER
    c = size / 2.0
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    light = glow_mask(size, c, c, GLOW_R * scale, GLOW_A)
    out.paste(Image.new("RGB", (size, size), JADE), (0, 0), light)

    layer = Image.new("L", (size, size), 0)
    r = RING_R * scale
    start = 270 + RING_GAP / 2
    ImageDraw.Draw(layer).arc(
        [c - r, c - r, c + r, c + r],
        start, start + (360 - RING_GAP),
        fill=255, width=max(1, round(RING_W * scale)),
    )
    layer = layer.point(lambda v: int(v * RING_A))
    out.paste(Image.new("RGB", (size, size), JADE), (0, 0), layer)
    return out


def squircle(size: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    a, pts = size / 2.0, []
    for i in range(721):
        th = i * math.pi / 360
        cs, sn = math.cos(th), math.sin(th)
        x = a * math.copysign(abs(cs) ** (2 / SUPER), cs)
        y = a * math.copysign(abs(sn) ** (2 / SUPER), sn)
        pts.append((a + x, a + y))
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def cropped(master: Image.Image, size: int, shape: str) -> Image.Image:
    """런처가 보는 모습 — 108dp 캔버스의 가운데 72dp를 잘라 size에 채운다."""
    m = master.size[0]
    inset = (m - VISIBLE * m / CANVAS) / 2
    face = master.crop((round(inset), round(inset), round(m - inset), round(m - inset)))
    face = face.resize((size, size), Image.LANCZOS).convert("RGB")
    if shape == "square":
        return face
    mask = squircle(size) if shape == "squircle" else Image.new("L", (size, size), 0)
    if shape == "circle":
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(face, (0, 0), mask)
    return out


def splash(w: int, h: int, mark: Image.Image) -> Image.Image:
    """스플래시 — 앱 배경과 같은 그라데이션 위에 표식 하나.

    ⛔ 흰 배경을 쓰지 않는다. 웹뷰가 그려지기 전 화면이므로 앱 배경과
      이어지지 않으면 열 때마다 흰 번쩍임이 생긴다.
    """
    img = gradient(w, h, w / 2, 0, 1.15 * max(w, h))
    side = round(min(w, h) * 0.34)
    m = mark.resize((side, side), Image.LANCZOS)
    img.paste(m, ((w - side) // 2, (h - side) // 2), m)
    return img


DENSITIES = [("mdpi", 1), ("hdpi", 1.5), ("xhdpi", 2), ("xxhdpi", 3), ("xxxhdpi", 4)]
SPLASH_SIZES = [
    ("drawable", 480, 320),
    ("drawable-port-mdpi", 320, 480), ("drawable-port-hdpi", 480, 800),
    ("drawable-port-xhdpi", 720, 1280), ("drawable-port-xxhdpi", 960, 1600),
    ("drawable-port-xxxhdpi", 1280, 1920),
    ("drawable-land-mdpi", 480, 320), ("drawable-land-hdpi", 800, 480),
    ("drawable-land-xhdpi", 1280, 720), ("drawable-land-xxhdpi", 1600, 960),
    ("drawable-land-xxxhdpi", 1920, 1280),
]


def svg_source() -> str:
    """웹 아이콘의 벡터 원본. PNG와 **같은 수치**에서 나온다."""
    circ = 2 * math.pi * RING_R
    visible = (360 - RING_GAP) / 360 * circ
    gap = RING_GAP / 360 * circ
    offset = -((270 + RING_GAP / 2) % 360) / 360 * circ
    stops = "\n".join(
        '    <stop offset="%.2f" stop-color="%s" stop-opacity="%.3f"/>'
        % (i / 10, "#%02X%02X%02X" % JADE, ((1 - i / 10) ** GLOW_FALLOFF) * GLOW_A)
        for i in range(11)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" width="{CANVAS}" height="{CANVAS}">
  <!-- Peace in Mind 앱 아이콘 — scripts/gen_icons.py가 PNG와 함께 생성한다.
       ⛔ 손으로 고치지 말 것. 색은 app/src/theme.js에서 읽는다.
       모양: 자정 그라데이션 + 호흡하는 빛 + 위쪽 {RING_GAP}도가 열린 얇은 원(03-c).
       원을 닫지 않은 것은 "들이쉬는 중"으로 읽히게 하려는 것이다. -->
  <defs>
    <radialGradient id="bg" cx="50%" cy="0%" r="115%">
      <stop offset="0" stop-color="#{PLUM[0]:02X}{PLUM[1]:02X}{PLUM[2]:02X}"/>
      <stop offset="0.45" stop-color="#{INK[0]:02X}{INK[1]:02X}{INK[2]:02X}"/>
      <stop offset="1" stop-color="#{INKDEEP[0]:02X}{INKDEEP[1]:02X}{INKDEEP[2]:02X}"/>
    </radialGradient>
    <radialGradient id="glow">
{stops}
    </radialGradient>
  </defs>
  <rect width="{CANVAS}" height="{CANVAS}" fill="url(#bg)"/>
  <circle cx="256" cy="256" r="{GLOW_R}" fill="url(#glow)"/>
  <circle cx="256" cy="256" r="{RING_R}" fill="none"
          stroke="#{JADE[0]:02X}{JADE[1]:02X}{JADE[2]:02X}" stroke-width="{RING_W}"
          stroke-linecap="round" opacity="{RING_A}"
          stroke-dasharray="{visible:.1f} {gap:.1f}" stroke-dashoffset="{offset:.1f}"/>
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="아이콘·스플래시 생성")
    ap.add_argument("--check", action="store_true",
                    help="쓰지 않고, 지금 파일이 생성 결과와 같은지만 본다")
    args = ap.parse_args()

    full, fore = master_full(), master_foreground()
    written, stale = [], []

    def emit(path: Path, img: Image.Image | None = None, text: str | None = None):
        data = text.encode("utf-8") if text is not None else None
        if data is None:
            import io
            buf = io.BytesIO()
            img.save(buf, "PNG")
            data = buf.getvalue()
        if args.check:
            cur = path.read_bytes() if path.exists() else b""
            # PNG는 인코더 판본에 따라 바이트가 달라질 수 있어 크기만 본다
            same = (cur == data) if text is not None else (path.exists() and abs(len(cur) - len(data)) < 512)
            (written if same else stale).append(path)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)

    # --- 웹 -----------------------------------------------------------------
    emit(WEB_ICONS / "icon.svg", text=svg_source())
    for n in (180, 192, 512):
        emit(WEB_ICONS / f"icon-{n}.png", full.resize((n, n), Image.LANCZOS))
    # maskable — 표식이 이미 중앙 51%라 안전 원(80%) 안이다. 같은 그림을 쓴다.
    emit(WEB_ICONS / "icon-maskable-512.png", full.resize((512, 512), Image.LANCZOS))

    # --- 안드로이드 런처 -----------------------------------------------------
    for name, mult in DENSITIES:
        fg = round(108 * mult)
        emit(RES / f"mipmap-{name}" / "ic_launcher_foreground.png",
             fore.resize((fg, fg), Image.LANCZOS))
        legacy = round(48 * mult)
        emit(RES / f"mipmap-{name}" / "ic_launcher.png", cropped(full, legacy, "squircle"))
        emit(RES / f"mipmap-{name}" / "ic_launcher_round.png", cropped(full, legacy, "circle"))

    # --- 배경색 -------------------------------------------------------------
    emit(RES / "values" / "ic_launcher_background.xml", text=(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- scripts/gen_icons.py가 생성한다. theme.js의 inkDeep이다. -->\n"
        "<resources>\n"
        '    <color name="ic_launcher_background">#%02X%02X%02X</color>\n'
        "</resources>\n" % INKDEEP
    ))

    # --- 스플래시 -----------------------------------------------------------
    mark = fore.resize((MASTER, MASTER), Image.LANCZOS)
    for folder, w, h in SPLASH_SIZES:
        emit(RES / folder / "splash.png", splash(w, h, mark))

    if args.check:
        if stale:
            print("아이콘이 생성 결과와 다릅니다 — python scripts/gen_icons.py 를 실행하십시오:")
            for p in stale:
                print("  ", p.relative_to(ROOT))
            return 1
        print("아이콘 %d개가 생성 결과와 같습니다." % len(written))
        return 0

    print("아이콘 %d개 생성 — 모양 03-c(틈 %d도 · 선 %d) · 색은 theme.js에서 읽었다"
          % (len(written), RING_GAP, RING_W))
    print("  빛 r%d @%.2f · 원 r%d w%d @%.2f · 바깥 반지름 %.2fdp (안전원 33dp)"
          % (GLOW_R, GLOW_A, RING_R, RING_W, RING_A, (RING_R + RING_W / 2) / DP))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
