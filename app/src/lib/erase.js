/**
 * 「이 기기에서 기록 지우기」 — 무엇을 어떤 순서로 지우는가 (HANDOFF 2.147 · ㄱ-2).
 *
 * [기록을 지운다 = 처음 상태로 돌아간다 — 알림도 꺼진다 (2026-10-08 사용자 결정)]
 *   설정 저장소를 비우면 NOTIFY_ON도 사라져 기본값(꺼짐)이 된다. 그런데 예전에는
 *   **예약을 취소하지 않았다** — 지운 뒤 최대 14일간 알림이 계속 왔고, 다음 콜드
 *   스타트에서 refreshSchedule이 「꺼짐」을 보고 지워 끈 적도 없는데 조용히 멎었다.
 *   알림 설정만 남기는 것도, 지금 같은 중간 상태도 아니라 **함께 끈다.**
 *
 * ⚠⚠ 원인은 **순서**였다 — 기록 지우기(2e91d2d · 08-24)가 먼저 생기고, 알림 키가
 *   일주일 뒤(77547ff · 08-31) 같은 저장소(db.js STORE_SETTINGS)에 들어오면서
 *   지우기 쪽을 손보지 않았다. ★ **같은 저장소에 키를 더할 때는 여기를 볼 것** —
 *   지우면 그 키가 무엇을 남기는지(예약 · 캐시 · 외부 상태).
 *
 * [왜 따로 떼었나]
 *   notify.js는 노드 테스트에서 불러올 수 없고(JSON import), db.js가 notify.js를
 *   부르면 그것까지 끌려온다. 순서만 갖고 실제 동작은 주입받아야 지워 보는 검사를
 *   돌릴 수 있다(notify.test.js — 지운 뒤 저장값과 예약이 같은 상태를 말하는가).
 */
export async function eraseRecords({ cancelNotifications, clearStore, clearTraces }) {
  // 예약을 **먼저** 지운다. 실패해도 기록은 지운다 — 사용자는 지우라고 했다.
  //   저장값이 꺼짐이 되므로 다음 콜드 스타트의 refreshSchedule이 남은 예약을 지운다.
  try {
    await cancelNotifications();
  } catch {
    // 위 주석대로 넘어간다
  }
  const ok = await clearStore();
  await clearTraces();
  return ok;
}
