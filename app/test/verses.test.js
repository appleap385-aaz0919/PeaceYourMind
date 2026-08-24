/**
 * 구절 계층 검사 — PYM에만 있는 화면이라 FYM 테스트에 대응물이 없다.
 *
 * 여기서 지키는 것
 *   · 저작인격권 — 본문을 가공하지 않고, 출처 표기가 화면에 있다
 *   · 감정 풀과 위기 풀의 격리
 *   · "다른 구절 보기"가 같은 구절을 다시 내놓지 않는다
 *   · 구절 데이터가 없거나 깨져도 화면이 죽지 않는다
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  CRISIS_POOL_KEY,
  __test__ as versesTest,
  attributionOf,
  crisisVerses,
  isUsableVerses,
  lastVerseId,
  nextVerse,
  pickVerse,
  rememberVerse,
  versesFor,
} from "../src/lib/verses.js";
import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const verses = JSON.parse(readFileSync(join(root, "src", "data", "verses.json"), "utf8"));
const taxonomy = JSON.parse(readFileSync(join(root, "src", "data", "taxonomy.json"), "utf8"));
// 소스 검사는 전부 readSource()를 지난다 — 주석이 검사를 오염시킨다(helpers.js).
const verseCardSrc = readSource("components", "VerseCard.jsx");
const aboutSrc = readSource("components", "About.jsx");
const crisisSrc = readSource("components", "CrisisScreen.jsx");
const readerSrc = readSource("components", "ChapterReader.jsx");
const appSrc = readSource("App.jsx");

const ATTRIBUTION = "성경전서 개역한글판, 대한성서공회";

// --- 저작인격권 --------------------------------------------------------------

test("verses.json이 출처 표기를 들고 있다", () => {
  assert.equal(verses.attribution, ATTRIBUTION);
  assert.equal(attributionOf(verses), ATTRIBUTION);
});

test("출처 표기가 없어도 기본 문구로 대체된다 (표기가 사라지지 않는다)", () => {
  assert.equal(attributionOf({}), ATTRIBUTION);
  assert.equal(attributionOf(null), ATTRIBUTION);
  assert.equal(attributionOf({ attribution: "   " }), ATTRIBUTION);
});

/**
 * [2026-08-19 정책 변경 — 표기 자리가 두 곳에서 한 곳으로 줄었다]
 *   전에는 구절 카드와 "이 앱에 대해" 두 곳에 표기가 있었고, 이 자리의 테스트도
 *   "구절 카드가 출처를 그린다"였다. 카드 상자를 걷어내고 본문이 화면의 첫
 *   인상이 된 뒤 카드 쪽 표기를 뺐다(VerseCard.jsx 상단 주석).
 *
 *   ⚠ 그래서 이 검사를 **없애지 않고 옮겼다.** 성명표시권은 저작재산권과 달리
 *     만료되지 않으므로 앱 어딘가에는 반드시 표기가 있어야 한다. 표기 자리가
 *     한 곳뿐이라는 것은 그 한 곳이 **더 중요해졌다**는 뜻이지 덜 중요해졌다는
 *     뜻이 아니다. 아래 두 검사가 그 요건을 고정한다.
 */
test("이 앱에 대해 화면에 출처 표기가 있다 (성명표시권 — 삭제 금지)", () => {
  assert.ok(
    aboutSrc.includes("attribution"),
    "출처 표기가 앱에서 사라졌다. 성명표시권은 만료되지 않는다",
  );
  assert.ok(
    aboutSrc.includes("성경 본문"),
    "출처를 밝히는 절이 사라졌다",
  );
});

test("이 앱에 대해 화면으로 갈 길이 있다 (표기에 도달할 수 없으면 표기가 아니다)", () => {
  // 표기가 파일에 있어도 화면에 갈 수 없으면 고지가 되지 않는다.
  // 셸 하단의 진입 버튼이 그 유일한 경로다.
  assert.ok(appSrc.includes("이 앱에 대해"), "정보 화면 진입 버튼이 없다");
  assert.ok(appSrc.includes("attributionOf(versesData)"), "정보 화면에 표기가 전달되지 않는다");
});

/* --- 영상 절 문구 — 보증 어휘가 다시 들어오지 않게 한다 (2026-08-24) ---------
 *
 * 개정 전 문구는 "사람이 확인해 승인한 채널의 영상만 담습니다"였다.
 * allowlist를 사람이 만드는 것은 사실이지만, 화면에서 "승인"이라고 말하면
 * **품질·정통성을 보증한 것으로 읽힌다.** 같은 절 아래 문단의 "영상의 내용은
 * 각 채널의 견해이며 이 앱의 입장과 같지 않을 수 있습니다"와도 충돌했다.
 *
 * ⚠ 이 문구를 고정하는 검사가 **하나도 없었다.** 그래서 바꿔도 게이트가 걸리지
 *   않았고, 되돌아와도 걸리지 않는다. 아래 두 검사가 그 자리다.
 */
const ENDORSEMENT_WORDS = ["승인", "심사", "검증", "인증", "보증"];

test("이 앱에 대해 — 영상 절에 보증 어휘가 없다 (책임 범위)", () => {
  for (const word of ENDORSEMENT_WORDS) {
    assert.ok(
      !aboutSrc.includes(`${word}한 채널`) && !aboutSrc.includes(`${word}된 채널`),
      `"${word}"이 채널을 수식하고 있다. 화면에서 보증으로 읽히므로 쓰지 않는다`,
    );
  }
  assert.ok(
    !aboutSrc.includes("사람이 확인해 승인한"),
    "개정 전 문구가 되돌아왔다 (HANDOFF 2.50 ④)",
  );
});

test("이 앱에 대해 — 영상을 어떻게 고르는지는 여전히 말한다", () => {
  // 보증 어휘를 뺀다고 침묵하면 안 된다. 오해가 생겼을 때 화면에서 댈 근거가
  // 사라진다 — allowlist는 저장소에 있지 사용자가 보는 곳에 없다.
  assert.ok(
    aboutSrc.includes("미리 정해 둔 채널 목록"),
    "영상을 어떻게 고르는지에 대한 설명이 사라졌다",
  );
  assert.ok(
    aboutSrc.includes("검색으로 모으지 않으며"),
    "무작위 수집이 아니라는 사실이 사라졌다 — 오해를 가장 빨리 푸는 문장이다",
  );
});

/* --- 기록 삭제 — 문서가 약속한 것을 코드가 지키는가 (2026-08-24) -------------
 *
 * taxonomy.yaml ui.revisit.privacy_note가 "설정에 기록 삭제 버튼을 둔다"고
 * 약속하고 db.js에 clearAllLocalData()가 있는데 **호출부가 없었다.**
 * 문서가 약속한 것을 코드가 안 지키는 상태였고, 개인정보처리방침이 그 문장을
 * 쓸 수 없었다. 아래 검사가 그 자리다.
 */
test("이 앱에 대해 — 기록 삭제 버튼이 실제로 연결돼 있다", () => {
  assert.ok(aboutSrc.includes("clearAllLocalData"), "기록 삭제가 호출되지 않는다");
  assert.ok(
    aboutSrc.includes("clearBrowsingTraces"),
    "열람 흔적(썸네일·장 본문 캐시)이 함께 지워지지 않는다",
  );
  assert.ok(aboutSrc.includes("<EraseRecords />"), "버튼이 화면에 놓이지 않았다");
});

test("기록 삭제는 한 번 더 묻는다 (되돌릴 수 없다)", () => {
  // 한 번에 지우면 안 되고, 그렇다고 window.confirm은 이 앱의 톤이 아니다.
  assert.ok(aboutSrc.includes('"asking"'), "확인 단계가 없다");
  assert.ok(aboutSrc.includes("그만두기"), "물러설 길이 없다");
  assert.ok(
    !aboutSrc.includes("window.confirm") && !aboutSrc.includes("alert("),
    "브라우저 경고창을 쓰고 있다 — 시스템 목소리는 이 화면의 톤이 아니다",
  );
});

test("앱 셸 캐시는 지우지 않는다 (흔적이 아니라 성능이다)", () => {
  const dbSrc = readSource("lib", "db.js");
  assert.ok(dbSrc.includes("pym-thumbs-"), "썸네일 캐시가 삭제 대상에서 빠졌다");
  assert.ok(dbSrc.includes("pym-krv-"), "장 본문 캐시가 삭제 대상에서 빠졌다");
  assert.ok(
    !dbSrc.includes('"pym-shell-'),
    "앱 셸까지 지우면 오프라인에서 앱이 열리지 않는다 — 흔적도 아니다",
  );
});

/* --- 광고 제외 — 방침에 적은 약속을 코드가 지키는가 (2026-08-24) -------------
 *
 * 개인정보처리방침 2절이 이렇게 약속한다:
 *   "위기 상황 안내 화면과 '이어서 읽기'(성경 본문) 화면에는 광고를 넣지 않습니다."
 *
 * ⚠ **문서만으로는 못 막는다.** 나중에 인피드 컴포넌트를 만들고 나서
 *   "여기도 넣으면 수익이 오르지 않나" 하는 순간 방침 위반이 된다.
 *   광고 코드가 아직 없는 지금 검사를 먼저 둔다 — 넣는 순간 걸리게.
 *
 * 검사 대상 어휘는 앞으로 쓸 이름을 미리 못 박은 것이다.
 * 인피드 컴포넌트를 다른 이름으로 만들거든 **이 목록에 그 이름을 추가할 것.**
 */
const AD_TOKENS = ["adsbygoogle", "googlesyndication", "InFeedAd", "AdSlot", "data-ad-client"];
const AD_FREE_SCREENS = [
  ["CrisisScreen.jsx", "위기 화면 — 도움이 급한 자리다"],
  ["ChapterReader.jsx", "이어서 읽기 — 본문을 읽는 자리다"],
];

for (const [file, why] of AD_FREE_SCREENS) {
  test(`광고 없음: ${file} (${why})`, () => {
    const src = readSource("components", file);
    for (const token of AD_TOKENS) {
      assert.ok(
        !src.includes(token),
        `${file}에 "${token}"이 들어왔다. 개인정보처리방침 2절이 이 화면에 광고를 ` +
          `넣지 않겠다고 약속했으므로, 넣으면 방침 위반이다`,
      );
    }
  });
}

test("개인정보처리방침으로 가는 길이 앱에 있다", () => {
  // 방침이 배포돼 있어도 앱에서 갈 수 없으면 고지가 되지 않는다 (출처 표기와 같은 논리).
  assert.ok(aboutSrc.includes("PRIVACY_URL"), "방침 링크 상수가 없다");
  assert.ok(
    /const PRIVACY_URL = "[^"]+"/.test(aboutSrc),
    "PRIVACY_URL이 비어 있다 — 빈 문자열이면 링크가 그려지지 않는다",
  );
  assert.ok(aboutSrc.includes("개인정보처리방침"), "링크 문구가 없다");
});

/* --- 문의처 — 방침과 앱이 같은 주소를 말하는가 (2026-08-24) -----------------
 *
 * 개인정보처리방침에 문의처가 없으면 스토어 심사에서 걸린다. 그리고 방침과 앱이
 * **다른 주소**를 말하면 어느 쪽이 맞는지 알 수 없다 — 둘을 함께 고정한다.
 *
 * ⚠ 방침은 public/의 정적 HTML이라 readSource()(src/ 전용)를 못 쓴다.
 *   대신 HTML 주석을 걷어내고 읽는다 — 주석이 검사를 오염시키는 함정은
 *   확장자가 달라도 똑같이 성립한다 (helpers.js 머리말).
 */
const privacyHtml = readFileSync(
  join(here, "..", "public", "privacy", "index.html"),
  "utf8",
).replace(/<!--[\s\S]*?-->/g, "");

test("개인정보처리방침에 문의처가 있다 (스토어 심사 요건)", () => {
  const found = privacyHtml.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) || [];
  assert.ok(found.length > 0, "방침 8절에 이메일이 없다 — 심사에서 걸린다");
  assert.ok(
    !privacyHtml.includes("(준비 중)"),
    "'(준비 중)'이 남아 있다. 자리표시자를 둔 채로 출시하지 않는다",
  );
});

test("방침과 앱이 같은 문의처를 말한다", () => {
  const inPolicy = (privacyHtml.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) || [])[0];
  const inApp = (aboutSrc.match(/const CONTACT = "([^"]*)"/) || [])[1];
  assert.ok(inApp, "About.jsx의 CONTACT가 비어 있다 — 앱 화면에 문의처가 안 그려진다");
  assert.equal(
    inApp,
    inPolicy,
    "방침과 앱의 문의처가 다르다. 두 곳이 갈리면 어느 쪽이 맞는지 알 수 없다",
  );
});

test("구절 카드·위기 화면·이어서 읽기는 출처를 그리지 않는다 (2026-08-19 정책)", () => {
  // 되돌리는 것 자체는 판단의 문제지만, **조용히** 되돌아가지는 않게 한다.
  // 이 검사가 깨지면 위 정책 주석을 함께 고쳤는지 확인할 것.
  assert.ok(!verseCardSrc.includes("styles.attribution"), "구절 카드에 표기가 다시 생겼다");
  assert.ok(!crisisSrc.includes("styles.attribution"), "위기 화면에 표기가 다시 생겼다");
  assert.ok(!readerSrc.includes("styles.attribution"), "이어서 읽기에 표기가 다시 생겼다");
});

/**
 * [2026-08-20 — 표기 한 곳의 무게가 늘었다]
 *   "이어서 읽기"가 생기면서 앱이 노출하는 본문이 **구절 하나에서 장 단위로**
 *   커졌다. 표기 자리는 여전히 "이 앱에 대해" 한 곳이므로, 그 한 곳이 이제
 *   앱 전체의 본문을 커버하는 유일한 표기다.
 *
 *   위 검사(About에 표기가 있다 · 그 화면으로 갈 길이 있다)가 그대로 요건을
 *   고정한다. 여기서 더하는 것은 **본문을 가공하지 않는다**는 쪽이다 —
 *   장 단위로 그리면 "길면 자르자"는 유혹이 구절 하나일 때보다 크다.
 */
test("이어서 읽기가 본문을 가공하지 않는다 (동일성유지권)", () => {
  const forbidden = [
    "unit.text.slice",
    "unit.text.substring",
    "unit.text.replace",
    "unit.text.trim",
    "text.slice",
  ];
  for (const pattern of forbidden) {
    assert.ok(!readerSrc.includes(pattern), `본문을 가공한다: ${pattern}`);
  }
  assert.ok(readerSrc.includes("{unit.text}"), "본문을 그대로 렌더링해야 한다");
});

test("이어서 읽기는 장 경계를 넘지 않는다 (다음 장을 부르지 않는다)", () => {
  // 규칙은 chapters.js가 지키지만(chapters.test.js), 화면이 직접 다음 장을
  // 계산해 부르기 시작하면 그 규칙을 우회한다.
  assert.ok(
    !/chapter\s*[+-]\s*1/.test(readerSrc),
    "화면이 이웃 장을 계산한다 — 범위는 그 장이다",
  );
});

test("구절 카드가 본문을 가공하지 않는다 (동일성유지권)", () => {
  // slice·substring·replace·trim 같은 문자열 가공이 본문에 닿으면 안 된다.
  const forbidden = ["verse.text.slice", "verse.text.substring", "verse.text.replace", "verse.text.trim"];
  for (const pattern of forbidden) {
    assert.ok(!verseCardSrc.includes(pattern), `본문을 가공한다: ${pattern}`);
  }
  assert.ok(verseCardSrc.includes("{verse.text}"), "본문을 그대로 렌더링해야 한다");
});

test("개역한글 옛 표기가 살아 있다", () => {
  // 현대 맞춤법으로 "고치는" 것이 곧 훼손이다. 표본으로 몇 개만 본다.
  const all = verses.verses.map((v) => v.text).join(" ");
  const archaic = ["찌어다", "찌라", "하느니라", "하시니라", "이니라"];
  const found = archaic.filter((token) => all.includes(token));
  assert.ok(found.length >= 2, `옛 표기가 사라졌다 (발견: ${found})`);
});

// --- 감정 풀 / 위기 풀 -------------------------------------------------------

test("모든 감정 세분류에 구절이 있다", () => {
  const ids = taxonomy.categories.flatMap((c) => c.subcategories.map((s) => s.id));
  for (const id of ids) {
    assert.ok(versesFor(verses, id).length > 0, `${id}에 구절이 없다`);
  }
});

test("versesFor는 위기 구절을 돌려주지 않는다", () => {
  const crisisIds = new Set(verses.crisis.map((v) => v.id));
  const ids = taxonomy.categories.flatMap((c) => c.subcategories.map((s) => s.id));
  for (const id of ids) {
    for (const verse of versesFor(verses, id)) {
      assert.ok(!crisisIds.has(verse.id), `${id}에 위기 구절이 섞였다: ${verse.id}`);
    }
  }
});

test("crisisVerses는 감정 구절을 돌려주지 않는다", () => {
  const emotionIds = new Set(verses.verses.map((v) => v.id));
  for (const verse of crisisVerses(verses)) {
    assert.ok(!emotionIds.has(verse.id));
  }
});

test("위기 구절 풀이 비어 있지 않다", () => {
  assert.ok(crisisVerses(verses).length >= 5);
});

// --- 회전 -------------------------------------------------------------------

const pool = [
  { id: "a", ref: "a", text: "a" },
  { id: "b", ref: "b", text: "b" },
  { id: "c", ref: "c", text: "c" },
];

test("다른 구절 보기는 반드시 다음 구절로 넘어간다", () => {
  // 랜덤이면 같은 것이 다시 나올 수 있고, 그러면 버튼이 고장 난 것처럼 읽힌다.
  assert.equal(nextVerse(pool, "a").id, "b");
  assert.equal(nextVerse(pool, "b").id, "c");
  assert.equal(nextVerse(pool, "c").id, "a", "한 바퀴 돌면 처음으로");
});

test("현재 구절을 모르면 첫 구절부터", () => {
  assert.equal(nextVerse(pool, "없는id").id, "a");
});

test("직전 구절은 다시 뽑히지 않는다", () => {
  for (let i = 0; i < 50; i += 1) {
    assert.notEqual(pickVerse(pool, "a").id, "a");
  }
});

/**
 * [2026-08-19 — 배선이 빠져 있던 자리를 고정한다]
 *   pickVerse는 처음부터 previousId를 받게 돼 있었고 KEYS.VERSE_INDEXES도
 *   정의돼 있었는데 **호출부가 아무것도 넘기지 않았다.** 그래서 위의
 *   "직전 구절은 다시 뽑히지 않는다" 테스트는 통과하는데 실제 앱에서는
 *   재방문 시 같은 구절이 1/10 확률로 다시 나왔다 — 함수는 옳고
 *   부르는 쪽이 틀린 유형이라 함수 테스트만으로는 잡히지 않는다.
 *   그래서 아래는 **호출부를 검사한다.**
 */
test("직전 구절 기억이 왕복한다 (인덱스가 아니라 id를 저장한다)", () => {
  versesTest.reset();
  assert.equal(lastVerseId("anxiety.worry"), null, "기록이 없으면 제외할 것도 없다");

  rememberVerse("anxiety.worry", "b");
  assert.equal(lastVerseId("anxiety.worry"), "b");
  assert.deepEqual(versesTest.snapshot(), { "anxiety.worry": "b" });

  // 풀에 구절이 추가돼 순서가 밀려도 같은 구절을 가리켜야 한다.
  // 인덱스를 저장했다면 여기서 다른 구절을 가리키게 된다.
  const grown = [{ id: "z", ref: "r", text: "t" }, ...pool];
  for (let i = 0; i < 30; i += 1) {
    assert.notEqual(pickVerse(grown, lastVerseId("anxiety.worry")).id, "b");
  }

  // 세분류마다 따로 기억한다 — 한 화면의 기록이 다른 화면을 막으면 안 된다.
  rememberVerse("joy.proud", "c");
  assert.equal(lastVerseId("anxiety.worry"), "b");
  assert.equal(lastVerseId("joy.proud"), "c");
  versesTest.reset();
});

test("잘못된 입력은 기억하지 않는다 (기록이 오염되면 회전이 멈춘다)", () => {
  versesTest.reset();
  rememberVerse("anxiety.worry", null);
  rememberVerse("anxiety.worry", undefined);
  rememberVerse("", "b");
  assert.deepEqual(versesTest.snapshot(), {});
  versesTest.reset();
});

test("App이 직전 구절을 실제로 넘긴다 (함수만 옳고 호출부가 빠졌던 결함)", () => {
  // 감정 화면과 위기 화면 **양쪽** — 위기 풀도 10건이라 반복이 눈에 띈다.
  assert.match(
    appSrc,
    /pickVerse\(\s*pool,\s*lastVerseId\(subcategory\.id\)/,
    "감정 화면이 직전 구절을 제외하지 않는다",
  );
  assert.match(
    appSrc,
    /pickVerse\(\s*crisisVerses\(versesData\),\s*lastVerseId\(CRISIS_POOL_KEY\)/,
    "위기 화면이 직전 구절을 제외하지 않는다",
  );
  assert.ok(
    appSrc.includes("rememberVerse(subcategory.id, verse.id)"),
    "보여준 구절을 기억하지 않으면 다음 방문에서 제외할 수 없다",
  );
  assert.ok(
    appSrc.includes("rememberVerse(CRISIS_POOL_KEY, verse.id)"),
    "위기 화면이 보여준 구절을 기억하지 않는다",
  );
  assert.ok(
    appSrc.includes("loadVerseHistory()"),
    "시작 시 기록을 읽지 않으면 첫 선택에 반영되지 않는다",
  );
});

test("공감 문구는 구절을 넘겨도 바뀌지 않는다 (버튼이 약속한 것만 바꾼다)", () => {
  // empathy가 verse에 의존하면 "다른 구절"이 화면 전체를 다시 뽑는 버튼이 된다.
  // 근거는 App.jsx의 VerseCard 위 주석에 있다.
  const empathyMemo = appSrc.match(
    /const empathy = useMemo\([\s\S]{0,200}?\);/,
  );
  assert.ok(empathyMemo, "공감 문구 선택부를 찾지 못했다");
  assert.ok(
    !/verse/.test(empathyMemo[0]),
    "공감 문구가 구절에 의존한다 — 구절을 넘길 때마다 문장이 바뀐다",
  );
});

test("구절이 하나뿐이면 그것을 돌려준다", () => {
  const single = [{ id: "only", ref: "r", text: "t" }];
  assert.equal(pickVerse(single, "only").id, "only");
  assert.equal(nextVerse(single, "only").id, "only");
});

// --- 깨진 데이터 -------------------------------------------------------------

test("구절 데이터가 없거나 깨져도 죽지 않는다", () => {
  assert.deepEqual(versesFor(null, "anxiety.worry"), []);
  assert.deepEqual(versesFor({}, "anxiety.worry"), []);
  assert.deepEqual(crisisVerses(null), []);
  assert.equal(pickVerse([]), null);
  assert.equal(pickVerse(null), null);
  assert.equal(nextVerse([], "x"), null);
});

test("쓸 만한 구절 데이터인지 판정한다", () => {
  assert.equal(isUsableVerses(verses), true);
  assert.equal(isUsableVerses(null), false);
  assert.equal(isUsableVerses({ verses: [] }), false);
  assert.equal(isUsableVerses({ verses: [{ id: "a" }] }), false, "ref·text가 없으면 거부");
});

test("모든 구절에 id·ref·text가 있다", () => {
  for (const verse of [...verses.verses, ...verses.crisis]) {
    assert.ok(verse.id && verse.ref && verse.text, `깨진 구절: ${JSON.stringify(verse)}`);
    assert.ok(verse.text.length > 5, `본문이 너무 짧다: ${verse.id}`);
  }
});

test("번역본 표시가 개역한글이다", () => {
  assert.equal(verses.translation, "krv1961");
});
