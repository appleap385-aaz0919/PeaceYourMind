/**
 * 광고 — **규칙과 약속을 함께 지킨다.**
 *
 * 여기서 지키는 것
 *   · 자리는 계산되지 박히지 않는다 (폴백 비율이 매일 달라진다 — HANDOFF 2.42)
 *   · 층 경계를 비운다 (폴백 헤더는 이 화면의 정직성 장치다)
 *   · 라벨 어휘와 규격 — 어기면 **정책 위반**이지 취향 문제가 아니다
 *   · slot이 비면 아무것도 그리지 않는다 (빈 상자를 배포하지 않는다)
 *   · client ID가 세 곳에서 같다 (코드 · 앱 · 방침)
 *
 * ⚠ 화면 제외(위기·이어서 읽기) 검사는 verses.test.js에 이미 있다.
 *   그쪽 AD_TOKENS 목록에 "AdSlot"이 들어 있어 이 구현이 새면 걸린다.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  AD_CLIENT,
  AD_HEIGHT,
  AD_SLOT,
  AD_WIDTH,
  BASE_SLOTS,
  MIN_BOUNDARY_GAP,
  MIN_LEAD,
  MIN_TAIL,
  adPositions,
  positionsWithin,
} from "../src/lib/ads.js";
import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
// 소스 검사는 전부 readSource()를 지난다 — 주석이 검사를 오염시킨다(helpers.js).
const adSlotSrc = readSource("components", "AdSlot.jsx");
const videoListSrc = readSource("components", "VideoList.jsx");
const appSrc = readSource("App.jsx");
// 정적 HTML은 src/ 밖이라 readSource()를 못 쓴다 — 주석만 같은 이유로 걷어낸다.
const stripHtml = (...parts) =>
  readFileSync(join(root, ...parts), "utf8").replace(/<!--[\s\S]*?-->/g, "");
const indexHtml = stripHtml("index.html");
const privacyHtml = stripHtml("public", "privacy", "index.html");

// =============================================================================
// 자리 계산 — HANDOFF 2.51의 배포본 24화면 실측을 그대로 돌린다
// =============================================================================

/**
 * 그날 배포본의 폴백 시작 위치 분포. 전부 20건 화면이다.
 * fallbackStart가 null이면 폴백이 없는 화면(주제분 20건).
 *
 * ⚠ 이 표는 **그날의 스냅숏**이다. 배포본 값이 달라졌다고 고치지 말 것 —
 *   규칙이 어느 분포에서도 성립하는지 보는 것이 목적이다.
 */
const DEPLOYED_2026_08_24 = [
  { fallbackStart: null, screens: 6, expected: [5, 11, 17] },
  { fallbackStart: 9, screens: 2, expected: [5, 11, 17] },
  { fallbackStart: 10, screens: 1, expected: [5, 11, 17] },
  { fallbackStart: 11, screens: 3, expected: [5, 12, 17] },
  { fallbackStart: 13, screens: 1, expected: [5, 10, 17] },
  { fallbackStart: 14, screens: 2, expected: [5, 11, 17] },
  { fallbackStart: 16, screens: 2, expected: [5, 11, 17] },
  { fallbackStart: 18, screens: 3, expected: [5, 11, 15] },
  { fallbackStart: 19, screens: 2, expected: [5, 11, 16] },
  { fallbackStart: 20, screens: 2, expected: [5, 11, 17] },
];

const TOTAL = 20;

for (const { fallbackStart, expected } of DEPLOYED_2026_08_24) {
  const label = fallbackStart === null ? "폴백 없음" : `폴백 시작 ${fallbackStart}번`;
  test(`자리 계산: ${label} → [${expected}]`, () => {
    const themeCount = fallbackStart === null ? TOTAL : fallbackStart - 1;
    assert.deepEqual(
      adPositions({ themeCount, fallbackCount: TOTAL - themeCount }),
      expected,
    );
  });
}

test("실측 24화면 전부에서 광고가 3개다 (경계 충돌 0건)", () => {
  let screens = 0;
  for (const row of DEPLOYED_2026_08_24) {
    screens += row.screens;
    assert.equal(row.expected.length, 3, `${row.fallbackStart}에서 광고가 3개가 아니다`);
  }
  assert.equal(screens, 24, "실측 화면 수가 24가 아니다 — 표가 어긋났다");
});

// =============================================================================
// 규칙 자체 — 분포를 가리지 않고 성립하는가
// =============================================================================

test("어떤 층 배분에서도 네 규칙이 전부 지켜진다", () => {
  for (let total = 0; total <= 40; total += 1) {
    for (let themeCount = 0; themeCount <= total; themeCount += 1) {
      const fallbackCount = total - themeCount;
      const spots = adPositions({ themeCount, fallbackCount });
      const boundary = themeCount > 0 && fallbackCount > 0 ? themeCount : null;
      const where = `theme=${themeCount} fallback=${fallbackCount}`;

      assert.ok(spots.length <= BASE_SLOTS.length, `${where}: 광고가 3개를 넘었다`);
      assert.equal(new Set(spots).size, spots.length, `${where}: 같은 자리에 두 개`);

      for (const spot of spots) {
        assert.ok(spot >= MIN_LEAD, `${where}: ${spot}번 — 열자마자 광고다`);
        assert.ok(total - spot >= MIN_TAIL, `${where}: ${spot}번 — 꼬리가 모자라다`);
        if (boundary !== null) {
          assert.ok(
            Math.abs(spot - boundary) >= MIN_BOUNDARY_GAP,
            `${where}: ${spot}번이 층 경계(${boundary})에 붙었다 — 폴백 헤더가 광고 라벨처럼 읽힌다`,
          );
        }
      }
    }
  }
});

test("규칙을 어기느니 광고를 버린다 (짧은 목록)", () => {
  assert.deepEqual(adPositions({ themeCount: 0, fallbackCount: 0 }), []);
  assert.deepEqual(adPositions({ themeCount: 6, fallbackCount: 0 }), [], "6건이면 꼬리가 없다");
  assert.deepEqual(adPositions({ themeCount: 7, fallbackCount: 0 }), [5]);
});

test("층 경계가 없으면(한쪽이 비면) 기준 자리를 그대로 쓴다", () => {
  assert.deepEqual(adPositions({ themeCount: 20, fallbackCount: 0 }), [5, 11, 17]);
  assert.deepEqual(adPositions({ themeCount: 0, fallbackCount: 20 }), [5, 11, 17]);
});

test("인자가 없어도 죽지 않는다", () => {
  assert.deepEqual(adPositions(), []);
  assert.deepEqual(adPositions({}), []);
});

test("통합 번호를 층 안의 번호로 옮긴다", () => {
  // 주제분 10 + 폴백 10, 자리 [5, 12, 17]
  const spots = [5, 12, 17];
  assert.deepEqual([...positionsWithin(spots, 0, 10)], [5], "주제분 층");
  assert.deepEqual([...positionsWithin(spots, 10, 10)], [2, 7], "폴백 층");
});

// =============================================================================
// 정책 — 어기면 위반이다
// =============================================================================

test("⛔ 자리를 상수로 박지 않는다 (VideoList)", () => {
  assert.ok(videoListSrc.includes("adPositions("), "VideoList가 자리를 계산하지 않는다");
  assert.ok(
    !/\[\s*5\s*,\s*11\s*,\s*17\s*\]/.test(videoListSrc),
    "5·11·17이 화면 코드에 박혔다. 폴백 비율이 매일 달라 경계가 움직인다(2.51)",
  );
});

test("라벨은 '광고'다 — 다른 어휘를 쓰지 않는다", () => {
  assert.ok(adSlotSrc.includes(">광고<"), "라벨 '광고'가 없다");
  for (const banned of ["추천", "함께 보기", "관련 영상", "스폰서드"]) {
    assert.ok(
      !adSlotSrc.includes(`>${banned}<`),
      `"${banned}"는 허용 어휘가 아니다 — 광고·스폰서 링크뿐이다`,
    );
  }
});

test("라벨 언어가 폴백 층 헤더와 같다 (11.5px · 0.2em · T.muted)", () => {
  assert.ok(adSlotSrc.includes("fontSize: 11.5"), "11.5px가 아니다");
  assert.ok(adSlotSrc.includes('letterSpacing: "0.2em"'), "자간 0.2em이 아니다");
  assert.ok(adSlotSrc.includes("color: T.muted"), "T.muted가 아니다");
});

test("⛔ 목록 항목 레이아웃을 흉내내지 않는다", () => {
  for (const token of ["thumbnailUrl", "styles.thumb", "objectFit"]) {
    assert.ok(
      !adSlotSrc.includes(token),
      `광고가 썸네일+제목 레이아웃을 흉내냈다("${token}"). 구분이 안 되면 위반이다`,
    );
  }
});

test("규격은 320×100 디스플레이다 (인피드가 아니다)", () => {
  assert.equal(AD_WIDTH, 320);
  assert.equal(AD_HEIGHT, 100);
  assert.ok(
    !adSlotSrc.includes("data-ad-format"),
    "고정 규격이라 data-ad-format을 쓰지 않는다 — 반응형이면 높이가 늘어난다",
  );
  assert.ok(adSlotSrc.includes('data-full-width-responsive="false"'));
});

test("slot이 비면 광고 요소를 그리지 않는다 (빈 상자를 배포하지 않는다)", () => {
  assert.equal(AD_SLOT, "", "slot이 채워졌다 — 승인 후라면 이 테스트를 갱신할 것");
  assert.ok(/if \(!AD_SLOT\) return/.test(adSlotSrc), "slot이 비었을 때 빠져나가는 길이 없다");
});

test("자리표시자는 개발 서버에서만 뜬다 (배포본 번들에서 사라진다)", () => {
  assert.ok(adSlotSrc.includes("import.meta.env.DEV"), "개발 전용 가지가 없다");
  assert.ok(
    !adSlotSrc.includes("import.meta.env?.DEV"),
    "옵셔널 체이닝을 쓰면 vite가 정적 치환을 못 해 자리표시자가 배포본에 남는다",
  );
});

test("push는 <ins>당 정확히 한 번이다 (SPA 재조립 대비)", () => {
  assert.ok(adSlotSrc.includes("pushed.current"), "중복 push 방어가 없다");
  assert.ok(
    videoListSrc.includes("<Fragment key={video.videoId}>"),
    "목록 재조립 시 광고가 새로 마운트되지 않는다",
  );
});

test("광고를 불러오지 못해도 화면이 죽지 않는다", () => {
  assert.ok(adSlotSrc.includes("try {") && adSlotSrc.includes("catch"), "push가 무방비다");
});

// =============================================================================
// 배포 설정 — 세 곳이 같은 값을 말하는가
// =============================================================================

test("client ID가 코드·앱·방침에서 같다", () => {
  assert.match(AD_CLIENT, /^ca-pub-\d+$/, "client 형식이 아니다");
  for (const [name, html] of [
    ["앱 index.html", indexHtml],
    ["방침", privacyHtml],
  ]) {
    assert.ok(
      html.includes(`client=${AD_CLIENT}`),
      `${name}의 AdSense 태그가 ${AD_CLIENT}를 가리키지 않는다`,
    );
  }
});

test("소유권 확인 스니펫이 <head>에 있다", () => {
  for (const [name, html] of [
    ["앱 index.html", indexHtml],
    ["방침", privacyHtml],
  ]) {
    const head = html.slice(0, html.indexOf("</head>"));
    assert.ok(
      head.includes("pagead/js/adsbygoogle.js"),
      `${name}: 스니펫이 <head>에 없다 — 크롤러가 소유권을 확인하지 못한다`,
    );
  }
});

test("방침 페이지에는 광고를 게재하지 않는다 (읽는 자리다)", () => {
  // 소유권 확인 스크립트는 <head>에 있어야 하므로 그것까지 막지는 않는다.
  // 막는 것은 **광고 자리**(<ins class="adsbygoogle">)다.
  assert.ok(
    !/<ins[^>]*adsbygoogle/.test(privacyHtml),
    "방침 본문에 광고 자리가 들어왔다 — 방침은 읽는 자리다",
  );
});

test("⚠ 결과 화면 좌우 여백이 320 규격을 만든다 — 바꾸지 않는다", () => {
  assert.ok(
    appSrc.includes('padding: "34px 20px 40px"'),
    "좌우 여백이 20px에서 바뀌었다. 360px에서 콘텐츠 폭이 320이 아니게 되어 " +
      "광고 규격이 어긋난다(HANDOFF 2.51 실측)",
  );
});

test("맞춤 광고 거부 방법이 방침에 있다 (AdSense 필수 콘텐츠)", () => {
  assert.ok(privacyHtml.includes("adssettings.google.com"), "Google 광고 설정 안내가 없다");
  assert.ok(privacyHtml.includes("aboutads.info"), "일괄 거부 안내가 없다");
});
