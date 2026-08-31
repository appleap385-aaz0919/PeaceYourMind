/**
 * 아침 알림 — 플러그인을 다루는 쪽. 고르는 규칙은 notifySelect.js에 있다.
 *
 * [구조적 제약 — 미리 예약해야 한다]
 *   서버 푸시도 백그라운드 실행도 없다. 그래서 알림 **내용이 예약 시점에
 *   고정된다.** `on: {hour, minute}`로 반복시키면 매일 같은 구절이 간다.
 *   그래서 14일치를 서로 다른 구절로 예약하고, 앱을 열 때마다 다시 채운다.
 *
 *   ★ 부작용이 오히려 맞다 — 14일간 앱을 안 열면 알림이 멎는다.
 *     떠난 사람을 계속 부르지 않는 것이 이 앱의 태도다.
 *
 * [권한 — 첫 실행에 묻지 않는다]
 *   이 앱의 첫 화면은 "지금 마음이 어떠세요"다. 거기에 시스템 권한 팝업을
 *   얹으면 첫인상이 다이얼로그가 된다. 사용자가 About에서 토글을 켜는
 *   **그 순간에만** 묻는다.
 *
 * [⛔ 구절 데이터를 인자로 받지 않는다 — 2026-08-31 실측으로 고쳤다]
 *   처음에는 호출부가 data를 넘기게 했는데, About이 **영상 데이터**(dataRef)를
 *   넘겨 풀이 빈 배열이 됐다. 예약이 조용히 0건이 되고 아무 오류도 나지 않는다.
 *   구절 풀은 번들 상수이지 런타임 데이터가 아니므로 여기서 직접 읽는다 —
 *   틀린 것을 넘길 자리 자체를 없앤다.
 *
 * ⚠ 웹에서는 아무것도 하지 않는다. 플러그인이 없으므로 모든 진입점이
 *   조용히 false를 돌려준다 — offline.js가 배경 갱신 실패를 다루는 것과 같다.
 */

import versesData from "../data/verses.json";
import { KEYS, getSetting, setSetting } from "./db.js";
import {
  WINDOW_DAYS,
  notificationContent,
  notifyPool,
  pickSequence,
  pruneSeen,
  recentlySent,
  scheduleTimes,
} from "./notifySelect.js";

const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;

/** 알림 채널. 안드로이드가 설정 화면에서 이 이름으로 보여준다. */
const CHANNEL_ID = "morning_verse";

/**
 * 예약 id 범위. 이 앱이 만든 것만 지우기 위해 대역을 정해 둔다.
 * ⚠ 남의 알림까지 cancel하지 않도록, 취소할 때도 이 범위만 본다.
 */
const ID_BASE = 4100;

export const DEFAULT_TIME = "09:00";
/** ⚠ 기본값은 **켜짐**이다(사용자 결정). 권한은 그래도 토글에서만 묻는다. */
export const DEFAULT_ON = true;

let boxed = null;

/**
 * 플러그인을 늦게 부른다 — 웹 번들에 안 실리고, 없으면 null이다.
 *
 * ⛔ **상자에 담아 돌려준다.** 플러그인 프록시를 async 함수에서 그대로 return하면
 *   JS가 그것을 thenable로 보고 `.then()`을 부른다. Capacitor 프록시는 모든
 *   속성 접근을 네이티브 호출로 바꾸므로
 *     j: "LocalNotifications.then()" is not implemented on android
 *   가 던져지고, 이 모듈의 모든 진입점이 catch에 걸려 조용히 0을 돌려준다.
 *   알림이 하나도 안 오는데 아무 오류도 화면에 없다 — 2026-08-31에 실기기
 *   콘솔을 잡아서야 찾았다.
 */
async function api() {
  if (!IS_APP) return null;
  if (boxed) return boxed;
  try {
    const mod = await import("@capacitor/local-notifications");
    boxed = { ln: mod.LocalNotifications };
    return boxed;
  } catch {
    return null;
  }
}

export async function readSettings() {
  const on = await getSetting(KEYS.NOTIFY_ON, DEFAULT_ON);
  const time = await getSetting(KEYS.NOTIFY_TIME, DEFAULT_TIME);
  return { on: on !== false, time: typeof time === "string" ? time : DEFAULT_TIME };
}

export function parseTime(text) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(text || ""));
  if (!m) return { hour: 9, minute: 0 };
  const hour = Math.min(23, Math.max(0, Number(m[1])));
  const minute = Math.min(59, Math.max(0, Number(m[2])));
  return { hour, minute };
}

/**
 * 권한을 확인하고, 없으면 묻는다.
 * @returns {Promise<boolean>} 보낼 수 있는가
 */
export async function ensurePermission() {
  const box = await api();
  if (!box) return false;
  const { ln } = box;
  try {
    let status = await ln.checkPermissions();
    if (status.display !== "granted") status = await ln.requestPermissions();
    return status.display === "granted";
  } catch {
    return false;
  }
}

async function ensureChannel(ln) {
  try {
    await ln.createChannel({
      id: CHANNEL_ID,
      name: "아침 구절",
      description: "정한 시각에 구절 한 절을 보냅니다.",
      importance: 3, // 기본. 소리는 울리되 화면을 가로채지 않는다
      visibility: 1,
    });
  } catch {
    /* 채널 생성 실패는 치명적이지 않다 — 기본 채널로 나간다 */
  }
}

/** 이 앱이 예약한 것만 지운다. */
async function cancelOurs(ln) {
  try {
    const pending = await ln.getPending();
    const ours = (pending?.notifications || []).filter(
      (n) => n.id >= ID_BASE && n.id < ID_BASE + WINDOW_DAYS,
    );
    if (ours.length) await ln.cancel({ notifications: ours.map((n) => ({ id: n.id })) });
  } catch {
    /* 무시 */
  }
}

export async function cancelAll() {
  const box = await api();
  if (box) await cancelOurs(box.ln);
}

/**
 * 14일치를 다시 채운다. 앱을 열 때마다 부른다.
 *
 * ⚠ 매번 전부 취소하고 다시 넣는다. 남은 것을 세어 모자란 만큼만 넣는 방식은
 *   시각이 바뀌었을 때 옛 예약이 남고, 그 상태를 확인할 방법이 없다.
 *   14개는 다시 넣어도 싸다.
 *
 * @returns {Promise<number>} 실제로 예약한 개수
 */
export async function refreshSchedule(now = new Date()) {
  const box = await api();
  if (!box) return 0;
  const { ln } = box;

  const { on, time } = await readSettings();
  await cancelOurs(ln);
  if (!on) return 0;

  // 권한이 없으면 조용히 멈춘다. 여기서 묻지 않는다 — 토글이 묻는 자리다.
  try {
    const status = await ln.checkPermissions();
    if (status.display !== "granted") return 0;
  } catch {
    return 0;
  }

  const pool = notifyPool(versesData);
  if (!pool.length) return 0;

  const seenRaw = await getSetting(KEYS.NOTIFY_SEEN, {});
  const seen = pruneSeen(seenRaw, now.getTime());
  const lastBook = await getSetting(KEYS.NOTIFY_LAST_BOOK, null);

  const verses = pickSequence(
    pool,
    recentlySent(seen, now.getTime()),
    WINDOW_DAYS,
    Math.random,
    lastBook,
  );
  if (!verses.length) return 0;

  const { hour, minute } = parseTime(time);
  const times = scheduleTimes(hour, minute, verses.length, now);

  await ensureChannel(ln);
  const notifications = verses.map((verse, i) => {
    const { title, body, largeBody } = notificationContent(verse);
    return {
      id: ID_BASE + i,
      title,
      body,
      largeBody,
      channelId: CHANNEL_ID,
      schedule: { at: times[i], allowWhileIdle: false },
      // ⛔ **정확한 알람을 쓰지 않는다.** 기본값이 true라 명시적으로 꺼야 한다.
      //   매니페스트에서 SCHEDULE_EXACT_ALARM을 걷어냈으므로, 켜 두면 플러그인이
      //   시스템의 "알람 및 리마인더" 설정 화면을 열고 그 결과를 기다리며
      //   **schedule()이 영영 응답하지 않는다** — 실기기에서 그렇게 멈췄다
      //   (2026-08-31). 매일 정해진 시각 알림은 inexact가 맞는 용도다.
      isExactNotification: false,
      // 탭했을 때 어느 구절인지 알아야 화면을 연다.
      extra: { verseId: verse.id },
    };
  });

  try {
    await ln.schedule({ notifications });
  } catch {
    return 0;
  }

  // 보낸 것으로 기록한다. 예약 시점에 적는 이유: 실제 발송을 앱이 알 수 없고,
  // 30일 창의 목적이 "최근에 고른 것을 다시 고르지 않는다"이기 때문이다.
  const stamped = { ...seen };
  verses.forEach((verse, i) => {
    stamped[verse.id] = times[i].toISOString();
  });
  await setSetting(KEYS.NOTIFY_SEEN, stamped);
  await setSetting(KEYS.NOTIFY_LAST_BOOK, verses[verses.length - 1].read?.book ?? null);
  return notifications.length;
}

/** 토글을 켜고 끈다. 켤 때만 권한을 묻는다. */
export async function setEnabled(next) {
  if (next) {
    const ok = await ensurePermission();
    if (!ok) return false; // 호출부가 토글을 되돌린다
    await setSetting(KEYS.NOTIFY_ON, true);
    await refreshSchedule();
    return true;
  }
  await setSetting(KEYS.NOTIFY_ON, false);
  await cancelAll();
  return true;
}

export async function setTime(text) {
  await setSetting(KEYS.NOTIFY_TIME, text);
  await refreshSchedule();
}

/**
 * 알림을 탭해서 들어왔는지 본다.
 *
 * 두 경로가 있다 — 앱이 죽어 있었으면 getDeliveredNotifications가 아니라
 * 리스너가 먼저 붙어야 하고, 살아 있었으면 리스너로 온다. 그래서 앱 시작 때
 * 리스너를 걸고 거기서 verseId를 넘긴다.
 *
 * @param {(verseId: string) => void} onOpen
 * @returns {Promise<() => void>} 해제 함수
 */
export async function listenForTaps(onOpen) {
  const box = await api();
  if (!box) return () => {};
  const { ln } = box;
  try {
    const handle = await ln.addListener("localNotificationActionPerformed", (event) => {
      const id = event?.notification?.extra?.verseId;
      if (id) onOpen(id);
    });
    return () => handle.remove();
  } catch {
    return () => {};
  }
}
