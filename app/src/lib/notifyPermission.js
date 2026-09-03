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

/**
 * **켤 때의 판단** — 순수 함수. 값으로 단언할 수 있게 꺼냈다 (2026-09-03).
 *
 * [왜 꺼냈나]
 *   "끄고 다시 켜면 안 켜진다"가 두 번 나왔다. 한 번은 가드가 사용자를 가둔 것이었고
 *   (⛔ 표식 permission), 두 번째는 재현하지 못했다. 판단이 setEnabled 안에 섞여
 *   있으면 **어느 갈래에서 막혔는지 값으로 확인할 수 없다.**
 *   ★ 그래서 갈래를 이름으로 만든다. 회귀가 갈래마다 값을 단언한다.
 *
 * @param {{userInitiated:boolean, offBy:string|null, outcome?:string}} state
 *   outcome은 **물어본 뒤**의 결과다. ask가 false면 묻지 않았으므로 무시된다.
 * @returns {{ask:boolean, ok:boolean, mark:"clear"|"permission"|"keep"}}
 *   ask   시스템에 물어도 되는가
 *   ok    켜도 되는가
 *   mark  OFF_BY 표식을 어떻게 할 것인가 — clear 지운다 · permission 남긴다 · keep 그대로
 */
export function enableDecision({ userInitiated = false, offBy = null, outcome } = {}) {
  // ⛔ 가드는 **자동 경로에만** 건다. 사용자가 누른 것은 통과시킨다 —
  //   막으면 한 번 거부한 사람이 영영 켤 수 없다(2026-09-03 실사용 결함).
  if (!userInitiated && offBy === OFF_BY.PERMISSION) {
    return { ask: false, ok: false, mark: "keep" };
  }
  if (outcome === PERMISSION.GRANTED) return { ask: true, ok: true, mark: "clear" };
  // ⚠ 거부일 때만 표식을 남긴다. unknown(못 읽음)은 아무것도 안 건드린다.
  if (outcome === PERMISSION.DENIED) return { ask: true, ok: false, mark: "permission" };
  return { ask: true, ok: false, mark: "keep" };
}

/**
 * **영구 거절인가** — 시스템이 팝업을 더 이상 띄우지 않는 상태 (2026-09-03 실측).
 *
 * [⛔ outcome과 다른 축이다 — 4번째 값으로 만들지 않는다]
 *   permissionOutcome은 "권한이 있나"를 셋으로 답한다. 이것은 "물어볼 수 있나"이고,
 *   둘은 갈래가 다르다. 4번째 값으로 끼워 넣으면 shouldTurnOff·enableDecision의
 *   기존 갈래를 **조용히 지나친다** — 이 파일이 처음부터 경계한 사고 유형이다.
 *   (2.107 ②가 「정확함」과 「깨움」을 갈라 둔 것과 같은 이유다.)
 *
 * [★ 어떻게 알 수 있나 — Capacitor가 이미 세고 있다]
 *   requestPermissions 결과가 올 때마다 Bridge.validatePermissions가
 *   shouldShowRequestPermissionRationale을 읽어 SharedPreferences(PluginPermStates)에
 *   적는다. rationale이 true면 "prompt-with-rationale", false면 **"denied"**.
 *   checkPermissions는 그 값을 그대로 웹에 돌려준다. 그래서 우리가 셀 것이 없다.
 *     아직 안 물음      prompt                  (플래그 없음)
 *     한 번 거절        prompt-with-rationale   (USER_SET)
 *     ★ 영구 거절       denied                  (USER_SET|USER_FIXED)
 *     허용             granted
 *
 * [⛔⛔ 물어본 **뒤**의 값만 믿는다]
 *   물어보기 **전** 값은 낡을 수 있다 — 실측했다. 캐시가 "denied"인 채로 OS 쪽
 *   USER_FIXED만 풀리면(설정에서 알림을 켰다 다시 끈 경우) 팝업을 띄울 수 있는데도
 *   캐시는 "denied" 그대로다. 그 값을 믿고 안내를 띄우면 **팝업이 뜰 수 있는
 *   상태에서 "설정으로 가라"고 말하게 된다.**
 *   ⚠ requestPermissions가 끝난 직후에는 안전하다 — validatePermissions가
 *     플러그인 콜백보다 **먼저** 돌아 캐시를 새로 쓴다(Plugin.triggerPermissionCallback).
 *
 * ⚠ Android 12 이하에서는 checkPermissions가 areNotificationsEnabled()를 문자열로
 *   준다. 거기서의 "denied"는 사용자가 설정에서 알림을 끈 것이고, 런타임 팝업 자체가
 *   없으므로 **안내할 내용이 같다**(설정에서 켜야 한다). 그래서 갈래를 안 나눈다.
 *
 * @param {unknown} raw  물어본 **뒤** checkPermissions()가 돌려준 것
 * @param {boolean} threw  호출이 던졌거나 플러그인이 없으면 true
 */
export function isBlocked(raw, threw = false) {
  // ⛔ 못 읽었으면 **아니라고 답한다.** 모르는 상태에서 "설정으로 가라"고
  //   말하는 것이 잘못 안내하는 쪽이다 — 안전한 방향은 아무 말도 안 하는 것이다.
  if (threw) return false;
  if (!raw || typeof raw !== "object") return false;
  // ⛔ 화이트리스트다. 정확히 "denied"만이다 — prompt·prompt-with-rationale은
  //   아직 물어볼 수 있는 상태이고, 모르는 값은 물어볼 수 있는 쪽으로 센다.
  return raw.display === "denied";
}
