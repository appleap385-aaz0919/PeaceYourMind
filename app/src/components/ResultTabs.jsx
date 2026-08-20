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
  row: { display: "flex", alignItems: "center", margin: "0 0 20px" },
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
    color: T.muted,
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
