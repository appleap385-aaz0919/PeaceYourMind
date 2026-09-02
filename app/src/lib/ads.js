/**
 * 광고 자리 계산 — **규칙이지 상수가 아니다.**
 *
 * [왜 5·11·17을 박으면 안 되는가 — HANDOFF 2.51]
 *   처음에 그렇게 잡았다가 배포본으로 확인하니 24화면 중 6화면에서 폴백 층
 *   헤더와 겹쳤다. 폴백 시작 위치가 화면마다 다르기 때문이다(9~20).
 *   그리고 그 분포는 **매일 달라진다**(HANDOFF 2.42) — 오늘 안 겹친다고
 *   내일 안 겹치는 것이 아니다. 그래서 자리를 층에 상대적으로 계산한다.
 *
 * [층 경계를 비우는 이유는 미관이 아니다]
 *   폴백 헤더("딱 맞는 건 아니지만…")는 이 화면의 **정직성 장치**다.
 *   기대를 걸지 않게 하려고 먼저 말하는 문장인데(VideoList.jsx 주석),
 *   그 앞뒤에 광고가 붙으면 헤더가 광고의 라벨처럼 읽히거나 층이 뒤섞인다.
 *
 * [번호 규칙]
 *   자리는 "몇 번째 **항목 뒤**인가"이고 1부터 센다. 두 층을 이어 붙인
 *   통합 번호다 — 주제분 10건 + 폴백 5건이면 항목 번호는 1~15이고,
 *   12번은 폴백의 두 번째 항목이다.
 *
 * ⚠ 이 파일은 순수 함수만 둔다. DOM도 React도 모른다 — 그래야 24화면 분포를
 *   테스트로 통째로 돌려 볼 수 있다(verses.test.js).
 */

/** AdSense 계정. 소유권 확인 태그(index.html)와 같은 값이어야 한다. */
export const AD_CLIENT = "ca-pub-5074778849873789";

/**
 * 광고 단위 ID — **승인 후 발급된다. 지금은 비어 있다.**
 *
 * ⚠ 비어 있으면 광고 요소를 아예 그리지 않는다(AdSlot.jsx).
 *   빈 박스를 배포하지 않기 위해서다 — 자리만 잡아 둔 회색 상자는
 *   "고장난 화면"으로 읽히고, 위계 실측(2.35·2.36)도 헛것을 재게 된다.
 *
 * ⛔ **승인이 나면 WEB_AD_SLOT에만 값을 넣는다.** 아래 IS_APP 분기가
 *   앱에서는 그 값을 무시한다 — AdSense 프로그램 정책이 앱 안의 AdSense를
 *   금지하기 때문이다("Integrated into a software application ...").
 *   ⚠ 여기를 고쳐 앱에도 값이 가게 만들지 말 것. 앱 광고는 AdMob으로 따로 간다.
 */
const WEB_AD_SLOT = "";

/**
 * 앱(Capacitor) 빌드인가. vite define이 넣는다.
 *
 * ⚠ `typeof` 가드가 필요하다 — 이 모듈은 노드 테스트(ads.test.js)가 직접
 *   import하고, 거기에는 vite의 치환이 없다. chapters.js가 __KRV_BASE__에
 *   쓰는 것과 같은 형태다. 기본값은 웹(false)이다.
 */
const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;

export const AD_SLOT = IS_APP ? "" : WEB_AD_SLOT;

/**
 * 앱(AdMob) 배너 단위 ID — **저장소에는 비어 있다.**
 *
 * ⛔ 데모 단위 ID를 여기 적지 말 것. 실제 단위로 바꿀 때 빠뜨릴 자리가 된다.
 *   값은 App ID와 **같은 파일**에서 온다 — app/android/admob.properties 의
 *   admob.bannerId 를 vite가 읽어 define으로 넣는다(2026-09-02 · HANDOFF 2.102).
 *   ⚠ 환경변수(ADMOB_BANNER_ID)였던 것을 옮겼다. 잊으면 광고도 고지도 없는
 *     앱이 나가는데 게이트가 전부 통과했기 때문이다.
 * ⚠ WEB_AD_SLOT과 짝이다 — 매체마다 자기 값을 갖고, 서로를 모른다.
 */
const APP_AD_UNIT =
  typeof __ADMOB_BANNER_ID__ === "string" ? __ADMOB_BANNER_ID__ : "";

/**
 * ★ **광고를 그리는가 — 매체가 갈려도 답은 이 값 하나다.**
 *
 * [왜 값을 하나로 모으는가 — 2026-09-02]
 *   About의 광고 고지가 `AD_SLOT`에 묶여 있었다. 웹만 있던 동안에는 그것이
 *   맞았다 — 고지와 광고가 **같은 값**으로 움직여 갈라질 수 없었다.
 *   그런데 앱이 AdMob으로 갈리면서 `AD_SLOT`은 앱에서 항상 빈 문자열이 됐고,
 *   그대로 두면 **앱에서 고지가 사라진 채 광고만 나간다.**
 *   ⛔ 매체가 둘로 갈렸으니 값도 **매체를 아는 값**이 되어야 한다.
 *
 * ⚠ 이것은 "광고가 실제로 채워졌는가"가 아니다. 그쪽은 adsApp.js의
 *   bannerSpace가 본다. 여기는 **광고를 켰는가**만 말한다.
 */
export const adsEnabled = IS_APP ? Boolean(APP_AD_UNIT) : Boolean(AD_SLOT);

/** 앱 배너 단위 ID. ⚠ adsEnabled가 false면 부를 일이 없다. */
export const APP_BANNER_UNIT = APP_AD_UNIT;

/**
 * 규격 — ⛔ **여기는 웹(AdSense) 값이다. 앱과 같이 움직이지 않는다.**
 *
 * 320은 우연이 아니라 App.jsx의 좌우 여백 20px에서 나온 값이다(2.51).
 *
 * [⚠ 앱이 320×50으로 내려갈 때 이 값은 100으로 남겼다 — 사용자 판단 2026-09-02]
 *   앱의 띠는 화면 **최하단에 떠 있는 것**이고, 웹의 광고는 목록 **항목 사이에
 *   끼우는 것**이다. 웹은 그 자리를 320×100으로 설계했고, 색·여백 위계 실측
 *   (2.35·2.36)이 그 값 **위에** 서 있다. 높이를 내리면 그 실측을 다시 해야 한다.
 *   ★ 매체가 갈린 것을 값에도 반영한다 — 같은 숫자를 두 매체가 공유하면
 *     한쪽을 고칠 때마다 다른 쪽을 흔든다. adsApp.js의 BANNER_HEIGHT와는
 *     **일부러 다른 상수다.**
 */
export const AD_WIDTH = 320;
export const AD_HEIGHT = 100;

/** 기준 자리 — 규칙이 비면 여기서 출발한다. 결과가 아니라 **출발점**이다. */
export const BASE_SLOTS = [5, 11, 17];

/** 첫 광고 앞에 최소 몇 항목을 두는가. "열자마자 광고"를 피한다(약 390px). */
export const MIN_LEAD = 5;
/** 층 경계에서 몇 항목 이상 떨어지는가. */
export const MIN_BOUNDARY_GAP = 2;
/** 광고 뒤에 몇 항목 이상 남기는가. 항목 하나만 남는 자리를 피한다. */
export const MIN_TAIL = 2;
/** 몇 칸까지 밀어 보는가. ±1 → ±2 → ±3. */
export const MAX_SHIFT = 3;

/**
 * 이 화면의 광고 자리.
 *
 * @param {{themeCount: number, fallbackCount: number}} counts 층별 항목 수
 * @returns {number[]} 오름차순 자리 번호. "이 번호의 항목 뒤에 광고가 온다"
 *
 * 자리를 못 찾은 광고는 **버린다.** 규칙을 어기고 끼워 넣지 않는다 —
 * 목록이 짧으면 광고가 2개거나 0개일 수 있고, 그게 맞다.
 */
export function adPositions({ themeCount = 0, fallbackCount = 0 } = {}) {
  const total = themeCount + fallbackCount;

  // 층 경계는 두 층이 **다 있을 때만** 존재한다. 한쪽이 비면 헤더가 하나뿐이라
  // 목록 중간에 경계가 없다. null은 "경계 없음"이고 0번 항목 뒤와 구별된다.
  const boundary = themeCount > 0 && fallbackCount > 0 ? themeCount : null;

  const taken = [];
  for (const base of BASE_SLOTS) {
    const spot = nearestOpenSpot(base, { total, boundary, taken });
    if (spot !== null) taken.push(spot);
  }
  return taken.sort((a, b) => a - b);
}

/**
 * 기준에서 가장 가까운 빈자리. ±1 → ±2 → ±3 순으로 넓혀 가며 찾는다.
 *
 * 같은 거리면 **앞쪽(작은 번호)을 먼저** 본다. 뒤로 미는 것은 꼬리 여유를
 * 깎아 다음 광고와 붙기 쉽고, 목록 끝에서 규칙이 연쇄로 깨진다.
 */
function nearestOpenSpot(base, context) {
  if (isOpen(base, context)) return base;
  for (let shift = 1; shift <= MAX_SHIFT; shift += 1) {
    for (const candidate of [base - shift, base + shift]) {
      if (isOpen(candidate, context)) return candidate;
    }
  }
  return null;
}

/** 이 번호의 항목 뒤에 광고를 놓아도 되는가. 네 규칙 전부를 통과해야 한다. */
function isOpen(spot, { total, boundary, taken }) {
  if (spot < MIN_LEAD) return false; // 첫 광고 규칙
  if (total - spot < MIN_TAIL) return false; // 꼬리 규칙
  if (boundary !== null && Math.abs(spot - boundary) < MIN_BOUNDARY_GAP) return false;
  return !taken.includes(spot); // 이미 광고가 있는 자리
}

/**
 * 통합 번호를 층 안의 번호로 옮긴다.
 *
 * 화면은 층마다 별도의 <ul>로 그려지므로(VideoList), 자리 번호를 그 층
 * 기준으로 바꿔 줘야 한다. 경계 자리는 위 규칙이 이미 비웠기 때문에
 * "이 광고가 어느 층 것인가"가 애매해지는 경우는 없다.
 *
 * @param {number[]} positions adPositions()의 결과
 * @param {number} offset 이 층 앞에 있는 항목 수 (주제분 층은 0)
 * @param {number} length 이 층의 항목 수
 * @returns {Set<number>} 이 층에서 "몇 번째 항목 뒤"인지 (1부터)
 */
export function positionsWithin(positions, offset, length) {
  const local = new Set();
  for (const spot of positions) {
    const inside = spot - offset;
    if (inside >= 1 && inside <= length) local.add(inside);
  }
  return local;
}
