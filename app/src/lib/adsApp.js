/**
 * 앱 전용 광고 — 최하단 고정 띠배너의 **판단**만 여기 있다.
 * 네이티브 호출은 이 파일에 없다 (그쪽은 bannerNative.js).
 *
 * ⛔ **ads.js와 다른 물건이다.** ads.js는 웹(AdSense)이 목록 **항목 사이**에
 *   끼우는 자리를 계산한다. 여기는 앱(AdMob)이 화면 **최하단에 떠 있는 띠**를
 *   언제 보일지 정한다. 두 매체가 갈리는 것이 전제다 (HANDOFF 2.96).
 *
 * [⛔ 기본이 숨김이다 — 이 파일의 설계 전체가 여기서 나온다]
 *   "화면을 떠날 때 숨긴다"로 짜면 브리지 왕복 지연 동안 띠가 남는다.
 *   고정 띠는 화면이 바뀌어도 자리를 지키므로 그 한 프레임이 실제 노출이다.
 *   그래서 뒤집는다 — **허용 화면일 때만 보인다.**
 *   ★ 노출 위험의 방향이 바뀐다. 늦게 뜨는 것은 안전하고, 늦게 사라지는 것이 사고다.
 *   ⚠ 콜드 스타트도 이것으로 풀린다 — 알림을 탭해 앱이 처음 뜰 때 첫 화면이
 *     DailyVerse다. 기본이 숨김이면 배너를 **아예 만들지 않는다.**
 *
 * [⚠ 회귀는 소스 텍스트로 짜지 않는다]
 *   지금 notify.test.js와 AD_FREE_SCREENS는 화면 파일 안에 광고 토큰이 있는지
 *   본다. 띠는 Shell에서 그리므로 그 파일들에 토큰이 남지 않는다 —
 *   **통과하면서 띠는 화면에 남는다.** 그래서 판단을 순수 함수로 꺼내
 *   테스트가 화면 종류마다 직접 단언하게 한다.
 */

/**
 * 화면 종류. **App.jsx의 분기와 하나씩 짝이다.**
 *
 * ⛔ 여기 값을 늘리면 App.jsx의 분기도 늘어야 하고, 그 반대도 같다.
 *   목록이 갈리면 **새 화면이 조용히 광고 허용으로 들어온다** — 회귀가 그것을 막는다.
 */
export const SCREEN = Object.freeze({
  DAILY_VERSE: "dailyVerse", // 알림으로 열린 구절
  ABOUT: "about",
  LOADING: "loading",
  CRISIS: "crisis",
  RESULT: "result", // 구절 + 이어서 읽기 · 말씀 · 찬양 탭
  EMPTY: "empty", // 입력이 비었다
  NO_MATCH: "noMatch", // 분류 실패
  INPUT: "input",
});

/**
 * 띠 높이. LARGE_BANNER 320×100의 100이다 (HANDOFF 2.96 안 1).
 *
 * ★ **상수인 것이 이 안을 고른 이유다.** 적응형 배너는 높이를 SDK가 정하므로
 *   하단 요소 조정을 런타임 값으로 해야 하고, 그러면 띠가 뜨기 전과 후에
 *   레이아웃이 한 번 움직인다.
 * ⚠ 폭 320은 고정이라 360dp 화면에서 좌우 20dp씩 남는다. 감수한 대가다.
 */
export const BANNER_HEIGHT = 100;

/**
 * 지금 어느 화면인가. **App.jsx의 분기 순서를 그대로 옮긴 것이다.**
 *
 * ⚠ 순서가 곧 우선순위다. dailyVerse가 맨 앞인 것은 "알림을 탭해서 들어온
 *   사람이 보고 싶은 것은 그 구절"이기 때문이고(App.jsx 주석), 그 규칙이
 *   여기서도 같아야 한다. 회귀가 App.jsx의 분기 순서와 대조한다.
 *
 * @param {{dailyVerse?: unknown, showAbout?: boolean, phase?: string,
 *          resultKind?: string}} state
 * @returns {string} SCREEN의 값 하나
 */
export function currentScreen({ dailyVerse, showAbout, phase, resultKind } = {}) {
  if (dailyVerse) return SCREEN.DAILY_VERSE;
  if (showAbout) return SCREEN.ABOUT;
  if (phase === "loading") return SCREEN.LOADING;
  if (phase === "result") {
    if (resultKind === "crisis") return SCREEN.CRISIS;
    if (resultKind === "ok") return SCREEN.RESULT;
    if (resultKind === "empty") return SCREEN.EMPTY;
    return SCREEN.NO_MATCH;
  }
  return SCREEN.INPUT;
}

/**
 * 이 화면에 띠를 보일 것인가.
 *
 * ⛔ **허용 목록이다. 금지 목록이 아니다.** 새 화면이 생기면 기본이 "안 보임"이라야
 *   조용히 새는 일이 없다. 금지 목록으로 짜면 목록에 추가하는 것을 잊는 날
 *   광고가 위기 화면에 뜬다.
 *
 * 광고 있음  결과 화면 하나뿐이다 — 이어서 읽기 · 말씀 · 찬양 탭이 전부 그 안에 있다
 *           (HANDOFF 2.95). 탭별로 갈릴 것이 없어 판단이 화면 하나로 끝난다
 * 광고 없음  위기 화면 · 알림으로 열린 구절 — **이 앱의 약속이다**(About 광고 절)
 *           입력·로딩·About·실패 화면도 안 보인다. 보일 이유가 없다
 */
export function bannerVisible(screen) {
  return screen === SCREEN.RESULT;
}

/**
 * 하단에 비워 둘 높이(px). 떠 있는 버튼을 올리고 문서 끝을 미는 값이다.
 *
 * ⛔ **광고가 채워지지 않으면 0이다 (사용자 결정 · 2026-08-31).**
 *   빈 띠가 하단 100px을 먹는 것은 광고 없이 자리만 차지하는 최악의 상태다.
 *   웹에서 AD_SLOT이 비면 요소를 아예 안 그리기로 한 것과 **같은 원칙**이다.
 *   ⚠ 그래서 이 값은 "보일 화면인가"만으로 정해지지 않는다. 실제로 채워졌는지를
 *     AdMob이 알려 준 뒤에야 100이 된다. 로드 실패·미채움이면 다시 0으로 접는다.
 *
 * @param {{screen: string, filled?: boolean}} state
 */
export function bannerSpace({ screen, filled = false } = {}) {
  return bannerVisible(screen) && filled ? BANNER_HEIGHT : 0;
}
