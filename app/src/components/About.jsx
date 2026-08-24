/**
 * 이 앱에 대해 — 출처 표기·면책·운영 주체를 밝히는 자리.
 *
 * [출처 표기가 여기에만 있다 — 2026-08-19 정책]
 *   전에는 구절 카드에도 있었다. 카드 상자를 걷어낸 뒤 본문 아래 회색 한 줄이
 *   구절의 여운을 끊어 뺐고(VerseCard.jsx 상단 주석), 표기 자리는 이 화면만
 *   남았다. **성명표시권은 저작재산권과 달리 만료되지 않는다.**
 *   자리가 하나뿐이라는 것은 이 화면의 표기가 **더 중요해졌다**는 뜻이다.
 *   화면 정리를 이유로 지우자는 제안은 거절해야 한다 — 요건이지 취향이 아니다.
 *   verses.test.js가 이 화면에 표기가 있는지, 여기로 오는 길이 있는지를 검사한다.
 *
 * [스토어 출시 대비 — 2026-08-19 자리만 잡았다]
 *   구글 플레이·애플 앱스토어 심사가 요구하는 항목을 구조로 먼저 넣었다.
 *   실제 값(제작자명·연락처·처리방침 URL)은 아직 정하지 않아 TODO로 둔다.
 *   ⚠ **TODO가 남은 채로 스토어에 올리면 안 된다.** HANDOFF "스토어 출시 전
 *     확정 필요" 목록이 이 파일의 TODO와 짝이다.
 *
 *   개인정보처리방침은 **양쪽 스토어 모두 필수**이며, 데이터를 수집하지 않는
 *   앱도 면제되지 않는다. "수집하지 않는다"는 사실 자체를 문서로 밝혀야 한다.
 *   PYM은 실제로 수집하지 않으므로(로그인·계정·서버 전송 없음) 그 사실을
 *   그대로 쓰면 되고, 아래 "기록" 절의 문장이 그 초안이다.
 *
 * [면책 문구의 톤 — 앱 전체와 맞추되 흐리지 않는다]
 *   이 앱은 조용한 어조로 말하지만 면책은 **명확해야** 한다. 부드럽게 쓰다가
 *   "의료 서비스가 아니다"가 읽히지 않으면 면책이 아니다. 그래서 면책 두 절만
 *   단정형("아닙니다", "이용해 주세요")을 쓴다.
 */

import { useState } from "react";

import { clearAllLocalData, clearBrowsingTraces } from "../lib/db.js";
import { T, SERIF } from "../theme.js";

// vite.config.js가 package.json에서 주입한다. 손으로 적지 않는다.
const VERSION = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "";

// TODO(스토어 출시): 실제 값으로 교체한다. HANDOFF "스토어 출시 전 확정 필요" 참조.
//   빈 문자열이면 그 줄을 그리지 않는다 — "TODO"라고 적힌 화면이 사용자에게
//   보이는 것보다 항목이 없는 편이 낫고, 값을 넣는 순간 자동으로 나타난다.
const OPERATOR = ""; // 예: "홍길동" 또는 "OO 스튜디오"
const CONTACT = ""; // 예: "pym@example.com"
const PRIVACY_URL = ""; // 예: "https://example.com/pym/privacy"

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
        {/*
          ⛔ "승인"·"심사"·"검증" 같은 보증 어휘를 쓰지 않는다 (2026-08-24 개정).
            개정 전 문구는 "사람이 확인해 승인한 채널의 영상만 담습니다"였다.
            allowlist를 사람이 만드는 것은 사실이지만, 화면에서 "승인"이라고 말하면
            **품질·정통성을 보증한 것으로 읽힌다.** 아래 저작권 문단의
            "이 앱의 입장과 같지 않을 수 있습니다"와도 미묘하게 충돌했다.

            빼되 침묵하지는 않는다 — "어떻게 고르는가"에 답이 없으면 오해가 생겼을 때
            화면에서 댈 근거가 사라진다(allowlist는 저장소에 있지 사용자가 보는 곳에 없다).
            그래서 **보증이 아니라 사실**만 말한다: 목록이 미리 정해져 있고 검색하지 않는다.
            회귀는 app/test/behavior.test.js가 막는다.
        */}
        <p style={styles.note}>
          영상은 미리 정해 둔 채널 목록에서만 가져옵니다. 검색으로 모으지 않으며,
          앱이 유튜브에 직접 묻지도 않습니다. 영상을 누르면 유튜브로 이동합니다.
        </p>
        {/* 콘텐츠 면책 — 저작권 귀속과 이 앱의 역할을 분명히 한다. */}
        <p style={styles.note}>
          모든 영상의 저작권은 각 채널에 있습니다. 이 앱은 영상을 저장하거나
          재가공하지 않고 링크만 제공합니다. 영상의 내용은 각 채널의 견해이며
          이 앱의 입장과 같지 않을 수 있습니다.
        </p>
      </section>

      <section style={styles.block}>
        <h2 style={styles.heading}>기록</h2>
        <p style={styles.note}>
          입력한 내용은 기기 밖으로 나가지 않습니다. 로그인도 계정도 없고,
          방문 기록과 마지막으로 고른 형식만 이 기기에 남습니다.
          개인정보를 수집하지 않으며 어떤 것도 서버로 보내지 않습니다.
        </p>
        <EraseRecords />
        {PRIVACY_URL ? (
          <p style={styles.body}>
            <a href={PRIVACY_URL} target="_blank" rel="noreferrer" style={styles.link}>
              개인정보처리방침
            </a>
          </p>
        ) : null}
      </section>

      <section style={styles.block}>
        <h2 style={styles.heading}>도움이 필요할 때</h2>
        {/* 위기 안내 면책 — 이 절에서 가장 중요한 문장이다. 앱이 상담을
            대신한다고 오해하면 정작 필요한 순간에 전화를 걸지 않게 된다. */}
        <p style={styles.note}>
          이 앱은 의료 서비스나 상담 서비스가 아닙니다. 진단이나 치료를 제공하지
          않습니다. 마음이 많이 힘들거나 위급하다고 느껴질 때는 아래 전문 상담
          연락처를 이용해 주세요. 언제든 연결할 수 있습니다.
        </p>
        <p style={styles.body}>자살예방 상담전화 109</p>
        <p style={styles.body}>정신건강 위기상담전화 1577-0199</p>
      </section>

      {OPERATOR || CONTACT || VERSION ? (
        <section style={styles.block}>
          <h2 style={styles.heading}>만든 곳</h2>
          {OPERATOR ? <p style={styles.body}>{OPERATOR}</p> : null}
          {CONTACT ? (
            <p style={styles.body}>
              <a href={`mailto:${CONTACT}`} style={styles.link}>
                {CONTACT}
              </a>
            </p>
          ) : null}
          {VERSION ? <p style={styles.note}>버전 {VERSION}</p> : null}
        </section>
      ) : null}

      <button type="button" onClick={onBack} style={styles.back}>
        돌아가기
      </button>
    </div>
  );
}

/**
 * 기록 삭제 — taxonomy.yaml ui.revisit.privacy_note가 약속한 버튼이다.
 *
 * [확인 단계를 두되 경고창은 쓰지 않는다 (2026-08-24)]
 *   되돌릴 수 없으므로 한 번에 지우면 안 된다. 그렇다고 window.confirm은
 *   이 앱의 톤과 맞지 않는다 — 브라우저 기본 대화상자는 시스템 목소리이고,
 *   이 화면은 조용히 말하는 자리다. **버튼 자신이 한 번 더 묻는다.**
 *     1) "기록 지우기"        → 누르면
 *     2) "정말 지울까요? 예"  → 누르면 지운다
 *     3) "지웠어요"           → 상태만 바뀐다. 화면을 가로막지 않는다
 *   물러설 길을 함께 둔다 — 2)에서 "아니요"가 옆에 있다.
 */
function EraseRecords() {
  const [step, setStep] = useState("idle"); // idle → asking → done

  const erase = async () => {
    await clearAllLocalData();
    await clearBrowsingTraces();
    setStep("done");
  };

  if (step === "done") {
    return <p style={styles.note}>지웠어요. 다음에 오시면 처음처럼 맞이할게요.</p>;
  }

  if (step === "asking") {
    return (
      <p style={styles.note}>
        방문 기록과 받아 둔 목록이 사라집니다. 되돌릴 수 없어요.{" "}
        <button type="button" onClick={erase} style={styles.eraseYes}>
          지울게요
        </button>
        <button type="button" onClick={() => setStep("idle")} style={styles.eraseNo}>
          그만두기
        </button>
      </p>
    );
  }

  return (
    <button type="button" onClick={() => setStep("asking")} style={styles.erase}>
      이 기기에서 기록 지우기
    </button>
  );
}

const styles = {
  title: { fontFamily: SERIF, fontSize: 19, fontWeight: 400, margin: "6px 0 24px", color: T.mist },
  block: { marginBottom: 26 },
  heading: { fontSize: 12.5, fontWeight: 400, color: T.sand, margin: "0 0 8px", letterSpacing: "0.04em" },
  body: { margin: "0 0 4px", fontSize: 14, color: T.mist, lineHeight: 1.7 },
  note: { margin: "0 0 8px", fontSize: 13, color: T.muted, lineHeight: 1.8, wordBreak: "keep-all" },
  link: { color: T.jade, textDecoration: "none", borderBottom: `1px solid ${T.jade}59` },
  back: {
    display: "block",
    margin: "20px auto 0",
    background: "none",
    border: "none",
    color: "#ffffff40",
    fontSize: 12.5,
    cursor: "pointer",
  },
  // 기록 삭제 — 되돌릴 수 없으므로 눈에 띄되 앞으로 나서지는 않는다.
  // 본문(note)과 같은 크기로 두어 "설정 항목"이 아니라 "문장 옆의 행동"으로 읽히게 한다.
  erase: {
    background: "none",
    border: "none",
    padding: 0,
    color: T.muted,
    fontSize: 13,
    textDecoration: "underline",
    textUnderlineOffset: 3,
    cursor: "pointer",
  },
  eraseYes: {
    background: "none",
    border: "none",
    padding: 0,
    marginRight: 12,
    color: T.jade,
    fontSize: 13,
    textDecoration: "underline",
    textUnderlineOffset: 3,
    cursor: "pointer",
  },
  eraseNo: {
    background: "none",
    border: "none",
    padding: 0,
    color: T.muted,
    fontSize: 13,
    cursor: "pointer",
  },
};
