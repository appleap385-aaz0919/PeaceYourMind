/**
 * IndexedDB (idb) — videos 캐시와 settings.
 *
 * PLAN.md 4절:
 *   videos_cache : videos.json 원본 + 수신 시각
 *   settings     : 마지막 갱신 시각, 방문 기록, 문구 회전 인덱스
 *
 * 저장하는 건 전부 기기 안에만 있다. 서버로 나가는 경로가 코드에 없다.
 */

import { openDB } from "idb";

const DB_NAME = "peaceyourmind";
const DB_VERSION = 1;

export const STORE_VIDEOS = "videos_cache";
export const STORE_SETTINGS = "settings";

// videos_cache에 저장되는 유일한 키. 통째로 교체하므로 레코드가 하나뿐이다.
const VIDEOS_KEY = "current";

let dbPromise = null;

function db() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(database) {
        if (!database.objectStoreNames.contains(STORE_VIDEOS)) {
          database.createObjectStore(STORE_VIDEOS);
        }
        if (!database.objectStoreNames.contains(STORE_SETTINGS)) {
          database.createObjectStore(STORE_SETTINGS);
        }
      },
    });
  }
  return dbPromise;
}

/**
 * IndexedDB를 못 쓰는 환경(시크릿 모드 일부, 저장소 차단)에서도 앱은 동작해야 한다.
 * 실패를 예외로 올리지 않고 null/기본값을 돌려준다 — 캐시가 없으면 번들 시드로 산다.
 */
async function safely(operation, fallback) {
  try {
    return await operation();
  } catch {
    return fallback;
  }
}

// --- videos 캐시 -------------------------------------------------------------

export async function readVideosCache() {
  return safely(async () => (await db()).get(STORE_VIDEOS, VIDEOS_KEY), null);
}

/**
 * 캐시를 통째로 교체한다.
 *
 * 호출자는 **완전히 받은 데이터만** 넘겨야 한다 (PLAN.md "완전히 받은 뒤에만 캐시 교체").
 * 부분 응답을 조각조각 쓰지 않도록 이 함수는 병합을 제공하지 않는다.
 */
export async function writeVideosCache(data, receivedAt = new Date()) {
  return safely(async () => {
    await (await db()).put(
      STORE_VIDEOS,
      { data, receivedAt: receivedAt.toISOString() },
      VIDEOS_KEY,
    );
    return true;
  }, false);
}

export async function clearVideosCache() {
  return safely(async () => {
    await (await db()).delete(STORE_VIDEOS, VIDEOS_KEY);
    return true;
  }, false);
}

// --- settings ----------------------------------------------------------------

export async function getSetting(key, fallback = null) {
  return safely(async () => {
    const value = await (await db()).get(STORE_SETTINGS, key);
    return value === undefined ? fallback : value;
  }, fallback);
}

export async function setSetting(key, value) {
  return safely(async () => {
    await (await db()).put(STORE_SETTINGS, value, key);
    return true;
  }, false);
}

/** 설정 화면의 "기록 삭제" — taxonomy.yaml ui.revisit.privacy_note */
export async function clearAllLocalData() {
  return safely(async () => {
    const database = await db();
    await database.clear(STORE_SETTINGS);
    await database.clear(STORE_VIDEOS);
    return true;
  }, false);
}

/**
 * 브라우저 캐시에 남은 **열람 흔적**을 지운다.
 *
 * [무엇을 지우고 무엇을 남기는가 — 흔적인가 성능인가로 갈랐다 (2026-08-24)]
 *   pym-thumbs-*  지운다   어떤 영상을 봤는지가 남는다 (최근 200개)
 *   pym-krv-*     지운다   어떤 장을 열었는지가 남는다.
 *                          성경 본문 자체는 개인정보가 아니지만,
 *                          **"내가 무엇을 읽었는지"는 흔적이다**
 *   pym-shell-*   남긴다   앱 화면 파일이다. 누가 써도 같고 흔적이 아니다.
 *                          지우면 오프라인에서 앱이 열리지 않게 된다 —
 *                          지울 이유가 없는데 잃는 것만 있다
 *
 * ⚠ 캐시는 지워도 **다시 열면 다시 받는다.** 흔적을 지우는 것이지 기능을 끄는 것이
 *   아니다. 그래서 되돌릴 수 없는 것은 IndexedDB 쪽(방문 기록·회전 상태)뿐이다.
 */
const TRACE_CACHES = ["pym-thumbs-", "pym-krv-"];

export async function clearBrowsingTraces() {
  if (typeof caches === "undefined") return false;
  try {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((name) => TRACE_CACHES.some((prefix) => name.startsWith(prefix)))
        .map((name) => caches.delete(name)),
    );
    return true;
  } catch {
    return false;
  }
}

export const KEYS = {
  MEDIA_TYPE: "media_type", // [말씀]/[찬양] 토글의 마지막 선택 (세분류별)
  VERSE_INDEXES: "verse_indexes", // 직전에 보여준 구절 (구절 회전용)
  LAST_CHECKED_AT: "last_checked_at", // version.json을 마지막으로 확인한 시각
  LAST_VISIT_AT: "last_visit_at",
  VISIT_COUNT_TODAY: "visit_count_today",
  VISIT_DATE: "visit_date",
  LAST_SUBCATEGORY_ID: "last_subcategory_id",
  MESSAGE_INDEXES: "message_indexes", // 직전에 보여준 문구 인덱스 (문구 회전용)

  // --- 아침 알림 (2026-08-31) ---------------------------------------------
  NOTIFY_ON: "notify_on", // 켜짐 여부
  NOTIFY_TIME: "notify_time", // "09:00"
  // ⛔ VERSE_INDEXES를 재사용하지 않는다. 그것은 "화면이 마지막으로 보여준
  //   구절"이고 목적이 다르다 — 섞으면 알림 때문에 화면의 구절 회전이
  //   건너뛰어진다. 알림은 제 기록을 따로 갖는다.
  NOTIFY_SEEN: "notify_seen", // {verseId: ISO 날짜}. 30일 지나면 버린다
  NOTIFY_LAST_BOOK: "notify_last_book", // 창을 이어 붙일 때 연속 금지용
};
