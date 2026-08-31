/**
 * 알림으로 들어온 화면 — 구절 하나와 이어서 읽기, 그리고 입력으로 가는 문.
 *
 * [⛔ 결과 화면을 재사용하지 않는다]
 *   결과 화면은 **감정 세분류를 전제한다.** 알림에는 감정이 없다 — 사용자가
 *   아무 말도 하지 않았다. 재사용하려면 세분류를 지어내야 하고, 그 순간
 *   화면이 하지 않은 판단을 한 척하게 된다.
 *
 * [⛔ 영상을 붙이지 않는다]
 *   영상은 감정 분류의 산출물이다. 감정을 모르는 자리에서 고를 근거가 없다.
 *
 * [⛔ 배너도 띄우지 않는다 (3단계 대비)]
 *   먼저 다가가 놓고 그 첫 화면에 광고를 두면 "알림으로 불러 광고를 보여준다"로
 *   읽힌다. App.jsx의 배너 규칙이 "결과 화면에서만"인 이유가 이것이다.
 *
 * [하단은 입구다]
 *   "지금 마음을 적어볼까요"가 입력 화면으로 보낸다. 알림이 **종착지가 아니라
 *   입구**가 되게 하는 한 줄이다.
 */

import { ChapterReader } from "./ChapterReader.jsx";
import { VerseCard } from "./VerseCard.jsx";
import { T } from "../theme.js";

export function MorningVerse({ verse, onWrite }) {
  if (!verse) return null;

  return (
    <div className="rise">
      <p style={styles.eyebrow}>오늘 아침의 구절</p>

      <VerseCard verse={verse} canRotate={false} />

      {/* read는 293건 전부에 있다(gen_verses_json.py가 붙인다). 그래도 없을 때
          조용히 비우는 쪽을 택한다 — 위기 구절에는 read가 없고, 데이터가
          비면 화면이 죽는 것보다 한 절만 보이는 편이 낫다. */}
      {verse.read ? <ChapterReader key={verse.id} read={verse.read} /> : null}

      <button type="button" onClick={onWrite} style={styles.write}>
        지금 마음을 적어볼까요
      </button>
    </div>
  );
}

const styles = {
  eyebrow: {
    margin: "6px 0 18px",
    fontSize: 12.5,
    color: T.muted,
    letterSpacing: "0.04em",
  },
  write: {
    display: "block",
    margin: "34px auto 0",
    padding: "11px 20px",
    background: "none",
    border: `1px solid ${T.jade}40`,
    borderRadius: 99,
    color: T.jade,
    fontSize: 13.5,
    // ⚠ <button>은 font-family를 상속하지 않는다 (About.jsx back 주석과 같은 이유).
    fontFamily: "inherit",
  },
};
