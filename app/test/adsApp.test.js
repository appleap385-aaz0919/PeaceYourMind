/**
 * 앱 고정 띠배너 — **어느 화면에서 보이는가**를 지킨다.
 *
 * ⛔ 여기가 소스 텍스트를 보지 않는 이유
 *   기존 회귀(notify.test.js · verses.test.js의 AD_FREE_SCREENS)는 화면 파일 안에
 *   광고 토큰이 있는지 본다. 띠는 Shell에서 그리므로 그 파일들에 토큰이 남지
 *   않는다 — **통과하면서 띠는 화면에 남는다.** 그 구멍을 메우는 것이 이 파일이다.
 *
 * 지키는 것
 *   · 위기 화면과 알림 구절 화면에 띠가 없다 (앱의 약속)
 *   · 새 화면은 **기본이 안 보임**이다 (허용 목록이지 금지 목록이 아니다)
 *   · 화면 판정이 App.jsx의 분기 **순서**와 같다
 *   · 광고가 안 채워지면 자리를 0으로 접는다
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  BANNER_MARGIN,
  bannerLift,
  BANNER_HEIGHT,
  BANNER_GAP,
  SCREEN,
  bannerSpace,
  bannerVisible,
  currentScreen,
} from "../src/lib/adsApp.js";
import { readSource } from "./helpers.js";

const appSrc = readSource("App.jsx");
const adsAppSrc = readSource("lib", "adsApp.js");

/* --- 어디에 보이는가 ------------------------------------------------------ */

test("⛔ 위기 화면에 띠가 없다", () => {
  assert.equal(bannerVisible(SCREEN.CRISIS), false);
  assert.equal(bannerSpace({ screen: SCREEN.CRISIS, filled: true }), 0);
});

test("⛔ 알림으로 열린 구절 화면에 띠가 없다", () => {
  // 먼저 다가가 놓고 광고를 보이면 그렇게 읽힌다 (HANDOFF 2.92).
  assert.equal(bannerVisible(SCREEN.DAILY_VERSE), false);
  assert.equal(bannerSpace({ screen: SCREEN.DAILY_VERSE, filled: true }), 0);
});

test("결과 화면에만 띠가 보인다 (이어서 읽기·말씀·찬양이 그 안에 있다)", () => {
  assert.equal(bannerVisible(SCREEN.RESULT), true);
  for (const screen of Object.values(SCREEN)) {
    if (screen === SCREEN.RESULT) continue;
    assert.equal(bannerVisible(screen), false, `${screen}에 띠가 보인다`);
  }
});

test("⛔ 허용 목록이다 — 모르는 화면은 안 보인다", () => {
  // 금지 목록으로 짜면 목록에 넣는 것을 잊는 날 광고가 위기 화면에 뜬다.
  for (const unknown of ["", null, undefined, "newScreen", "result "]) {
    assert.equal(bannerVisible(unknown), false, `${String(unknown)}에 띠가 보인다`);
  }
});

/* --- 빈 띠는 접는다 ------------------------------------------------------- */

test("⛔ 광고가 안 채워지면 자리를 0으로 접는다", () => {
  // 빈 띠가 하단을 먹는 것은 광고 없이 자리만 차지하는 최악의 상태다.
  // 웹에서 AD_SLOT이 비면 요소를 아예 안 그리는 것과 같은 원칙이다.
  // ★ 배경면도 이 값에 묶여 있다 — 0이면 배경면·간격·하단 요소가 함께 사라진다.
  assert.equal(bannerSpace({ screen: SCREEN.RESULT, filled: false }), 0);
  assert.equal(bannerSpace({ screen: SCREEN.RESULT }), 0, "filled 기본값이 true다");
  assert.equal(
    bannerSpace({ screen: SCREEN.RESULT, filled: true }),
    BANNER_HEIGHT + BANNER_GAP.insetUnknown,
    "safeArea 없이 부르면 인셋을 모르는 쪽으로 간다",
  );
});

test("띠 높이는 50이다 (표준 배너 320×50)", () => {
  // 상수인 것이 안 1을 고른 이유다 — 적응형은 높이를 SDK가 정해서
  // 하단 조정이 런타임 값이 되고, 띠 전후로 레이아웃이 한 번 움직인다.
  // ★ 100 → 50은 실기기 관측이 뒤집었다 (HANDOFF 2.104).
  assert.equal(BANNER_HEIGHT, 50);
});

test("네이티브 adSize가 BANNER_HEIGHT와 짝이다", () => {
  // ⛔ 한쪽만 바꾸면 비워 둔 자리와 실제 띠 높이가 어긋난다.
  //   그 어긋남은 화면에 "배너 아래 빈 공간"으로 나타난다 — 2.103이 그 모양이다.
  const native = readSource("lib", "bannerNative.js");
  assert.ok(
    native.includes('adSize: "BANNER"'),
    "네이티브가 320×50을 요청하지 않는다",
  );
  assert.ok(
    !native.includes("LARGE_BANNER"),
    "LARGE_BANNER(320×100)가 남아 있다 — BANNER_HEIGHT 50과 어긋난다",
  );
});

test("★ 간격이 둘이다 — 인셋을 읽을 수 있는가로 갈린다", () => {
  // ⛔ 갈래 A는 safeArea가 실제 인셋이라 **위 여백이 GAP으로 고정된다**(인셋 무관).
  //   갈래 B는 safeArea가 0으로 주입되어 인셋을 모르므로 상한을 가정해야 한다.
  assert.ok(BANNER_GAP.insetKnown > 0, "인셋을 아는 쪽 간격이 0이다");
  assert.ok(
    BANNER_GAP.insetUnknown >= 48,
    `인셋을 모르는 쪽이 3버튼 48dp를 못 흡수한다 (${BANNER_GAP.insetUnknown})`,
  );
  assert.ok(
    BANNER_GAP.insetUnknown > BANNER_GAP.insetKnown,
    "모를 때가 알 때보다 크지 않다 — 상한을 가정하는 쪽이 더 커야 한다",
  );
  assert.notEqual(BANNER_GAP.insetKnown, BANNER_HEIGHT, "간격이 높이를 따라가면 가른 뜻이 없다");
});

test("★ 위 여백이 어느 조건에서도 음수가 되지 않는다", () => {
  // 위 여백 = safeArea + GAP − 인셋.
  // ⛔ 이것이 2.112가 고친 결함이다 — 인셋 48에서 −8이라 배너가 면 위로 튀어나왔다.
  const space = (sa) => bannerSpace({ screen: SCREEN.RESULT, filled: true, safeAreaBottom: sa });
  const topGap = (sa, inset) => space(sa) - (inset + BANNER_HEIGHT);

  // 갈래 A — safeArea = 인셋. 위 여백이 인셋과 무관하게 고정된다
  // ⚠ 인셋 0은 뺀다 — **"인셋이 0"과 "못 읽는다"를 구분할 수 없다.**
  //   0이면 항상 모르는 쪽(48)으로 가고, 그것이 안전한 방향이다(아래 단언).
  for (const inset of [16, 24, 48, 64, 96]) {
    assert.equal(
      topGap(inset, inset),
      BANNER_GAP.insetKnown,
      `갈래 A 인셋 ${inset}에서 위 여백이 고정값이 아니다`,
    );
  }
  // 갈래 B — safeArea = 0. 알려진 인셋에서 음수가 아니어야 한다
  for (const inset of [24, 48]) {
    assert.ok(topGap(0, inset) >= 0, `갈래 B 인셋 ${inset}에서 위 여백이 음수다`);
  }
  // 인셋이 0인 기기(하단 바가 없다)도 음수가 아니다
  assert.equal(topGap(0, 0), BANNER_GAP.insetUnknown, "인셋 0에서 모르는 쪽으로 가지 않는다");
  // ⚠ 갈래 B에서 인셋이 상한을 넘으면 음수가 된다 — 그것이 남는 한계다(2.112)
  assert.ok(topGap(0, 64) < 0, "상한을 넘는 인셋에서 음수가 되는 성질이 사라졌다 — 문서와 어긋난다");
});

test("safeArea를 못 읽으면(0) 더 넉넉한 쪽으로 간다 — 오판이 안전한 방향이다", () => {
  const known = bannerSpace({ screen: SCREEN.RESULT, filled: true, safeAreaBottom: 24 });
  const unknown = bannerSpace({ screen: SCREEN.RESULT, filled: true, safeAreaBottom: 0 });
  // 인셋 24를 0으로 오판해도 자리가 줄지 않는다
  assert.ok(unknown >= known, "0으로 오판할 때 오히려 자리가 줄어든다 — 위험한 방향이다");
  // 이상한 입력에 끌려가지 않는다
  for (const bad of [-10, NaN, undefined, "48"]) {
    assert.equal(
      bannerSpace({ screen: SCREEN.RESULT, filled: true, safeAreaBottom: bad }),
      BANNER_HEIGHT + BANNER_GAP.insetUnknown,
      `이상한 safeArea(${String(bad)})가 그대로 더해진다`,
    );
  }
});

test("배경면이 bottomInset에 묶여 있다 (광고가 없으면 안 그린다)", () => {
  // ⛔ 어제 안 ②를 기각한 사유가 "광고가 없을 때 배경 띠가 남는다"였다.
  //   배경을 filled에 묶으면 그 문제가 없어진다 — 여기서 그것을 고정한다.
  assert.ok(
    appSrc.includes("{band.h > 0 ?"),
    "배경면이 높이에 걸려 있지 않다 — 광고가 없어도 띠가 남는다",
  );
  assert.ok(
    appSrc.includes("bandStyle(band.h, band.lift)") &&
      appSrc.includes("bandFadeStyle(band.h, band.lift)"),
    "배경면과 페이드가 같은 기하(높이·띄움)를 쓰지 않는다 — 갈라지면 실틈이 생긴다",
  );
  // ⛔ 전체 폭이어야 한다. 좌우를 띄우면 화면 맨 아래 모서리로 내용이 샌다.
  // ⛔ 전체 폭은 그대로다. 바닥에서 **띄우는** 것만 바뀌었다 (2.118 안 2) —
  //   lift가 배너 아래 여백을 만든다. 0으로 되돌리면 배너가 바닥에 붙는다.
  assert.ok(
    /function bandStyle\(height, lift = 0\)/.test(appSrc),
    "bandStyle이 높이와 띄움을 따로 받지 않는다",
  );
  assert.ok(
    /left: 0,[\s\S]*?right: 0,[\s\S]*?bottom: lift,/.test(appSrc),
    "배경면이 전체 폭이 아니거나 lift만큼 띄우지 않는다",
  );
  // ⛔ 1px 실선은 넣지 않는다 (사용자 결정) — 페이드가 그 자리를 대신한다.
  assert.ok(
    appSrc.includes("BAND_FADE"),
    "위쪽 페이드가 없다 — 배너가 면 위로 삐져나올 때 닫을 것이 없다",
  );
});

/* --- 화면 판정이 App.jsx와 같은가 ----------------------------------------- */

test("화면 판정이 App.jsx의 분기 순서와 같다", () => {
  // ⚠ currentScreen은 App.jsx의 분기를 옮겨 적은 것이다. 순서가 갈리면
  //   같은 상태에서 다른 화면으로 판정하고, 띠가 엉뚱한 곳에 뜬다.
  const order = ["if (dailyVerse)", "if (showAbout)", "PHASE.LOADING", "PHASE.RESULT"];
  const at = order.map((needle) => appSrc.indexOf(needle));
  for (const [i, index] of at.entries()) {
    assert.ok(index > 0, `App.jsx에서 ${order[i]}를 찾지 못했다`);
  }
  for (let i = 1; i < at.length; i += 1) {
    assert.ok(at[i - 1] < at[i], `App.jsx 분기 순서가 바뀌었다: ${order[i - 1]} → ${order[i]}`);
  }
});

test("상태 조합마다 화면이 하나로 정해진다", () => {
  assert.equal(currentScreen({ dailyVerse: { id: "x" } }), SCREEN.DAILY_VERSE);
  // 알림 화면이 다른 모든 분기보다 먼저다 — About이 켜져 있어도 이긴다.
  assert.equal(
    currentScreen({ dailyVerse: { id: "x" }, showAbout: true, phase: "result" }),
    SCREEN.DAILY_VERSE,
  );
  assert.equal(currentScreen({ showAbout: true, phase: "result" }), SCREEN.ABOUT);
  assert.equal(currentScreen({ phase: "loading" }), SCREEN.LOADING);
  assert.equal(currentScreen({ phase: "result", resultKind: "crisis" }), SCREEN.CRISIS);
  assert.equal(currentScreen({ phase: "result", resultKind: "ok" }), SCREEN.RESULT);
  assert.equal(currentScreen({ phase: "result", resultKind: "empty" }), SCREEN.EMPTY);
  assert.equal(currentScreen({ phase: "result", resultKind: "nomatch" }), SCREEN.NO_MATCH);
  assert.equal(currentScreen({ phase: "input" }), SCREEN.INPUT);
  assert.equal(currentScreen({}), SCREEN.INPUT, "아무것도 없으면 입력 화면이다");
});

/* --- 웹과 갈린다 ---------------------------------------------------------- */

test("⛔ 앱 광고 판단이 웹 자리 계산을 가져다 쓰지 않는다", () => {
  // ads.js는 목록 항목 **사이**를 계산한다. 여기는 화면 **최하단**이다.
  // 섞이면 한쪽을 고칠 때 다른 쪽이 조용히 따라 바뀐다.
  for (const token of ["BASE_SLOTS", "adPositions", "positionsWithin", "AD_SLOT"]) {
    assert.ok(!adsAppSrc.includes(token), `adsApp.js가 웹 자리 계산(${token})을 쓴다`);
  }
});

test("⛔ 판단 파일에 네이티브 호출이 없다", () => {
  // 순수 함수라야 테스트가 화면 종류마다 직접 단언할 수 있다.
  for (const token of ["@capacitor", "showBanner", "AdMob"]) {
    assert.ok(!adsAppSrc.includes(token), `adsApp.js에 네이티브 호출(${token})이 들어왔다`);
  }
});

/* --- 배선 ----------------------------------------------------------------
 *
 * ⚠ 위 순수 함수가 맞아도 **App이 그것을 안 쓰면 아무 일도 일어나지 않는다.**
 *   여기서 배선을 본다. 소스를 읽는 검사이지만 대상이 화면 파일의 광고 토큰이
 *   아니라 **연결 구조**라, 띠배너를 못 보던 그 구멍과는 다른 것을 본다.
 */

test("App이 화면 판정과 자리 계산을 직접 쓴다", () => {
  for (const token of ["currentScreen({", "bannerSpace({", "bannerVisible(screen)"]) {
    assert.ok(appSrc.includes(token), `App.jsx가 ${token}을 쓰지 않는다`);
  }
});

test("⛔ Shell 호출마다 bottomInset이 간다 (한 곳이라도 빠지면 그 화면만 어긋난다)", () => {
  // ⚠ 여는 태그 **안쪽만** 본다. 문서 전체의 bottomInset을 세면
  //   Shell이 떠 있는 버튼에 넘기는 것까지 섞여 수가 맞아 보인다.
  const openings = [...appSrc.matchAll(/<Shell(?=[\s>])[^>]*>/g)].map((m) => m[0]);
  assert.ok(openings.length > 0, "Shell 호출을 찾지 못했다");
  const missing = openings.filter((tag) => !tag.includes("bottomInset={bottomInset}"));
  assert.equal(
    missing.length,
    0,
    `Shell ${openings.length}곳 중 ${missing.length}곳에 bottomInset이 빠졌다`,
  );
});

test("Shell의 아래 여백이 조건부다 (띠가 없으면 늘리지 않는다)", () => {
  // 늘리기만 하면 띠가 없는 화면에 빈 여백이 생긴다.
  assert.ok(
    /paddingBottom: `calc\(40px \+ \$\{bottomInset\}px\)`/.test(appSrc),
    "Shell이 bottomInset으로 아래 여백을 늘리지 않는다",
  );
});

test("★ 떠 있는 버튼 둘이 같은 함수로 올라간다", () => {
  // floatingStyle 하나를 공유하므로 한 곳만 고치면 둘 다 옮겨진다.
  // 갈라지면 한쪽만 띠에 가린다.
  const common = readSource("components", "common.jsx");
  assert.ok(
    /function floatingStyle\(shown, reducedMotion, bottomInset = 0\)/.test(common),
    "floatingStyle이 bottomInset을 받지 않는다",
  );
  assert.ok(
    /bottom: FLOATING_BOTTOM \+ bottomInset/.test(common),
    "floatingStyle이 bottomInset만큼 올라가지 않는다",
  );
  // ⚠ 토스트는 2026-09-03에 **상단 중앙**으로 옮겼다(사용자 확정). 더 이상
  //   떠 있는 버튼에서 파생시키지 않는다 — 상단은 파생시킬 요소가 없다.
  assert.ok(
    /export const FLOATING_BOTTOM = \d+;/.test(common) &&
      /export const FLOATING_HEIGHT = \d+;/.test(common),
    "떠 있는 버튼의 자리 상수가 밖으로 나와 있지 않다",
  );
  const calls = common.match(/floatingStyle\(shown, reducedMotion, bottomInset\)/g) || [];
  assert.equal(calls.length, 2, `두 버튼이 함께 쓰지 않는다 (${calls.length}곳)`);
});

test("⛔ 네이티브 어댑터가 화면을 판단하지 않는다", () => {
  // 판단이 두 곳에 있으면 갈라지고, 갈라지는 순간 위기 화면에 광고가 뜬다.
  const native = readSource("lib", "bannerNative.js");
  for (const token of ["SCREEN", "currentScreen", "bannerVisible", "crisis", "dailyVerse"]) {
    assert.ok(!native.includes(token), `bannerNative.js가 화면을 판단한다 (${token})`);
  }
});

/* --- 안 2: 배너가 배경면 가운데에 놓인다 (2026-09-03 · HANDOFF 2.118) -------
 *
 * ⛔ 여기 있는 것은 **기하 모형**이다. 실제 배너가 그 자리에 앉는지는
 *   실측으로만 안다 — 이 검사는 "우리가 계산한 값이 대칭인가"만 본다.
 *
 *   화면 아래끝을 0으로, 위를 +로 센다.
 *     I  하단 시스템 인셋      P  웹뷰가 아래에서 잘린 양 (A·B=0 · C=I)
 *     배너 아래끝  = I + m     배경면 아래끝 = P + X
 */

function geometry({ I, P, injected = null, safeAreaBottom = 0 }) {
  const state = {
    screen: SCREEN.RESULT,
    filled: true,
    safeAreaBottom,
    insetBottomReal: injected,
  };
  const H = bannerSpace(state);
  const X = bannerLift(state);
  const bandBottom = P + X;
  const bannerBottom = I + BANNER_MARGIN;
  return {
    H,
    X,
    below: bannerBottom - bandBottom,
    above: bandBottom + H - (bannerBottom + BANNER_HEIGHT),
  };
}

const BRANCHES = [
  { name: "갈래 A 태블릿(48)", I: 48, P: 0, injected: 48, safeAreaBottom: 48 },
  { name: "갈래 A 폰 제스처(24)", I: 24, P: 0, injected: 24, safeAreaBottom: 24 },
  { name: "갈래 B 제스처(24)", I: 24, P: 0, injected: 24, safeAreaBottom: 0 },
  { name: "갈래 B 3버튼(48)", I: 48, P: 0, injected: 48, safeAreaBottom: 0 },
  { name: "갈래 C 3버튼(48)", I: 48, P: 48, injected: 0, safeAreaBottom: 0 },
  { name: "갈래 C 제스처(24)", I: 24, P: 24, injected: 0, safeAreaBottom: 0 },
];

for (const b of BRANCHES) {
  test(`★ ${b.name} — 위·아래 여백이 m으로 같다`, () => {
    const g = geometry(b);
    assert.equal(g.above, BANNER_MARGIN, `위 여백이 m이 아니다 (${g.above})`);
    assert.equal(g.below, BANNER_MARGIN, `아래 여백이 m이 아니다 (${g.below})`);
    assert.equal(g.H, BANNER_HEIGHT + 2 * BANNER_MARGIN, "배경면 높이가 50+2m이 아니다");
  });
}

test("★ 배경면 높이는 인셋과 무관하다 — 주입값이 오면 갈래 구분이 사라진다", () => {
  const heights = BRANCHES.map((b) => geometry(b).H);
  assert.deepEqual(new Set(heights).size, 1, `갈래마다 높이가 다르다: ${heights}`);
});

test("⛔ 폴백(주입값 없음)에서 **음수가 생기지 않는다**", () => {
  const cases = [
    { I: 24, P: 0, safeAreaBottom: 24 },
    { I: 48, P: 0, safeAreaBottom: 48 },
    { I: 24, P: 0, safeAreaBottom: 0 },
    { I: 48, P: 0, safeAreaBottom: 0 },
    { I: 48, P: 48, safeAreaBottom: 0 },
    { I: 24, P: 24, safeAreaBottom: 0 },
    { I: 64, P: 0, safeAreaBottom: 64 },
  ];
  for (const c of cases) {
    const g = geometry({ ...c, injected: null });
    assert.ok(g.above >= 0, `폴백에서 위 여백이 음수다 (${g.above}) — ${JSON.stringify(c)}`);
    assert.ok(g.below >= 0, `폴백에서 아래 여백이 음수다 (${g.below}) — ${JSON.stringify(c)}`);
  }
});

test("⛔ 폴백은 2026-09-03 이전과 **같은 기하**다 (lift가 margin을 상쇄한다)", () => {
  // 갈래 C 3버튼 — 옛 값: 배경면 98 · 위 48 · 아래 0
  const g = geometry({ I: 48, P: 48, injected: null, safeAreaBottom: 0 });
  assert.equal(g.H, 98);
  assert.equal(g.above, 48);
  assert.equal(g.below, 0);
});

test("⛔ 못 쓸 주입값은 폴백으로 간다 (음수·NaN·문자열·null)", () => {
  for (const bad of [null, undefined, -1, NaN, "48", {}]) {
    const g = geometry({ I: 48, P: 48, injected: bad, safeAreaBottom: 0 });
    assert.equal(g.H, 98, `${String(bad)} 가 대칭식으로 갔다`);
  }
});

test("광고가 안 채워지면 높이도 lift도 0이다", () => {
  const off = { screen: SCREEN.RESULT, filled: false, insetBottomReal: 48 };
  assert.equal(bannerSpace(off), 0);
  assert.equal(bannerLift(off), 0);
});

test("⛔ 배경면을 띄우면 그 **아래 틈을 덮는다** (콘텐츠가 새지 않게)", () => {
  // ④를 지키려 배경면을 인셋만큼 띄웠더니 그 자리로 스크롤 콘텐츠가 지나갔다.
  // 갈래 B에서만 드러났다 — C는 lift 0이고 A는 시스템 바 뒤라 덜 띈다 (2026-09-03).
  assert.ok(
    /function bandCoverStyle\(lift\)/.test(appSrc),
    "덮개 함수가 없다 — 띄운 틈으로 콘텐츠가 샌다",
  );
  assert.ok(
    /bandCoverStyle\(band\.lift\)/.test(appSrc),
    "덮개를 lift로 그리지 않는다",
  );
  assert.ok(
    /band\.lift > 0 \?/.test(appSrc),
    "lift가 0일 때도 덮개를 그린다 — 갈래 C에는 틈이 없다",
  );
  // ⛔ 덮개가 배경면보다 먼저 와야 한다 (뒤에 오면 배경면을 가린다)
  const cover = appSrc.indexOf("bandCoverStyle(band.lift)");
  const band = appSrc.indexOf("bandStyle(band.h, band.lift)");
  assert.ok(cover > -1 && band > -1 && cover < band, "덮개가 배경면 뒤에 그려진다");
});

test("★ 토스트는 상단 인셋을 env로 흡수한다 — 갈래별 주입이 필요 없다", () => {
  // 갈래 A는 웹뷰가 상태바 밑까지 가고(env 24) B·C는 이미 아래에 있다(env 0).
  // ⛔ 하단(--inset-bottom-real)과 달리 여기는 네이티브가 필요 없다.
  assert.ok(
    /top: "calc\(env\(safe-area-inset-top, 0px\) \+ \d+px\)"/.test(appSrc),
    "토스트가 상단 인셋을 env로 다루지 않는다",
  );
  assert.ok(
    /width: "fit-content"/.test(appSrc) && /margin: "0 auto"/.test(appSrc),
    "토스트 상자가 내용 폭으로 가운데 놓이지 않는다",
  );
});

test("⛔ 토스트 움직임이 앱의 결을 따른다 — .rise의 거울이고 reduced-motion을 지킨다", () => {
  assert.ok(/@keyframes toastIn \{ from\{opacity:0;transform:translateY\(-10px\)\}/.test(appSrc),
    "toastIn이 rise의 거울(위에서 내려앉기)이 아니다");
  assert.ok(/reducedMotion\s*\?\s*"none"/.test(appSrc),
    "reduced-motion에서 움직임을 빼지 않는다");
});

test("★ 나가는 움직임이 들어오는 것의 **거울**이다 — 거리·시간이 같다", () => {
  // ⛔ 실측이 만든 규칙이다 (2026-09-03). 나갈 때 6px이던 시절에는
  //   opacity 0.5 시점의 이동이 3.08px뿐이라 페이드로만 보였다.
  assert.ok(
    /@keyframes toastOut \{ from\{opacity:1;transform:translateY\(0\)\} to\{opacity:0;transform:translateY\(-10px\)\}/.test(appSrc),
    "toastOut의 거리가 toastIn과 다르다 — 대칭이 깨졌다",
  );
  assert.ok(
    /const TOAST_IN_MS = 450;/.test(appSrc) && /const TOAST_OUT_MS = 450;/.test(appSrc),
    "들어오고 나가는 시간이 같지 않다",
  );
  // ease = cubic-bezier(.25,.1,.25,1)의 거울은 (1−x2,1−y2,1−x1,1−y1)이다.
  assert.ok(
    /const TOAST_OUT_EASE = "cubic-bezier\(\.75,0,\.75,\.9\)";/.test(appSrc),
    "나가는 곡선이 ease의 거울이 아니다",
  );
  assert.ok(
    /toastIn \$\{TOAST_IN_MS\}ms ease both/.test(appSrc),
    "들어오는 곡선이 ease가 아니다 — 결이 갈렸다",
  );
});

test("★ 머무는 시간과 총 노출 — 나가는 움직임이 그 뒤에 얹힌다", () => {
  assert.ok(/const TOAST_MS = 4600;/.test(appSrc), "머무는 시간이 4.6초가 아니다");
  // ⛔ 구조를 못 박는다 — hide는 TOAST_MS에, 제거는 TOAST_MS + TOAST_OUT_MS에.
  //   더하는 구조가 깨지면 나가는 움직임이 잘린다.
  assert.ok(
    /setToastLeaving\(true\), TOAST_MS\)/.test(appSrc),
    "나가는 시작이 머무는 시간에 걸려 있지 않다",
  );
  assert.ok(
    /setToast\(""\), TOAST_MS \+ TOAST_OUT_MS\)/.test(appSrc),
    "제거가 머무는 시간 + 나가는 시간이 아니다 — 움직임이 잘린다",
  );
});

test("⛔ 영구 거절 안내는 **물어본 뒤에만** 뜬다 · 설정으로 보내지 않는다", () => {
  // ★ 물어보기 전 값은 낡을 수 있다(2026-09-03 실측). setEnabled가 false를
  //   돌려준 **뒤**라야 Capacitor 캐시가 새로 쓰인 상태다.
  const fail = appSrc.indexOf("if (next && !ok) {");
  const ask = appSrc.indexOf("await isPermissionBlocked()");
  assert.ok(fail > -1 && ask > fail, "안내 판정이 켜기 실패 뒤에 있지 않다");
  assert.ok(
    /const TOAST_BLOCKED = "기기 설정에서 알림을 켜 주세요";/.test(appSrc),
    "안내 문구가 확정값과 다르다",
  );
  // ⛔ 사용자 확정 — 시스템 설정 화면으로 **보내지 않는다.** 알려만 준다.
  assert.ok(
    !/APP_NOTIFICATION_SETTINGS|openSettings|App\.openUrl/.test(appSrc),
    "설정 화면으로 보내는 코드가 생겼다 — 사용자가 기각한 방식이다",
  );
  // ⛔ 토글은 OFF로 남는다. 실패 갈래에서 다시 켜면 안 된다.
  const revert = appSrc.indexOf("setNotifyOn(false);", fail);
  assert.ok(revert > fail && revert < ask, "실패했는데 토글을 먼저 되돌리지 않는다");
});
