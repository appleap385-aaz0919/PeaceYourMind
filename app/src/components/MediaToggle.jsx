/**
 * [말씀]/[찬양] 토글 — 결과 화면 상단.
 *
 * [비활성화하지 않는다 — 이게 이 컴포넌트의 핵심 규칙이다]
 *   한쪽 풀이 비어도 버튼을 끄지 않는다 (PLAN.md 3.4).
 *   비활성 버튼은 사용자에게 "고장"으로 읽히지만, 문장은 상황 설명으로 읽힌다.
 *   그래서 빈 쪽을 눌러도 전환은 되고, 목록 자리에 "지금은 말씀 영상만 있어요"가
 *   대신 뜬다. 그 문장은 VideoList가 그린다.
 *
 * [기본값은 감정마다 다르다]
 *   themes.yaml media_defaults — 지친 사람에게는 30분 설교보다 찬양이,
 *   막막한 사람에게는 그 반대가 맞다. 다만 분류가 완벽하지 않아 기본값이 안 맞는
 *   경우가 상당수 나올 것을 전제하므로, 전환은 옵션이 아니라 필수 요건이다.
 *   설정 화면에 숨기지 않고 결과 화면 상단에 둔다.
 */

import { MEDIA } from "../lib/videos.js";
import { T } from "../theme.js";

const LABELS = { [MEDIA.SERMON]: "말씀", [MEDIA.WORSHIP]: "찬양" };

export function MediaToggle({ value, counts, onChange }) {
  return (
    <div role="group" aria-label="영상 형식" style={styles.row}>
      {[MEDIA.SERMON, MEDIA.WORSHIP].map((type) => {
        const active = value === type;
        return (
          <button
            key={type}
            type="button"
            onClick={() => onChange(type)}
            aria-pressed={active}
            // disabled를 쓰지 않는다. 위 주석 참조 — 의도적이다.
            style={{ ...styles.button, ...(active ? styles.active : null) }}
          >
            {LABELS[type]}
            <span style={styles.count}>{counts?.[type] ?? 0}</span>
          </button>
        );
      })}
    </div>
  );
}

const styles = {
  row: { display: "flex", gap: 8, margin: "4px 0 18px" },
  button: {
    flex: "0 0 auto",
    display: "inline-flex",
    alignItems: "baseline",
    gap: 6,
    padding: "8px 16px",
    borderRadius: 999,
    border: "1px solid #ffffff1a",
    background: "transparent",
    color: T.muted,
    fontSize: 13.5,
    fontFamily: "inherit",
    cursor: "pointer",
  },
  active: {
    background: "#ffffff12",
    borderColor: "#ffffff33",
    color: T.mist,
  },
  count: { fontSize: 11, opacity: 0.55 },
};
