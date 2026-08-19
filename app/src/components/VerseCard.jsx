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
 *     · 본문 SERIF 22px / 행간 1.95 — 화면에서 가장 큰 글자다 (길면 낮춘다, 아래 참조)
 *     · 장절은 sand 색 작은 글씨로 본문 바로 아래
 *     · 위아래 넉넉한 여백이 카드 테두리 역할을 한다
 *   이름은 그대로 VerseCard다. 화면상 상자가 아니어도 "구절 한 장"이라는
 *   단위는 유지되기 때문이다.
 *
 * [저작인격권 — 이 컴포넌트가 지키는 것]
 *   개역한글(1961)은 저작재산권이 만료됐지만 **저작인격권은 만료되지 않는다.**
 *     동일성유지권  본문을 한 글자도 바꾸지 않는다 — 옛 표기(-ㄹ찌어다, 잠간)를
 *                   현대 맞춤법으로 "고치는" 것이 곧 훼손이다. 이 컴포넌트는
 *                   text를 어떤 방식으로도 가공하지 않는다(줄바꿈·말줄임 금지).
 *     성명표시권    "성경전서 개역한글판, 대한성서공회" 표기가 앱에 있어야 한다.
 *
 * [출처 표기를 여기서 뺐다 — 2026-08-19 정책 변경]
 *   원래는 구절 카드와 "이 앱에 대해" 두 곳에 뒀다. 근거는 "구절만 보고 나가는
 *   사용자에게도 표기가 보여야 한다"였다. 그 판단을 바꾼 이유는 화면이 바뀌었기
 *   때문이다 — 카드 상자를 걷어내고(위 개정) 본문이 화면의 첫 인상이 된 뒤로는,
 *   본문 바로 아래 10.5px 회색 한 줄이 구절의 여운을 끊는 마지막 요소가 됐다.
 *
 *   ⚠ **표기 자체를 없앤 것이 아니다.** 성명표시권은 만료되지 않으므로 앱
 *     어딘가에는 반드시 있어야 하고, 그 자리가 "이 앱에 대해" 화면이다.
 *     그 화면의 표기는 **어떤 경우에도 삭제하지 않는다.** 화면 정리를 이유로
 *     지우자는 제안이 나오면 거절해야 한다 — 이쪽은 취향이 아니라 요건이다.
 *     verses.test.js가 About에 표기가 있는지를 검사해 이 요건을 고정한다.
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
 *   ~60자    165건 (66%) → 22px   기본 크기가 대다수에 적용된다
 *   61~100자  70건 (28%) → 20px
 *   101~131자 15건  (6%) → 18px   최장은 렘 17:7-8(131자, calm.stable)
 *
 * [2026-08-19 한 단계 키웠다 — 20/18/16.5 → 22/20/18]
 *   상자를 걷어낸 뒤 본문이 화면의 주인공이 됐으니 그에 맞는 크기가 필요하다.
 *   기준은 "커 보이는가"가 아니라 **360px에서 구절과 공감 문구가 한 화면에
 *   들어오는가**다. 그게 이 화면의 구조이기 때문이다 — 구절을 읽고 바로 아래
 *   공감 문구로 이어지는 것이 결과 화면의 한 호흡이고, 공감 문구를 보려고
 *   스크롤해야 하면 그 호흡이 끊긴다.
 *
 * [실측 — 360×640 뷰포트, 최장 구절 렘 17:7-8(131자). 크기를 바꾸면 다시 잰다]
 *
 *                구절 크기  구절 높이  공감 문구 하단  640px 안에 들어오는가
 *   개정 전         16.5px    193px       338px         들어옴
 *   개정 후(채택)     18px    211px       358px         들어옴  여유 282px
 *
 *   **최악 케이스도 커진다** — 상한 구간이 16.5→18px이므로 가장 긴 구절도
 *   한 단계 올라간다. 그래도 채택한 이유는 여유가 282px 남기 때문이다.
 *   공감 문구까지가 358px이고 640px 화면에 다 들어온다.
 *   ⚠ 다음에 더 키우려면 이 수치부터 다시 재라. 상한 구간(18px)이 한계선이고,
 *     여기서 2px 더 올리면 131자 구절이 한 화면을 넘길 위험이 있다.
 *
 * [행간은 비율로 유지한다]
 *   1.95를 크기와 무관하게 쓴다. px로 고정하면 작은 글자에서 행간이 과해져
 *   같은 화면인데 다른 결로 읽힌다. 비율이면 줄 간격이 글자와 함께 줄어든다.
 */
const SIZE_STEPS = [
  { max: 60, fontSize: 22 },
  { max: 100, fontSize: 20 },
  { max: Infinity, fontSize: 18 },
];
const LINE_HEIGHT = 1.95;

export function verseFontSize(text) {
  const length = (text || "").length;
  return SIZE_STEPS.find((step) => length <= step.max).fontSize;
}


export function VerseCard({ verse, onNext, canRotate }) {
  if (!verse) return null;

  return (
    <section style={styles.wrap} aria-label="오늘의 구절">
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
    </section>
  );
}

const styles = {
  wrap: { margin: "10px 0 34px" },
  // lead(도입 캡션)는 2026-08-19에 없앴다. prop까지 지웠다 —
  // 쓰이지 않는 prop을 남겨 두면 다음 사람이 왜 있는지 모른다.
  // 상자를 걷어내고 본문이 화면의 첫 인상이 된 이상, 도입 한 줄이 그 앞을 막는다.
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
};
