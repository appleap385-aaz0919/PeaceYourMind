/**
 * 플러그인 고정 — **네이티브 동작이 조용히 바뀌는 것**을 잡는다.
 *
 * [왜 필요한가 — HANDOFF 2.118]
 *   배너 기하 설계가 `@capacitor-community/admob`의 **소스를 읽어** 세운 것이다.
 *     · 인셋 보정이 **Android 15+에서만** 돈다 (BannerExecutor.java)
 *     · 그 보정이 **리스너**라 회전에 스스로 따라간다
 *     · 그래서 우리는 margin을 **상수**로 넘길 수 있다
 *   ⛔ 이 셋은 **회귀로 단언할 수 없다.** 실측으로만 알고, 플러그인이 올라가면
 *     말없이 바뀐다. 그러면 배너가 어긋나는데 우리 테스트는 전부 통과한다.
 *   ★ 그래서 **버전을 못 박는다.** 버전이 움직이면 이 테스트가 실패하고,
 *     그때 사람이 소스를 다시 읽는 것이 절차다.
 *
 * ⚠ 이 테스트가 실패하면 "버전을 고쳐서 통과시키는" 것이 답이 아니다.
 *   BannerExecutor.java의 위 세 성질을 **다시 확인한 뒤에** 고정값을 옮긴다.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

// ⚠ .json 은 주석이 없으므로 직접 읽는다. **소스(.js)는 반드시 readSource()다** —
//   주석이 검사를 오염시킨 사건이 세 번 있었다(helpers.js 상단).
const pkg = JSON.parse(readFileSync(join(app, "package.json"), "utf8"));

/** ⛔ 여기를 고치기 전에 위 주석을 읽을 것. */
const PINNED = Object.freeze({
  "@capacitor-community/admob": "8.1.0",
  "@capacitor/local-notifications": "8.3.1",
});

for (const [name, version] of Object.entries(PINNED)) {
  test(`⛔ ${name} 이 ${version} 그대로다 (네이티브 동작을 소스로 확인한 버전)`, () => {
    const declared = pkg.dependencies[name];
    assert.ok(declared, `${name} 이 dependencies에 없다`);
    const installed = JSON.parse(
      readFileSync(join(app, "node_modules", name, "package.json"), "utf8"),
    ).version;
    assert.equal(
      installed,
      version,
      `설치본이 ${installed} 다 — 배너 기하(2.118)와 알림 알람(2.116)이 이 플러그인의 ` +
        `네이티브 동작에 기대고 있다. 버전을 올렸으면 BannerExecutor.java와 ` +
        `LocalNotificationManager.kt를 다시 읽고 고정값을 옮길 것`,
    );
  });
}

test("⛔ 배너 margin이 상수다 — 인셋에서 계산하면 첫 호출 값이 굳는다", () => {
  const src = readSource("lib", "bannerNative.js");
  const m = /margin:\s*([^,]+)/.exec(src);
  assert.ok(m, "showBanner에 margin이 없다");
  const value = m[1].trim();
  assert.ok(
    /^(-?\d+|BANNER_MARGIN)$/.test(value),
    `margin이 상수가 아니다 (${value}) — showBanner는 처음 한 번만 불리므로 ` +
      `인셋에서 계산하면 그때 값이 굳는다. 인셋은 배경면(웹)의 lift가 흡수한다 (2.118)`,
  );
  assert.ok(
    !/safeArea|nset/.test(src),
    "bannerNative.js가 인셋을 참조한다 — 배너 자리는 상수여야 한다",
  );
});

test("⛔ 배너 margin과 배경면의 m이 **같은 값**이다 (갈리면 가운데가 아니다)", () => {
  const native = readSource("lib", "bannerNative.js");
  assert.ok(
    /margin:\s*BANNER_MARGIN/.test(native),
    "showBanner가 BANNER_MARGIN을 쓰지 않는다 — 두 값이 갈리면 배너가 " +
      "배경면 가운데에서 벗어난다",
  );
  assert.ok(
    native.includes('from "./adsApp.js"'),
    "BANNER_MARGIN을 adsApp.js에서 가져오지 않는다 — 값이 두 벌이 된다",
  );
});
