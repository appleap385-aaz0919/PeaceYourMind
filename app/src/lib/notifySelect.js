/**
 * 알림 구절 고르기 — **순수 함수만 둔다.** 플러그인도 DOM도 모른다.
 *
 * [왜 화면과 다른 기준으로 고르는가 — 2026-08-31]
 *   결과 화면은 사용자가 감정을 말한 **뒤에** 구절을 고른다. 그래서 1인칭
 *   고백(시편)이 강하다 — 말한 마음을 받아 주기 때문이다.
 *   알림은 정반대다. 사용자는 아무 말도 하지 않았다. 그 자리에 "내 영혼아
 *   네가 어찌하여 낙망하며"가 도착하면 **감정을 넘겨짚는다.**
 *   그래서 시편 전체를 빼고, 약속·초대형 구절만 남긴다.
 *
 *   ⚠ 이것은 시편이 약해서가 아니다. HANDOFF 2.39가 "1인칭으로 자기 감정을
 *     말하는 장르는 시편뿐"이라고 실측해 두었고, 그 강점이 이 자리에서만
 *     약점이 된다.
 *
 * [제외는 데이터가 정한다]
 *   ⛔ id 목록을 여기에 박지 않는다. verses.yaml의 `notify: false`가 출처이고
 *     gen_verses_json.py가 내보낸다. 코드에 박으면 큐레이션과 갈라지고,
 *     구절이 바뀔 때 아무도 고치지 않는다.
 *   왜 뺐는지는 verses.yaml의 notify_note에 있다 — 되살리려는 사람이 읽는다.
 *
 * ⛔ 위기 구절(data.crisis)은 읽지 않는다. 이 모듈에 들어올 길이 없다.
 */

/** 알림에 쓰지 않는 책. 표시 문자열이 아니라 read.book(데이터 필드)으로 본다. */
const EXCLUDED_BOOK = "Psalms";

/** 최근 이만큼 안에 보낸 구절은 다시 보내지 않는다. */
export const SEEN_WINDOW_DAYS = 30;

/** 한 번에 예약해 두는 날 수. 앱을 열 때마다 이만큼으로 채운다. */
export const WINDOW_DAYS = 14;

/**
 * 알림 후보 — 시편과 notify: false를 뺀 나머지.
 *
 * `notify`는 제외된 구절에만 있다(gen_verses_json.py). 없으면 대상이라는
 * 뜻이므로 `!== false`로 읽는다 — `=== true`로 읽으면 전부 빠진다.
 */
export function notifyPool(data) {
  const verses = data?.verses;
  if (!Array.isArray(verses)) return [];
  return verses.filter(
    (v) => v && v.notify !== false && v.read?.book !== EXCLUDED_BOOK,
  );
}

/**
 * 최근 30일 안에 보낸 구절 id.
 *
 * @param {Record<string, string>} seen  {verseId: ISO 날짜}
 */
export function recentlySent(seen, now = Date.now()) {
  const cutoff = now - SEEN_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const out = new Set();
  for (const [id, at] of Object.entries(seen || {})) {
    const t = new Date(at).getTime();
    if (Number.isFinite(t) && t >= cutoff) out.add(id);
  }
  return out;
}

/**
 * **아직 오지 않은 예약 기록을 버린다.**
 *
 * [왜 필요한가 — 2026-08-31 실측으로 찾았다]
 *   NOTIFY_SEEN은 예약 **시점**에 적는다(실제 발송을 앱이 알 수 없다).
 *   그런데 refreshSchedule은 앱을 열 때마다 창을 통째로 다시 짠다 —
 *   그때마다 14건이 **누적**되어, 여덟 번쯤 열면 107건 풀 전체가
 *   "최근 보냄"이 된다. 실기기에서 notify_seen이 107건까지 찼다.
 *   그러면 30일 중복 회피가 무의미해지고 매번 폴백 경로로 고른다.
 *
 *   ★ 다시 짤 때는 옛 예약을 **취소**하므로, 아직 오지 않은 것은 보낸 적이
 *     없다. 그래서 미래 날짜 기록은 버리고 다시 채운다. 지나간 것만 남는다 —
 *     그것이 "실제로 받은 구절"이고 30일 창이 겨냥하는 대상이다.
 */
export function dropScheduled(seen, now = Date.now()) {
  const out = {};
  for (const [id, at] of Object.entries(seen || {})) {
    const t = new Date(at).getTime();
    if (Number.isFinite(t) && t <= now) out[id] = at;
  }
  return out;
}

/** 30일이 지난 기록은 버린다. 안 버리면 설정이 영원히 자란다. */
export function pruneSeen(seen, now = Date.now()) {
  const cutoff = now - SEEN_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const out = {};
  for (const [id, at] of Object.entries(seen || {})) {
    const t = new Date(at).getTime();
    if (Number.isFinite(t) && t >= cutoff) out[id] = at;
  }
  return out;
}

/**
 * 다음 N일치 구절을 고른다.
 *
 * 규칙 세 가지가 순서대로 적용된다.
 *   1. 최근 30일에 보낸 것은 뺀다
 *   2. **같은 책이 이틀 연속 오지 않는다** — 책별 상한은 쓰지 않는다
 *      (상한은 풀만 깎고 다양성을 늘리지 못한다. 실측으로 확인했다)
 *   3. 그 안에서 무작위
 *
 * ⚠ 후보가 마르면 규칙을 **순서대로 푼다.** 먼저 연속 금지를 풀고,
 *   그래도 없으면 30일 창을 푼다. 아무것도 못 보내는 것보다 낫고,
 *   푸는 순서가 정해져 있어야 결과를 설명할 수 있다.
 *
 * @param {object[]} pool      notifyPool()의 결과
 * @param {Set<string>} recent 최근 30일에 보낸 id
 * @param {number} count       고를 개수
 * @param {() => number} rng   0~1 난수. 테스트가 고정한다
 * @param {string|null} lastBook 직전에 보낸 책 (창을 이어 붙일 때)
 */
export function pickSequence(pool, recent, count, rng = Math.random, lastBook = null) {
  const chosen = [];
  const used = new Set();
  let prevBook = lastBook;

  for (let i = 0; i < count; i += 1) {
    const fresh = pool.filter((v) => !used.has(v.id) && !recent.has(v.id));
    // 1차: 연속 금지까지 지킨다
    let candidates = fresh.filter((v) => v.read?.book !== prevBook);
    // 2차: 연속 금지를 푼다
    if (!candidates.length) candidates = fresh;
    // 3차: 30일 창을 푼다 (풀 자체가 마른 경우)
    if (!candidates.length) {
      candidates = pool.filter((v) => !used.has(v.id) && v.read?.book !== prevBook);
      if (!candidates.length) candidates = pool.filter((v) => !used.has(v.id));
    }
    if (!candidates.length) break;

    const verse = candidates[Math.floor(rng() * candidates.length) % candidates.length];
    chosen.push(verse);
    used.add(verse.id);
    prevBook = verse.read?.book ?? null;
  }
  return chosen;
}

/**
 * 다음 알림이 울릴 시각들.
 *
 * 오늘 그 시각이 이미 지났으면 내일부터 시작한다 — 예약하자마자 울리는 것을
 * 막는다. 앱을 여는 행위가 알림을 부르면 안 된다.
 */
export function scheduleTimes(hour, minute, count, now = new Date()) {
  const first = new Date(now);
  first.setHours(hour, minute, 0, 0);
  if (first.getTime() <= now.getTime()) first.setDate(first.getDate() + 1);

  const times = [];
  for (let i = 0; i < count; i += 1) {
    const t = new Date(first);
    t.setDate(first.getDate() + i);
    times.push(t);
  }
  return times;
}

/**
 * 알림 하나의 내용.
 *
 * [톤 — 앱의 목소리를 바꾸지 않는다]
 *   제목은 **구절 참조**다. 안드로이드가 헤더에 앱 이름을 이미 보여주므로
 *   "오늘의 말씀" 같은 라벨을 더할 이유가 없고, 매일 달라 반복으로도 안 읽힌다.
 *   ⛔ "오늘도 힘내세요" 같은 격려를 넣지 않는다. 이 앱은 화면에서도 단정하지
 *     않는다 — 알림에서만 갑자기 격려하면 톤이 깨진다.
 */
export function notificationContent(verse) {
  return { title: verse.ref, body: verse.text, largeBody: verse.text };
}
