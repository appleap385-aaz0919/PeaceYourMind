/**
 * 이어서 읽기 — 지금 뜬 구절이 속한 장을 앞뒤로 읽는다.
 *
 *   구절 카드   시편 130:1  "여호와여 내가 깊은데서 주께 부르짖었나이다"
 *   이 화면     시편 130편 · 2-5 / 8
 *                 2  주여 내 소리를 들으시며…
 *                 3  여호와여 주께서 죄악을 감찰하실찐대…
 *
 * [범위는 그 장이다 — 장 경계를 넘지 않는다]
 *   시편 130편(8절)은 금방 끝나고 시편 119편(176절)은 44페이지다. 그래도
 *   장에서 멈추는 이유는 분량이 아니다 —
 *     ① 통제할 수 없는 본문이 이어진다. 130편이 끝나고 131편이 열리면
 *        감정에 맞춰 고른 구절 뒤에 아무 검수도 거치지 않은 본문이 붙는다.
 *        위기 화면에 이 탭을 넣지 않는 것과 **같은 종류의 위험**이다.
 *     ② 끝을 정할 수 없다. 한 장을 넘으면 두 장도 넘어야 하고
 *        시편 150편 다음은 잠언 1장이다. 멈추는 자리에 근거가 없다.
 *
 * [출처 표기를 여기에 두지 않는다 — 그런데 그래서 달라지는 것이 있다]
 *   구절 카드와 같은 판단이다. 본문의 여운을 끊는 회색 한 줄을 두지 않는다.
 *
 *   ⚠ **그러나 이 화면이 생기면서 앱이 노출하는 본문의 양이 구절 하나에서
 *     장 단위로 커졌다.** 표기 자리는 여전히 "이 앱에 대해" 한 곳뿐이므로,
 *     그 한 곳이 이제 **앱 전체의 본문을 커버하는 유일한 표기**다.
 *     성명표시권은 저작재산권과 달리 만료되지 않는다. 그 표기는 어떤
 *     경우에도 삭제하지 않으며, 화면 정리를 이유로 지우자는 제안이 나오면
 *     거절해야 한다 — 이쪽은 취향이 아니라 요건이다.
 *     verses.test.js가 About의 표기와 그 화면으로 가는 길을 검사해 고정한다.
 *
 * [말하지 않는 것 둘 — 2026-08-20 결정 D]
 *   ① 장 처음부터 열렸다는 사실(20건)을 말하지 않는다
 *   ② 위에 뜬 구절이 어느 것인지 표시하지 않는다
 *   장 머리와 절 번호가 이미 위치를 알려준다. 굳이 설명하면 "원래는 뒤부터
 *   여야 하는데"·"왜 여기만 다르지"라는 없던 질문을 만든다.
 *   말 없이 자연스러운 쪽이 이 앱의 톤이다.
 */

import { useEffect, useState } from "react";

import {
  PAGE_SIZE,
  chapterUnits,
  clampCursor,
  initialCursor,
  lastCursor,
  loadChapter,
  pageUnits,
} from "../lib/chapters.js";
import { T, SERIF } from "../theme.js";

/**
 * 본문 크기 — 고정 17px. **구절 카드의 22/20/18을 쓰지 않는다.**
 *
 * 그 사다리는 근거가 다르다(VerseCard.jsx). 기준이 "360px에서 구절과 공감
 * 문구가 한 화면에 들어오는가"였고, "구절 한 개가 화면의 주인공"이라는 전제
 * 위에 있다. 이어서 읽기는 전제가 둘 다 다르다 — 연속해서 읽는 본문이고,
 * 한 화면에 담을 대상이 아니다.
 *
 * 17px인 이유는 chapters.js의 PAGE_SIZE 주석에 있다(중앙값 45자가 17px에서
 * 2줄, 18px에서 3줄이 된다). 그리고 이 값이 구절 최소 단계 18px보다 작아
 * **위계도 함께 지킨다** — 구절이 주인공이라는 것이 크기로도 유지된다.
 */
const TEXT_SIZE = 17;
const LINE_HEIGHT = 1.85;

export function ChapterReader({ read }) {
  const [chapter, setChapter] = useState(null);
  const [cursor, setCursor] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setChapter(null);
    setFailed(false);
    (async () => {
      const loaded = await loadChapter(read.book, read.chapter);
      if (cancelled) return;
      if (!loaded) {
        setFailed(true);
        return;
      }
      const units = chapterUnits(loaded.verses);
      setChapter({ ...loaded, units });
      setCursor(initialCursor(read.from, units));
    })();
    return () => {
      cancelled = true;
    };
  }, [read.book, read.chapter, read.from]);

  if (failed) return <Unavailable />;
  if (!chapter) return <Loading />;

  const page = pageUnits(chapter.units, cursor);
  const total = chapter.verses.length;
  const last = lastCursor(chapter.units);
  const span =
    page.length === 0
      ? ""
      : `${page[0].from}-${page[page.length - 1].to}`.replace(/^(\d+)-\1$/, "$1");

  return (
    <section aria-label="이어서 읽기" style={styles.wrap}>
      <p style={styles.head}>
        <span style={styles.title}>{chapter.title}</span>
        {/* 진도는 시편 119편(176절)에서 특히 일한다 — 규모를 먼저 알려주면
            4페이지 만에 끝나지 않는 것이 결함으로 읽히지 않는다. */}
        <span style={styles.progress}>
          {span} / {total}
        </span>
      </p>

      <div style={styles.body}>
        {page.map((unit) => (
          <p key={unit.from} style={styles.verse}>
            {/* 절 번호는 위 첨자를 쓰지 않는다. 11.5px가 다시 축소되면 읽히지
                않고, 이 화면은 선도 면도 쓰지 않는다 — 색 차이(sand/mist)
                하나로 번호와 본문이 갈린다.

                ⚠ 번호와 본문 사이에 **줄바꿈 없는 공백**을 넣는다. margin만으로는
                  화면에서만 떨어져 보이고 textContent에서는 "36이에"로 붙는다 —
                  구절을 복사해 나가는 사람과 스크린리더가 그것을 받는다.
                  일반 공백이 아닌 이유는 그 자리가 줄바꿈 지점이 되면 번호만
                  앞줄에 남을 수 있기 때문이다. */}
            <span style={styles.number}>{unit.label}</span>
            {"\u00a0"}
            {unit.text}
          </p>
        ))}
      </div>

      {last > 0 ? (
        <p style={styles.nav}>
          <button
            type="button"
            onClick={() => setCursor((c) => clampCursor(c - PAGE_SIZE, chapter.units))}
            disabled={cursor <= 0}
            style={{ ...styles.step, ...(cursor <= 0 ? styles.stepOff : null) }}
          >
            이전
          </button>
          <span style={styles.divider} />
          <button
            type="button"
            onClick={() => setCursor((c) => clampCursor(c + PAGE_SIZE, chapter.units))}
            disabled={cursor >= last}
            style={{ ...styles.step, ...(cursor >= last ? styles.stepOff : null) }}
          >
            다음
          </button>
        </p>
      ) : null}
    </section>
  );
}

/**
 * 받는 중. **스켈레톤이나 스피너를 두지 않는다.**
 * 장 파일은 중앙값 1.2KB(gzip)라 대개 한 프레임에 끝난다. 그 자리에
 * 로딩 장식을 넣으면 없어도 될 깜빡임만 생긴다.
 */
function Loading() {
  return <p style={styles.quiet}>본문을 가져오는 중이에요.</p>;
}

/**
 * 못 받았을 때 — **실패로 말하지 않는다.**
 *
 * 이 앱에서 없는 것은 늘 문장으로 말한다(VideoList의 EmptySide, 위기 화면의
 * 영상 자리). 그 문장들이 공통으로 지키는 것은 "사용자가 무엇을 잘못한 것도,
 * 앱이 고장 난 것도 아니다"이다.
 *
 * ⚠ 여기서 특히 조심할 것: 구절 화면 자체는 번들이라 멀쩡하다. 이 탭 하나가
 *   못 열린 것뿐인데 "오프라인입니다" 같은 문장을 쓰면 앱 전체가 죽은 것처럼
 *   읽힌다. 그래서 주어를 본문으로 두고("본문을 못 불러왔어요"), 되돌아갈
 *   자리가 있다는 것을 함께 말한다. 재시도 여지를 남기되 재시도 버튼은 두지
 *   않는다 — 누르는 순간 성공/실패가 다시 판정되고, 그러면 이 자리가
 *   상태 설명이 아니라 조작 화면이 된다.
 */
function Unavailable() {
  return (
    <p style={styles.quiet}>
      지금은 본문을 못 불러왔어요. 잠시 뒤에 다시 열면 보일 거예요.
    </p>
  );
}

const styles = {
  wrap: { margin: "0 0 30px" },
  head: {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    margin: "0 0 18px",
  },
  title: { color: T.sand, fontFamily: SERIF, fontSize: 13.5 },
  progress: { color: "#ffffff33", fontSize: 11.5 },
  body: { margin: 0 },
  verse: {
    margin: "0 0 14px",
    fontFamily: SERIF,
    fontSize: TEXT_SIZE,
    lineHeight: LINE_HEIGHT,
    color: T.mist,
    wordBreak: "keep-all",
  },
  number: {
    marginRight: 4,
    color: T.sand,
    fontFamily: SERIF,
    fontSize: 11.5,
  },
  nav: {
    display: "flex",
    alignItems: "center",
    margin: "22px 0 0",
  },
  step: {
    padding: 0,
    background: "none",
    border: "none",
    color: T.muted,
    fontSize: 12.5,
    fontFamily: "inherit",
    cursor: "pointer",
    // ⚠ 단축 속성(borderBottom)을 쓰지 않는다 — 2026-08-19 결함과 같은 자리다.
    //   단축으로 색을 깔고 다른 상태에서 borderBottomColor만 얹으면, 상태가
    //   돌아올 때 React가 개별 속성만 지운다. 그 자리가 원래 색으로 되살아나지
    //   않고 불투명 검정으로 해석돼 **꺼진 버튼에 검은 밑줄**이 남는다.
    //   양쪽 상태가 항상 같은 개별 속성을 지정하면 값이 교체되기만 한다.
    //   (MediaToggle에서 같은 실수를 한 번 했다 — ResultTabs.jsx 주석 참조)
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: "#ffffff26",
    lineHeight: 1.4,
  },
  // 장 끝에서는 끈다. 형식 토글과 달리 여기서 disabled가 맞는 이유는,
  // 이 버튼이 약속하는 것이 "형식 전환"이 아니라 "그 방향으로 더 있다"이기
  // 때문이다. 더 없는데 눌리면 그것이 고장으로 읽힌다.
  stepOff: {
    color: "#ffffff26",
    borderBottomColor: "transparent",
    cursor: "default",
  },
  divider: { width: 1, height: 11, background: "#ffffff1f", margin: "0 14px" },
  quiet: {
    margin: "0 0 30px",
    color: T.muted,
    fontSize: 14,
    lineHeight: 1.75,
  },
};
