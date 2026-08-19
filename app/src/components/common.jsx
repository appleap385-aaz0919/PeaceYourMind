import { T, SERIF } from "../theme.js";

/** 영상 목록 하단에 조용히 붙는 한 마디 + 돌아가기. 프로토타입 그대로. */
export function Closing({ text, onBack }) {
  return (
    <div style={{ marginTop: 32, textAlign: "center" }}>
      <div style={{ fontFamily: SERIF, fontSize: 14.5, color: T.muted, lineHeight: 1.8 }}>
        {text}
      </div>
      <button
        onClick={onBack}
        style={{
          marginTop: 26,
          background: "none",
          border: "none",
          // #ffffff40 → #ffffff66 (2026-08-19). 근거는 취향이 아니라 대비다 —
          // 배경 #141E24에 대해 2.27:1이었고, 상호작용 요소의 최소선으로 보는
          // 3:1에 못 미쳤다. #ffffff66은 3.78:1로 그 선을 넘는다.
          // 더 올리지 않은 것은 바로 위 마무리 문구(T.muted, 6.28:1)보다
          // 조용해야 하기 때문이다 — 문장이 먼저 읽히고 버튼이 뒤따라야 한다.
          // ⚠ FYM의 같은 버튼도 #ffffff40이다. 두 앱 공통 과제로 남겼다.
          color: "#ffffff66",
          fontSize: 12.5,
        }}
      >
        다시 적어보기
      </button>
    </div>
  );
}

/** 빈 입력·분류 실패 안내. 오류가 아니라 초대처럼 보이게 한다. */
export function Msg({ title, sub, onBack, back = "돌아가기" }) {
  return (
    <div className="rise" style={{ textAlign: "center", paddingTop: 60 }}>
      <div style={{ fontFamily: SERIF, fontSize: 19, color: T.mist, lineHeight: 1.7 }}>
        {title}
      </div>
      <div style={{ fontSize: 13.5, color: T.muted, marginTop: 12 }}>{sub}</div>
      <button
        onClick={onBack}
        style={{
          marginTop: 30,
          padding: "11px 24px",
          borderRadius: 3,
          border: `1px solid ${T.jade}4d`,
          background: "transparent",
          color: T.jade,
          fontSize: 13,
        }}
      >
        {back}
      </button>
    </div>
  );
}

/**
 * 위기 안내 블록 — 상담 안내가 화면 최상단·최대 강조로 항상 먼저 온다.
 * 영상은 이 블록 아래에 놓인다 (taxonomy.yaml content_policy.placement).
 */
export function CrisisBlock({ message, resources }) {
  return (
    <div
      style={{
        border: `1px solid ${T.sand}4d`,
        background: `${T.sand}0f`,
        borderRadius: 4,
        padding: "22px 20px",
      }}
    >
      <div style={{ fontFamily: SERIF, fontSize: 17, lineHeight: 1.75, color: T.mist }}>
        {message}
      </div>
      <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 9 }}>
        {resources.map((resource) => (
          <a
            key={resource.number}
            href={`tel:${resource.number}`}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "12px 15px",
              border: `1px solid ${T.sand}40`,
              borderRadius: 3,
              textDecoration: "none",
            }}
          >
            <span style={{ fontSize: 13.5, color: T.mist }}>{resource.name}</span>
            <span
              style={{
                fontFamily: SERIF,
                fontSize: 18,
                color: T.sand,
                letterSpacing: "0.04em",
              }}
            >
              {resource.number}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
