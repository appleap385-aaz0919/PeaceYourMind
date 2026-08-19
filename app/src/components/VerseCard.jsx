/**
 * 구절 카드 — PYM의 중심 화면 요소.
 *
 * [상자가 아니라 여백으로 구분한다 — 2026-08-19 개정]
 *   처음에는 배경(#ffffff08) + 테두리 + radius 18의 카드였다. 그러니 화면에서
 *   가장 무거운 요소가 **본문이 아니라 상자**가 됐고, 그 안에 pill 버튼까지 있어
 *   면이 겹쳐 보였다. FYM은 같은 팔레트를 쓰면서도 선을 거의 쓰지 않는다 —
 *   입력은 밑줄 하나, 구분은 1px 선 하나다.
 *
 *   그래서 카드를 걷어내고 타이포와 여백만 남겼다.
 *     · 본문 SERIF 20px / 행간 1.95 — 화면에서 가장 큰 글자다
 *     · 장절은 sand 색 작은 글씨로 본문 바로 아래
 *     · 위아래 넉넉한 여백이 카드 테두리 역할을 한다
 *   이름은 그대로 VerseCard다. 화면상 상자가 아니어도 "구절 한 장"이라는
 *   단위는 유지되기 때문이다.
 *
 * [출처 표기가 여기 있는 이유]
 *   개역한글(1961)은 저작재산권이 만료됐지만 **저작인격권 두 가지**가 남는다.
 *     동일성유지권  본문을 한 글자도 바꾸지 않는다 — 옛 표기(-ㄹ찌어다, 잠간)를
 *                   현대 맞춤법으로 "고치는" 것이 곧 훼손이다. 이 컴포넌트는
 *                   text를 어떤 방식으로도 가공하지 않는다(줄바꿈·말줄임 금지).
 *     성명표시권    "성경전서 개역한글판, 대한성서공회"를 표기한다.
 *   설정 화면에만 두면 구절이 보이는 자리에는 표기가 없게 된다.
 *
 * [다른 구절 보기]
 *   순환이지 랜덤이 아니다. 버튼을 누르는 것은 "이건 지금 안 맞는다"는 뜻인데
 *   랜덤이면 같은 구절이 다시 나올 수 있고, 그러면 버튼이 고장 난 것처럼 읽힌다.
 */

import { T, SERIF } from "../theme.js";

/**
 * 본문 길이에 따른 글자 크기 — **자르지 않고 크기로 맞춘다.**
 *
 * 구절에 길이 상한을 두지 않는 것이 원칙이다. 롬 8:38-39("사망이나 생명이나…")나
 * 렘 17:7-8("물 가에 심기운 나무가…")처럼 긴 구절은 **길이가 곧 내용**이다 —
 * 열거가 쌓이면서 만드는 압도감, 조건과 결과의 대비가 그 구절의 뜻이다.
 * 잘라내면 동일성유지권 위반이고, 목록에서 빼면 그 세분류의 대표 구절이 사라진다.
 *
 * [250구절의 실제 분포 — 구간을 여기에 맞췄다]
 *   ~40자 91건 · 41~60자 74건   → 66%가 60자 이하. 기본 크기가 대다수에 적용된다
 *   61~80자 53건 · 81~100자 17건 → 28%
 *   101~131자 15건               → 6%. 최장은 렘 17:7-8(131자)
 *
 * [실측 — 줄 수와 높이 (행간비 1.95, 뷰포트 360px / 420px)]
 *
 *            16.5px          18px          20px
 *   61자     2~3줄           2~3줄         3줄       ← 20px만 한 줄 더 쓴다
 *   78자     3~4줄  97px     3~4줄 105px   4줄 156px
 *   101자    4줄   129px     4~5줄 140px   5줄 195px ← 좁은 화면에서 16.5가 한 줄 적다
 *   131자    5~6줄 161px     5~6줄 175px   6~7줄 273px
 *
 *   20 → 18 (60자 경계)   61자가 420px에서 3줄→2줄, 78자가 4줄→3줄로 준다
 *   18 → 16.5 (100자 경계) 360px에서 101자가 5줄→4줄. 넓은 화면에서는 줄 수가
 *                          같고 높이만 8% 줄지만, **좁은 폰에서 차이가 난다**
 *                          — 이 앱은 폰에서 읽는 화면이라 그쪽을 기준으로 잡았다
 *
 *   결과: 최장 구절(131자)에서도 구절 → 공감 문구가 첫 화면에 들어온다
 *         (공감 문구 상단 337px / 뷰포트 900px).
 *
 * [행간은 비율로 유지한다]
 *   1.95를 크기와 무관하게 쓴다. px로 고정하면 작은 글자에서 행간이 과해져
 *   같은 화면인데 다른 결로 읽힌다. 비율이면 줄 간격이 글자와 함께 줄어든다.
 */
const SIZE_STEPS = [
  { max: 60, fontSize: 20 },
  { max: 100, fontSize: 18 },
  { max: Infinity, fontSize: 16.5 },
];
const LINE_HEIGHT = 1.95;

export function verseFontSize(text) {
  const length = (text || "").length;
  return SIZE_STEPS.find((step) => length <= step.max).fontSize;
}


export function VerseCard({ verse, attribution, onNext, canRotate, lead }) {
  if (!verse) return null;

  return (
    <section style={styles.wrap} aria-label="오늘의 구절">
      {lead ? <p style={styles.lead}>{lead}</p> : null}

      {/* 본문은 가공하지 않는다 — 동일성유지권.
          길면 자르는 것이 아니라 글자 크기를 한 단계 낮춘다. */}
      <p style={{ ...styles.text, fontSize: verseFontSize(verse.text) }}>{verse.text}</p>

      <p style={styles.meta}>
        <span style={styles.ref}>{verse.ref}</span>
        {canRotate ? (
          <>
            <span style={styles.dot}>·</span>
            <button type="button" onClick={onNext} style={styles.rotate}>
              다른 구절
            </button>
          </>
        ) : null}
      </p>

      <p style={styles.attribution}>{attribution}</p>
    </section>
  );
}

const styles = {
  wrap: { margin: "10px 0 34px" },
  lead: {
    margin: "0 0 16px",
    fontSize: 11.5,
    letterSpacing: "0.2em",
    color: T.muted,
  },
  text: {
    margin: 0,
    fontFamily: SERIF,
    // fontSize는 본문 길이에 따라 verseFontSize()가 정한다.
    lineHeight: LINE_HEIGHT,
    color: T.mist,
    wordBreak: "keep-all",
  },
  meta: {
    display: "flex",
    alignItems: "baseline",
    gap: 8,
    margin: "18px 0 0",
    fontSize: 13,
  },
  ref: { color: T.sand, fontFamily: SERIF },
  dot: { color: "#ffffff26" },
  rotate: {
    padding: 0,
    background: "none",
    border: "none",
    color: T.muted,
    fontSize: 12.5,
    fontFamily: "inherit",
    cursor: "pointer",
    borderBottom: "1px solid #ffffff26",
    lineHeight: 1.4,
  },
  attribution: {
    margin: "14px 0 0",
    fontSize: 10.5,
    color: "#ffffff30",
    letterSpacing: "0.01em",
  },
};
