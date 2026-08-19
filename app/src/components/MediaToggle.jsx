/**
 * [말씀] / [찬양] 전환 — 결과 화면, 영상 목록 바로 위.
 *
 * [버튼 두 개가 아니라 글자 전환이다 — 2026-08-19 개정]
 *   처음에는 pill 버튼 두 개였다(테두리 + 배경 + radius 999). 구절 카드 아래에
 *   또 하나의 면이 생겨 화면이 무거웠고, FYM의 각진 3~4px 언어와도 어긋났다.
 *   지금은 글자 두 개를 나란히 두고 **선택된 쪽만 밝게** 한다.
 *   밑줄 1px이 현재 위치를 알려주는 유일한 선이다.
 *
 * [비활성화하지 않는다 — 이 컴포넌트의 핵심 규칙]
 *   한쪽 풀이 비어도 끄지 않는다 (PLAN.md 3.4). 비활성 버튼은 사용자에게
 *   "고장"으로 읽히지만, 문장은 상황 설명으로 읽힌다. 그래서 빈 쪽을 눌러도
 *   전환은 되고, 목록 자리에 "지금은 말씀 영상만 있어요"가 대신 뜬다
 *   (그 문장은 VideoList가 그린다).
 *
 * [기본값은 감정마다 다르다]
 *   themes.yaml media_defaults — 지친 사람에게는 30분 설교보다 찬양이,
 *   막막한 사람에게는 그 반대가 맞다. 다만 분류가 완벽하지 않아 기본값이 안 맞는
 *   경우가 상당수 나올 것을 전제하므로, 전환은 옵션이 아니라 필수 요건이다.
 *   설정 화면에 숨기지 않고 결과 화면에 둔다.
 */

import { MEDIA } from "../lib/videos.js";
import { T } from "../theme.js";

const LABELS = { [MEDIA.SERMON]: "말씀", [MEDIA.WORSHIP]: "찬양" };

export function MediaToggle({ value, counts, onChange }) {
  return (
    <div role="group" aria-label="영상 형식" style={styles.row}>
      {[MEDIA.SERMON, MEDIA.WORSHIP].map((type, index) => {
        const active = value === type;
        return (
          <span key={type} style={styles.cell}>
            {index > 0 ? <span style={styles.divider} /> : null}
            <button
              type="button"
              onClick={() => onChange(type)}
              aria-pressed={active}
              // disabled를 쓰지 않는다. 위 주석 참조 — 의도적이다.
              style={{ ...styles.button, ...(active ? styles.active : null) }}
            >
              {LABELS[type]}
              <span style={{ ...styles.count, ...(active ? styles.countActive : null) }}>
                {counts?.[type] ?? 0}
              </span>
            </button>
          </span>
        );
      })}
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
    borderBottom: "1px solid transparent",
    color: T.muted,
    fontSize: 14,
    fontFamily: "inherit",
    cursor: "pointer",
    letterSpacing: "0.02em",
  },
  active: { color: T.mist, borderBottomColor: `${T.jade}99` },
  count: { fontSize: 11, color: "#ffffff33" },
  countActive: { color: T.muted },
};
