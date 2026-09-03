/**
 * 고정 띠배너 — 네이티브를 다루는 쪽. **보일지 말지 정하는 규칙은 adsApp.js에 있다.**
 *
 * ⚠ 웹에서는 아무것도 하지 않는다. 플러그인이 없으므로 모든 진입점이 조용히
 *   돌아간다 — notify.js가 로컬 알림에 대해 하는 것과 같은 구조다.
 *
 * [⛔ 광고 단위 ID가 없으면 아무것도 안 한다]
 *   ads.js의 APP_BANNER_UNIT은 저장소에서 빈 문자열이다. 값은 환경변수로만
 *   들어온다(vite define). 비어 있으면 여기서 멈춘다 — adsEnabled가 false라
 *   About의 고지도 안 그려지므로 **광고와 고지가 함께 없다.**
 *
 * [⛔ import를 늦게 부른다 — 그러나 **지정자는 리터럴이어야 한다**]
 *   웹 번들에 네이티브 플러그인이 실리면 안 된다 — 그래서 동적 import다
 *   (notify.js와 같은 구조).
 *   ⚠ 2026-09-02에 한 번 틀렸다 — 플러그인이 없던 동안 빌드가 서는 것을
 *     막으려고 `/* @vite-ignore *​/` + 변수 지정자를 썼다. 그러면 vite가
 *     묶지 않아 **런타임에 bare specifier를 받으려 하고 404가 난다.**
 *     catch에 걸려 조용히 null이 되고, 배너가 영영 안 뜼다.
 *   ★ 설치된 지금은 리터럴로 써야 vite가 별도 청크로 묶는다.
 */

import { APP_BANNER_UNIT } from "./ads.js";
import { BANNER_MARGIN } from "./adsApp.js";

const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;

let boxed = null;
let created = false;

/**
 * 플러그인을 늦게 부른다. 없으면 null이다.
 *
 * ⛔ **상자에 담아 돌려준다.** 플러그인 프록시를 async 함수에서 그대로 return하면
 *   JS가 thenable로 보고 `.then()`을 부르고, Capacitor 프록시는 그것을 네이티브
 *   호출로 바꾼다 — notify.js가 실기기에서 그 사고를 겪었다(HANDOFF 2.92 ①).
 */
async function api() {
  if (!IS_APP || !APP_BANNER_UNIT) return null;
  if (boxed) return boxed;
  try {
    const mod = await import("@capacitor-community/admob");
    boxed = { ad: mod.AdMob };
    return boxed;
  } catch {
    return null;
  }
}

/**
 * 띠를 보이거나 숨긴다.
 *
 * ⛔ **부르는 쪽이 "보여야 하는가"를 이미 판정해서 넘긴다.** 여기서 화면을
 *   판단하지 않는다 — 판단이 두 곳에 있으면 갈라지고, 갈라지는 순간
 *   위기 화면에 광고가 뜬다.
 *
 * ⚠ 처음 보일 때만 만든다(showBanner). 그 뒤로는 resume/hide로 오간다 —
 *   매번 새로 만들면 광고 요청이 화면 전환마다 나간다.
 *
 * @param {boolean} shown
 */
export async function setBannerShown(shown) {
  const box = await api();
  if (!box) return;
  try {
    if (!shown) {
      if (created) await box.ad.hideBanner();
      return;
    }
    if (created) {
      await box.ad.resumeBanner();
      return;
    }
    await box.ad.initialize({});
    await box.ad.showBanner({
      adId: APP_BANNER_UNIT,
      // ⛔ BANNER(320×50 · 표준 배너)다. 적응형은 높이를 SDK가 정해서
      //   하단 조정이 런타임 값이 된다 (HANDOFF 2.96 안 1).
      // ⚠ adsApp.js의 BANNER_HEIGHT와 **짝이다.** 한쪽만 바꾸면
      //   비워 둔 자리와 실제 띠 높이가 어긋난다 — 회귀가 둘을 함께 본다.
      // ★ 100 → 50은 실기기 관측이 뒤집은 것이다 (HANDOFF 2.104).
      //   콘솔 단위는 새로 만들지 않았다 — 콘솔이 크기를 묻지 않는다(C3).
      adSize: "BANNER",
      position: "BOTTOM_CENTER",
      // ★ 배너를 배경면 **가운데**에 놓기 위해 아래로 m만큼 띄운다 (2.118 안 2).
      //   ⛔ adsApp.js의 BANNER_MARGIN과 **같은 값이어야 한다.** 갈리면 배너가
      //     가운데에서 벗어난다 — pluginPins.test.js가 둘을 함께 본다.
      //   ⛔ **상수다.** 인셋에서 계산하지 말 것 — showBanner는 처음 한 번만
      //     불리므로 그때 값이 굳는다. 인셋은 배경면(웹)이 lift로 흡수한다.
      //   ★ 플러그인은 Android 15+ 에서만 여기에 인셋을 더하는데, 그것도
      //     **리스너**라 회전에 스스로 따라간다 (BannerExecutor.java 실측).
      margin: BANNER_MARGIN,
    });
    created = true;
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
