/**
 * 고정 띠배너 — 네이티브를 다루는 쪽. **보일지 말지 정하는 규칙은 adsApp.js에 있다.**
 *
 * ⚠ 웹에서는 아무것도 하지 않는다. 플러그인이 없으므로 모든 진입점이 조용히
 *   돌아간다 — notify.js가 로컬 알림에 대해 하는 것과 같은 구조다.
 *
 * [⛔ 아직 플러그인이 설치돼 있지 않다 — 2026-09-02]
 *   AdMob 앱과 광고 단위 ID가 계정 인증 뒤에 나온다(HANDOFF 2.96 (다)).
 *   그때까지 이 파일은 **아무것도 띄우지 않고 filled를 false로 둔다.**
 *   ★ 그래도 배선은 지금 넣는다 — 레이아웃이 띠 높이 하나로 구동되는지를
 *     먼저 세워 두면, 플러그인이 붙을 때 갈아 끼울 자리가 한 곳뿐이다.
 *
 * [⚠ import를 정적으로 쓰지 않는 이유가 둘이다]
 *   ① 웹 번들에 네이티브 플러그인이 실리면 안 된다 (notify.js와 같은 이유)
 *   ② **지금은 패키지가 아예 없다.** 정적 import면 vite가 해석에 실패해
 *     빌드가 통째로 선다. 변수 지정자 + @vite-ignore로 런타임까지 미룬다.
 *   ⛔ 플러그인을 설치한 뒤에도 이 형태를 유지할 것 — ①이 그대로 남는다.
 */

const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;

/**
 * ⚠ 문자열을 변수에 담는 것이 핵심이다. 리터럴로 쓰면 vite가 해석하려 든다.
 */
const PLUGIN = "@capacitor-community/admob";

let boxed = null;

/**
 * 플러그인을 늦게 부른다. 없으면 null이다.
 *
 * ⛔ **상자에 담아 돌려준다.** 플러그인 프록시를 async 함수에서 그대로 return하면
 *   JS가 thenable로 보고 `.then()`을 부르고, Capacitor 프록시는 그것을 네이티브
 *   호출로 바꾼다 — notify.js가 실기기에서 그 사고를 겪었다(HANDOFF 2.92 ①).
 */
async function api() {
  if (!IS_APP) return null;
  if (boxed) return boxed;
  try {
    const mod = await import(/* @vite-ignore */ PLUGIN);
    boxed = { ad: mod.AdMob };
    return boxed;
  } catch {
    return null; // 아직 안 붙었다. 조용히 없는 것으로 둔다
  }
}

/**
 * 띠를 보이거나 숨긴다.
 *
 * ⛔ **부르는 쪽이 "보여야 하는가"를 이미 판정해서 넘긴다.** 여기서 화면을
 *   판단하지 않는다 — 판단이 두 곳에 있으면 갈라지고, 갈라지는 순간
 *   위기 화면에 광고가 뜬다.
 *
 * @param {boolean} shown
 * @returns {Promise<void>}
 */
export async function setBannerShown(shown) {
  const box = await api();
  if (!box) return;
  try {
    if (shown) await box.ad.resumeBanner();
    else await box.ad.hideBanner();
  } catch {
    /* 실패는 치명적이지 않다 — 띠가 안 보일 뿐이다 */
  }
}

/**
 * 광고가 실제로 채워졌는지 지켜본다.
 *
 * ⛔ **채워지지 않으면 자리를 주지 않는다**(사용자 결정 · 2026-08-31).
 *   빈 띠가 하단 100px을 먹는 것은 광고 없이 자리만 차지하는 최악의 상태이고,
 *   웹에서 AD_SLOT이 비면 요소를 아예 안 그리는 것과 같은 원칙이다.
 *
 * @param {(filled: boolean) => void} onChange
 * @returns {Promise<() => void>} 해제 함수
 */
export async function watchBannerFill(onChange) {
  const box = await api();
  if (!box) return () => {};
  try {
    const loaded = await box.ad.addListener("bannerAdLoaded", () => onChange(true));
    const failed = await box.ad.addListener("bannerAdFailedToLoad", () => onChange(false));
    return () => {
      loaded.remove();
      failed.remove();
    };
  } catch {
    return () => {};
  }
}
