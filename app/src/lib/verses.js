/**
 * 구절 선택 — verses.json을 읽는 유일한 지점.
 *
 * ⚠ 이 파일의 존재 이유는 격리다. lib/videos.js가 crisis와 일반 풀을 갈라 두는 것과
 *   같은 이유이며, 여기서는 **감정 구절과 위기 구절**을 가른다.
 *
 *   위기 구절은 최상위 `crisis` 배열에만 있고 `verses`에는 없다. 감정 매핑을 타지
 *   않는 운영자 고정 큐레이션이다(PLAN.md 7절). 위기 상태에서 문제가 되는 표현은
 *   감정 화면에서 문제가 되지 않는 것과 다르다 — 시편 34:18을 위기 풀에서 뺀 것이
 *   그 사례다(후반부 "중심에 통회하는 자"가 구원의 조건처럼 읽힐 여지).
 *
 *   그래서 아래 두 함수는 서로의 배열에 접근하지 않는다.
 *
 * [출처 표기는 데이터에서 온다]
 *   attribution 필드는 verses.json이 들고 온다. 화면에 하드코딩하지 않는 이유는
 *   저작인격권(성명표시권) 요구가 데이터와 함께 움직여야 하기 때문이다 —
 *   나중에 번역본을 바꾸면 표기도 같이 바뀌어야 한다.
 *
 * [직전 구절 기억 — 2026-08-19 배선 완료]
 *   `pickVerse`는 처음부터 previousId를 받게 돼 있었고 `KEYS.VERSE_INDEXES`도
 *   db.js에 정의돼 있었는데, **호출부가 아무것도 넘기지 않아 둘 다 죽어 있었다.**
 *   그래서 문구는 재방문해도 직전 것이 안 나오는데 구절만 1/10 확률로 또 나왔다.
 *   설계가 없었던 게 아니라 배선이 빠진 것이라, 있는 자리를 잇기만 했다.
 *
 *   ⚠ **인덱스가 아니라 id를 저장한다** (문구 쪽과 다른 점이다).
 *     문구 풀은 taxonomy.yaml에 고정돼 순서가 안 변하지만, 구절 풀은
 *     세분류에 구절을 더하면 순서가 밀린다. 인덱스를 저장하면 그때 저장된
 *     숫자가 **다른 구절**을 가리키게 되어 "직전 것 제외"가 조용히 어긋난다.
 *     id는 구절이 추가돼도 같은 구절을 가리킨다.
 */

import { KEYS, getSetting, setSetting } from "./db.js";

// 위기 풀의 기억 키. 세분류 id와 같은 이름공간을 쓰지만 점(.)이 없어 겹치지 않는다.
export const CRISIS_POOL_KEY = "crisis";

// 세션 동안의 캐시. 매 표시마다 IndexedDB를 기다릴 이유가 없고,
// 저장은 뒤에서 비동기로 따라간다 (messages.js와 같은 구조).
let lastShown = {};
let loaded = false;

/** 앱 시작 시 한 번. 화면이 그려지기 전에 끝나야 첫 선택부터 반영된다. */
export async function loadVerseHistory() {
  if (loaded) return;
  const stored = await getSetting(KEYS.VERSE_INDEXES, {});
  lastShown = stored && typeof stored === "object" ? stored : {};
  loaded = true;
}

/** 이 풀에서 직전에 보여준 구절 id. 기록이 없으면 null(=제외할 것 없음). */
export function lastVerseId(poolKey) {
  const id = lastShown[poolKey];
  return typeof id === "string" ? id : null;
}

/** 방금 보여준 구절을 기억한다. 첫 선택과 "다른 구절" 양쪽에서 부른다. */
export function rememberVerse(poolKey, verseId) {
  if (!poolKey || typeof verseId !== "string") return;
  lastShown[poolKey] = verseId;
  void persist();
}

let pending = null;
function persist() {
  // 연속 호출을 한 번의 쓰기로 묶는다 (messages.js persist와 같은 이유).
  if (pending) return pending;
  pending = Promise.resolve().then(async () => {
    pending = null;
    await setSetting(KEYS.VERSE_INDEXES, lastShown);
  });
  return pending;
}

export const __test__ = {
  reset() {
    lastShown = {};
    loaded = false;
  },
  snapshot: () => ({ ...lastShown }),
  seed(map) {
    lastShown = { ...map };
    loaded = true;
  },
};

/** 감정 세분류에 붙은 구절들. 위기 배열에는 접근하지 않는다. */
export function versesFor(data, subcategoryId) {
  if (!data || !Array.isArray(data.verses)) return [];
  return data.verses.filter(
    (v) => Array.isArray(v.emotion_tags) && v.emotion_tags.includes(subcategoryId),
  );
}

/** 위기 화면 구절. data.crisis만 읽는다. */
export function crisisVerses(data) {
  if (!data || !Array.isArray(data.crisis)) return [];
  return data.crisis;
}

/** 출처 표기 — 없으면 빈 문자열이 아니라 기본 문구를 돌려준다. */
export function attributionOf(data) {
  const text = typeof data?.attribution === "string" ? data.attribution.trim() : "";
  return text || "성경전서 개역한글판, 대한성서공회";
}

/**
 * 직전에 보여준 것을 제외하고 하나 고른다.
 *
 * 문구 회전(lib/messages.js)과 같은 규칙이다. 구절은 세분류당 10개 안팎이라
 * 재추첨 방식이면 같은 것이 연달아 나오는 체감이 크다.
 *
 * @param {object[]} pool
 * @param {string|null} previousId 직전에 보여준 구절 id
 */
export function pickVerse(pool, previousId = null) {
  if (!Array.isArray(pool) || pool.length === 0) return null;
  if (pool.length === 1) return pool[0];

  const candidates = pool.filter((v) => v.id !== previousId);
  const from = candidates.length ? candidates : pool;
  return from[Math.floor(Math.random() * from.length)];
}

/**
 * "다른 구절 보기" — 지금 보고 있는 것 다음 구절로 넘어간다.
 *
 * 랜덤이 아니라 순환인 이유: 사용자가 버튼을 누르는 것은 "이건 지금 안 맞는다"는
 * 뜻이다. 랜덤이면 같은 구절이 다시 나올 수 있고, 그러면 버튼이 고장 난 것처럼
 * 읽힌다. 한 바퀴 돌면 처음으로 돌아오지만, 그건 풀을 다 본 것이므로 정상이다.
 */
export function nextVerse(pool, currentId) {
  if (!Array.isArray(pool) || pool.length === 0) return null;
  const index = pool.findIndex((v) => v.id === currentId);
  if (index < 0) return pool[0];
  return pool[(index + 1) % pool.length];
}

/** 구절 데이터가 화면에 쓸 만한 모양인지. 깨진 번들에서 화면이 죽지 않게 한다. */
export function isUsableVerses(data) {
  if (!data || typeof data !== "object") return false;
  if (!Array.isArray(data.verses) || data.verses.length === 0) return false;
  return data.verses.every(
    (v) => v && typeof v.id === "string" && typeof v.ref === "string" && typeof v.text === "string",
  );
}
