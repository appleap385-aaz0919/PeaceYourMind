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
  attributionOf,
  crisisVerses,
  isUsableVerses,
  nextVerse,
  pickVerse,
  versesFor,
} from "../src/lib/verses.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const verses = JSON.parse(readFileSync(join(root, "src", "data", "verses.json"), "utf8"));
const taxonomy = JSON.parse(readFileSync(join(root, "src", "data", "taxonomy.json"), "utf8"));
const verseCardSrc = readFileSync(join(root, "src", "components", "VerseCard.jsx"), "utf8");
const aboutSrc = readFileSync(join(root, "src", "components", "About.jsx"), "utf8");

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

test("구절 카드가 출처를 그린다", () => {
  assert.ok(verseCardSrc.includes("attribution"), "카드에 출처 표기가 없다");
});

test("정보 화면에도 출처가 있다 (중복 표기는 요건이다)", () => {
  assert.ok(aboutSrc.includes("attribution"));
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
