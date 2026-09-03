import { useEffect, useState } from "react";
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

/**
 * 빈 입력·분류 실패 안내. 오류가 아니라 초대처럼 보이게 한다.
 *
 * [보조 버튼 — 2026-08-25]
 *   분류 실패 문구가 "다른 말로 다시 적어 주셔도 좋아요"라고 말한다. 그러면
 *   **그 길이 한 번에 닿아야 한다.** 전에는 고르는 화면으로 간 뒤 거기서
 *   "직접 적기"를 또 눌러야 했다 — 두 번 이동이라 문구가 거짓이 된다.
 *   ⚠ 문구와 경로는 함께 고쳐야 한다. 한쪽만 고치면 화면이 거짓말을 한다.
 *
 *   모양은 Closing의 "다시 적어보기"와 같은 조용한 텍스트 버튼이다
 *   (#ffffff66 · 12.5px). 주 버튼(테두리 있는 jade)과 위계를 갈라 둔다 —
 *   무엇이 기본 경로인지 화면이 말해야 한다.
 */
export function Msg({ title, sub, onBack, back = "돌아가기", onAlt, alt }) {
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
      {onAlt ? (
        <div>
          <button
            type="button"
            onClick={onAlt}
            style={{
              marginTop: 14,
              padding: "6px 10px",
              border: "none",
              background: "transparent",
              color: "#ffffff66",
              fontSize: 12.5,
            }}
          >
            {alt}
          </button>
        </div>
      ) : null}
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

/**
 * 스크롤하면 우하단에 나타나는 "다시 적기". **FYM 원본 그대로다.**
 *
 * 결과가 길면 하단의 "다시 적어보기"까지 내려가야만 돌아갈 수 있었다.
 * 처음부터 떠 있으면 화면을 방해하므로, 스크롤을 시작한 뒤에만 조용히 나타난다.
 *
 * 최상단에서는 나타나지 않는다. 그 자리는 공감 문장이 처음 읽히는 자리이고,
 * 마음을 털어놓고 답을 받는 순간에 무르기 동작이 함께 보이면 안 된다.
 * 스크롤을 시작했다는 것은 이미 그 문장을 지났다는 뜻이라 타이밍이 맞다.
 *
 * ⚠⚠ **App 최상위에, `.rise` 바깥에 렌더해야 한다.** (HANDOFF 4.8)
 *   `.rise`는 animation-fill-mode: both라 끝난 뒤에도 transform: translateY(0)이
 *   남는다. `none`이 아닌 transform은 fixed 자손의 containing block을 만들어
 *   이 버튼이 뷰포트가 아니라 그 div에 붙는다 — 화면에 떠 있지 않고 문서와
 *   함께 흘러가 버린다. 2026-08-19에 실제로 그렇게 넣었다가 되돌렸다.
 *   `transform` 외에 filter·perspective·will-change·backdrop-filter도 같다.
 *
 *   증상이 "fixed인데 안 붙는다"라 CSS만 봐서는 원인을 못 찾는다.
 *   스크롤 전후로 getBoundingClientRect().top을 재서 변화가 0이어야 진짜 fixed다.
 *   behavior.test.js가 렌더 위치를 검사한다.
 */
const REVEAL_AFTER_PX = 100;

/**
 * 떠 있는 버튼의 모양 — FloatingRestart와 FloatingBack이 함께 쓴다.
 * 둘은 하는 일이 다르지만 **같은 자리에 같은 모양으로** 나타나야 한다.
 * 한쪽만 고치면 화면에 두 종류의 떠 있는 버튼이 생긴다.
 */
/**
 * 떠 있는 버튼의 자리 — **다른 것이 이 위에 얹힐 때 여기서 파생시킨다.**
 *
 * ⛔ 토스트가 이 둘로 자기 bottom을 계산한다 (2.119). 배경면 높이·페이드에서
 *   쌓아 올리면 배경면이 98→82로 바뀔 때 따라가지 못한다.
 * ⚠ FLOATING_HEIGHT는 실측값이다(패딩 10 + 글자 12.5 + 패딩 10 ≈ 40dp).
 *   패딩이나 글자 크기를 바꾸면 여기도 바꾼다 — 회귀가 토스트와의 관계만 본다.
 */
export const FLOATING_BOTTOM = 24;
export const FLOATING_HEIGHT = 40;

function floatingStyle(shown, reducedMotion, bottomInset = 0) {
  return {
    position: "fixed",
    right: 20,
    // ★ 띠배너가 뜨면 그만큼 올라간다. **두 버튼이 이 함수 하나를 쓰므로
    //   여기 한 줄이 둘을 다 옮긴다** — 한쪽만 올라가는 날이 없다.
    // ⚠ bottomInset은 "보일 화면인가"만으로 정해지지 않는다. 광고가 실제로
    //   채워졌을 때만 100이고, 미채움이면 0으로 돌아온다(adsApp.js bannerSpace).
    //   그래서 띠가 접히면 버튼도 **함께 내려온다.**
    bottom: FLOATING_BOTTOM + bottomInset,
    padding: "10px 16px",
    borderRadius: 99,
    border: `1px solid ${T.jade}33`,
    background: `${T.ink}d9`,
    backdropFilter: "blur(6px)",
    WebkitBackdropFilter: "blur(6px)",
    color: T.muted,
    fontSize: 12.5,
    letterSpacing: "0.04em",
    opacity: shown ? 1 : 0,
    pointerEvents: shown ? "auto" : "none",
    transition: reducedMotion ? "none" : "opacity .3s ease",
  };
}

/**
 * "이 앱에 대해" 화면의 떠 있는 "돌아가기".
 *
 * 이 화면도 결과 화면처럼 길다 — 절이 여섯이고 하단 "돌아가기"까지 한참
 * 내려가야 한다. FloatingRestart와 **같은 조건·같은 자리·같은 모양**이다
 * (스크롤 100px 뒤 등장 · 우하단 · HANDOFF 2.22).
 *
 * ⚠⚠ FloatingRestart와 똑같이 **Shell에서, `.rise` 바깥에** 렌더해야 한다.
 *   (HANDOFF 4.8) 화면 컴포넌트 안에 두면 `.rise`의 transform이 containing
 *   block을 만들어 fixed가 죽는다. behavior.test.js가 렌더 위치를 검사한다.
 *
 * [하단 고정 버튼과 겹치지 않게 한다]
 *   하단 "돌아가기"는 **그대로 둔다**(사용자 결정). 다만 그것이 화면에
 *   들어오면 같은 일을 하는 버튼이 둘 보이므로, 그동안 떠 있는 쪽을 숨긴다.
 *   ⚠ 위치를 비교하지 않고 **보이는가**로 판단한다 — 하단 버튼은 가운데
 *     정렬이고 떠 있는 버튼은 우측이라 픽셀이 겹치지 않을 수도 있지만,
 *     피하려는 것은 충돌이 아니라 **중복 노출**이다.
 */
export function FloatingBack({ onClick, reducedMotion, anchorId, bottomInset = 0 }) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const update = () => {
      const scrolled = window.scrollY > REVEAL_AFTER_PX;
      const anchor = anchorId ? document.getElementById(anchorId) : null;
      // 하단 버튼이 화면 안에 있는가. 없으면(anchor null) 스크롤만 본다.
      const anchorVisible = anchor
        ? (() => {
            const box = anchor.getBoundingClientRect();
            return box.top < window.innerHeight && box.bottom > 0;
          })()
        : false;
      setShown(scrolled && !anchorVisible);
    };
    update(); // 이미 스크롤된 상태로 들어올 수 있다
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [anchorId]);

  if (reducedMotion && !shown) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-hidden={!shown}
      tabIndex={shown ? 0 : -1}
      style={floatingStyle(shown, reducedMotion, bottomInset)}
    >
      돌아가기
    </button>
  );
}

export function FloatingRestart({ onClick, reducedMotion, bottomInset = 0 }) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const onScroll = () => setShown(window.scrollY > REVEAL_AFTER_PX);
    onScroll(); // 이미 스크롤된 상태로 들어올 수 있다
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // reduced-motion이면 페이드를 쓰지 않는다. 나타나고 사라지는 것 자체는 유지한다.
  if (reducedMotion && !shown) return null;

  return (
    <button
      onClick={onClick}
      aria-hidden={!shown}
      tabIndex={shown ? 0 : -1}
      style={floatingStyle(shown, reducedMotion, bottomInset)}
    >
      다시 적기
    </button>
  );
}
