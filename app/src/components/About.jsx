/**
 * 이 앱에 대해 — 출처 표기와 데이터 취급을 밝히는 자리.
 *
 * [출처 표기가 두 곳에 있는 이유]
 *   구절 카드 안에도, 이 화면에도 있다. 중복이 아니라 요건이다 —
 *   저작인격권(성명표시권)은 본문이 노출되는 자리에 표기를 요구하고,
 *   설정/정보 화면의 표기는 앱 전체에 대한 고지다. 둘 중 하나만 두면
 *   구절만 보고 나가는 사용자나 정보 화면만 보는 사용자 한쪽이 빈다.
 */

import { T, SERIF } from "../theme.js";

export function About({ attribution, onBack }) {
  return (
    <div className="rise">
      <h1 style={styles.title}>이 앱에 대해</h1>

      <section style={styles.block}>
        <h2 style={styles.heading}>성경 본문</h2>
        <p style={styles.body}>{attribution}</p>
        <p style={styles.note}>
          본문은 한 글자도 고치지 않고 그대로 싣습니다. 개역한글은 옛 표기를 쓰며,
          현대 맞춤법으로 고치지 않는 것이 원문을 지키는 방식입니다.
        </p>
      </section>

      <section style={styles.block}>
        <h2 style={styles.heading}>영상</h2>
        <p style={styles.note}>
          사람이 확인해 승인한 채널의 영상만 담습니다. 검색으로 모으지 않으며,
          앱이 유튜브에 직접 묻지도 않습니다. 영상을 누르면 유튜브로 이동합니다.
        </p>
      </section>

      <section style={styles.block}>
        <h2 style={styles.heading}>기록</h2>
        <p style={styles.note}>
          입력한 내용은 기기 밖으로 나가지 않습니다. 로그인도 계정도 없고,
          방문 기록과 마지막으로 고른 형식만 이 기기에 남습니다.
        </p>
      </section>

      <section style={styles.block}>
        <h2 style={styles.heading}>도움이 필요할 때</h2>
        <p style={styles.note}>
          마음이 많이 힘들 때는 언제든 연결할 수 있습니다.
        </p>
        <p style={styles.body}>자살예방 상담전화 109</p>
        <p style={styles.body}>정신건강 위기상담전화 1577-0199</p>
      </section>

      <button type="button" onClick={onBack} style={styles.back}>
        돌아가기
      </button>
    </div>
  );
}

const styles = {
  title: { fontFamily: SERIF, fontSize: 19, fontWeight: 400, margin: "6px 0 24px", color: T.mist },
  block: { marginBottom: 26 },
  heading: { fontSize: 12.5, fontWeight: 400, color: T.sand, margin: "0 0 8px", letterSpacing: "0.04em" },
  body: { margin: "0 0 4px", fontSize: 14, color: T.mist, lineHeight: 1.7 },
  note: { margin: "0 0 4px", fontSize: 13, color: T.muted, lineHeight: 1.8, wordBreak: "keep-all" },
  back: {
    display: "block",
    margin: "20px auto 0",
    background: "none",
    border: "none",
    color: "#ffffff40",
    fontSize: 12.5,
    cursor: "pointer",
  },
};
