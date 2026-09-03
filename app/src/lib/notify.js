/**
 * 구절 알림 — 플러그인을 다루는 쪽. 고르는 규칙은 notifySelect.js에 있다.
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
  OFF_BY,
  PERMISSION,
  enableDecision,
  isBlocked,
  permissionOutcome,
  shouldTurnOff,
} from "./notifyPermission.js";
import {
  WINDOW_DAYS,
  dropScheduled,
  notificationContent,
  notifyPool,
  pickSequence,
  pruneSeen,
  recentlySent,
  scheduleTimes,
} from "./notifySelect.js";

const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;

/**
 * 알림 채널.
 *
 * ⚠ **id는 morning_verse 그대로 둔다.** 사용자가 보는 것은 name("구절 알림")이고
 *   id는 안드로이드가 기기에 저장하는 내부 키다. 바꾸면 이미 설치된 기기에
 *   채널이 하나 더 생기고 옛 채널이 설정 화면에 유령으로 남는다 — 사용자가
 *   얻는 것은 없고 잃는 것만 있다. 시각을 밤으로 바꿔도 id는 보이지 않는다.
 */
const CHANNEL_ID = "morning_verse";

/**
 * 예약 id 범위. 이 앱이 만든 것만 지우기 위해 대역을 정해 둔다.
 * ⚠ 남의 알림까지 cancel하지 않도록, 취소할 때도 이 범위만 본다.
 */
const ID_BASE = 4100;

export const DEFAULT_TIME = "09:00";
/**
 * ⚠ 기본값은 **꺼짐**이다 (2026-09-03 · 사용자 확정 · HANDOFF 2.119).
 *
 * [왜 켜짐에서 내렸나]
 *   Android 13+ 는 POST_NOTIFICATIONS가 런타임 권한이라, 기본이 켜짐이면
 *   신규 설치에서 **화면은 「켜짐」인데 예약은 0건**이 된다(2.116 ②).
 *   A′가 그것을 꺼짐으로 내리므로 13+ 에서는 어차피 꺼짐으로 보인다.
 *   그런데 12 이하만 켜짐으로 남으면 **OS에 따라 첫 화면이 갈린다** — 혼란스럽다.
 *   그래서 전 버전을 꺼짐으로 통일한다.
 * ⚠ 대가 — Android 12 이하 신규 사용자는 **잘 되던 알림이 꺼진 채 시작한다.**
 *   감수한 대가다. 12 이하는 토글을 켜면 시스템 팝업 없이 바로 켜지므로
 *   진입 비용이 낮다는 것이 근거다.
 * ⛔ **기존 사용자는 영향이 없다.** 이 값은 저장값이 없을 때만 쓰인다 —
 *   이미 켜 둔 사람의 notify_on 은 그대로다.
 */
export const DEFAULT_ON = false;

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
 *
 * ⚠ **boolean이 아니라 3값을 돌려준다** (2026-09-03 · HANDOFF 2.119).
 *   호출부가 "거부됐다"와 "못 읽었다"를 갈라야 하기 때문이다 —
 *   거부일 때만 표식을 남기고, 그 표식이 있으면 **다시는 시스템에 묻지 않는다.**
 *   안드로이드는 두 번 거절하면 영구 거절이라 팝업을 최대 1회만 소모한다.
 *
 * @returns {Promise<"granted"|"denied"|"unknown">}
 */
export async function ensurePermission() {
  const box = await api();
  if (!box) return PERMISSION.UNKNOWN;
  const { ln } = box;
  // ⛔ 판정은 **permissionOutcome 한 곳**이다. 여기서 display를 직접 비교하면
  //   판정이 두 곳으로 갈리고, 나중에 한쪽만 고쳐진다 (회귀가 이것을 막는다).
  let raw = null;
  let threw = false;
  try {
    raw = await ln.checkPermissions();
  } catch {
    threw = true;
  }
  const first = permissionOutcome(raw, threw);
  if (first !== PERMISSION.DENIED) return first; // granted면 통과, unknown이면 묻지 않는다
  // ⚠ 못 읽었으면 **묻지 않는다.** 상태를 모르는 채로 시스템 팝업을 소모하면
  //   안드로이드의 "두 번 거절이면 영구 거절"을 헛되이 쓴다.
  // ⛔ 이미 거부 표식이 있으면 여기까지 오지 않는다 — setEnabled가 막는다.
  try {
    return permissionOutcome(await ln.requestPermissions());
  } catch {
    return PERMISSION.UNKNOWN;
  }
}

/**
 * **영구 거절인가** — 켜기가 실패한 뒤 호출부가 안내를 띄울지 정할 때 쓴다.
 *
 * ⛔⛔ **setEnabled가 false를 돌려준 직후에만 부른다.** 그때는 requestPermissions가
 *   막 끝나 Capacitor 캐시가 새로 쓰인 상태다. 그 전에 부르면 낡은 값을 읽고,
 *   **팝업이 뜰 수 있는 상태에 "설정으로 가세요"를 띄우게 된다**(2026-09-03 실측).
 * ⛔ 판정은 isBlocked 한 곳이다. 여기서 display를 직접 비교하지 말 것.
 * ⚠ 웹·플러그인 실패에서는 false다 — 모르면 아무 말도 안 하는 쪽이 안전하다.
 */
export async function isPermissionBlocked() {
  const box = await api();
  if (!box) return false;
  try {
    return isBlocked(await box.ln.checkPermissions());
  } catch {
    return isBlocked(null, true);
  }
}

/**
 * 채널을 만든다. 앱을 열 때마다 부르지만, 만들어지는 것은 처음 한 번뿐이다.
 *
 * ⛔ **여기 적힌 값은 "처음 설치된 기기"에만 적용된다.**
 *   안드로이드는 이미 존재하는 채널의 importance·sound·vibration을
 *   코드로 바꾸지 못한다. 갱신되는 것은 name·description·group뿐이고,
 *   importance는 사용자가 손대지 않았을 때 **낮추는 것만** 된다.
 *   같은 id로 지웠다 다시 만드는 우회도 막혀 있다 — 옛 설정이 복원된다.
 *   → 이 값을 고치면 **재설치한 기기에서만** 반영된다. 출시 전에 확정할 것.
 */
async function ensureChannel(ln) {
  try {
    await ln.createChannel({
      id: CHANNEL_ID,
      name: "구절 알림",
      description: "정한 시각에 구절 한 절을 보냅니다.",
      importance: 3, // 기본. 소리는 울리되 화면을 가로채지 않는다
      visibility: 1,
      // ⚠ **넘기지 않으면 플러그인이 false를 박는다.** 우리가 안 정하면
      //   "진동 없음"이 정해진다 — NotificationChannelManager.kt의
      //   getBoolean("vibration", false)가 기본값이다. 2026-08-31 실기기에서
      //   mVibrationEnabled=false로 굳어 있었고, 그것이 진동이 없던 원인이다.
      vibration: true,
      // ⛔ sound는 넘기지 않는다 — 이것이 **의도한 상태**다.
      //   넘길 수 있는 값은 res/raw의 파일명뿐이고, 비워 두면 안드로이드가
      //   **기기 기본 알림음**을 쓴다. 사용자가 자기 기기에서 이미 고른 소리다.
      //   앱이 자기 소리를 강요하지 않는 것이 이 앱의 태도에 맞다.
      //   ⚠ 플러그인 타입 문서(definitions.d.ts)는 "sound를 안 주면 소리가
      //     없다"고 적혀 있으나 **구현과 다르다.** 실기기 dumpsys가
      //     mSound=content://settings/system/notification_sound로 확인해 준다.
      //     문서를 믿고 여기에 파일명을 넣지 말 것.
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

  // 권한을 **셋으로** 읽는다 (2026-09-03 · HANDOFF 2.116 ②).
  //   ⛔ 여기서 묻지 않는 것은 그대로다 — 토글과 D가 묻는 자리다.
  //   ★ 바뀐 것은 **denied일 때 저장값을 함께 내리는 것**이다.
  //     그래야 화면의 「켜짐」이 거짓말을 멈춘다.
  //   ⛔ unknown(못 읽음)에서는 **아무것도 건드리지 않는다.**
  //     일시적 실패에 사용자 설정이 꺼지면 알림이 조용히 영영 멎는다.
  let raw = null;
  let threw = false;
  try {
    raw = await ln.checkPermissions();
  } catch {
    threw = true;
  }
  const outcome = permissionOutcome(raw, threw);
  if (outcome !== PERMISSION.GRANTED) {
    if (shouldTurnOff({ outcome, storedOn: on })) {
      await setSetting(KEYS.NOTIFY_ON, false);
      await setSetting(KEYS.NOTIFY_OFF_BY, OFF_BY.PERMISSION);
    }
    return 0;
  }

  const pool = notifyPool(versesData);
  if (!pool.length) return 0;

  const seenRaw = await getSetting(KEYS.NOTIFY_SEEN, {});
  // ⚠ 순서가 중요하다. 30일을 넘긴 것을 버리고(pruneSeen), 그다음 **아직 오지
  //   않은 예약**을 버린다(dropScheduled) — 바로 위에서 그것들을 취소했으므로
  //   보낸 적이 없다. 이 한 줄이 없으면 앱을 열 때마다 기록이 누적되어
  //   풀 전체가 "최근 보냄"으로 굳는다(실기기에서 107건까지 찼다).
  const seen = dropScheduled(pruneSeen(seenRaw, now.getTime()), now.getTime());
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
      // ★ allowWhileIdle — **켜 둔다** (2026-09-03 · HANDOFF 2.116 ①).
      //   [왜] 배터리 세이버가 켜진 채 앱이 백그라운드면 이 알람이
      //     **+364일 뒤로 밀린다.** 남은 시간이 경과한 만큼만 줄어드는 것을
      //     실측했다 — 목표 시각이 고정이라 「미룸」이 아니라 **사실상 취소**다.
      //     아침 09:00에 앱이 포그라운드일 리 없으므로, 끄면 배터리 세이버를
      //     쓰는 기기에서 구절 알림이 **조용히 영영 안 온다.**
      //   [무엇이 바뀌나] 플러그인의 setExactIfPossible에서
      //     set(RTC) → **setAndAllowWhileIdle(RTC_WAKEUP)** 이 된다.
      //     ✅ 권한이 필요 없다 — SCHEDULE_EXACT_ALARM과 무관하다
      //     ✅ 여전히 **비정확 알람**이다. 창(window)이 그대로라 몇 분~수십 분
      //       늦을 수 있다. 2.92가 거절한 것은 "정확함"이고 이것은 "깨움"이다 —
      //       2.107 ②가 갈라 둔 다른 축이다
      //   ⛔ **false로 되돌리지 말 것.** notify.test.js가 이 값을 단언한다
      schedule: { at: times[i], allowWhileIdle: true },
      // ⛔ **정확한 알람은 여전히 쓰지 않는다.** 기본값이 true라 명시적으로 꺼야 한다.
      //   매니페스트에서 SCHEDULE_EXACT_ALARM을 걷어냈으므로, 켜 두면 플러그인이
      //   시스템의 "알람 및 리마인더" 설정 화면을 열고 그 결과를 기다리며
      //   **schedule()이 영영 응답하지 않는다** — 실기기에서 그렇게 멈췄다
      //   (2026-08-31). 매일 정해진 시각 알림은 inexact가 맞는 용도다.
      //   ★ 그 화면을 여는 조건을 플러그인 소스에서 확인했다 —
      //     honorExact = notifications.any { it.isExactNotification }
      //     (LocalNotificationsPlugin.kt). **allowWhileIdle과는 무관하다.**
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
/**
 * @param {boolean} next 켤 것인가
 * @param {{userInitiated?: boolean}} opts
 *   ⛔ **사용자가 직접 누른 것인가.** 이 한 값이 팝업 가드를 가른다 — 아래를 볼 것.
 */
export async function setEnabled(next, { userInitiated = false } = {}) {
  if (next) {
    /**
     * ⛔⛔ **가드는 자동 경로에만 건다. 사용자가 누른 것은 통과시킨다.**
     *
     * [왜 이렇게 됐나 — 실사용이 실측을 뒤집었다 (2026-09-03)]
     *   처음에는 거부 표식이 있으면 **무조건** 막았다("팝업은 최대 1회").
     *   그런데 그러면 **한 번 거부한 사용자가 마음을 바꿔도 켤 수 없다.**
     *   토글이 눌리지 않고 아무 반응도 없다 — 막다른 길이다.
     *   실기기에서 그 상태를 사용자가 먼저 발견했다. 세션의 검증은
     *   CDP click으로 했는데 그것은 표식이 없는 상태만 봤다.
     *
     * ★ 안드로이드는 **두 번** 거절해야 영영 안 띄운다. 한 번 거부 뒤에는
     *   아직 한 번 더 물을 수 있고, 그 한 번은 **사용자가 요청했을 때** 쓴다.
     * ⚠ 이미 영구 거절된 뒤라면 requestPermissions가 팝업 없이 즉시 denied를
     *   돌려준다 — 소모할 것이 없으므로 눌러도 손해가 없다.
     * ⛔ 자동 경로(About 진입 등)에서는 여전히 막는다. 우리가 사용자 대신
     *   팝업을 소모하지 않는다는 원칙은 그대로다.
     */
    const offBy = await getSetting(KEYS.NOTIFY_OFF_BY, null);
    // ⛔ 판단은 **enableDecision 한 곳**이다. 여기서 조건을 늘리지 말 것 —
    //   갈래가 코드에 흩어지면 "어디서 막혔는지"를 값으로 확인할 수 없다.
    let d = enableDecision({ userInitiated, offBy });
    if (!d.ask) return false;
    d = enableDecision({ userInitiated, offBy, outcome: await ensurePermission() });
    if (d.mark === "permission") await setSetting(KEYS.NOTIFY_OFF_BY, OFF_BY.PERMISSION);
    if (!d.ok) return false; // 호출부가 토글을 되돌린다
    await setSetting(KEYS.NOTIFY_ON, true);
    if (d.mark === "clear") await setSetting(KEYS.NOTIFY_OFF_BY, null);
    await refreshSchedule();
    return true;
  }
  await setSetting(KEYS.NOTIFY_ON, false);
  // ⛔ 사용자가 직접 껐다는 표식. D가 이 값을 보고 다시 묻지 않는다.
  await setSetting(KEYS.NOTIFY_OFF_BY, OFF_BY.USER);
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
