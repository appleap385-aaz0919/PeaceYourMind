/**
 * 하드웨어 뒤로가기 — 지금 화면에서 **무엇을 할지**만 정한다 (HANDOFF 2.136 · 2.146).
 *
 * [잡는 것은 네이티브, 판단은 여기]
 *   Capacitor 6부터 뒤로가기는 @capacitor/app이 없으면 웹에 오지 않는다(2.136 실측).
 *   그래서 MainActivity가 잡아 window[BACK_HANDLER]()에 묻고, true면 소비하고
 *   아니면 플랫폼 기본(백그라운드)으로 넘긴다. 무엇을 할지는 이 파일이 정한다.
 *
 * [순서 — App.jsx가 화면을 고르는 순서와 같다]
 *   알림 구절 → About → (로딩) → 결과 → 입력. 위에 덮인 것부터 닫는다.
 *   ★ 알림 구절과 About은 **덮개**다. 닫으면 아래 깔린 화면이 그대로 돌아온다 —
 *     알림 구절도 「덮개만 닫기」(안 ㄱ · 2026-10-06 사용자 결정). 알림을 누를 때
 *     사용자가 보던 화면으로 돌아가는 것이 안드로이드 관습이다.
 *   ⛔ 「지금 마음을 적어볼까요」(입력으로 가며 비움)와 목적지가 갈린다. 버튼은
 *     「새로 시작」이고 뒤로가기는 「취소」다 — 달라야 맞다.
 *
 * ⚠ 순수 함수로 둔다. 상태를 바꾸는 것은 App.jsx다 — 여기는 판단표만 갖는다.
 */

import { MODE, PHASE } from "./flow.js";

/** ⛔ MainActivity의 JS_BACK이 부르는 이름이다. 갈리면 뒤로가기가 조용히 앱을 내리기만 한다. */
export const BACK_HANDLER = "pymBack";

export const BACK = {
  /** 알림 구절 덮개를 닫는다 — 아래 화면이 돌아온다. */
  CLOSE_DAILY_VERSE: "closeDailyVerse",
  /** About을 닫는다 — 들어온 화면이 돌아온다. */
  CLOSE_ABOUT: "closeAbout",
  /** 결과에서 초기 입력 화면으로 (FLOW.RETRACE · 글자를 남긴다). */
  RETRACE: "retrace",
  /** 고르는 화면의 한 걸음 뒤 — 세분류 → 대분류 → 직접 적기 (FLOW.BACK). */
  STEP_BACK: "stepBack",
  /** 소비하지 않는다 — 초기 입력 화면·로딩. 플랫폼 기본(백그라운드)이다. */
  NONE: "none",
};

export function backAction({ dailyVerse, showAbout, flow }) {
  if (dailyVerse) return BACK.CLOSE_DAILY_VERSE;
  if (showAbout) return BACK.CLOSE_ABOUT;
  if (flow.phase === PHASE.RESULT) return BACK.RETRACE;
  if (flow.phase === PHASE.INPUT && flow.mode === MODE.SELECT) return BACK.STEP_BACK;
  // ⚠ 로딩은 1초 남짓이다. 그 사이 누르면 앱이 내려가고, 분류는 계속돼
  //   돌아오면 결과가 떠 있다. 로딩을 끊는 갈래는 만들지 않았다.
  return BACK.NONE;
}
