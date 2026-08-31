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
  BANNER_HEIGHT,
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
  // 빈 띠가 하단 100px을 먹는 것은 광고 없이 자리만 차지하는 최악의 상태다.
  // 웹에서 AD_SLOT이 비면 요소를 아예 안 그리는 것과 같은 원칙이다.
  assert.equal(bannerSpace({ screen: SCREEN.RESULT, filled: false }), 0);
  assert.equal(bannerSpace({ screen: SCREEN.RESULT }), 0, "filled 기본값이 true다");
  assert.equal(bannerSpace({ screen: SCREEN.RESULT, filled: true }), BANNER_HEIGHT);
});

test("띠 높이는 100이다 (LARGE_BANNER 320×100)", () => {
  // 상수인 것이 안 1을 고른 이유다 — 적응형은 높이를 SDK가 정해서
  // 하단 조정이 런타임 값이 되고, 띠 전후로 레이아웃이 한 번 움직인다.
  assert.equal(BANNER_HEIGHT, 100);
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
