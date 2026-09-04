#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Play 스토어 그래픽 이미지(1024×500) 생성기 — 그리고 스토어 아이콘 검사.

[왜 생성물인가 — gen_icons.py와 같은 이유]
  손으로 만든 자산은 색을 바꾸는 날 아무도 다시 뽑지 못한다. 아이콘이 실제로
  그랬다(2.91). 그래픽 이미지도 같은 함정에 두지 않는다.
  ⛔ 색을 여기에 적지 않는다. app/src/theme.js에서 읽는다 —
    gen_icons.py가 쓰는 것과 **같은 출처**다.

[모양 — 안 ㄱ (2026-09-04 사용자 확정)]
  앱 배경 그라데이션 위에 「끊긴 원 · 숨」 표식과 이름만 둔다.
  ⛔ 성경 구절을 넣지 않는다 — 저작권 문제가 될 수 있다.
  ⛔ 스크린샷 축소본을 넣지 않는다 — 1024×500에서 읽히지 않고, 스크린샷은
    스토어가 따로 보여준다.
  ★ 새 그림을 그리지 않는다. 앱이 이미 쓰는 시각 언어(그라데이션 · 빛 · 끊긴 원)
    그대로라, 스토어에서 앱으로 넘어올 때 같은 것을 본다.

[⚠ 안전 여백 — 잘릴 수 있다]
  Play는 그래픽 이미지를 자리마다 다르게 자르고, 일부 배치에서는 위에 다른
  것이 겹친다. 그래서 표식과 글자를 **가운데 80% 안**에 둔다.
  ⛔ 가장자리에 뜻이 있는 것을 두지 않는다.

[⚠ 서체]
  이름이 라틴 문자라 시스템 세리프(Georgia)를 쓴다. 앱 본문은 한글 명조
  (theme.js SERIF)지만 여기에 쓸 글자가 "Peace in Mind"뿐이라 한글 서체가
  필요하지 않다. ⛔ 서체를 못 찾으면 **조용히 기본 서체로 가지 않고 멈춘다** —
    그림이 달라진 것을 아무도 모르는 것이 가장 나쁘다.

실행:  python scripts/gen_feature_graphic.py          (--check 로 대조만)
"""

from __future__ import annotations

import argparse
import io
import math
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("Pillow가 필요합니다:  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
THEME_JS = ROOT / "app" / "src" / "theme.js"
STORE = ROOT / "app" / "store"
STORE_ICON = ROOT / "app" / "public" / "icons" / "icon-512.png"

W, H = 1024, 500
SUPER = 3.0                      # 오버샘플 배율. 곡선과 글자를 매끄럽게 한다

# --- 표식 기하 — gen_icons.py의 비율을 1024×500에 맞춘 것 -------------------
#   ⚠ gen_icons.py는 512 캔버스에 GLOW_R=152 · RING_R=124 · RING_W=13이다.
#     여기서는 높이에 맞춰 줄인다. 비율(빛:원:선)은 그대로 지킨다.
MARK_D = 248                     # 표식이 차지하는 지름
GLOW_R = MARK_D * (152 / 512)
GLOW_A = 0.95
GLOW_FALLOFF = 2.2
RING_R = MARK_D * (124 / 512)
RING_W = max(2, round(MARK_D * (13 / 512)))
RING_A = 0.76
RING_GAP = 90                    # 위쪽 틈 (도)

TITLE = "Peace in Mind"
TITLE_PT = 78
GAP = 44                         # 표식과 글자 사이

FONT_CANDIDATES = (
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/constan.ttf",
)


def theme_colors() -> dict[str, tuple[int, int, int]]:
    """theme.js의 색 토큰을 읽는다. **여기가 유일한 출처다.**"""
    src = THEME_JS.read_text(encoding="utf-8")
    found = dict(re.findall(r'(\w+):\s*"(#[0-9A-Fa-f]{6})"', src))
    need = ("plum", "ink", "inkDeep", "jade", "mist")
    missing = [k for k in need if k not in found]
    if missing:
        sys.exit("theme.js에서 색을 찾지 못했습니다: %s" % ", ".join(missing))
    return {k: tuple(int(found[k][i:i + 2], 16) for i in (1, 3, 5)) for k in need}


C = theme_colors()
PLUM, INK, INKDEEP, JADE, MIST = C["plum"], C["ink"], C["inkDeep"], C["jade"], C["mist"]


def _lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(w: int, h: int, cx: float, cy: float, radius: float) -> Image.Image:
    """앱 배경과 같은 그라데이션 — 위쪽 자주에서 바깥 검정으로.

    ⚠ gen_icons.py의 같은 이름 함수와 **같은 곡선**이다(0.45에서 꺾인다).
      두 곳이 갈리면 스토어와 앱의 배경이 달라 보인다.
    """
    step = 4 if max(w, h) > 600 else 1
    sw, sh = max(1, w // step), max(1, h // step)
    img = Image.new("RGB", (sw, sh))
    px = img.load()
    for y in range(sh):
        for x in range(sw):
            t = min(1.0, math.hypot(x * step - cx, y * step - cy) / radius)
            px[x, y] = _lerp(PLUM, INK, t / 0.45) if t < 0.45 else _lerp(INK, INKDEEP, (t - 0.45) / 0.55)
    img = img if step == 1 else img.resize((w, h), Image.BICUBIC)
    return dither(img)


def dither(img: Image.Image) -> Image.Image:
    """⚠ 1024×500에서는 **띠(banding)가 보인다.**

    8비트로 반올림하면서 같은 값이 넓게 뭉치기 때문이고, 아이콘(512)에서는
    작아서 안 보이던 것이 여기서 드러났다(2026-09-04 눈으로 확인).
    ±1~2 수준의 잡음을 얹어 경계를 흩는다. 곡선 자체는 바뀌지 않는다.
    ⛔ gen_icons.py에는 넣지 않는다 — 거기서는 안 보이고, 아이콘은 바이트가
      바뀌면 --check가 어긋난다.
    """
    import random
    rnd = random.Random(20260904)          # ★ 고정 씨앗 — 돌릴 때마다 같은 그림이 나온다
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            n = rnd.randint(-2, 2)
            px[x, y] = (max(0, min(255, r + n)),
                        max(0, min(255, g + n)),
                        max(0, min(255, b + n)))
    return img


def glow(size: int, radius: float) -> Image.Image:
    """호흡하는 빛의 알파. gen_icons.py와 같은 (1-t)^2.2 곡선이다."""
    m = Image.new("L", (size, size), 0)
    px = m.load()
    c = size / 2.0
    for y in range(size):
        for x in range(size):
            t = math.hypot(x - c, y - c) / radius
            if t < 1.0:
                px[x, y] = int(255 * ((1 - t) ** GLOW_FALLOFF) * GLOW_A)
    return m


def mark(size: int, scale: float) -> Image.Image:
    """빛 + 끊긴 원. 투명 배경 위에 그려 배경에 얹는다."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    light = glow(size, GLOW_R * scale)
    img.paste(Image.new("RGBA", (size, size), JADE + (255,)), (0, 0), light)

    layer = Image.new("L", (size, size), 0)
    r = RING_R * scale
    c = size / 2.0
    # PIL 각도계는 3시가 0°, 시계 방향. 위쪽은 270°.
    start = 270 + RING_GAP / 2
    ImageDraw.Draw(layer).arc(
        [c - r, c - r, c + r, c + r],
        start, start + (360 - RING_GAP),
        fill=int(255 * RING_A), width=max(1, round(RING_W * scale)),
    )
    img.paste(Image.new("RGBA", (size, size), JADE + (255,)), (0, 0), layer)
    return img


def load_font(px: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, px)
    # ⛔ 기본 서체로 조용히 넘어가지 않는다. 그림이 달라진 것을 아무도 모른다.
    sys.exit(
        "세리프 서체를 찾지 못했습니다. 다음 중 하나가 필요합니다:\n  "
        + "\n  ".join(FONT_CANDIDATES)
        + "\n  다른 서체를 쓰려면 FONT_CANDIDATES에 경로를 더하세요."
    )


def render() -> Image.Image:
    w, h = W * int(SUPER), H * int(SUPER)
    # 빛이 화면 가운데 조금 위에서 퍼진다 — 앱 입력 화면과 같은 자리다.
    img = gradient(w, h, w / 2, h * 0.42, max(w, h) * 0.78).convert("RGBA")

    scale = SUPER
    msize = round(MARK_D * scale)
    m = mark(msize, scale)

    font = load_font(round(TITLE_PT * scale))
    d = ImageDraw.Draw(img)
    tb = d.textbbox((0, 0), TITLE, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    # 표식 + 틈 + 글자를 하나의 덩어리로 가운데 놓는다.
    total = msize + GAP * scale + tw
    x0 = (w - total) / 2
    cy = h / 2
    img.alpha_composite(m, (round(x0), round(cy - msize / 2)))
    d.text((x0 + msize + GAP * scale - tb[0], cy - th / 2 - tb[1]), TITLE,
           font=font, fill=MIST + (255,))

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)

    # ⚠ 안전 여백 확인 — 덩어리가 가운데 80% 안에 있는가.
    safe_x = W * 0.10
    if x0 / SUPER < safe_x or (x0 + total) / SUPER > W - safe_x:
        sys.exit(
            "내용이 안전 여백(가운데 80%%)을 벗어납니다. "
            "TITLE_PT나 MARK_D를 줄이세요. (지금 폭 %.0fpx / 허용 %.0fpx)"
            % (total / SUPER, W - safe_x * 2)
        )
    return out


def check_store_icon() -> list[str]:
    """스토어 아이콘 512×512 요건 — ⛔ 투명이 있으면 Play가 거부한다."""
    problems = []
    if not STORE_ICON.exists():
        return ["스토어 아이콘이 없습니다: %s  (python scripts/gen_icons.py)" % STORE_ICON]
    im = Image.open(STORE_ICON)
    if im.size != (512, 512):
        problems.append("크기가 512×512가 아닙니다: %s" % (im.size,))
    if "A" in im.getbands():
        alpha = im.getchannel("A")
        if min(alpha.getdata()) < 255:
            problems.append("**투명한 픽셀이 있습니다** — Play는 아이콘의 투명을 허용하지 않습니다")
    size = STORE_ICON.stat().st_size
    if size > 1024 * 1024:
        problems.append("1MB를 넘습니다: %d bytes" % size)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Play 그래픽 이미지 생성 · 스토어 아이콘 검사")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 대조만 한다")
    args = ap.parse_args()

    out = STORE / "feature-graphic-1024x500.png"
    img = render()
    buf = io.BytesIO()
    img.save(buf, "PNG")
    data = buf.getvalue()

    if args.check:
        cur = out.read_bytes() if out.exists() else b""
        # PNG는 인코더 판본에 따라 바이트가 달라질 수 있어 크기만 본다(gen_icons.py와 같다)
        same = out.exists() and abs(len(cur) - len(data)) < 512
        print(("일치  " if same else "어긋남 ") + str(out))
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print("썼다  %s  (%d bytes · %d×%d)" % (out, len(data), W, H))

    problems = check_store_icon()
    if problems:
        print("\n⛔ 스토어 아이콘 문제:")
        for p in problems:
            print("   " + p)
        return 1
    print("✅ 스토어 아이콘  %s  (512×512 · 투명 없음 · %d bytes)"
          % (STORE_ICON, STORE_ICON.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
