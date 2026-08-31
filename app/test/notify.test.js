/**
 * 구절 알림 — 고르는 규칙과 알림 계약.
 *
 * 여기서 지키는 것
 *   · 풀이 설계대로 걸러진다 (시편 전체 · notify: false · 위기 격리)
 *   · 같은 책이 이틀 연속 오지 않는다
 *   · 최근 30일에 보낸 것을 다시 보내지 않는다
 *   · 규칙이 마르면 **정해진 순서로** 풀린다
 *   · VERSE_INDEXES를 재사용하지 않는다
 *   · 권한을 첫 실행에 묻지 않는다
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  SEEN_WINDOW_DAYS,
  dropScheduled,
  WINDOW_DAYS,
  notificationContent,
  notifyPool,
  pickSequence,
  pruneSeen,
  recentlySent,
  scheduleTimes,
} from "../src/lib/notifySelect.js";
import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const verses = JSON.parse(
  readFileSync(join(here, "..", "src", "data", "verses.json"), "utf8"),
);
const notifySrc = readSource("lib", "notify.js");
const selectSrc = readSource("lib", "notifySelect.js");
const aboutSrc = readSource("components", "About.jsx");
const dailySrc = readSource("components", "DailyVerse.jsx");
const appSrc = readSource("App.jsx");

const DAY = 24 * 60 * 60 * 1000;

/* --- 풀 ------------------------------------------------------------------ */

test("알림 풀은 107건이다 (시편 전체 + notify:false 23건 제외)", () => {
  const pool = notifyPool(verses);
  assert.equal(pool.length, 107);
  assert.equal(verses.verses.filter((v) => v.notify === false).length, 23);
  assert.equal(verses.verses.filter((v) => v.read.book === "Psalms").length, 163);
});

test("시편은 read.book으로 판정한다 (표시 문자열이 아니다)", () => {
  // ref는 화면에 보이는 문자열이라 문구가 바뀌면 깨진다. 데이터 필드를 본다.
  assert.ok(
    selectSrc.includes('EXCLUDED_BOOK = "Psalms"'),
    "책 이름 상수가 없다",
  );
  assert.ok(
    selectSrc.includes("v.read?.book !== EXCLUDED_BOOK"),
    "read.book이 아니라 다른 것으로 시편을 판정하고 있다",
  );
  assert.ok(
    !notifyPool(verses).some((v) => v.read.book === "Psalms"),
    "풀에 시편이 남았다",
  );
});

test("제외된 구절은 데이터가 정한다 — 코드에 id가 박혀 있지 않다", () => {
  // 코드에 목록을 박으면 큐레이션과 갈라지고, 구절이 바뀔 때 아무도 안 고친다.
  for (const id of ["exo.3.3", "lam.3.19", "mat.5.4", "jhn.11.35"]) {
    assert.ok(!selectSrc.includes(id), `notifySelect.js에 ${id}가 박혀 있다`);
    assert.ok(!notifySrc.includes(id), `notify.js에 ${id}가 박혀 있다`);
  }
  assert.ok(
    selectSrc.includes("v.notify !== false"),
    "notify 플래그를 !== false 로 읽지 않는다 — === true 면 전부 빠진다",
  );
});

test("서사와 탄식이 풀에 남지 않았다", () => {
  const pool = notifyPool(verses);
  assert.equal(pool.filter((v) => v.theme === "bible_story").length, 0);
  assert.equal(pool.filter((v) => v.theme === "lament").length, 0);
});

test("⛔ 위기 구절은 풀에 들어올 길이 없다", () => {
  const pool = notifyPool(verses);
  const crisisIds = new Set(verses.crisis.map((v) => v.id));
  assert.ok(!pool.some((v) => crisisIds.has(v.id)), "위기 구절이 섞였다");
  // notifyPool은 data.verses만 본다 — crisis 배열을 아예 읽지 않는다.
  assert.ok(!selectSrc.includes("crisis"), "notifySelect.js가 crisis를 언급한다");
});

/* --- 배치 제약 ------------------------------------------------------------ */

test("같은 책이 이틀 연속 오지 않는다", () => {
  const pool = notifyPool(verses);
  let rng = 0;
  const seq = pickSequence(pool, new Set(), 60, () => {
    rng = (rng * 9301 + 49297) % 233280; // 재현 가능한 난수
    return rng / 233280;
  });
  assert.equal(seq.length, 60);
  for (let i = 1; i < seq.length; i += 1) {
    assert.notEqual(
      seq[i].read.book,
      seq[i - 1].read.book,
      `${i}일째에 ${seq[i].read.book}가 연속으로 왔다`,
    );
  }
});

test("직전 창의 마지막 책과도 연속되지 않는다", () => {
  const pool = notifyPool(verses);
  const seq = pickSequence(pool, new Set(), 5, () => 0, "Isaiah");
  assert.notEqual(seq[0].read.book, "Isaiah", "창을 이어 붙일 때 연속이 생겼다");
});

test("책별 상한을 쓰지 않는다 (풀만 깎고 다양성을 늘리지 못한다)", () => {
  assert.ok(!selectSrc.includes("CAP") && !selectSrc.includes("상한"),
    "책별 상한이 들어왔다 — 배치 제약으로 푸는 것이 결정이었다");
});

/* --- 중복 회피 ------------------------------------------------------------ */

test("최근 30일에 보낸 구절은 다시 고르지 않는다", () => {
  const pool = notifyPool(verses);
  const now = Date.now();
  const recent = new Set(pool.slice(0, 40).map((v) => v.id));
  const seq = pickSequence(pool, recent, 14, () => 0.5);
  assert.ok(seq.every((v) => !recent.has(v.id)), "최근에 보낸 구절이 다시 나왔다");
  assert.equal(SEEN_WINDOW_DAYS, 30);
});

test("30일이 지난 기록은 버린다 (설정이 영원히 자라지 않는다)", () => {
  const now = Date.now();
  const seen = {
    old: new Date(now - 31 * DAY).toISOString(),
    fresh: new Date(now - 3 * DAY).toISOString(),
    broken: "날짜아님",
  };
  assert.deepEqual(Object.keys(pruneSeen(seen, now)), ["fresh"]);
  assert.deepEqual([...recentlySent(seen, now)], ["fresh"]);
});

test("⛔ VERSE_INDEXES를 재사용하지 않는다 (화면의 구절 회전이 건너뛰어진다)", () => {
  assert.ok(
    !notifySrc.includes("VERSE_INDEXES"),
    "알림이 화면의 구절 기록을 건드린다",
  );
  assert.ok(notifySrc.includes("NOTIFY_SEEN"), "알림 전용 키를 쓰지 않는다");
});

/* --- 규칙이 마를 때 -------------------------------------------------------- */

test("후보가 마르면 연속 금지를 먼저 풀고, 그다음 30일 창을 푼다", () => {
  // 한 책에 두 건뿐인 풀 — 연속 금지를 지키면 두 번째를 못 고른다.
  const tiny = [
    { id: "a", read: { book: "Onlybook" }, ref: "A 1:1", text: "가" },
    { id: "b", read: { book: "Onlybook" }, ref: "B 1:1", text: "나" },
  ];
  const seq = pickSequence(tiny, new Set(), 2, () => 0);
  assert.equal(seq.length, 2, "연속 금지를 풀지 못해 멈췄다");

  // 전부 최근에 봤어도 아무것도 못 보내는 것보다 낫다.
  const all = new Set(["a", "b"]);
  const seq2 = pickSequence(tiny, all, 1, () => 0);
  assert.equal(seq2.length, 1, "30일 창을 풀지 못해 아무것도 못 골랐다");
});

/* --- 시각 ---------------------------------------------------------------- */

test("예약하자마자 울리지 않는다 (오늘 시각이 지났으면 내일부터)", () => {
  const now = new Date("2026-08-31T10:00:00");
  const times = scheduleTimes(9, 0, 3, now);
  assert.ok(times[0].getTime() > now.getTime(), "과거 시각을 예약했다");
  assert.equal(times[0].getDate(), 1, "다음 날로 넘어가지 않았다");
  assert.equal(times[1].getTime() - times[0].getTime(), DAY);
  assert.equal(times.length, 3);
});

test("아직 지나지 않았으면 오늘 보낸다", () => {
  const now = new Date("2026-08-31T07:00:00");
  const times = scheduleTimes(9, 0, 1, now);
  assert.equal(times[0].getDate(), 31);
});

test("창은 14일이다", () => {
  assert.equal(WINDOW_DAYS, 14);
});

/* --- 내용과 톤 ------------------------------------------------------------ */

test("제목은 구절 참조, 본문은 구절이다", () => {
  const verse = notifyPool(verses)[0];
  const { title, body, largeBody } = notificationContent(verse);
  assert.equal(title, verse.ref);
  assert.equal(body, verse.text);
  assert.equal(largeBody, verse.text, "긴 구절이 접힌 알림에서 잘린다");
});

test("⛔ 앱의 목소리로 격려하지 않는다", () => {
  // 화면에서도 단정하지 않는 앱이다. 알림에서만 갑자기 격려하면 톤이 깨진다.
  for (const word of ["힘내", "화이팅", "좋은 하루", "오늘도"]) {
    assert.ok(!selectSrc.includes(word), `알림 문구에 "${word}"가 들어왔다`);
  }
});

/* --- 권한과 화면 ----------------------------------------------------------- */

test("권한을 첫 실행에 묻지 않는다 — 토글을 켤 때만 묻는다", () => {
  assert.ok(
    !appSrc.includes("ensurePermission") && !appSrc.includes("requestPermissions"),
    "앱 시작 경로가 권한을 묻는다",
  );
  assert.ok(
    notifySrc.includes("export async function setEnabled") &&
      /setEnabled[\s\S]*ensurePermission/.test(notifySrc),
    "토글이 권한을 묻지 않는다",
  );
});

test("알림 화면에 영상과 광고가 없다", () => {
  for (const token of ["VideoList", "AdSlot", "adsbygoogle", "layersFor"]) {
    assert.ok(!dailySrc.includes(token), `알림 화면에 ${token}이 들어왔다`);
  }
  assert.ok(dailySrc.includes("ChapterReader"), "이어서 읽기가 없다");
  assert.ok(dailySrc.includes("지금 마음을 적어볼까요"), "입력으로 가는 문이 없다");
});

test("알림 화면이 다른 모든 분기보다 먼저다", () => {
  const daily = appSrc.indexOf("if (dailyVerse)");
  const about = appSrc.indexOf("if (showAbout)");
  assert.ok(daily > 0, "알림 화면 분기가 없다");
  assert.ok(daily < about, "알림 화면이 다른 화면 뒤에 있다");
});

test("설정은 About 안 위쪽 절에 있다", () => {
  const notify = aboutSrc.indexOf("<NotifySettings");
  const bible = aboutSrc.indexOf("성경 본문");
  assert.ok(notify > 0, "About에 알림 설정이 없다");
  assert.ok(notify < bible, "알림 설정이 아래쪽에 있다 — 긴 화면에서 못 찾는다");
});

test("SCHEDULE_EXACT_ALARM을 매니페스트에서 걷어낸다", () => {
  const manifest = readFileSync(
    join(here, "..", "android", "app", "src", "main", "AndroidManifest.xml"),
    "utf8",
  );
  assert.ok(
    /SCHEDULE_EXACT_ALARM[\s\S]{0,80}tools:node="remove"/.test(manifest),
    "정확한 알람 권한이 그대로 병합된다 — 매일 알림에는 필요 없다",
  );
});

test("구절 풀을 인자로 받지 않는다 (틀린 데이터를 넘길 자리가 없다)", () => {
  // 2026-08-31 실측: About이 dataRef(영상 데이터)를 넘겨 풀이 빈 배열이 됐고,
  // 예약이 조용히 0건이 됐다. 아무 오류도 나지 않아 화면만으로는 못 찾는다.
  assert.ok(
    notifySrc.includes('import versesData from "../data/verses.json"'),
    "notify.js가 구절 데이터를 직접 읽지 않는다",
  );
  assert.ok(
    /export async function refreshSchedule\(now = new Date\(\)\)/.test(notifySrc),
    "refreshSchedule이 여전히 데이터를 인자로 받는다",
  );
  assert.ok(
    !/<About[^>]*data=/.test(appSrc),
    "About에 data 프롭을 넘기고 있다 — 알림이 그것을 구절로 오해할 수 있다",
  );
  assert.ok(
    notifySrc.includes("notifyPool(versesData)"),
    "풀을 번들 구절이 아닌 다른 것에서 만든다",
  );
});

test("권한 응답을 기다리는 동안에도 설정 절이 보인다", () => {
  // 2026-08-31 실측: ready를 권한 응답 뒤에 세워 About을 열었는데
  // 알림 절이 통째로 사라졌다. 먼저 그리고 나중에 갱신한다.
  const ready = aboutSrc.indexOf("setReady(true)");
  const perm = aboutSrc.indexOf("await ensurePermission()");
  assert.ok(ready > 0 && perm > 0, "설정 절의 초기화 흐름을 찾지 못했다");
  assert.ok(ready < perm, "권한을 기다린 뒤에야 화면을 그린다 — 절이 사라진다");
});

test("⛔ 정확한 알람을 요청하지 않는다 (schedule이 멈추는 원인이었다)", () => {
  // 2026-08-31 실측: isExactNotification의 기본값이 true라, 매니페스트에서
  // SCHEDULE_EXACT_ALARM을 걷어낸 상태로 예약하면 플러그인이 시스템의
  // "알람 및 리마인더" 화면을 열고 결과를 기다린다 — schedule()이 영영
  // 응답하지 않고 예약은 0건이 된다. 아무 오류도 나지 않는다.
  assert.ok(
    notifySrc.includes("isExactNotification: false"),
    "정확한 알람을 끄지 않았다 — 권한을 뺀 상태에서 schedule()이 멈춘다",
  );
});

test("⛔ 플러그인 프록시를 async 함수에서 그대로 돌려주지 않는다", () => {
  // 2026-08-31 실기기 콘솔:
  //   j: "LocalNotifications.then()" is not implemented on android
  // async 함수의 return 값이 thenable이면 JS가 .then()을 부르고, Capacitor
  // 프록시는 그것을 네이티브 호출로 바꾼다. 모든 진입점이 조용히 실패했다.
  assert.ok(
    notifySrc.includes("boxed = { ln: mod.LocalNotifications }"),
    "플러그인을 상자에 담지 않는다 — thenable로 풀려 네이티브 호출이 된다",
  );
  assert.ok(
    !/return\s+mod\.LocalNotifications/.test(notifySrc),
    "플러그인을 그대로 return한다",
  );
  assert.ok(
    notifySrc.includes("const { ln } = box"),
    "호출부가 상자에서 꺼내 쓰지 않는다",
  );
});

test("⛔ 앱을 여러 번 열어도 보낸 기록이 누적되지 않는다", () => {
  // 2026-08-31 실측: refreshSchedule이 창을 다시 짤 때마다 14건을 누적 기록해
  // 여덟 번쯤 열자 107건 풀 전체가 "최근 보냄"이 됐다(notify_seen 107건).
  // 30일 중복 회피가 무의미해지고 매번 폴백 경로로 고르게 된다.
  const now = Date.parse("2026-09-01T09:00:00");
  const seen = {
    delivered: "2026-08-30T09:00:00.000Z",   // 지나간 것 — 남아야 한다
    scheduled1: "2026-09-05T00:00:00.000Z",  // 아직 안 온 것 — 버려야 한다
    scheduled2: "2026-09-10T00:00:00.000Z",
  };
  assert.deepEqual(Object.keys(dropScheduled(seen, now)), ["delivered"]);

  // 창을 다시 짜도 크기가 자라지 않는다
  let store = {};
  for (let round = 0; round < 10; round += 1) {
    store = dropScheduled(store, now);
    for (let i = 0; i < 14; i += 1) store[`v${round}-${i}`] = new Date(now + (i + 1) * DAY).toISOString();
  }
  assert.equal(Object.keys(store).length, 14, "다시 짤 때마다 기록이 누적된다");

  assert.ok(
    notifySrc.includes("dropScheduled(pruneSeen("),
    "refreshSchedule이 미래 예약 기록을 버리지 않는다",
  );
});

test("알림 화면은 참조를 머리 줄에 한 번만 그린다", () => {
  // 2026-08-31 실기기 비교로 정한 구조(ㄱ안). 구절 아래 참조와 이어서 읽기
  // 헤더가 같은 T.sand·세리프로 연달아 나와 경쟁하던 것을 없앴다.
  assert.ok(
    /오늘의 구절 <span style=\{styles\.eyebrowRef\}>· \{verse\.ref\}<\/span>/.test(dailySrc),
    "참조가 머리 줄에 없다",
  );
  assert.ok(
    /<VerseCard verse=\{verse\} canRotate=\{false\} hideRef \/>/.test(dailySrc),
    "구절 아래 참조를 끄지 않았다 — 참조가 두 번 나온다",
  );
  // 결과 화면은 그대로다 — 거기 참조는 "다른 구절" 버튼과 한 몫이다.
  assert.ok(!/hideRef/.test(appSrc), "결과 화면에서도 참조를 껐다");
});

test("시안 비교용 임시 코드가 남지 않았다", () => {
  for (const src of [dailySrc, readSource("components", "ChapterReader.jsx")]) {
    assert.ok(!src.includes("__pymVariant"), "변주 스위치가 남았다");
    assert.ok(!src.includes("progressOnly"), "변주 분기가 남았다");
  }
});
