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
 * 띠 높이. **표준 배너 320×50의 50이다** (2026-09-02 · HANDOFF 2.104).
 *
 * ★ **상수인 것이 이 안을 고른 이유다.** 적응형 배너는 높이를 SDK가 정하므로
 *   하단 요소 조정을 런타임 값으로 해야 하고, 그러면 띠가 뜨기 전과 후에
 *   레이아웃이 한 번 움직인다.
 * ⚠ 폭 320은 고정이라 360dp 화면에서 좌우 20dp씩 남는다.
 *   ★ 그 20dp가 이제 **배경면이 드러나는 자리**다 — 감수한 대가가 쓸모가 됐다.
 *
 * [왜 100에서 내려왔나 — 계산이 아니라 관측이 뒤집었다]
 *   100dp는 360×640dp 화면에서 세로의 약 16%다. 측정은 맞았지만(300px =
 *   100.0dp · format=320x100_as) **실기기에서 컸다.** 사용자가 화면을 보고 내렸다.
 * ⚠ 웹(AdSense)의 AD_HEIGHT는 **100 그대로다.** 매체가 갈렸으면 값도 갈린다 —
 *   ads.js의 그 상수 옆에 근거를 적어 두었다.
 */
export const BANNER_HEIGHT = 50;

/**
 * 띠 **위로** 비워 두는 간격 — ⛔ **둘이다.** 인셋을 읽을 수 있는가로 갈린다.
 *
 * [왜 둘인가 — 2026-09-02 · HANDOFF 2.112]
 *   배너는 화면 맨 아래가 아니라 **하단 시스템 인셋만큼 위에** 앉는다.
 *   배경면 높이 = 50 + safeArea + GAP 이므로
 *     위 여백 = (50 + safeArea + GAP) − (인셋 + 50) = **safeArea + GAP − 인셋**
 *
 *   ★ 갈래 A(WebView ≥140)는 safeArea = 인셋이라 **위 여백이 GAP으로 고정된다** —
 *     인셋이 24든 48이든 상관없다. 상한을 가정할 필요가 없다
 *   ⛔ 갈래 B(WebView <140)는 safeArea가 **0으로 주입된다**(2.103 실측).
 *     인셋을 모르므로 GAP이 최악(3버튼 48dp)을 흡수해야 음수가 안 된다
 *
 * ⚠ 판정이 틀려도 **안전한 방향이다** — safeArea를 0으로 잘못 읽으면
 *   UNKNOWN(48)이 적용되어 여백이 넉넉해진다. 반대 방향(갈래 B인데 safeArea가
 *   실제 인셋보다 작게 잡히는 경우)만 음수가 될 수 있는데, 그러려면 Capacitor가
 *   0이 아닌 값을 주입해야 한다 — 갈래 B에서는 코드가 0을 넣는다
 */
const BANNER_GAP_INSET_KNOWN = 24;
const BANNER_GAP_INSET_UNKNOWN = 48;

/**
 * ★ **상하 여백 m** — 배너가 배경면 **가운데** 놓이게 하는 값 (2026-09-03 · 2.118 안 2).
 *
 * [요구 사양 ④] 배경면의 위·아래 여백이 같다. 그래서 배경면 높이 = 50 + 2m 이다.
 * ⛔ **네이티브 배너의 margin과 같은 값이다** (bannerNative.js가 이 값을 넘긴다).
 *   둘이 갈리면 배너가 가운데에서 벗어난다 — 회귀가 그것을 단언한다.
 * ★ **상수여야 한다.** 인셋에서 계산하면 showBanner 첫 호출 값이 굳는다.
 *   인셋은 배경면(웹)이 lift로 흡수하므로 이 값은 인셋과 무관하다.
 * ⚠ m에 **기하적 상한은 없다** — 세 갈래 어디서도 음수가 생기지 않는다.
 *   남는 상한은 심미 판단이다: 배경면(50+2m)이 화면의 몇 %를 먹는가.
 *   m=12 → 74dp(휴대폰 878.7dp의 8.4%) · m=16 → 82dp(9.3%) · m=24 → 98dp(11.2%)
 */
export const BANNER_MARGIN = 16;

/** 주입된 참 인셋이 쓸 만한 값인가. ⛔ 모르면 폴백으로 간다 — 그쪽이 음수가 안 된다. */
function usableInset(v) {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}

/**
 * ⛔ **두 상수를 밖에서 못 바꾸게 묶어 둔다.** 회귀가 관계식을 단언한다.
 * ⚠ UNKNOWN은 "갈래 B에서 가정하는 인셋 상한"이다. 알려진 최대는 3버튼 48dp이고,
 *   그보다 큰 기기가 없다고 **보장할 수 없다** — 갈래 A는 읽으니 이 가정이 필요 없다
 */
export const BANNER_GAP = Object.freeze({
  insetKnown: BANNER_GAP_INSET_KNOWN,
  insetUnknown: BANNER_GAP_INSET_UNKNOWN,
});

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
 * 겹친 배너 요청을 어떻게 처리하는가 — **순수 함수**. (2026-09-04 · HANDOFF 2.126)
 *
 * [⛔ 왜 이 판단이 밖으로 나왔나 — 깃발 하나가 결함을 만들었다]
 *   전에는 bannerNative.js가 `if (created) hideBanner()` 로 숨겼다.
 *   `created`는 showBanner가 **완주한 뒤에야** true가 되는데, 숨기기는 그
 *   깃발을 **문 앞에서** 본다. 그래서 배너를 만드는 창(에뮬 실측 0.59초) 안에
 *   결과 화면을 떠나면 hide가 통째로 건너뛰어지고, 뒤늦게 완주한 배너가
 *   **떠난 화면 위에 갇혔다.** About 본문과 알림 구절 본문을 가렸다.
 *   ★ 로그가 그것을 그대로 보여줬다 — `요청 shown=false created=false`.
 *
 * [★ 규칙 셋]
 *   ㄱ **숨기기는 조건이 없다.** 만든 적 없을 때 불러도 무해하다(플러그인이
 *     거부하고, 거부는 이제 로그에 남는다). 반대로 건너뛰면 배너가 갇힌다
 *   ㄴ **만드는 중이면 또 만들지 않는다.** 플러그인의 showBanner는 두 번째
 *     호출에서 call.resolve()를 부르지 않는다(BannerExecutor.java:66) —
 *     약속이 영영 안 풀린다. 그래서 skip이다
 *   ㄷ **마지막 요청이 이긴다.** wanted에 적어 두고 bannerSettled가 그것을 본다
 *
 * @param {{created:boolean, creating:boolean, wanted:boolean}} state
 * @param {boolean} shown 부르는 쪽이 판정한 "보여야 하는가"
 * @returns {{action:"hide"|"resume"|"skip"|"create", state:object}}
 */
export function bannerRequest(state, shown) {
  const next = { ...state, wanted: shown };
  if (!shown) return { action: "hide", state: next };
  if (next.created) return { action: "resume", state: next };
  if (next.creating) return { action: "skip", state: next };
  return { action: "create", state: { ...next, creating: true } };
}

/**
 * 배너를 다 만들었다(또는 만들다 실패했다) — **그 사이에 화면이 바뀌었는가.**
 *
 * ⛔ 이것이 **최후 방어**다. ㄱ(조건 없는 숨기기)만으로는 모자란다 —
 *   브리지 스레드 순서는 보장이 없어 hide가 show보다 먼저 닿으면
 *   플러그인이 "만든 적 없는 배너를 숨기려 한다"며 거부하고, 그러면
 *   뒤늦게 뜬 배너를 아무도 안 내린다.
 * ⚠ wanted가 true여도 **resume을 부른다.** 만드는 동안 끼어든 hide가
 *   배너를 GONE으로 만들어 놓았을 수 있다 — 그러면 결과 화면인데 배너가
 *   없다. 창 안에서 결과→다른 화면→결과로 오간 경우가 그것이다.
 *   ★ 만드는 일은 앱 한 판에 한 번뿐이라 이 여벌 호출도 한 번뿐이다.
 *
 * @param {{created:boolean, creating:boolean, wanted:boolean}} state
 * @param {boolean} ok showBanner가 성공했는가
 * @returns {{action:"resume"|"hide", state:object}}
 */
export function bannerSettled(state, ok) {
  const next = { ...state, creating: false, created: ok ? true : state.created };
  return { action: next.wanted ? "resume" : "hide", state: next };
}

/**
 * 하단에 비워 둘 높이(px) = 광고 + 그 위 간격.
 * 떠 있는 버튼을 올리고, 문서 끝을 밀고, **배경면의 높이가 된다.**
 *
 * ★ 이 값 하나가 넷을 함께 움직인다 — 광고 자리 · 배경면 · 하단 여백 ·
 *   떠 있는 버튼. 그래서 광고가 없으면 넷이 **함께 사라진다.**
 *
 * ⛔ **광고가 채워지지 않으면 0이다 (사용자 결정 · 2026-08-31).**
 *   빈 띠가 하단을 먹는 것은 광고 없이 자리만 차지하는 최악의 상태다.
 *   웹에서 AD_SLOT이 비면 요소를 아예 안 그리기로 한 것과 **같은 원칙**이다.
 *   ⚠ 그래서 이 값은 "보일 화면인가"만으로 정해지지 않는다. 실제로 채워졌는지를
 *     AdMob이 알려 준 뒤에야 값이 선다. 로드 실패·미채움이면 다시 0으로 접는다.
 *   ★ 배경면을 이 값에 묶은 것이 2026-09-01에 안 ②를 기각했던 사유
 *     ("광고가 없을 때 배경 띠가 남는다")를 없앤다.
 *
 * @param {{screen: string, filled?: boolean}} state
 */
export function bannerSpace({
  screen,
  filled = false,
  safeAreaBottom = 0,
  insetBottomReal = null,
} = {}) {
  if (!bannerVisible(screen) || !filled) return 0;
  // ★ 참 인셋이 오면 **대칭**이다. 갈래를 가리지 않는다 (2.118 안 2).
  if (usableInset(insetBottomReal)) return BANNER_HEIGHT + 2 * BANNER_MARGIN;
  // ⛔ 폴백 — 2.112의 옛 비대칭식. 대칭식은 상한 방어가 없어 음수가 될 수 있다.
  const sa = Number.isFinite(safeAreaBottom) && safeAreaBottom > 0 ? safeAreaBottom : 0;
  const gap = sa > 0 ? BANNER_GAP.insetKnown : BANNER_GAP.insetUnknown;
  return BANNER_HEIGHT + sa + gap;
}

/**
 * 배경면을 웹 좌표계 바닥에서 **얼마나 띄우는가**(X · dp).
 *
 * [왜 띄우는가 — 2.118 안 2]
 *   배너는 화면 아래끝에서 `인셋 + margin` 위에 앉는다. 배경면이 바닥(bottom:0)에
 *   붙어 있으면 아래 여백이 `인셋 + margin`이 되어 위와 같아질 수 없다.
 *   배경면을 **인셋만큼 띄우면** 아래 여백이 정확히 margin이 된다.
 *     아래 여백 = (I + m) − (P + X) = m      ← X = I − P (= 웹 좌표계 안의 인셋)
 *     위 여백  = (P + X + H) − (I + m + 50) = m
 *   ★ 두 값 모두 **인셋과 무관해진다.** 갈래 구분이 사라지는 자리가 여기다.
 *
 * ⛔ 폴백에서는 **m을 그대로 띄운다.** 네이티브 margin이 상수라 항상 m만큼
 *   올라가 있는데, 폴백 식(옛 식)은 margin이 0이던 시절의 값이기 때문이다.
 *   X = m 이 그 m을 상쇄해 **2026-09-03 이전과 정확히 같은 기하**가 된다.
 *   ⚠ 이 상쇄가 없으면 갈래 B 3버튼에서 위 여백이 음수가 된다 — 폴백이
 *     지켜야 할 단 하나가 그것이다.
 */
export function bannerLift({
  screen,
  filled = false,
  insetBottomReal = null,
} = {}) {
  if (!bannerVisible(screen) || !filled) return 0;
  return usableInset(insetBottomReal) ? insetBottomReal : BANNER_MARGIN;
}
