/**
 * 광고 한 칸 — 디스플레이 320×100.
 *
 * [인피드가 아니다 — HANDOFF 2.52]
 *   처음에는 인피드로 정했다가 뒤집었다. 인피드는 크기를 우리가 정하지 못해
 *   목록 항목(52~62px)과 뒤섞일 수 있고, 그러면 정책이 금지하는
 *   "광고와 콘텐츠를 구분하기 어렵게 만드는 것"이 된다.
 *
 * [⛔ 목록 항목을 흉내내지 않는다]
 *   92×52 썸네일 + 제목 + 부제 레이아웃을 광고에 쓰지 말 것. 잘 섞이는 것은
 *   장점이 아니라 **위반**이다(2.51). 여기서 톤을 지키는 방법은 "비슷하게
 *   보이게"가 아니라 "조용하게"다 — 배경 알파 하나와 여백으로만 말한다.
 *
 * [라벨은 "광고"뿐이다]
 *   허용되는 어휘는 "광고"와 "스폰서 링크"뿐이다. "추천"·"함께 보기"는 위반이다.
 *   글자 언어는 폴백 층 헤더와 같게 맞춘다(11.5px · 자간 0.2em · T.muted) —
 *   새 언어를 만들면 위계에 층이 하나 더 생긴다.
 *
 * [slot이 비면 아무것도 그리지 않는다]
 *   광고 단위 ID는 AdSense 승인 후에 발급된다. 그때까지 빈 상자를 배포하지
 *   않는다 — 회색 자리는 "고장"으로 읽힌다. 개발 서버에서만 자리표시자를
 *   보여 준다(import.meta.env.DEV).
 */

import { useEffect, useRef } from "react";

import { AD_CLIENT, AD_HEIGHT, AD_SLOT, AD_WIDTH } from "../lib/ads.js";
import { T } from "../theme.js";

/**
 * 개발 서버에서만 자리표시자를 그린다.
 * ⚠ 옵셔널 체이닝(import.meta.env?.DEV)을 쓰지 않는다 — vite가 정적으로
 *   치환하지 못해 자리표시자가 **배포본 번들에 남는다**(실측 확인).
 *   이 형태여야 프로덕션에서 false로 접히고 가지가 통째로 빠진다.
 */
const IS_DEV = import.meta.env.DEV;

/**
 * 이 컴포넌트가 **실제로 무언가를 그리는가.**
 *
 * ⚠⚠ 호출부가 빈 <li>를 만들지 않게 하는 값이다. 2026-08-24 광고 구현(4811cf8)
 *   이래 VideoList가 <li>를 조건 없이 그리고 안쪽만 null이 됐다. 목록이
 *   display:grid · gap:16px라 **높이 0인 칸이 행 하나를 차지하고 양옆에 16px씩
 *   붙어 32px 여백**이 생겼다(실측). 사용자에게는 층 경계처럼 보였다.
 * ⚠ **프로덕션 전용 결함이었다.** dev에서는 자리표시자가 그려져 간격이 정상이라
 *   개발 중에는 보이지 않는다. 그래서 회귀도 **프로덕션 조건(AD_SLOT 빈 값)**에서
 *   검사해야 한다 — dev 조건으로 검사하면 같은 결함을 또 놓친다.
 */
export const AD_SLOT_RENDERS = Boolean(AD_SLOT) || IS_DEV;

export function AdSlot() {
  const insRef = useRef(null);
  // push는 이 <ins>당 **정확히 한 번**이다. 두 번 부르면 AdSense가
  // "already have ads in them"으로 거부하고 그 자리가 빈 채로 남는다.
  const pushed = useRef(false);

  useEffect(() => {
    if (!AD_SLOT || pushed.current || !insRef.current) return;
    pushed.current = true;
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (error) {
      // 스크립트가 차단됐거나(광고 차단기) 오프라인이면 여기로 온다.
      // **화면은 살아 있어야 한다** — 광고는 이 앱의 본체가 아니다.
      // 조용히 삼키지 않고 남기되, 사용자에게는 아무것도 보이지 않는다.
      console.warn("[ads] 광고를 불러오지 못했습니다", error);
    }
  }, []);

  if (!AD_SLOT) return IS_DEV ? <Placeholder /> : null;

  return (
    <div style={styles.block}>
      <span style={styles.label}>광고</span>
      <ins
        ref={insRef}
        className="adsbygoogle"
        style={styles.unit}
        data-ad-client={AD_CLIENT}
        data-ad-slot={AD_SLOT}
        // 고정 규격이라 data-ad-format을 쓰지 않는다. 반응형으로 두면
        // 높이가 늘어 목록 밀도(2.51 실측 15.9%)가 달라진다.
        data-full-width-responsive="false"
      />
    </div>
  );
}

/** 개발 서버 전용. 자리와 크기만 확인한다 — 배포본에는 없다. */
function Placeholder() {
  return (
    <div style={styles.block}>
      <span style={styles.label}>광고</span>
      <div style={{ ...styles.unit, ...styles.placeholder }}>
        {AD_WIDTH}×{AD_HEIGHT} · slot 미발급
      </div>
    </div>
  );
}

const styles = {
  /**
   * 위아래 20px — 항목 사이 간격(16px)보다 넓다. **간격이 곧 경계다**(2.51).
   * 테두리를 두지 않는 것은 이 앱이 면을 늘리지 않기 때문이다(VerseCard 주석).
   */
  block: { margin: "20px 0", display: "flex", flexDirection: "column", gap: 4 },
  // 폴백 층 헤더(VideoList styles.heading)와 같은 값이다. 맞춰 둔 것이지
  // 우연이 아니다 — 한쪽을 고치면 다른 쪽도 본다.
  label: { fontSize: 11.5, color: T.muted, letterSpacing: "0.2em" },
  unit: {
    display: "inline-block",
    width: AD_WIDTH,
    height: AD_HEIGHT,
    background: "#ffffff08",
    borderRadius: 3,
    // ⚠ 320은 App.jsx의 padding "34px 20px 40px"이 360px 화면에서 남기는
    //   폭과 정확히 같다. 좌우 여백을 바꾸면 규격이 어긋난다(2.51).
    maxWidth: "100%",
  },
  placeholder: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    color: T.muted,
    letterSpacing: "0.04em",
  },
};
