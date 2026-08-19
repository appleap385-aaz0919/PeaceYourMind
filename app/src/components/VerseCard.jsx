/**
 * 구절 카드 — PYM의 중심 화면 요소.
 *
 * [출처 표기가 카드 안에 있는 이유]
 *   개역한글(1961)은 저작재산권 보호기간이 만료됐지만 **저작인격권 두 가지**가
 *   남는다 (verses.yaml 헤더).
 *     동일성유지권  본문을 한 글자도 바꾸지 않는다 — 옛 표기(-ㄹ찌어다, 잠간)를
 *                   현대 맞춤법으로 "고치는" 것이 곧 훼손이다. 그래서 이 컴포넌트는
 *                   text를 어떤 방식으로도 가공하지 않는다. 줄바꿈·말줄임 금지.
 *     성명표시권    "성경전서 개역한글판, 대한성서공회"를 표기한다.
 *
 *   설정 화면에만 두면 구절이 보이는 자리에는 표기가 없게 된다. 본문이 노출되는
 *   곳에 함께 두는 것이 안전하고, 설정 화면에도 중복해서 둔다.
 *
 * [다른 구절 보기]
 *   순환이지 랜덤이 아니다. 버튼을 누르는 것은 "이건 지금 안 맞는다"는 뜻인데
 *   랜덤이면 같은 구절이 다시 나올 수 있고, 그러면 버튼이 고장 난 것처럼 읽힌다.
 *   (lib/verses.js nextVerse 주석)
 */

import { T, SERIF } from "../theme.js";

export function VerseCard({ verse, attribution, onNext, canRotate, lead }) {
  if (!verse) return null;

  return (
    <section style={styles.card} aria-label="오늘의 구절">
      {lead ? <p style={styles.lead}>{lead}</p> : null}

      {/* 본문은 가공하지 않는다 — 동일성유지권 */}
      <p style={styles.text}>{verse.text}</p>

      <p style={styles.ref}>{verse.ref}</p>

      {canRotate ? (
        <button type="button" onClick={onNext} style={styles.rotate}>
          다른 구절 보기
        </button>
      ) : null}

      <p style={styles.attribution}>{attribution}</p>
    </section>
  );
}

const styles = {
  card: {
    background: "#ffffff08",
    border: "1px solid #ffffff14",
    borderRadius: 18,
    padding: "22px 20px 16px",
    margin: "18px 0 26px",
  },
  lead: {
    margin: "0 0 14px",
    fontSize: 13,
    letterSpacing: "0.02em",
    color: T.muted,
  },
  text: {
    margin: 0,
    fontFamily: SERIF,
    fontSize: 19,
    lineHeight: 1.75,
    color: T.mist,
    wordBreak: "keep-all",
  },
  ref: {
    margin: "16px 0 0",
    fontSize: 14,
    color: T.sand,
    fontFamily: SERIF,
  },
  rotate: {
    margin: "18px 0 0",
    padding: "9px 14px",
    background: "transparent",
    border: "1px solid #ffffff20",
    borderRadius: 999,
    color: T.muted,
    fontSize: 13,
    fontFamily: "inherit",
    cursor: "pointer",
  },
  attribution: {
    margin: "18px 0 0",
    fontSize: 11,
    color: "#ffffff33",
    letterSpacing: "0.01em",
  },
};
