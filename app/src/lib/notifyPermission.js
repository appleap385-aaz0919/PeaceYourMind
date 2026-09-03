/**
 * 알림 권한 상태를 **셋으로** 읽는다 — 순수 함수만 있다.
 *
 * [⛔ 왜 둘이 아니라 셋인가 — HANDOFF 2.116 ②]
 *   예전 코드는 이렇게 짜여 있었다.
 *     try  { if (status.display !== "granted") return 0; }
 *     catch { return 0; }
 *   **거부(denied)** 와 **못 읽음(throw)** 이 똑같이 0이었다. 여기에 곧장
 *   "꺼진 것으로 저장하자"를 넣으면 **일시적 실패에 사용자 설정이 꺼진다.**
 *   플러그인이 한 번 삐끗하면 알림이 조용히 영영 멎는다.
 *
 * [⛔ 화이트리스트로 판정한다]
 *   "granted가 아니면 denied"로 짜면 플러그인이 새 값을 돌려주는 날
 *   설정이 조용히 꺼진다. **모르는 값은 unknown이라야 안전한 방향이다** —
 *   unknown은 아무것도 건드리지 않기 때문이다.
 *
 * [★ "prompt"는 denied 쪽이다]
 *   Android 13+ 신규 설치의 상태가 정확히 "prompt"(아직 묻지 않음)이고,
 *   그것이 고치려는 구멍 그 자체다. 저장값은 기본 켜짐인데 예약은 0건이라
 *   화면만 「켜짐」으로 보이던 상태다.
 *   ⚠ Android 12 이하는 checkPermissions가 granted를 주므로 **영향이 없다.**
 */

export const PERMISSION = Object.freeze({
  GRANTED: "granted",
  DENIED: "denied",
  UNKNOWN: "unknown",
});

/**
 * ⛔ **여기 없는 값은 전부 unknown이다.** 목록을 늘릴 때는 그 값이 정말로
 *   "물어봤고 못 받았다"를 뜻하는지 확인할 것. Capacitor의 PermissionState는
 *   granted · denied · prompt · prompt-with-rationale 넷이다.
 */
const KNOWN_NOT_GRANTED = Object.freeze([
  "denied",
  "prompt",
  "prompt-with-rationale",
]);

/**
 * @param {unknown} raw  checkPermissions()가 돌려준 것 (없으면 null)
 * @param {boolean} threw  호출이 던졌거나 플러그인이 없으면 true
 * @returns {"granted"|"denied"|"unknown"}
 */
export function permissionOutcome(raw, threw = false) {
  if (threw) return PERMISSION.UNKNOWN;
  if (!raw || typeof raw !== "object") return PERMISSION.UNKNOWN;
  const display = raw.display;
  if (typeof display !== "string") return PERMISSION.UNKNOWN;
  if (display === "granted") return PERMISSION.GRANTED;
  if (KNOWN_NOT_GRANTED.includes(display)) return PERMISSION.DENIED;
  return PERMISSION.UNKNOWN;
}

/**
 * 저장값을 내려야 하는가. **denied일 때만이다.**
 *
 * ⚠ 이미 꺼져 있으면 쓰지 않는다 — 불필요한 쓰기와 경합을 피한다.
 *
 * @param {{outcome: string, storedOn: boolean}} state
 */
export function shouldTurnOff({ outcome, storedOn } = {}) {
  return outcome === PERMISSION.DENIED && storedOn === true;
}

/**
 * 왜 꺼졌는가. **D(맥락이 생긴 순간에 묻기)가 이 값을 본다.**
 *
 * ⛔ 사용자가 손으로 끈 것과 권한이 없어 내려간 것을 **가르지 않으면**,
 *   A′가 저장값을 내린 뒤 D가 "사용자가 껐다"고 오해해 영영 묻지 않는다.
 *   두 안이 서로를 막는 자리라 표식이 필요하다.
 */
export const OFF_BY = Object.freeze({
  USER: "user", // About 토글로 직접 껐다 — ⛔ D는 다시 묻지 않는다
  PERMISSION: "permission", // 권한이 없어 내려갔다 — D가 물을 수 있다
});
