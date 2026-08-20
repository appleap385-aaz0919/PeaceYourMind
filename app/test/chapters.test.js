/**
 * 이어서 읽기 — 장 본문의 페이지 규칙과 합본 구간 처리.
 *
 * 여기서 지키는 것
 *   · 시작 위치 — 인용한 끝 절 다음부터. 그럴 수 없는 49건의 처리
 *   · 장 경계를 넘지 않는다
 *   · 합본 구간(같은 본문이 연속 복제된 곳)을 한 번만 그린다
 *   · ★ 후렴(같은 본문이 떨어져 반복되는 곳)은 **합치지 않는다**
 *   · 감정 구절 289건 전부가 열 수 있는 장 파일을 가진다
 *
 * [반대 방향 검사가 더 중요하다]
 *   합본을 묶는 검사는 실패하면 화면에 같은 문장이 두 번 보여 눈에 띈다.
 *   후렴을 묶지 않는 검사는 실패해도 조용하다 — 시편 107편에서 절 8·15·21·31이
 *   하나로 접혀도 화면은 멀쩡해 보이고, 원문이 의도적으로 반복한 후렴이
 *   사라진 것을 아무도 모른다. 그쪽이 동일성유지권 위반이다.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  PAGE_SIZE,
  chapterUnits,
  chapterPath,
  clampCursor,
  initialCursor,
  lastCursor,
  pageUnits,
} from "../src/lib/chapters.js";
import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const verses = JSON.parse(readFileSync(join(root, "src", "data", "verses.json"), "utf8"));

/** app/public/krv/<book>/<chapter>.json — 배포되는 것과 같은 파일을 읽는다. */
function loadChapterFile(book, chapter) {
  const path = join(root, "public", "krv", book, `${chapter}.json`);
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : null;
}

// --- 합본 구간과 후렴 --------------------------------------------------------

test("중복이 없으면 절 하나가 단위 하나다", () => {
  const units = chapterUnits(["가", "나", "다"]);
  assert.equal(units.length, 3);
  assert.deepEqual(
    units.map((u) => u.label),
    ["1", "2", "3"],
  );
  assert.deepEqual(units[0], { from: 1, to: 1, label: "1", text: "가" });
});

test("연속으로 같은 본문은 한 단위로 묶고 절 번호를 범위로 적는다", () => {
  const units = chapterUnits(["같다", "같다", "같다", "다르다"]);
  assert.equal(units.length, 2);
  assert.deepEqual(units[0], { from: 1, to: 3, label: "1-3", text: "같다" });
  assert.deepEqual(units[1], { from: 4, to: 4, label: "4", text: "다르다" });
});

test("★ 떨어져 있는 같은 본문(후렴)은 합치지 않는다", () => {
  // 시편 46편 7절·11절 구조. 원문이 의도적으로 반복하는 것이라
  // 묶으면 후렴 하나가 화면에서 사라진다.
  const units = chapterUnits(["가", "후렴", "나", "후렴"]);
  assert.equal(units.length, 4);
  assert.deepEqual(
    units.map((u) => u.label),
    ["1", "2", "3", "4"],
  );
});

test("실제 데이터 — 합본 구간이 있는 장은 정확히 2개다", () => {
  // gen_krv_chapters.py의 리포트와 같은 값이어야 한다.
  // 큐레이션이 바뀌어 새 장이 들어오면 여기가 먼저 깨진다.
  const found = [];
  for (const verse of verses.verses) {
    const chapter = loadChapterFile(verse.read.book, verse.read.chapter);
    if (!chapter) continue;
    const units = chapterUnits(chapter.verses);
    if (units.some((unit) => unit.to > unit.from)) found.push(chapter.title);
  }
  assert.deepEqual([...new Set(found)].sort(), ["시편 92편", "이사야 30장"]);
});

test("실제 데이터 — 시편 92편 1-3절이 한 번만 그려진다", () => {
  const chapter = loadChapterFile("Psalms", 92);
  const units = chapterUnits(chapter.verses);
  assert.equal(units[0].label, "1-3");
  assert.equal(units[1].label, "4");
});

test("실제 데이터 — 시편 46편의 후렴 두 번이 그대로 남는다", () => {
  const chapter = loadChapterFile("Psalms", 46);
  const units = chapterUnits(chapter.verses);
  assert.equal(units.length, chapter.verses.length, "후렴이 접혔다");
  assert.equal(units[6].text, units[10].text, "7절과 11절은 같은 본문이 맞다");
});

// --- 시작 위치 ---------------------------------------------------------------

test("인용한 끝 절 다음부터 시작한다", () => {
  // 시편 130:1 → 2절부터. 8절짜리 장이라 뒤로 당길 필요가 없다.
  const units = chapterUnits(new Array(8).fill(0).map((_, i) => `절${i + 1}`));
  assert.equal(initialCursor(2, units), 1);
  assert.deepEqual(
    pageUnits(units, initialCursor(2, units)).map((u) => u.label),
    ["2", "3", "4", "5"],
  );
});

test("남은 절이 한 페이지보다 적으면 장 끝에 맞춰 뒤로 당긴다", () => {
  const units = chapterUnits(new Array(8).fill(0).map((_, i) => `절${i + 1}`));
  // 시편 130:6 → 7절부터면 2절뿐이다. 5-8절로 당긴다.
  assert.deepEqual(
    pageUnits(units, initialCursor(7, units)).map((u) => u.label),
    ["5", "6", "7", "8"],
  );
});

test("★ 인용 구절이 장의 마지막이면 장 처음부터 연다", () => {
  // 로마서 8:38-39 → from=40인데 로마서 8장은 39절로 끝난다.
  const units = chapterUnits(new Array(39).fill(0).map((_, i) => `절${i + 1}`));
  assert.equal(initialCursor(40, units), 0);
  assert.deepEqual(
    pageUnits(units, initialCursor(40, units)).map((u) => u.label),
    ["1", "2", "3", "4"],
  );
});

test("한 페이지보다 짧은 장은 통째로 한 페이지다", () => {
  // 시편 131편 3절 — 3절짜리 장이고 인용이 마지막 절이다.
  const units = chapterUnits(["가", "나", "다"]);
  assert.equal(initialCursor(4, units), 0);
  assert.equal(lastCursor(units), 0);
  assert.deepEqual(
    pageUnits(units, 0).map((u) => u.label),
    ["1", "2", "3"],
  );
});

// --- 이동 -------------------------------------------------------------------

test("이동은 페이지 크기만큼이고 장 밖으로 나가지 않는다", () => {
  const units = chapterUnits(new Array(11).fill(0).map((_, i) => `절${i + 1}`));
  const last = lastCursor(units); // 11 - 4 = 7
  assert.equal(last, 7);
  assert.equal(clampCursor(-3, units), 0);
  assert.equal(clampCursor(99, units), 7);
  assert.deepEqual(
    pageUnits(units, last).map((u) => u.label),
    ["8", "9", "10", "11"],
  );
});

test("어떤 페이지도 장 경계를 넘지 않는다", () => {
  for (const verse of verses.verses) {
    const chapter = loadChapterFile(verse.read.book, verse.read.chapter);
    const units = chapterUnits(chapter.verses);
    for (let cursor = 0; cursor <= lastCursor(units); cursor += 1) {
      const page = pageUnits(units, cursor);
      assert.ok(page.length > 0, `${verse.ref}: 빈 페이지가 나왔다`);
      assert.ok(page.length <= PAGE_SIZE, `${verse.ref}: 페이지가 ${PAGE_SIZE}절을 넘는다`);
      assert.ok(page[0].from >= 1, `${verse.ref}: 1절 앞으로 나갔다`);
      assert.ok(
        page[page.length - 1].to <= chapter.verses.length,
        `${verse.ref}: 장 끝을 넘었다`,
      );
    }
  }
});

// --- 실제 데이터 전수 --------------------------------------------------------

test("감정 구절 289건 전부가 열 수 있는 장 파일을 가진다", () => {
  const missing = verses.verses
    .filter((v) => !loadChapterFile(v.read.book, v.read.chapter))
    .map((v) => v.ref);
  assert.deepEqual(missing, [], "장 파일이 없다 — gen_krv_chapters.py를 다시 돌릴 것");
});

test("★ 인용이 장의 마지막인 구절 20건이 전부 유효한 첫 페이지를 낸다", () => {
  // 289건 중 20건(6.9%)이다. 규칙이 없으면 이 구절들은 빈 화면이 된다.
  // 시편 23:6·로마서 8:38-39처럼 이 앱의 대표 구절이 여기 들어 있어
  // 예외로 둘 수 없다. 개수를 박아 두어 큐레이션이 바뀌면 눈에 띄게 한다.
  const atEnd = [];
  for (const verse of verses.verses) {
    const chapter = loadChapterFile(verse.read.book, verse.read.chapter);
    if (verse.read.from > chapter.verses.length) atEnd.push(verse);
  }
  assert.equal(atEnd.length, 20, "장 마지막 구절 수가 바뀌었다");

  for (const verse of atEnd) {
    const chapter = loadChapterFile(verse.read.book, verse.read.chapter);
    const units = chapterUnits(chapter.verses);
    assert.equal(initialCursor(verse.read.from, units), 0, `${verse.ref}: 장 처음이 아니다`);
    assert.ok(pageUnits(units, 0).length > 0, `${verse.ref}: 첫 페이지가 비었다`);
  }
});

test("모든 구절의 첫 페이지에 최소 한 단위가 있다", () => {
  for (const verse of verses.verses) {
    const chapter = loadChapterFile(verse.read.book, verse.read.chapter);
    const units = chapterUnits(chapter.verses);
    const page = pageUnits(units, initialCursor(verse.read.from, units));
    assert.ok(page.length > 0, `${verse.ref}: 첫 페이지가 비었다`);
  }
});

// --- 경로 -------------------------------------------------------------------

test("장 파일 경로가 배포 구조와 맞는다", () => {
  assert.ok(chapterPath("Psalms", 130).endsWith("krv/Psalms/130.json"));
});

// --- 격리 -------------------------------------------------------------------

test("위기 구절에는 이어서 읽기 시작점이 없다", () => {
  // 위기 구절의 앞뒤에 무엇이 있는지 통제할 수 없다. 데이터에 시작점이
  // 없어야 그 화면을 만드는 일이 한 줄짜리 실수로 가능해지지 않는다.
  for (const entry of verses.crisis) {
    assert.equal(entry.read, undefined, `${entry.id}: 위기 구절에 read가 붙었다`);
  }
});

test("chapters.js가 구절 데이터를 직접 읽지 않는다", () => {
  // 이 모듈은 장 본문만 다룬다. verses.json을 import하기 시작하면
  // 위기 풀이 같은 모듈의 사정거리에 들어온다.
  const source = readSource("lib", "chapters.js");
  assert.ok(!source.includes("verses.json"), "chapters.js가 구절 데이터를 읽는다");
  assert.ok(!source.includes("crisis"), "chapters.js가 위기 풀을 안다");
});
