/**
 * [이어서 읽기] │ [말씀] [찬양] — 결과 화면, 구절과 목록 사이.
 *
 * [2026-08-20 — MediaToggle에서 이름과 계약이 바뀌었다]
 *   전에는 영상 형식 두 개만 있는 토글이었다(role="group" aria-label="영상 형식").
 *   "이어서 읽기"가 들어오면서 세 가지가 안 맞게 됐다 —
 *     · 이어서 읽기는 **영상 형식이 아니다.** aria-label이 거짓말이 된다
 *     · 토글이 아니라 탭이 된다 → aria-pressed → aria-selected + tablist
 *     · 이어서 읽기에는 셀 것이 없다 (숫자 자리를 비운다)
 *   그래서 계약을 바꾸고 파일 이름도 바꿨다. 아래 [지키는 것]은 그대로 옮겼다.
 *
 * [구분선이 두 묶음을 가른다]
 *   왼쪽은 **본문**이고 오른쪽 둘은 **영상 형식**이다. 성격이 다른 것을 한 줄에
 *   놓으므로 선 하나로 갈라 둔다. 왼쪽부터 읽으면 구절 → 이어서 읽기 → 영상이라
 *   위에 있는 구절과 아래 있는 목록의 순서와도 맞는다.
 *   ⚠ 기본 선택은 여전히 말씀이나 찬양이다(media_defaults). 즉 첫 칸이 선택돼
 *     있지 않은데, 구분선이 있어 "두 묶음 중 오른쪽이 켜져 있다"로 읽힌다.
 *
 * [지키는 것 — MediaToggle에서 그대로 온다]
 *
 *   ① 버튼 두 개가 아니라 글자 전환이다 (2026-08-19 개정)
 *     처음에는 pill 버튼이었다(테두리 + 배경 + radius 999). 구절 카드 아래에
 *     또 하나의 면이 생겨 화면이 무거웠고, FYM의 각진 3~4px 언어와도 어긋났다.
 *     지금은 글자를 나란히 두고 **선택된 것만 밝게** 한다.
 *     밑줄 1px이 현재 위치를 알려주는 유일한 선이다.
 *
 *   ② 비활성화하지 않는다 — 이 컴포넌트의 핵심 규칙
 *     한쪽 풀이 비어도 끄지 않는다 (PLAN.md 3.4). 비활성 버튼은 사용자에게
 *     "고장"으로 읽히지만, 문장은 상황 설명으로 읽힌다. 그래서 빈 쪽을 눌러도
 *     전환은 되고, 목록 자리에 "지금은 말씀 영상만 있어요"가 대신 뜬다
 *     (그 문장은 VideoList가 그린다). 이어서 읽기도 같다 — 본문을 못 받아도
 *     탭은 눌리고, ChapterReader가 문장으로 말한다.
 *
 *   ③ 기본값은 감정마다 다르다
 *     themes.yaml media_defaults — 지친 사람에게는 30분 설교보다 찬양이,
 *     막막한 사람에게는 그 반대가 맞다. 분류가 완벽하지 않아 기본값이 안 맞는
 *     경우가 상당수 나올 것을 전제하므로, 전환은 옵션이 아니라 필수 요건이다.
 *     설정 화면에 숨기지 않고 결과 화면에 둔다.
 */

import { MEDIA } from "../lib/videos.js";
import { T } from "../theme.js";

/** 본문 탭의 값. MEDIA와 섞이지 않도록 별도 상수로 둔다. */
export const READING = "reading";

const LABELS = {
  [READING]: "이어서 읽기",
  [MEDIA.SERMON]: "말씀",
  [MEDIA.WORSHIP]: "찬양",
};

// 구분선은 **말씀 앞에만** 넣는다. 본문 묶음과 영상 형식 묶음의 경계다.
const GROUPS = [[READING], [MEDIA.SERMON, MEDIA.WORSHIP]];

export function ResultTabs({ value, counts, onChange }) {
  return (
    <div role="tablist" aria-label="결과 보기" style={styles.row}>
      {GROUPS.map((group, groupIndex) => (
        <span key={groupIndex} style={styles.cell}>
          {groupIndex > 0 ? <span style={styles.divider} /> : null}
          {group.map((tab) => {
            const active = value === tab;
            return (
              <button
                key={tab}
                type="button"
                role="tab"
                onClick={() => onChange(tab)}
                aria-selected={active}
                // disabled를 쓰지 않는다. 위 ② 참조 — 의도적이다.
                style={{
                  ...styles.button,
                  ...(active ? styles.active : null),
                  ...(tab === MEDIA.WORSHIP ? styles.spaced : null),
                }}
              >
                {LABELS[tab]}
                {/* 본문 탭에는 셀 것이 없다. 0을 그리면 "본문이 0건"으로 읽힌다. */}
                {counts?.[tab] === undefined ? null : (
                  <span
                    style={{ ...styles.count, ...(active ? styles.countActive : null) }}
                  >
                    {counts[tab]}
                  </span>
                )}
              </button>
            );
          })}
        </span>
      ))}
    </div>
  );
}

const styles = {
  /**
   * 탭 줄 위 1px 구분선 — **이 화면 위계를 만드는 것이 이것이다** (2026-08-20).
   *
   * [색과 여백으로 두 번 실패한 뒤에 넣었다 — HANDOFF 2.36]
   *   공감 문구(읽는 글)가 탭 줄의 일부처럼 읽히는 문제였다.
   *   탭 색을 85%로 내려도, 여백을 24/56으로 벌려도 해결되지 않았다.
   *
   *   빠져 있던 것은 색도 여백도 아니었다. **탭 줄에 컨트롤이라는 표시가
   *   아무것도 없었다** — 배경도 테두리도 없이 글자만 나란히 있고, 선택된
   *   것에만 1px 밑줄이 있을 뿐이다. 그러니 위의 문장과 같은 종류로 읽혔다.
   *   필요한 것은 네 번째 밝기 층이 아니라 "여기서 읽는 구간이 끝난다"는
   *   구조 신호였고, 그 일은 선이 한다.
   *
   * [선을 쓰는 것이 이 앱의 언어에 어긋나지 않는다]
   *   VerseCard가 카드 상자를 걷어낸 이유는 "면"을 없애기 위해서였지 선을
   *   금지한 것이 아니다. 그 주석이 인용하는 FYM의 규칙이 그대로다 —
   *   "입력은 밑줄 하나, **구분은 1px 선 하나**".
   *   색도 새로 만들지 않았다. `#ffffff1f`는 바로 아래 divider(탭 사이
   *   세로 실선)가 이미 쓰는 값이라, 가로세로 두 선이 같은 굵기·같은 밝기다.
   *
   * ⚠ 이 선을 지우면 색·여백을 아무리 만져도 문제가 돌아온다. 지우자는
   *   제안이 나오면 HANDOFF 2.36의 렌더 비교부터 다시 볼 것.
   */
  row: {
    display: "flex",
    alignItems: "center",
    margin: "0 0 20px",
    // 단축(borderTop)을 써도 안전한 자리다 — 상태에 따라 바뀌지 않는 정적
    // 선이라 아래 button의 결함(React가 개별 속성만 지우는 문제)이 생기지
    // 않는다. 그래도 같은 파일 안에서 표기를 섞지 않으려고 개별 속성을 쓴다.
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: "#ffffff1f",
    paddingTop: 18,
  },
  cell: { display: "inline-flex", alignItems: "center" },
  divider: {
    width: 1,
    height: 11,
    background: "#ffffff1f",
    margin: "0 14px",
  },
  button: {
    display: "inline-flex",
    alignItems: "baseline",
    gap: 6,
    padding: "2px 0 6px",
    background: "none",
    border: "none",
    // ⚠ 단축 속성(borderBottom)을 쓰지 않는다 — 2026-08-19 결함 수정.
    //   전에는 base가 `borderBottom: "1px solid transparent"`이고 active만
    //   borderBottomColor를 얹었다. 그러면 선택이 옮겨갈 때 React가 이전 버튼에서
    //   **개별 속성만 지우는데**, 단축으로 깔아 둔 색이 그 자리에서 되살아나지
    //   않고 불투명 검정(rgb(0,0,0))으로 해석됐다.
    //   결과: 비활성 탭에 검은 밑줄이 남아, 활성 탭의 흐린 jade(60%)보다
    //   오히려 진하게 보였다 — "밑줄이 반대"로 읽히던 것이 이것이다.
    //   양쪽 상태가 항상 같은 개별 속성을 지정하면 React가 값을 교체할 뿐이라
    //   이 현상이 생기지 않는다.
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: "transparent",
    /**
     * 비선택 탭 — T.muted를 85%로 낮춰 쓴다 (2026-08-20).
     *
     * [왜 낮췄나 — 밝기 단계가 둘밖에 없었다]
     *   실측하니 결과 화면에 밝기가 두 층뿐이었다.
     *     구절 · 선택 탭   T.mist   14.41:1
     *     공감 문구 · 비선택 탭   T.muted   6.28:1   <- 같은 값
     *   공감 문구는 **읽는 글**이고 탭은 **누르는 것**인데 색이 같아,
     *   문구가 탭 줄의 일부처럼 읽혔다.
     *
     * [왜 문구를 올리지 않고 탭을 내렸나]
     *   공감 문구를 올리는 안(T.mist 80% = 9.56:1)도 렌더로 확인했고 효과는
     *   더 컸다. 그런데 **앱이 사용자에게 말하는 문장은 전부 T.muted다** —
     *   공감 문구도, 마무리 문구도(common.jsx). 공감만 올리면 그 통일이
     *   깨지고, 맞추려면 마무리 문구까지 함께 올려야 한다.
     *   의미상으로도 "글은 그대로 두고 컨트롤이 물러난다"가 맞다.
     *
     * [왜 하필 D9(85%)인가 — CC(80%)는 경계에 얹힌다]
     *   탭 라벨은 아이콘이 아니라 **읽는 글자**라 WCAG AA 4.5:1에 걸린다.
     *   배경이 그라데이션이라 구간마다 다르므로 가장 불리한 상단(plum)에서 쟀다.
     *     100%  6.25:1     D9 85%  4.91:1  (여유 +0.41)
     *     CC 80%  4.50:1  <- 정확히 경계. 여유 0 — 배경을 조금만 손대도 깨진다
     *
     * ⚠ 선택 탭은 손대지 않았다. T.mist(14.41:1) + jade 60% 밑줄 그대로다 —
     *   2026-08-19에 고친 자리이고, "선택된 것만 뚜렷하게"가 이 개정의 목적이다.
     */
    color: `${T.muted}D9`,
    fontSize: 14,
    fontFamily: "inherit",
    cursor: "pointer",
    letterSpacing: "0.02em",
  },
  // 말씀과 찬양 사이는 같은 묶음이라 선이 아니라 간격으로만 띄운다.
  spaced: { marginLeft: 16 },
  active: { color: T.mist, borderBottomColor: `${T.jade}99` },
  count: { fontSize: 11, color: "#ffffff33" },
  countActive: { color: T.muted },
};
