/**
 * 알림 권한 3값 판정 — **값으로** 단언한다 (소스 문자열 검사가 아니다).
 *
 * 여기서 지키는 것
 *   · denied일 때만 저장값이 내려간다
 *   · 못 읽으면(throw · 플러그인 없음 · 이상한 값) **아무것도 안 건드린다**
 *   · 모르는 문자열은 unknown이다 (화이트리스트가 살아 있는가)
 *   · "prompt"는 denied다 — 고치려는 구멍이 정확히 그 상태다
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  OFF_BY,
  PERMISSION,
  enableDecision,
  isBlocked,
  permissionOutcome,
  shouldTurnOff,
} from "../src/lib/notifyPermission.js";
import { readSource } from "./helpers.js";

const notifySrc = readSource("lib", "notify.js");

/* --- 판정 --------------------------------------------------------------- */

test("granted는 granted다", () => {
  assert.equal(permissionOutcome({ display: "granted" }), PERMISSION.GRANTED);
});

test("★ prompt는 denied다 — 고치려는 구멍이 이 상태다", () => {
  assert.equal(permissionOutcome({ display: "prompt" }), PERMISSION.DENIED);
  assert.equal(
    permissionOutcome({ display: "prompt-with-rationale" }),
    PERMISSION.DENIED,
  );
  assert.equal(permissionOutcome({ display: "denied" }), PERMISSION.DENIED);
});

test("⛔ 못 읽은 경우는 전부 unknown이다 — denied로 떨어지면 안 된다", () => {
  assert.equal(permissionOutcome(null, true), PERMISSION.UNKNOWN, "throw");
  assert.equal(permissionOutcome(null), PERMISSION.UNKNOWN, "플러그인 없음");
  assert.equal(permissionOutcome(undefined), PERMISSION.UNKNOWN);
  assert.equal(permissionOutcome("granted"), PERMISSION.UNKNOWN, "문자열이 왔다");
  assert.equal(permissionOutcome({}), PERMISSION.UNKNOWN, "display가 없다");
  assert.equal(permissionOutcome({ display: 1 }), PERMISSION.UNKNOWN);
});

test("⛔ 처음 보는 문자열은 unknown이다 (화이트리스트 판정)", () => {
  for (const v of ["limited", "provisional", "restricted", "GRANTED", ""]) {
    assert.equal(
      permissionOutcome({ display: v }),
      PERMISSION.UNKNOWN,
      `"${v}"가 denied로 떨어졌다 — 모르는 값은 unknown이라야 안전하다`,
    );
  }
});

test("granted가 threw보다 앞서지 않는다 — 던졌으면 결과가 뭐든 unknown", () => {
  assert.equal(permissionOutcome({ display: "granted" }, true), PERMISSION.UNKNOWN);
});

/* --- 저장값을 내릴 것인가 ------------------------------------------------- */

test("denied이고 켜져 있을 때만 내린다", () => {
  assert.equal(shouldTurnOff({ outcome: PERMISSION.DENIED, storedOn: true }), true);
});

test("⛔ unknown에서는 내리지 않는다 — 일시적 실패에 설정이 꺼지면 안 된다", () => {
  assert.equal(shouldTurnOff({ outcome: PERMISSION.UNKNOWN, storedOn: true }), false);
});

test("granted면 내리지 않는다", () => {
  assert.equal(shouldTurnOff({ outcome: PERMISSION.GRANTED, storedOn: true }), false);
});

test("이미 꺼져 있으면 쓰지 않는다 (불필요한 쓰기·경합 방지)", () => {
  assert.equal(shouldTurnOff({ outcome: PERMISSION.DENIED, storedOn: false }), false);
  assert.equal(shouldTurnOff(), false);
});

/* --- 호출부가 실제로 이 판정을 쓰는가 -------------------------------------- */

test("⛔ notify.js가 display를 직접 비교하지 않는다 (판정이 한 곳이어야 한다)", () => {
  assert.ok(
    !/display\s*!==\s*"granted"/.test(notifySrc),
    "옛 2값 비교가 남아 있다 — 판정이 두 곳으로 갈리면 한쪽만 고쳐진다",
  );
  assert.ok(
    notifySrc.includes("permissionOutcome("),
    "notify.js가 permissionOutcome을 쓰지 않는다",
  );
  assert.ok(
    notifySrc.includes("shouldTurnOff("),
    "notify.js가 shouldTurnOff를 쓰지 않는다",
  );
});

test("⛔ 꺼진 이유를 남긴다 — 사용자가 끈 것과 권한이 없어 내려간 것을 가른다", () => {
  assert.ok(
    notifySrc.includes("OFF_BY.USER"),
    "setEnabled(false)가 사용자 표식을 안 남긴다",
  );
  assert.ok(
    notifySrc.includes("OFF_BY.PERMISSION"),
    "권한 경로가 표식을 안 남긴다 — D가 이것을 못 가리면 영영 안 묻는다",
  );
  assert.equal(OFF_BY.USER, "user");
  assert.equal(OFF_BY.PERMISSION, "permission");
});

/* --- 끄고 다시 켜는 길 — **값으로** 못 박는다 (2026-09-03) ------------------
 *
 * ⛔ "끄고 다시 켜면 안 켜진다"가 두 번 나왔다. 게이트로 고정한다.
 */

test("★★ 끈 뒤(OFF_BY=user)에 사용자가 켜면 **막히지 않는다**", () => {
  const d = enableDecision({ userInitiated: true, offBy: OFF_BY.USER });
  assert.equal(d.ask, true, "사용자가 껐다는 표식이 다시 켜는 것을 막는다");
});

test("★★ 거부 표식이 있어도 **사용자가 누르면** 묻는다 (막다른 길 방지)", () => {
  const d = enableDecision({ userInitiated: true, offBy: OFF_BY.PERMISSION });
  assert.equal(d.ask, true);
});

test("⛔ 자동 경로에서 거부 표식이 있으면 묻지 않는다", () => {
  const d = enableDecision({ userInitiated: false, offBy: OFF_BY.PERMISSION });
  assert.deepEqual(d, { ask: false, ok: false, mark: "keep" });
});

test("자동 경로라도 표식이 user면 묻는다 — 끈 것과 거부는 다르다", () => {
  assert.equal(enableDecision({ userInitiated: false, offBy: OFF_BY.USER }).ask, true);
  assert.equal(enableDecision({ userInitiated: false, offBy: null }).ask, true);
});

test("허용되면 켜고 표식을 지운다", () => {
  const d = enableDecision({ userInitiated: true, offBy: OFF_BY.USER, outcome: PERMISSION.GRANTED });
  assert.deepEqual(d, { ask: true, ok: true, mark: "clear" });
});

test("거부되면 못 켜고 표식을 남긴다", () => {
  const d = enableDecision({ userInitiated: true, offBy: null, outcome: PERMISSION.DENIED });
  assert.deepEqual(d, { ask: true, ok: false, mark: "permission" });
});

test("⛔ unknown이면 못 켜되 **표식을 건드리지 않는다**", () => {
  const d = enableDecision({ userInitiated: true, offBy: OFF_BY.USER, outcome: PERMISSION.UNKNOWN });
  assert.deepEqual(d, { ask: true, ok: false, mark: "keep" });
});

test("⛔ notify.js가 판단을 흩뜨리지 않는다 — enableDecision 한 곳이다", () => {
  assert.ok(notifySrc.includes("enableDecision("), "setEnabled가 판단 함수를 안 쓴다");
  assert.ok(
    !/offBy === OFF_BY\.PERMISSION/.test(notifySrc),
    "notify.js가 표식을 직접 비교한다 — 갈래가 두 곳으로 흩어진다",
  );
});

/* --- 영구 거절 판정 (2026-09-03) ---------------------------------------- */

test("★ 영구 거절만 blocked다 — display가 정확히 denied일 때", () => {
  assert.equal(isBlocked({ display: "denied" }), true);
});

test("⛔ 아직 물어볼 수 있는 상태는 blocked가 아니다", () => {
  // 이 둘에서 안내를 띄우면 **팝업이 뜰 수 있는데** 설정으로 보내게 된다.
  assert.equal(isBlocked({ display: "prompt" }), false, "아직 안 물음");
  assert.equal(isBlocked({ display: "prompt-with-rationale" }), false, "한 번 거절");
  assert.equal(isBlocked({ display: "granted" }), false, "허용");
});

test("⛔ 못 읽으면 blocked가 아니다 — 모르면 아무 말도 안 한다", () => {
  assert.equal(isBlocked(null, true), false, "throw");
  assert.equal(isBlocked(null), false, "플러그인 없음");
  assert.equal(isBlocked(undefined), false);
  assert.equal(isBlocked("denied"), false, "문자열이 왔다");
  assert.equal(isBlocked({}), false, "display가 없다");
  assert.equal(isBlocked({ display: 1 }), false);
  assert.equal(isBlocked({ display: "denied" }, true), false, "threw가 이긴다");
});

test("⛔ 모르는 값은 물어볼 수 있는 쪽으로 센다", () => {
  for (const v of ["blocked", "restricted", "limited", "DENIED", ""]) {
    assert.equal(isBlocked({ display: v }), false, `${v}가 blocked로 샜다`);
  }
});

test("★ blocked는 outcome과 **다른 축**이다 — 4번째 값이 아니다", () => {
  // 영구 거절은 permissionOutcome에서는 여전히 denied다. 그래야 A′(shouldTurnOff)와
  // enableDecision의 기존 갈래가 그대로 돈다.
  assert.equal(permissionOutcome({ display: "denied" }), PERMISSION.DENIED);
  assert.equal(isBlocked({ display: "denied" }), true);
  // 한 번 거절은 outcome은 같고 blocked만 다르다 — 축이 갈린다는 증거다.
  assert.equal(permissionOutcome({ display: "prompt-with-rationale" }), PERMISSION.DENIED);
  assert.equal(isBlocked({ display: "prompt-with-rationale" }), false);
});

test("⛔ notify.js가 display를 직접 비교하지 않는다 — isBlocked 한 곳이다", () => {
  assert.ok(notifySrc.includes("isBlocked("), "isPermissionBlocked가 판정 함수를 안 쓴다");
  assert.ok(
    !/display === "denied"/.test(notifySrc),
    "notify.js가 display를 직접 본다 — 판정이 두 곳으로 갈린다",
  );
});
