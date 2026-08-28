/**
 * 화면 흐름 상태 기계 — 입력·로딩·결과 사이의 **모든** 이동을 여기서 정한다.
 *
 * [왜 App.jsx에서 빼냈나 — 2026-08-28]
 *   "분류 실패에서 돌아오면 입력창을 비운다"(2026-08-25 사용자 결정)가
 *   **한 경로에서 지켜지지 않고 있었다.** 고친 곳은 두 곳(`reset`·`resetToPicker`)
 *   이었는데, 분류가 **대분류까지만** 맞은 경우(RESULT.CATEGORY)는 결과 화면을
 *   거치지 않고 곧장 고르는 화면으로 가고, 거기서 '직접 적기'로 돌아오면
 *   친 글자가 그대로 남았다. 세 번째 경로였고 아무도 그것을 세지 않았다.
 *
 *   회귀는 있었지만 **소스 문자열**을 검사했다 — `setText("")`가 한 곳인지,
 *   `onBack={resetToPicker}`인지. 그 검사는 전부 통과한 채로 화면이 고장나 있었다.
 *   ⚠ **이동을 검사하려면 이동이 값이어야 한다.** 그래서 상태 기계를 값으로 꺼냈다.
 *   test/flow.test.js가 이 그래프를 실제로 걸어 다니며 불변식을 검사한다.
 *
 * [불변식 — 이 파일이 지키는 약속]
 *   ★ 입력창의 글자는 **사용자가 직접 친 것일 때만** 남는다.
 *     앱이 한 번 응답하면(ANSWER) 그 뒤로 입력창이 다시 보이는 모든 상태에서
 *     비어 있다. 사용자가 스스로 고르는 화면을 구경하다 돌아오는 것(BACK)은
 *     응답이 아니므로 글자를 지우지 않는다 — 그건 아직 사용자의 문장이다.
 *
 * ⚠ 여기에 부수효과를 넣지 말 것. 순수해야 테스트가 그래프를 걸을 수 있다.
 *   무작위 문구 선택(pickMessage)처럼 순수하지 않은 것은 **행동의 payload로**
 *   받는다(placeholder). 고르는 일은 호출부가 하고 이 파일은 담기만 한다.
 */

import { RESULT } from "./classify.js";

export const PHASE = {
  INPUT: "input",
  LOADING: "loading",
  RESULT: "result",
};

export const MODE = {
  TEXT: "text",
  SELECT: "select",
};

export const FLOW = {
  /** 사용자가 입력창에 글자를 친다. **글자가 남는 유일한 근거다.** */
  TYPE: "type",
  /** 입력 화면에서 스스로 고르는 화면으로 간다 (앱의 응답이 아니다). */
  SWITCH_TO_PICKER: "switchToPicker",
  /** 고르는 화면 1단계에서 대분류를 골랐다. */
  PICK_CATEGORY: "pickCategory",
  /** 고르는 화면의 '한 걸음 뒤로'. 2단계면 1단계로, 1단계면 직접 적기로. */
  BACK: "back",
  /** 분류를 시작한다 (로딩 화면). */
  SUBMIT: "submit",
  /** 분류가 끝났다 — 결과·위기·빈 입력·분류 실패·대분류까지. */
  ANSWER: "answer",
  /** 결과나 실패 화면에서 입력 화면으로 돌아온다. */
  RESET: "reset",
  /** 분류 실패에서 고르는 화면으로 나간다. */
  RESET_TO_PICKER: "resetToPicker",
  /** 안내 문구만 바꾼다 (첫 로딩에서 한 번). */
  PLACEHOLDER: "placeholder",
};

export function initialFlow(placeholder = "") {
  return {
    phase: PHASE.INPUT,
    mode: MODE.TEXT,
    text: "",
    result: null,
    selectedCategory: null,
    placeholder,
  };
}

/**
 * 입력 화면으로 들어간다. **입력창을 비우는 유일한 자리다.**
 *
 * [왜 비우는가 — 2026-08-25 사용자 결정]
 *   마음이 힘들어 적은 문장이 화면에 그대로 남아 있는 것이 이 앱에 맞지 않다.
 *   결과를 보고 돌아오든, 못 알아들어서 돌아오든, 대분류까지만 알아들어
 *   되묻든 같다 — **셋 다 앱이 응답한 뒤**다.
 */
function enterInput(state, mode, category, placeholder) {
  return {
    phase: PHASE.INPUT,
    mode,
    text: "",
    result: null,
    selectedCategory: category ?? null,
    placeholder: placeholder ?? state.placeholder,
  };
}

export function flowReducer(state, action) {
  switch (action.type) {
    case FLOW.TYPE:
      return { ...state, text: action.text };

    case FLOW.SWITCH_TO_PICKER:
      // 사용자가 스스로 옮겨간 것이다. 친 글자는 아직 사용자의 것이라 남긴다.
      return { ...state, mode: MODE.SELECT };

    case FLOW.PICK_CATEGORY:
      return { ...state, selectedCategory: action.category };

    case FLOW.BACK:
      return state.selectedCategory
        ? { ...state, selectedCategory: null }
        : { ...state, mode: MODE.TEXT };

    case FLOW.SUBMIT:
      return { ...state, phase: PHASE.LOADING };

    case FLOW.ANSWER:
      // ⚠ 대분류까지만 맞은 경우는 **결과 화면을 거치지 않는다.** 곧장 고르는
      //   화면으로 되묻고, 그것도 앱의 응답이므로 여기서 입력창을 비운다.
      //   이 한 줄이 2026-08-28에 고친 결함이다 (그전에는 화면만 바꿨다).
      if (action.outcome.kind === RESULT.CATEGORY) {
        return enterInput(state, MODE.SELECT, action.category, action.placeholder);
      }
      return { ...state, phase: PHASE.RESULT, result: action.outcome };

    case FLOW.RESET:
      return enterInput(state, MODE.TEXT, null, action.placeholder);

    case FLOW.RESET_TO_PICKER:
      return enterInput(state, MODE.SELECT, null, action.placeholder);

    case FLOW.PLACEHOLDER:
      return { ...state, placeholder: action.placeholder };

    default:
      return state;
  }
}

/** 지금 입력창이 화면에 보이는가 — 불변식을 검사할 지점이다. */
export function inputBoxVisible(state) {
  return state.phase === PHASE.INPUT && state.mode === MODE.TEXT;
}

/** 앱의 응답에 해당하는 행동. 이 뒤로는 입력창이 비어 있어야 한다. */
export const ANSWER_ACTIONS = [FLOW.ANSWER, FLOW.RESET, FLOW.RESET_TO_PICKER];
