/**
 * PYM 앱 — 감정 입력 → 구절 → 영상.
 *
 * FYM 앱의 흐름(입력·분류·로딩·결과)을 그대로 쓰되 결과 화면이 다르다.
 * FYM은 감정 다음이 영상이지만 PYM은 **구절이 먼저**다.
 *
 *   공감 문구 → 구절 카드 → [말씀]/[찬양] 토글 → 영상(주제분 → 폴백) → 마무리
 *
 * 한 화면에 세로로 놓고 첫 화면에는 구절까지만 보이게 한다. 탭을 늘리지 않으면서
 * 구절이 주인공인 구성이다.
 *
 * [바꾸지 않은 것 — FYM에서 검증된 값]
 *   로딩 최소 노출 1000ms. 즉답은 기계적으로 느껴지고, 짧은 뜸이 "듣고 있다"는
 *   감각을 만든다. 800ms와 비교해 1000ms가 더 차분하게 읽혀 확정된 값이며,
 *   prefers-reduced-motion에서도 지연은 유지한다 — 끄는 건 애니메이션이지 뜸이 아니다.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import taxonomy from "./data/taxonomy.json";
import versesData from "./data/verses.json";

import { RESULT, classify, findSubcategory, subcategoriesOf } from "./lib/classify.js";
import { FLOW, MODE, PHASE, flowReducer, initialFlow } from "./lib/flow.js";
import { KEYS, getSetting, setSetting } from "./lib/db.js";
import { usePrefersReducedMotion, withMinDuration } from "./lib/offline.js";
import {
  loadMessageIndexes,
  pickMessage,
  greetingSlot,
  recordVisit,
  revisitSlot,
  sameDayGreetingPool,
} from "./lib/messages.js";
import { loadInitialData, shouldCheck, syncInBackground } from "./lib/sync.js";
import { listenForTaps, readSettings, refreshSchedule, setEnabled } from "./lib/notify.js";
import {
  CRISIS_POOL_KEY,
  attributionOf,
  crisisVerses,
  isUsableVerses,
  lastVerseId,
  loadVerseHistory,
  nextVerse,
  pickVerse,
  rememberVerse,
  versesFor,
} from "./lib/verses.js";
import {
  MEDIA,
  getCrisisVideos,
  layersFor,
  screenFor,
  shuffleThemeLayer,
  toggleCounts,
} from "./lib/videos.js";

import { ChapterReader } from "./components/ChapterReader.jsx";
import {
  Closing,
  FLOATING_BOTTOM,
  FLOATING_HEIGHT,
  FloatingBack,
  FloatingRestart,
  Msg,
} from "./components/common.jsx";
import { CrisisScreen } from "./components/CrisisScreen.jsx";
import { READING, ResultTabs } from "./components/ResultTabs.jsx";
import { VerseCard, verseFontSize } from "./components/VerseCard.jsx";
import { VideoList } from "./components/VideoList.jsx";
import { ABOUT_BACK_ID, About } from "./components/About.jsx";
import { bannerLift, bannerSpace, bannerVisible, currentScreen } from "./lib/adsApp.js";
import { setBannerShown, watchBannerFill } from "./lib/bannerNative.js";
import { DailyVerse } from "./components/DailyVerse.jsx";
import { T, SERIF } from "./theme.js";

const MIN_DURATION_MS = taxonomy.ui.loading.min_duration_ms;
/**
 * 공감 문구 크기 — **구절보다 항상 작다.**
 *
 * 15.5px은 PC에서 작아 보였다. 실측(360·420·1280px)에서 15.5~18px은 줄 수가
 * 전부 같아 — 공감 문구는 짧아서 크기를 키워도 레이아웃이 흔들리지 않는다.
 * 즉 이 값은 레이아웃 제약이 아니라 **위계**로 정한다.
 *
 * 그런데 구절 본문이 길이에 따라 크기가 변한다(VerseCard의 SIZE_STEPS).
 * 공감 문구를 고정값으로 두면 가장 작은 구절 구간에서 **공감 문구가 구절보다
 * 커질 수 있다** — 구절이 주인공이라는 위계가 뒤집힌다.
 * 그래서 상한 17.5를 두되 구절 크기에 연동시킨다. min()이 그 안전장치다.
 *
 *   [2026-08-19 구절이 22/20/18로 커진 뒤]
 *   구절 22px (66%) → 공감 17.5px   구절 20px (28%) → 공감 17.5px
 *   구절 18px  (6%) → 공감 17.5px
 *
 * 지금은 세 구간 모두 상한 17.5px에 걸린다. 구절 최소 크기가 18px이라
 * 18 - 0.5 = 17.5가 상한과 같아졌기 때문이다. **연동을 지우지 말 것** —
 * 구절 크기를 다시 낮추면(예: 상한 구간 16.5px) 그 순간 다시 필요해진다.
 *
 * 구절 18px일 때 크기 차이는 0.5px로 작다. 그래도 위계가 유지되는 것은 크기만이
 * 근거가 아니기 때문이다 — 구절은 mist(밝은 색)에 화면 위쪽이고, 공감 문구는
 * muted(흐린 색)에 그 아래다. 세 신호가 같은 방향을 가리킨다.
 */
const EMPATHY_MAX = 17.5;
function empathyFontSize(verseText) {
  return Math.min(EMPATHY_MAX, verseFontSize(verseText) - 0.5);
}

export default function App() {
  // 화면 이동은 전부 lib/flow.js가 정한다 — 입력창을 비우는 규칙이 그 안에 있다.
  // ⚠ 여기서 setText 같은 낱개 세터를 다시 만들지 말 것. 경로가 갈리면
  //   2026-08-28에 고친 결함(대분류 되묻기에서 글자가 남는 것)이 그대로 돌아온다.
  const [flow, dispatch] = useReducer(flowReducer, taxonomy.ui.placeholders[0], initialFlow);
  const { phase, mode, text, result, selectedCategory, placeholder } = flow;
  const [loadingMessage, setLoadingMessage] = useState(taxonomy.ui.loading.messages[0]);
  const [greeting, setGreeting] = useState("");
  const [showAbout, setShowAbout] = useState(false);
  // 알림을 탭해서 들어온 구절. 있으면 그 화면이 다른 모든 것보다 먼저다.
  const [dailyVerse, setDailyVerse] = useState(null);
  const reducedMotion = usePrefersReducedMotion();

  const [data, setData] = useState(null);
  const dataRef = useRef(null);

  // 화면이 바뀌면 항상 맨 위에서 시작한다 (FYM과 같은 이유).
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [phase, mode, selectedCategory, result, showAbout, dailyVerse]);

  /**
   * 고정 띠배너 — **판단은 adsApp.js가 하고 여기서는 그것을 따르기만 한다.**
   *
   * ⛔ 기본이 숨김이다. "화면을 떠날 때 숨긴다"로 짜면 브리지 왕복 지연 동안
   *   띠가 남고, 고정 띠는 화면이 바뀌어도 자리를 지키므로 그 한 프레임이
   *   실제 노출이다. 그래서 **허용 화면일 때만 보인다**(HANDOFF 2.96 ②).
   * ⚠ 콜드 스타트도 이것으로 풀린다 — 알림을 탭해 앱이 처음 뜰 때 첫 화면이
   *   DailyVerse다. 기본이 숨김이면 배너를 아예 만들지 않는다.
   */
  const [bannerFilled, setBannerFilled] = useState(false);
  const screen = currentScreen({
    dailyVerse,
    showAbout,
    phase,
    resultKind: result?.kind,
  });
  // ★ 인셋을 읽을 수 있으면 배경면이 그만큼 커져 배너를 담는다 (HANDOFF 2.112).
  //   못 읽으면(갈래 B) bannerSpace가 상한을 가정한다 — 판정은 그 함수 안에 있다.
  const safeAreaBottom = useSafeAreaBottom();
  // ★ 네이티브가 넣어 주는 **참 인셋**(2.118 안 2). 오면 배경면이 대칭이 되고
  //   갈래 구분이 사라진다. 안 오면 bannerSpace가 옛 비대칭식으로 떨어진다.
  const insetBottomReal = useInsetBottomReal();
  const bandHeight = bannerSpace({
    screen,
    filled: bannerFilled,
    safeAreaBottom,
    insetBottomReal,
  });
  // 배경면을 웹 바닥에서 띄우는 양. 배너 아래에 여백을 만드는 것이 이 값이다.
  const bandLift = bannerLift({ screen, filled: bannerFilled, insetBottomReal });
  /**
   * ⚠ 문서와 떠 있는 버튼이 비켜야 하는 높이는 **배경면 높이 + 띄운 양**이다.
   *   배경면이 바닥에서 떠 있으므로 둘을 더해야 그 위에 선다.
   */
  const bottomInset = bandHeight + bandLift;

  const [notifyOn, setNotifyOn] = useState(false);
  const [toast, setToast] = useState("");
  useEffect(() => {
    let alive = true;
    readSettings().then((s) => alive && setNotifyOn(s.on));
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(() => setToast(""), TOAST_MS);
    return () => clearTimeout(id);
  }, [toast]);
  /**
   * 결과 화면 토글 — About 토글과 **같은 함수**를 쓴다 (2.119).
   *
   * ⛔ 토스트는 setEnabled가 true를 돌려준 **뒤에만** 띄운다.
   *   그 promise는 시스템 권한 팝업이 닫혀야 끝나므로 팝업 위에 뜰 수 없다.
   *   거부면 false라 안 뜬다. ⛔ 끌 때도 안 띄운다.
   */
  const toggleNotify = async () => {
    const next = !notifyOn;
    setNotifyOn(next);
    const ok = await setEnabled(next);
    if (next && !ok) {
      setNotifyOn(false); // 권한을 못 받았다. 되돌린다
      return;
    }
    if (next && ok) setToast(TOAST_TEXT);
  };
  const notify = { on: notifyOn, onToggle: toggleNotify };

  useEffect(() => {
    setBannerShown(bannerVisible(screen));
  }, [screen]);

  useEffect(() => {
    let alive = true;
    let release = () => {};
    (async () => {
      const off = await watchBannerFill((filled) => {
        if (alive) setBannerFilled(filled);
      });
      if (alive) release = off;
      else off();
    })();
    return () => {
      alive = false;
      release();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await Promise.all([loadMessageIndexes(), loadVerseHistory()]);
      const [{ data: initial }, visit] = await Promise.all([
        loadInitialData(),
        recordVisit(),
      ]);
      if (cancelled) return;

      dataRef.current = initial;
      setData(initial);
      dispatch({
        type: FLOW.PLACEHOLDER,
        placeholder: pickMessage("placeholder", taxonomy.ui.placeholders),
      });
      setGreeting(pickGreeting(visit));

      if (await shouldCheck()) {
        // UI를 막지 않는다. 갱신이 끝나도 보고 있는 화면은 바꾸지 않는다.
        syncInBackground(initial?.version ?? null).then((outcome) => {
          if (!cancelled && outcome.updated && outcome.data) {
            dataRef.current = outcome.data;
          }
        });
      }

      // 구절 알림 — 14일치를 다시 채운다.
      // ⚠ 앱을 열 때가 유일한 시점이다. 크론도 백그라운드 실행도 없다.
      //   그래서 14일간 안 열면 알림이 멎는다 — 떠난 사람을 계속 부르지 않는
      //   것이 맞다고 판단했다(notify.js 머리말).
      // ⛔ 여기서 권한을 묻지 않는다. 토글이 묻는 자리다.
      refreshSchedule().catch(() => {});
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * 알림을 탭해서 들어온 경우 — 그 구절 화면을 연다.
   *
   * 리스너를 앱 시작에 건다. 앱이 죽어 있다가 알림으로 깨어난 경우에도
   * 브리지가 준비된 뒤 이 이벤트가 오기 때문이다.
   */
  useEffect(() => {
    let stop = () => {};
    listenForTaps((verseId) => {
      const found = (versesData.verses || []).find((v) => v.id === verseId);
      if (found) setDailyVerse(found);
    }).then((off) => {
      stop = off;
    });
    return () => stop();
  }, []);

  /**
   * 분류 결과를 화면에 붙인다.
   *
   * ⚠ **대분류까지만 맞은 경우도 여기를 지난다.** 그 경로는 결과 화면을 거치지
   *   않고 곧장 고르는 화면으로 되묻는데, 2026-08-28 전에는 화면만 바꾸고
   *   입력창을 비우지 않았다 — '다시 적기'로 돌아오면 친 글자가 그대로였다.
   *   무엇을 비울지는 flowReducer가 정한다(lib/flow.js). 여기서 분기하지 말 것.
   */
  const show = useCallback((outcome) => {
    if (outcome.kind !== RESULT.CATEGORY) setData(dataRef.current);
    dispatch({
      type: FLOW.ANSWER,
      outcome,
      category:
        outcome.kind === RESULT.CATEGORY
          ? taxonomy.categories.find((c) => c.id === outcome.category.id)
          : null,
      placeholder: pickMessage("placeholder", taxonomy.ui.placeholders),
    });
  }, []);

  const run = useCallback(
    async (input) => {
      dispatch({ type: FLOW.SUBMIT });
      setLoadingMessage(pickMessage("loading", taxonomy.ui.loading.messages));
      // 분류는 수십 ms에 끝난다. 최소 노출 시간을 두는 것이 요점이다.
      // withMinDuration은 **함수**를 받는다 (프라미스가 아니다) — 시작 시각을
      // 자기가 재야 최소 노출을 정확히 계산할 수 있기 때문이다.
      const outcome = await withMinDuration(
        () => classify(input, taxonomy),
        MIN_DURATION_MS,
      );
      show(outcome);
    },
    [show],
  );

  const chooseSubcategory = useCallback(
    (subcategoryId) => {
      const found = findSubcategory(taxonomy, subcategoryId);
      if (!found) return;
      void setSetting(KEYS.LAST_SUBCATEGORY_ID, subcategoryId);
      show({ kind: RESULT.OK, ...found });
    },
    [show],
  );

  /**
   * 입력 화면으로 되돌린다. 비우는 규칙은 flowReducer가 갖는다(lib/flow.js).
   *
   * ⚠ 인자를 받지 않는다. Msg·Closing이 `onClick={onBack}`으로 넘기므로
   *   **클릭 이벤트가 첫 인자로 들어온다.** 목적지를 인자로 받는 함수 하나로
   *   두면 그 자리에 이벤트 객체가 앉는다. 그래서 목적지별로 나눈다.
   */
  const goInput = useCallback(
    (type) =>
      dispatch({
        type,
        placeholder: pickMessage("placeholder", taxonomy.ui.placeholders),
      }),
    [],
  );
  const reset = useCallback(() => goInput(FLOW.RESET), [goInput]);
  /** 분류 실패에서 나가는 길 — 고르는 화면으로 간다. 비우는 것은 위와 같다. */
  const resetToPicker = useCallback(() => goInput(FLOW.RESET_TO_PICKER), [goInput]);

  /**
   * 알림 화면 — **다른 모든 분기보다 먼저다.**
   *
   * 알림을 탭해서 들어온 사람이 보고 싶은 것은 그 구절이지, 지난번에 보던
   * 결과 화면이 아니다. 나가는 길은 "지금 마음을 적어볼까요" 하나뿐이고
   * 그것이 입력 화면으로 보낸다 — 알림이 입구가 되게 하는 문이다.
   * ⛔ 떠 있는 버튼(onRestart)을 주지 않는다. 돌아갈 "이전 화면"이 없다.
   */
  if (dailyVerse) {
    return (
      <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast}>
        <DailyVerse
          verse={dailyVerse}
          onWrite={() => {
            setDailyVerse(null);
            reset();
          }}
        />
      </Shell>
    );
  }

  if (showAbout) {
    // 떠 있는 버튼과 하단 버튼이 **같은 함수**를 쓴다. 복귀 경로가 둘로
    // 갈리면 한쪽만 고쳐지는 날이 온다.
    const closeAbout = () => setShowAbout(false);
    return (
      <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast} onAboutBack={closeAbout} reducedMotion={reducedMotion}>
        <About attribution={attributionOf(versesData)} onBack={closeAbout} />
      </Shell>
    );
  }

  if (phase === PHASE.LOADING) {
    return (
      <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast}>
        <div style={styles.loadingWrap}>
          {/* 호흡 애니메이션이 한 사이클 도는 동안 기다린다. reduced-motion에서는
              애니메이션만 꺼지고 지연(1000ms)은 유지된다 — 뜸은 시간에서 나온다. */}
          <div className="orb" style={styles.orb} />
          <p style={styles.loadingText}>{loadingMessage}</p>
        </div>
      </Shell>
    );
  }

  if (phase === PHASE.RESULT && result) {
    if (result.kind === RESULT.CRISIS) {
      return (
        <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast} onRestart={reset} reducedMotion={reducedMotion}>
          <Crisis data={data} onBack={reset} />
        </Shell>
      );
    }
    if (result.kind === RESULT.OK) {
      return (
        <Shell
          bottomInset={bottomInset}
          band={{ h: bandHeight, lift: bandLift }}
          toast={toast}
          onAbout={() => setShowAbout(true)}
          onRestart={reset}
          reducedMotion={reducedMotion}
        >
          <Result result={result} data={data} onBack={reset} notify={notify} />
        </Shell>
      );
    }
    if (result.kind === RESULT.EMPTY) {
      return (
        <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast}>
          <Msg
            title={taxonomy.ui.empty_input[0]}
            sub={taxonomy.ui.empty_input[1] || ""}
            onBack={reset}
            back="골라서 찾기"
          />
        </Shell>
      );
    }
    return (
      <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast}>
        <Msg
          title={taxonomy.ui.no_match[0]}
          sub={taxonomy.ui.no_match[1] || ""}
          onBack={resetToPicker}
          back="골라서 찾기"
          onAlt={reset}
          alt="다시 적기"
        />
      </Shell>
    );
  }

  return (
    <Shell bottomInset={bottomInset} band={{ h: bandHeight, lift: bandLift }} toast={toast} onAbout={() => setShowAbout(true)}>
      <Input
        mode={mode}
        text={text}
        placeholder={placeholder}
        greeting={greeting}
        selectedCategory={selectedCategory}
        onType={(value) => dispatch({ type: FLOW.TYPE, text: value })}
        onSwitchToPicker={() => dispatch({ type: FLOW.SWITCH_TO_PICKER })}
        onPickCategory={(category) => dispatch({ type: FLOW.PICK_CATEGORY, category })}
        onStepBack={() => dispatch({ type: FLOW.BACK })}
        onSubmit={run}
        onChoose={chooseSubcategory}
      />
    </Shell>
  );
}

/** 결과 화면 — 공감 문구 → 구절 → 토글 → 영상(2층) → 마무리 */
function Result({ result, data, onBack, notify }) {
  const subcategory = result.subcategory;
  const pool = useMemo(() => versesFor(versesData, subcategory.id), [subcategory.id]);
  const [verse, setVerse] = useState(() =>
    pickVerse(pool, lastVerseId(subcategory.id)),
  );
  const [mediaType, setMediaType] = useState(
    () => taxonomy.media_defaults[subcategory.id] || MEDIA.WORSHIP,
  );
  /**
   * 지금 보고 있는 것 — 영상인가 본문인가.
   *
   * ★ **mediaType의 세 번째 값으로 만들지 않는다.** mediaType은 IndexedDB에
   *   영속되므로(아래 effect), 이어서 읽기가 그 값이 되면 다음 방문에 결과
   *   화면이 영상 없이 본문부터 열린다. 그리고 개인정보처리방침 문안이
   *   전제하는 "마지막으로 고른 형식"의 뜻이 조용히 바뀐다.
   *
   *   그래서 상태를 둘로 둔다. 이어서 읽기를 눌러도 mediaType은 그대로이고,
   *   말씀/찬양으로 돌아오면 원래 고르던 형식이 살아 있다.
   *   pane은 저장하지 않는다 — **이 기능은 기기에 남기는 것을 늘리지 않는다.**
   */
  const [pane, setPane] = useState("videos");

  // 지금 보여준 구절을 기억한다 — 다음 방문에서 이것만 빼고 뽑는다.
  // 첫 선택과 "다른 구절" 양쪽이 verse를 바꾸므로 effect 하나로 둘 다 덮는다.
  useEffect(() => {
    if (verse?.id) rememberVerse(subcategory.id, verse.id);
  }, [subcategory.id, verse?.id]);

  // 마지막으로 고른 형식을 기억한다 — 기본값이 안 맞는 사용자가 매번 누르지 않게.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await getSetting(KEYS.MEDIA_TYPE, null);
      if (!cancelled && stored && stored[subcategory.id]) {
        setMediaType(stored[subcategory.id]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subcategory.id]);

  const empathy = useMemo(
    () => pickMessage(`empathy:${subcategory.id}`, subcategory.empathy_messages),
    [subcategory.id],
  );
  const closing = useMemo(
    () => pickMessage(`closing:${subcategory.id}`, subcategory.closing_messages),
    [subcategory.id],
  );

  const screen = screenFor(data, subcategory.id);
  const videos = screen?.videos ?? [];
  const counts = toggleCounts(videos);

  /**
   * 주제분 섞기 씨앗 — **이 화면이 뜰 때 한 번만** 뽑는다 (2026-08-28 결정).
   *
   * 배치가 주는 주제분 순서는 채널 묶음이라(lib/videos.js shuffleThemeLayer 주석)
   * 한 채널이 연속 3건씩 붙어 나온다. 개별 영상 단위로 섞어 그것을 흩는다.
   *
   * ⛔ 씨앗을 렌더마다 새로 뽑으면 안 된다. useState 초기화 함수라 **마운트당
   *   한 번**만 실행된다 — 그래서 스크롤·탭 전환에 순서가 흔들리지 않는다.
   *   섞기 자체도 씨앗에 대해 순수 함수라 몇 번을 다시 계산해도 결과가 같다.
   * ★ 감정을 다시 입력하면 App이 result를 null로 되돌려 이 컴포넌트가 사라졌다
   *   다시 뜬다. 그때 새 씨앗을 받는다 — 그것이 "다시 입력하면 새로 섞인다"다.
   */
  const [shuffleSeed] = useState(() => Math.floor(Math.random() * 0x100000000));
  const layers = useMemo(() => {
    const split = layersFor(videos, mediaType);
    // 폴백은 섞지 않는다 — 배치가 전체 최신순으로 주고 헤더가 그 순서를 약속한다
    return { ...split, theme: shuffleThemeLayer(split.theme, shuffleSeed) };
  }, [videos, mediaType, shuffleSeed]);

  /**
   * 탭 하나가 두 가지 일을 한다 — 본문으로 가거나, 영상 형식을 고르거나.
   * 형식을 고를 때만 기억한다. 본문 탭은 아무것도 남기지 않는다.
   */
  const chooseTab = (next) => {
    if (next === READING) {
      setPane("reading");
      return;
    }
    setPane("videos");
    setMediaType(next);
    void (async () => {
      const stored = (await getSetting(KEYS.MEDIA_TYPE, {})) || {};
      await setSetting(KEYS.MEDIA_TYPE, { ...stored, [subcategory.id]: next });
    })();
  };

  return (
    <div className="rise">
      {/* 구절이 먼저다. 공감 문구는 구절과 영상 사이의 다리 역할을 한다 —
          화면의 첫 인상을 말씀이 갖고, 그다음 문장이 그것을 지금 감정에
          이어 붙인 뒤, 영상으로 넘어간다.

          [“다른 구절”은 구절만 바꾼다 — 공감 문구는 그대로다. 2026-08-19 확정]
            empathy가 [subcategory.id]에만 memo돼 있어 구절을 넘겨도 문장이
            유지된다. 우연이 아니라 이대로 두는 것이 맞다.
              1. 공감 문구는 **감정**에 답한 문장이지 구절에 딸린 문장이 아니다.
                 구절을 넘겼다고 다시 뽑으면 "앱이 내 마음을 다시 읽었다"는
                 신호가 되는데, 사용자의 감정은 그대로다.
              2. 버튼이 약속한 것은 "다른 구절"이지 "다시 뽑기"가 아니다.
                 이름이 말하지 않은 것까지 바꾸면 버튼을 믿을 수 없게 된다.
              3. 구절 바로 아래 문장이라, 같이 바뀌면 화면이 리셋된 것처럼
                 읽혀 "같은 자리에서 구절만 넘긴다"는 감각이 깨진다.
            ⚠ 크기는 연동된다(empathyFontSize) — 그건 위계를 지키는 장치이지
              내용 연동이 아니다. 둘을 같은 것으로 보고 묶지 말 것. */}
      <VerseCard
        verse={verse}
        canRotate={pool.length > 1}
        onNext={() => setVerse(nextVerse(pool, verse?.id))}
      />

      <p style={{ ...styles.empathy, fontSize: empathyFontSize(verse?.text) }}>
        {empathy}
      </p>

      <ResultTabs
        value={pane === "reading" ? READING : mediaType}
        counts={counts}
        onChange={chooseTab}
        notify={notify}
      />
      {/* [완전 연동 — key 하나가 그 일을 전부 한다. 2026-08-20 결정 A]
            "다른 구절"을 누르면 verse.id가 바뀌고, key가 바뀌면 React가
            컴포넌트를 새로 마운트한다. 읽던 위치가 그 자리에서 사라지고
            새 구절의 장이 열린다 — **연동을 위한 코드가 따로 없다.**
            느슨한 연동(위치를 유지하는 쪽)은 검토하지 않았다. 상태가 둘로
            갈려 "지금 보는 본문이 위 구절과 같은 장인가"를 화면이 늘
            설명해야 하고, 그 비용이 얻는 것보다 크다.

          ⚠ 탭 선택(pane)은 리셋하지 않는다. 본문을 보던 사람이 "다른 구절"을
            누르면 같은 자리에 새 장 머리("시편 42편")가 뜨므로, 무엇이
            바뀌었는지 화면이 스스로 설명한다.

          ⚠ read가 없으면 그리지 않는다. 위기 구절에는 read가 없고(생성기가
            붙이지 않는다), 이 화면은 위기 경로를 타지 않지만 — 데이터가
            없을 때 조용히 비는 쪽이 옳다. */}
      {pane === "reading" && verse?.read ? (
        <ChapterReader key={verse.id} read={verse.read} />
      ) : (
        <VideoList
          layers={layers}
          mediaType={mediaType}
          otherCount={
            mediaType === MEDIA.SERMON ? counts[MEDIA.WORSHIP] : counts[MEDIA.SERMON]
          }
        />
      )}

      <Closing text={closing} onBack={onBack} />
    </div>
  );
}

/** 위기 화면 — 구절도 영상도 별도 풀에서 온다 */
function Crisis({ data, onBack }) {
  const response = taxonomy.safety.crisis_response;
  const verse = useMemo(
    () => pickVerse(crisisVerses(versesData), lastVerseId(CRISIS_POOL_KEY)),
    [],
  );
  const videos = useMemo(() => getCrisisVideos(data), [data]);

  // 위기 풀도 10건이라 반복이 눈에 띈다. 감정 화면과 같은 규칙을 쓴다.
  useEffect(() => {
    if (verse?.id) rememberVerse(CRISIS_POOL_KEY, verse.id);
  }, [verse?.id]);
  const closing = useMemo(
    () => pickMessage("closing:crisis", response.closing_messages),
    [response.closing_messages],
  );
  return (
    <CrisisScreen
      response={response}
      verse={verse}
      videos={videos}
      closing={closing}
      onBack={onBack}
    />
  );
}

/**
 * 입력 화면 — 텍스트 모드와 선택 모드가 **같은 헤더를 공유한다.**
 *
 * [2026-08-19] 배치를 FYM 구조로 맞췄다. 색·문구가 아니라 배치 문제였다.
 *   ① 배경  헤드라인 뒤 radial glow(orb). 균일한 어둠에는 시선이 모이는 지점이
 *            없다. 이 glow가 후광 역할을 해서 첫 문장을 붙든다
 *   ② 정렬  헤더는 중앙 정렬. 좌측 정렬이면 인사가 질문이 아니라 **입력 필드
 *            라벨**처럼 읽힌다 — 실제로 "지금은 어떤 마음인가요?"는 라벨이 아니라
 *            재방문 인사 풀(same_day)의 한 문장이다
 *   ③ 수직  height 150의 헤더 블록이 위 여백을 만든다
 *   ④ 캡션  자간 넓은 작은 글씨가 헤드라인 위에 있어야 헤드라인이 무거워진다
 *
 * [헤더가 모드 분기 **바깥**에 있는 것이 핵심이다 — 2026-08-19 [A]]
 *   처음에는 선택 모드가 헤더 없이 질문만 그렸다. 그러면 "골라서 찾을래요"를
 *   누른 순간 캡션·인사·glow가 통째로 사라져 **다른 화면으로 넘어간 것처럼**
 *   보인다. 실제로는 같은 화면에서 입력 방식만 바꾼 것인데도 그렇다.
 *   FYM은 헤더를 ternary 밖에 두어 이 문제가 없다. 같은 구조로 맞췄다.
 *
 *   React가 같은 위치의 같은 엘리먼트로 조정하므로 헤더 DOM이 유지되고,
 *   .rise 애니메이션도 다시 돌지 않는다 — 전환이 "바뀌는" 것이 아니라
 *   "아래쪽만 갈리는" 것으로 보이는 이유다. **분기 안으로 옮기지 말 것.**
 */
function Input({
  mode,
  text,
  placeholder,
  greeting,
  selectedCategory,
  onType,
  onSwitchToPicker,
  onPickCategory,
  onStepBack,
  onSubmit,
  onChoose,
}) {
  return (
    <div className="rise">
      <div style={styles.hero}>
        <div className="orb" style={styles.heroGlow} />
        <div style={styles.heroText}>
          <div style={styles.heroCaption}>오늘의 마음</div>
          <div style={styles.greeting}>{greeting}</div>
        </div>
      </div>

      {mode === MODE.SELECT ? (
        <SelectMode
          selectedCategory={selectedCategory}
          onPickCategory={onPickCategory}
          onStepBack={onStepBack}
          onChoose={onChoose}
        />
      ) : (
        <TextMode
          text={text}
          onType={onType}
          placeholder={placeholder}
          onSwitchToPicker={onSwitchToPicker}
          onSubmit={onSubmit}
        />
      )}
    </div>
  );
}

/**
 * 키보드가 올라오면 입력란을 화면 가운데로 끌어온다 (2026-09-02 · HANDOFF 2.107).
 *
 * [무엇이 문제였나 — 크기가 아니라 스크롤이었다]
 *   키보드가 뜨면 뷰포트는 **줄어든다**(실측 592 → 341dp). 그런데 브라우저가
 *   스크롤을 하지 않아 「마음 들여다보기」가 잘리고 「골라서 찾을래요」는 아예 밖으로 나갔다.
 *   ⛔ 브라우저 기본 동작은 **포커스된 요소**만 보이게 한다. 그 요소는 입력란이고
 *     입력란은 이미 보인다(bottom 294 < 341) — 그래서 스크롤할 이유가 없다.
 *     가려지는 것은 그 **아래 버튼**이고 버튼은 포커스 대상이 아니다.
 *
 * [⚠⚠ 타이밍이 요점이다 — focus에 걸면 안 된다]
 *   focus가 오는 시점에는 뷰포트가 **아직 592다.** 그때는 셋이 다 보이므로
 *   스크롤할 것이 없다. 줄어든 **뒤에** 해야 하고, 그래서 resize를 듣는다.
 *
 * [무엇을 듣는가 — visualViewport와 window를 **둘 다** 듣는다]
 *   실측(갈래 B)   innerHeight 592→341 · visualViewport.height 592→341. **둘 다 온다**
 *   갈래 A 예측    Capacitor가 웹뷰 부모에 setPadding(0,0,0,imeInsets.bottom)을 준다.
 *                그 패딩이 웹뷰를 줄이는 기전이고(실측: 부모 [0,0,1080,1920]는 그대로인데
 *                웹뷰만 [0,72][1080,1095]로 줄었다), 갈래 A도 **같은 값**을 쓴다
 *                → 640 → 365dp로 줄 것이다. 역시 둘 다 온다
 *   ★ 그래도 둘을 다 듣는 이유는 **레이아웃은 그대로인데 IME가 덮기만 하는** 구성이
 *     있을 수 있기 때문이다. 그때는 visualViewport만 줄어든다.
 *     하단에서 세운 기준과 같다 — 시험할 수 없는 갈래가 있으면 넓게 잡는다.
 *   ⚠ 먼저 온 쪽이 prev를 갱신하므로 뒤에 온 쪽은 축소량 0으로 보고 아무것도 안 한다.
 *
 * [⛔ 이 훅이 못 하는 것 — 뷰포트가 안 줄면 아무것도 못 한다]
 *   웹은 키보드를 직접 볼 수 없다. **뷰포트가 줄어드는 것으로만 안다.**
 *   실제로 줄지 않는 구성을 둘 봤다 —
 *     · insetsHandling "disable" (2.105 실험): 640 고정
 *     · 에뮬레이터의 스타일러스 필기 모드: 592 고정
 *   그런 자리에서는 이 훅이 **조용히 아무 일도 하지 않는다.** 증상은 지금과 같아진다.
 *   ⛔ 그것을 웹에서 고칠 방법이 없다. 한계로 적어 둔다.
 */
/**
 * 하단 시스템 인셋을 **웹이 읽을 수 있으면** 읽는다 (2026-09-02 · HANDOFF 2.112).
 *
 * [★ 이 값이 갈래를 가른다]
 *   갈래 A(WebView ≥140 + viewport-fit=cover)  Capacitor가 실제 인셋을 넘긴다.
 *     태블릿 실측 — env/변수 둘 다 **48px**(하단 taskbar), 상단 24px
 *   갈래 B(WebView <140)  Capacitor가 인셋을 **0으로 만들어 주입한다**(2.103 실측).
 *     0이 온다 = "모른다"는 뜻이고, bannerSpace가 그때만 상한(48)을 가정한다
 *
 * ⚠ 둘을 **함께** 본다 — Capacitor가 넣는 CSS 변수와 브라우저의 env()다.
 *   갈래·기기에 따라 한쪽만 채워질 수 있으므로 **큰 쪽**을 쓴다.
 *   ⛔ 0으로 잘못 읽는 것은 안전하다(여백이 넉넉해진다). 반대가 위험하다
 * ⚠ 회전·키보드로 바뀌므로 resize에 다시 읽는다.
 */
function readSafeAreaBottom() {
  if (typeof document === "undefined") return 0;
  let envPx = 0;
  try {
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:absolute;left:-9999px;visibility:hidden;height:env(safe-area-inset-bottom,0px)";
    document.body.appendChild(probe);
    envPx = parseFloat(getComputedStyle(probe).height) || 0;
    probe.remove();
  } catch {
    envPx = 0;
  }
  const varPx =
    parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--safe-area-inset-bottom"),
    ) || 0;
  return Math.max(envPx, varPx, 0);
}

function useSafeAreaBottom() {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const read = () => setValue(readSafeAreaBottom());
    read();
    const vp = window.visualViewport;
    vp?.addEventListener("resize", read);
    window.addEventListener("resize", read);
    window.addEventListener("orientationchange", read);
    return () => {
      vp?.removeEventListener("resize", read);
      window.removeEventListener("resize", read);
      window.removeEventListener("orientationchange", read);
    };
  }, []);
  return value;
}

/**
 * 네이티브가 넣어 주는 **참 하단 인셋**(dp) — 없으면 null이다 (2.118 안 2).
 *
 * ⛔ env(safe-area-inset-bottom)와 **다른 값이다.** env()는 갈래 A에서만 참이고
 *   B·C에서는 0을 준다. 이 변수는 MainActivity가 WindowInsets를 읽어
 *   `--inset-bottom-real`로 넣는다 — 세 갈래에서 모두 참이다.
 * ⚠ **null과 0을 갈라야 한다.** 갈래 C의 참값이 실제로 0이라, "안 왔다"를
 *   0으로 뭉개면 폴백으로 못 떨어진다.
 * ⚠ 회전·멀티윈도우에서 네이티브가 다시 넣으므로 resize에 다시 읽는다.
 */
function readInsetBottomReal() {
  if (typeof document === "undefined") return null;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue("--inset-bottom-real")
    .trim();
  if (!raw) return null;
  const px = parseFloat(raw);
  return Number.isFinite(px) && px >= 0 ? px : null;
}

/**
 * ⛔ 네이티브가 값을 넣은 뒤 쏘는 이벤트 이름. **MainActivity의 JS_EVENT와 짝이다.**
 *   주입은 마운트 뒤에 오므로 이것이 없으면 리액트가 폴백에 머문다 —
 *   실기기에서 배경면이 82가 아니라 122dp로 남는 것으로 드러났다(2026-09-03).
 */
const INSET_EVENT = "pym:inset";

function useInsetBottomReal() {
  const [value, setValue] = useState(() => readInsetBottomReal());
  useEffect(() => {
    const read = () => setValue(readInsetBottomReal());
    read();
    const vp = window.visualViewport;
    window.addEventListener(INSET_EVENT, read);
    vp?.addEventListener("resize", read);
    window.addEventListener("resize", read);
    window.addEventListener("orientationchange", read);
    return () => {
      window.removeEventListener(INSET_EVENT, read);
      vp?.removeEventListener("resize", read);
      window.removeEventListener("resize", read);
      window.removeEventListener("orientationchange", read);
    };
  }, []);
  return value;
}

/**
 * 토글을 켠 직후의 짧은 응답 (2026-09-03 · HANDOFF 2.119).
 *
 * ⛔ **설명이 아니라 응답이다.** 「구절 알림」 다섯 글자로는 무엇을 받는지가
 *   부족한데 탭 행에는 문장을 넣을 자리가 없다. 켠 뒤에 한 번 알린다.
 * ⛔ 시각을 넣지 않는다 — 사용자가 About에서 바꾼다. 「매일」도 넣지 않는다 —
 *   14일 창이 차면 스스로 멎는 설계와 어긋난다.
 *   「정한 시각에」는 **값이 아니라 관계**라 무엇으로 바꿔도 참이다.
 */
const TOAST_TEXT = "정한 시각에 구절 한 절을 보내드릴게요";
const TOAST_MS = 2600;

/**
 * ★ bottom을 **떠 있는 버튼에서 파생시킨다.** 배경면 높이·페이드에서 쌓아
 *   올리면 배경면이 82dp로 바뀔 때 따라가지 못한다.
 */
function toastStyle(bottomInset, reducedMotion) {
  return {
    position: "fixed",
    left: 24,
    right: 24,
    bottom: FLOATING_BOTTOM + bottomInset + FLOATING_HEIGHT + 12,
    padding: "12px 16px",
    borderRadius: 8,
    background: "rgba(20,30,36,.96)",
    border: "1px solid rgba(255,255,255,.10)",
    color: T.mist,
    fontSize: 13,
    lineHeight: 1.5,
    pointerEvents: "none",
    transition: reducedMotion ? "none" : "opacity .24s ease",
  };
}

const KEYBOARD_SHRINK_MIN = 120;

/**
 * 입력란 윗변이 이보다 위로 올라가지 않는다(px). ⛔ **이 하한이 설계의 핵심이다.**
 *
 * [왜 하한이 필요한가]
 *   기준이 "문서를 끝까지 민다"이므로, 문서가 길어지면 그만큼 더 밀린다.
 *   하한이 없으면 어느 날 **입력란이 화면 위로 사라진다** — 그리고 회귀는
 *   레이아웃 값을 못 보므로 **통과하면서 깨진다**(2.107의 한계 그대로).
 * ★ 문서가 길어질 때 밀려나는 것은 **아래쪽 요소이고 입력란이 아니다.**
 *   우선순위를 코드에 박아 두는 값이다.
 */
const MIN_INPUT_TOP = 100;

/**
 * 키보드가 올라오면 화면을 밀어 올려 입력란과 그 아래 요소들을 보이게 한다
 * (2026-09-02 · HANDOFF 2.107 · 2.111).
 *
 * [무엇이 문제였나 — 크기가 아니라 스크롤이었다]
 *   키보드가 뜨면 뷰포트는 **줄어든다**(실측 592 → 341dp). 그런데 브라우저가
 *   스크롤을 하지 않아 아래 요소들이 잘렸다.
 *   ⛔ 브라우저 기본 동작은 **포커스된 요소**만 보이게 한다. 그 요소는 입력란이고
 *     입력란은 이미 보인다 — 그래서 스크롤할 이유가 없다. 가려지는 것은
 *     그 **아래 요소들**이고 그것들은 포커스 대상이 아니다.
 *
 * [⚠⚠ 타이밍이 요점이다 — focus에 걸면 안 된다]
 *   focus가 오는 시점에는 뷰포트가 **아직 592다.** 그때는 다 보이므로 스크롤할
 *   것이 없다. 줄어든 **뒤에** 해야 하고, 그래서 resize를 듣는다.
 *
 * [★ 기준 — "문서를 끝까지 밀되 입력란 하한에서 멈춘다"]
 *   ⛔ **아래쪽 요소에 ref를 달지 않는다.** 「이 앱에 대해」는 Shell이 그리므로
 *     TextMode에서 ref로 잡을 수 없고, 잡으려 하면 구조 결합이 생긴다.
 *     대신 문서 끝을 기준으로 삼으면 **아래에 요소가 추가돼도 자동으로 포함된다.**
 *   ⚠ 이 설계가 **보장하는 것은 입력란 하한 하나뿐이다.**
 *     「이 앱에 대해」가 보이는 것은 보장이 아니라 **지금 레이아웃에서 실측된 결과다**
 *     (스크롤 144에서 [299,318], 뷰포트 341까지 23px 여유).
 *     ⛔ 문서가 **44px 이상 길어지면 다시 밀린다.** 그때 밀리는 것은 입력란이
 *       아니라 그 버튼이고, 그것이 의도한 우선순위다.
 *
 * [무엇을 듣는가 — visualViewport와 window를 **둘 다**]
 *   실측(갈래 B)  innerHeight 592 → 341 · visualViewport.height 592 → 341. 둘 다 온다
 *   갈래 A 예측   Capacitor가 웹뷰 부모에 setPadding(0,0,0,imeInsets.bottom)을 준다.
 *               그 패딩이 웹뷰를 줄이는 기전이고(실측: 부모 [0,0,1080,1920]는 그대로인데
 *               웹뷰만 [0,72][1080,1095]로 줄었다), 갈래 A도 **같은 값**을 쓴다
 *   ★ 그래도 둘을 다 듣는 이유는 **레이아웃은 그대로인데 IME가 덮기만 하는** 구성이
 *     있을 수 있기 때문이다. 그때는 visualViewport만 줄어든다
 *   ⚠ 먼저 온 쪽이 prev를 갱신하므로 뒤에 온 쪽은 축소량 0으로 보고 아무것도 안 한다
 *
 * [⛔ 이 훅이 못 하는 것 — 뷰포트가 안 줄면 아무것도 못 한다]
 *   웹은 키보드를 직접 볼 수 없다. **뷰포트가 줄어드는 것으로만 안다.**
 *   실제로 줄지 않는 구성을 둘 봤다 —
 *     · insetsHandling "disable" (2.105 실험): 640 고정
 *     · 에뮬레이터의 스타일러스 필기 모드: 592 고정
 *   그런 자리에서는 이 훅이 **조용히 아무 일도 하지 않는다.** 증상은 수정 전과 같아진다.
 *   ⛔ 그것을 웹에서 고칠 방법이 없다 — 2.109의 「길 1」이 그 값을 재 본 결과다.
 */
function useKeyboardReveal(ref) {
  useEffect(() => {
    const vp = window.visualViewport;
    const height = () => (vp ? vp.height : window.innerHeight);
    let prev = height();

    const onResize = () => {
      const now = height();
      const shrank = prev - now;
      prev = now;
      // ⚠ 커질 때는 아무것도 하지 않는다. 키보드가 내려가면 문서가 다시 뷰포트만
      //   해져 스크롤 여유가 0이 되고, **브라우저가 알아서 0으로 되돌린다**
      //   (실측 scrollY 144 → 0). 돌아오는 쪽에 코드가 필요 없다.
      if (shrank < KEYBOARD_SHRINK_MIN) return;
      const el = ref.current;
      // ⛔ 포커스가 이 입력란에 있을 때만이다. 회전 등 다른 축소에 끌려가지 않는다.
      if (!el || document.activeElement !== el) return;

      const maxScroll = document.documentElement.scrollHeight - now;
      const inputTop = el.getBoundingClientRect().top + window.scrollY;
      // ★ 문서 끝까지 밀되(maxScroll), 입력란이 하한 위로 오르면 거기서 멈춘다.
      //   min이 그 둘을 겨루게 하고, max(0, …)이 음수 스크롤을 막는다.
      const target = Math.max(0, Math.min(maxScroll, inputTop - MIN_INPUT_TOP));
      window.scrollTo({ top: target, behavior: "auto" });
    };

    vp?.addEventListener("resize", onResize);
    window.addEventListener("resize", onResize);
    return () => {
      vp?.removeEventListener("resize", onResize);
      window.removeEventListener("resize", onResize);
    };
  }, [ref]);
}

function TextMode({ text, onType, placeholder, onSwitchToPicker, onSubmit }) {
  // ⚠ 이 훅은 **여기에만** 있다. TextMode가 언마운트되면 리스너도 사라지므로
  //   결과 화면·About·선택 모드에는 이 스크롤이 새지 않는다.
  const inputRef = useRef(null);
  useKeyboardReveal(inputRef);

  return (
    <div style={styles.modeBlock}>
      {/* 한 줄 입력이다. textarea 4줄 상자였던 것을 바꿨다 —
          placeholder가 "한 줄로 적어봐요"라고 말하는데 4줄 상자를 내밀면
          말과 화면이 어긋나고, 큰 상자는 "길게 써야 하나" 하는 부담을 준다.
          FYM도 같은 이유로 input 한 줄이다. */}
      <input
        ref={inputRef}
        value={text}
        onChange={(e) => onType(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit(text)}
        placeholder={placeholder}
        aria-label="지금 마음"
        style={styles.input}
      />
      <button type="button" onClick={() => onSubmit(text)} style={styles.submit}>
        마음 들여다보기
      </button>
      <button type="button" onClick={onSwitchToPicker} style={styles.switch}>
        {taxonomy.ui.select_mode.switch_to_select}
      </button>
    </div>
  );
}

/**
 * 선택 모드 — 대분류 한 단계, 세분류 한 단계.
 *
 * 되돌아가는 버튼이 두 단계에서 같은 자리·같은 스타일이다(FYM과 같다).
 * 1단계에서는 텍스트 입력으로, 2단계에서는 대분류 목록으로 돌아간다 —
 * 사용자 입장에서는 "한 걸음 뒤로"라는 같은 동작이라 자리가 같아야 한다.
 */
function SelectMode({ selectedCategory, onPickCategory, onStepBack, onChoose }) {
  const items = selectedCategory
    ? subcategoriesOf(taxonomy, selectedCategory.id)
    : taxonomy.categories;

  return (
    <div style={styles.modeBlock}>
      <p style={styles.selectLead}>
        {selectedCategory
          ? taxonomy.ui.select_mode.step2
          : taxonomy.ui.select_mode.step1}
      </p>
      <div style={styles.grid}>
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() =>
              selectedCategory ? onChoose(item.id) : onPickCategory(item)
            }
            style={styles.chip}
          >
            {item.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onStepBack}
        style={styles.back}
      >
        {selectedCategory ? "← 다시 고르기" : taxonomy.ui.select_mode.switch_to_text}
      </button>
    </div>
  );
}

/**
 * 배경면 위쪽 페이드의 높이(px).
 *
 * ★ 이것이 1px 실선을 대신한다 (사용자 결정 · 2026-09-02).
 *   실선은 배너 윗변이 면의 윗변보다 삐져나올 때 좌우 20dp에만 보인다.
 *   페이드는 **하드 엣지가 없어** 삐져나와도 티가 나지 않는다 —
 *   인셋을 못 읽는다는 제약(2.103)이 그대로 이 선택의 근거다.
 * ⚠ 목록이 배너 뒤로 사라지는 것을 부드럽게 하는 것이 원래 목적이고,
 *   갈래 불확실성을 흡수하는 것은 덤으로 얻은 성질이다.
 */
const BAND_FADE = 24;

/** 띠배너 뒤 배경면. 높이는 bannerSpace가 준다 — 광고가 없으면 그리지 않는다. */
function bandStyle(height, lift = 0) {
  return {
    position: "fixed",
    left: 0,
    right: 0,
    // ★ 바닥이 아니라 **인셋 위**다 (2.118 안 2). 이 한 줄이 배너 아래 여백을 만든다.
    //   ⛔ 0으로 되돌리면 아래 여백이 사라져 배너가 바닥에 붙는다.
    bottom: lift,
    height,
    // ⚠ inkDeep이 아니라 ink다. 긴 목록의 아래쪽 배경이 이미 inkDeep이라
    //   같은 색으로 깔면 **면이 있는지 없는지 보이지 않는다.**
    //   한 단계 밝은 면이 "광고가 그 위에 놓였다"를 만든다.
    background: T.ink,
    // ⛔ 그림자는 이 면에만 줄 수 있다. 네이티브 AdView에는 CSS가 닿지 않는다.
    boxShadow: "0 -6px 20px rgba(0,0,0,.45)",
    pointerEvents: "none",
  };
}

/** 배경면 위로 이어지는 페이드. 목록이 여기서 배너 뒤로 사라진다. */
function bandFadeStyle(height, lift = 0) {
  return {
    position: "fixed",
    left: 0,
    right: 0,
    // ⚠ 1px 겹친다. 소수점 반올림으로 실틈이 생기면 **그 자리로 내용이 비친다** —
    //   이 변경이 없애려는 것이 바로 그 증상이다.
    bottom: lift + height - 1,
    height: BAND_FADE + 1,
    background: `linear-gradient(to top, ${T.ink}, ${T.ink}00)`,
    pointerEvents: "none",
  };
}

/**
 * 셸 — 모든 화면의 바깥틀.
 *
 * [떠 있는 버튼은 **여기서만** 그린다 — 2026-08-19]
 *   FloatingRestart는 position: fixed인데, 화면 내용은 전부 `.rise` 안에 있고
 *   `.rise`의 transform이 fixed 자손의 containing block을 만든다(HANDOFF 4.8).
 *   그래서 화면 컴포넌트 안에서 그리면 뷰포트가 아니라 그 div에 붙어
 *   문서와 함께 흘러가 버린다 — 실제로 그렇게 넣었다가 되돌렸다.
 *
 *   셸은 `{children}` **바깥**이고 조상 어디에도 transform이 없다.
 *   이 자리를 고정해 두면 호출부가 실수할 여지가 없다.
 *   ⚠ 화면 컴포넌트 안으로 옮기지 말 것.
 */
function Shell({
  children,
  onAbout,
  onAboutBack,
  onRestart,
  reducedMotion,
  bottomInset = 0,
  band = { h: 0, lift: 0 },
  toast = "",
}) {
  return (
    /**
     * ⚠ padding-bottom은 **조건부다.** 띠가 없는 화면에서 늘리면 빈 여백만
     *   생긴다. bottomInset이 0이면 원래 값(styles.shell) 그대로다.
     * ★ 이 한 값이 셋을 함께 움직인다 — 문서 끝("이 앱에 대해" · About의
     *   하단 "돌아가기" · 목록 마지막 항목)을 밀어 올리고, 떠 있는 버튼
     *   둘을 올린다. 띠가 접히면 셋 다 함께 내려온다.
     */
    <div
      style={{
        ...styles.shell,
        paddingBottom: `calc(40px + ${bottomInset}px)`,
      }}
    >
      <style>{`
        @keyframes breathe { 0%,100%{transform:scale(1);opacity:.30} 45%{transform:scale(1.20);opacity:.55} }
        @keyframes rise { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        .rise{animation:rise .7s ease both}
        .orb{animation:breathe 10s ease-in-out infinite}
        @media (prefers-reduced-motion: reduce){ .orb{animation:none} .rise{animation:none} }
        button{ font-family:inherit; cursor:pointer }
        a{ -webkit-tap-highlight-color: transparent }
        input::placeholder{ color:#ffffff40 }

        /* 포커스 표시 — 브라우저 기본 outline을 끄되 **반드시 대체 표시를 남긴다.**
           기본 outline은 흰 사각형이라, 면을 쓰지 않는 이 화면에서 상자가
           갑자기 하나 생긴 것처럼 보였다. 대신 밑줄을 jade로 밝힌다
           (#ffffff26 → ${T.jade}). 키보드 사용자가 지금 어디에 있는지 알아야
           하므로 outline:none만 두고 끝내면 안 된다 — 색 대비가 충분히 커서
           밑줄 하나로도 위치가 분명하다. */
        input:focus{ outline:none; border-bottom-color:${T.jade} !important }
      `}</style>
      <div style={styles.inner}>{children}</div>
      {/* ★ 띠배너 뒤에 까는 배경면 — ①의 결함을 덮고 ③의 "떠 있는 느낌"을 만든다.
          (2026-09-02 · HANDOFF 2.104)

          [왜 이것 하나로 둘이 풀리는가]
            네이티브 AdView는 하단 시스템 인셋만큼 위에 앉는데 **그 인셋을
            웹에서 읽을 수 없다**(2.103 — 갈래에 따라 0px이다).
            배경면은 **웹뷰 자기 아래끝**에 붙으므로 인셋 값을 몰라도
            배너 아래 틈을 덮는다. 그래서 시험할 수 없는 갈래에서도 맞는다.
          ⛔ 전체 폭이어야 한다. 카드처럼 좌우를 띄우면 화면 맨 아래 모서리로
            내용이 다시 샌다 — 덮어야 할 것이 화면 아래끝까지이기 때문이다.
          ★ 배너는 320dp 고정이라 360dp 화면에서 좌우 20dp씩 이 면이 드러난다.
            그 20dp가 "광고가 목록에서 떨어져 있다"를 만드는 자리다.
          ⚠ CSS는 AdView에 닿지 않는다. 그림자·모서리는 **이 면에만** 줄 수 있고,
            배너는 그 위에 얹힌다 — "광고가 카드 위에 놓인" 모양이 한계다.
          ⛔ 1px 실선은 넣지 않는다. 배너 윗변이 이 면의 윗변보다 위로
            삐져나올 수 있어(인셋이 클 때) 선이 배너 좌우 20dp에만 보인다.
            대신 **위쪽 페이드**로 닫는다 — 하드 엣지가 없으면 삐져나와도 티가 안 난다.
          ⚠ bottomInset이 0이면 **아무것도 그리지 않는다.** 광고가 없을 때
            배경 띠가 남는 것이 어제 이 안을 기각한 사유였다(2.104 ③). */}
      {band.h > 0 ? (
        <>
          <div aria-hidden="true" style={bandFadeStyle(band.h, band.lift)} />
          <div aria-hidden="true" style={bandStyle(band.h, band.lift)} />
        </>
      ) : null}
      {/* ⛔ 켤 때만 뜬다. 끄거나 거부되면 App이 아예 값을 넣지 않는다. */}
      {toast ? (
        <div role="status" aria-live="polite" style={toastStyle(bottomInset, reducedMotion)}>
          {toast}
        </div>
      ) : null}
      {onRestart ? (
        <FloatingRestart
          onClick={onRestart}
          reducedMotion={reducedMotion}
          bottomInset={bottomInset}
        />
      ) : null}
      {/* "이 앱에 대해"의 떠 있는 돌아가기. FloatingRestart와 같은 이유로
          **여기서** 그린다 — .rise 안에 두면 fixed가 죽는다(HANDOFF 4.8).
          anchorId는 하단 고정 버튼이다. 그것이 보이는 동안에는 숨는다. */}
      {onAboutBack ? (
        <FloatingBack
          onClick={onAboutBack}
          reducedMotion={reducedMotion}
          anchorId={ABOUT_BACK_ID}
          bottomInset={bottomInset}
        />
      ) : null}
      {onAbout ? (
        <button type="button" onClick={onAbout} style={styles.about}>
          이 앱에 대해
        </button>
      ) : null}
    </div>
  );
}

function pickGreeting(visit) {
  const slot = revisitSlot(visit);
  if (slot === "first_visit" || slot === "recent" || slot === "long_absence") {
    const pool = taxonomy.ui.revisit?.[slot];
    if (Array.isArray(pool) && pool.length) return pickMessage(`revisit:${slot}`, pool);
  }
  if (slot === "same_day") {
    const pool = sameDayGreetingPool(visit, taxonomy);
    if (Array.isArray(pool) && pool.length) return pickMessage("revisit:same_day", pool);
  }
  const greetings = taxonomy.ui.entry_greetings?.[greetingSlot()] || [];
  return greetings.length ? pickMessage("greeting", greetings) : "";
}

const styles = {
  shell: {
    minHeight: "100%",
    background: `radial-gradient(120% 90% at 50% 0%, ${T.plum} 0%, ${T.ink} 45%, ${T.inkDeep} 100%)`,
    color: T.mist,
    fontFamily: "'Noto Sans KR','Apple SD Gothic Neo',system-ui,sans-serif",
    padding: "34px 20px 40px",
    boxSizing: "border-box",
  },
  inner: { maxWidth: 520, margin: "0 auto" },

  // --- 입력 화면 헤더 (FYM 구조) ------------------------------------------
  hero: {
    position: "relative",
    height: 150,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  // 헤드라인 뒤에 깔리는 후광. .orb가 10초 주기로 호흡한다(Shell의 keyframes).
  // prefers-reduced-motion에서는 애니메이션만 꺼지고 glow 자체는 남는다 —
  // 시선을 모으는 것은 움직임이 아니라 밝기이기 때문이다.
  heroGlow: {
    position: "absolute",
    width: 190,
    height: 190,
    borderRadius: "50%",
    background: `radial-gradient(circle, ${T.jade}55 0%, ${T.jade}00 68%)`,
  },
  heroText: { position: "relative", textAlign: "center" },
  heroCaption: {
    fontSize: 12,
    letterSpacing: "0.22em",
    color: T.muted,
    marginBottom: 12,
  },
  greeting: {
    fontFamily: SERIF,
    fontSize: 25,
    fontWeight: 400,
    lineHeight: 1.5,
    color: T.mist,
  },

  // 상자가 아니라 밑줄 하나. FYM 입력과 같은 언어다 —
  // 테두리를 두르면 화면에 면이 하나 더 생긴다.
  // 포커스 표시는 Shell의 `input:focus` 규칙이 맡는다(밑줄이 jade로 밝아진다).
  input: {
    width: "100%",
    marginTop: 30,
    background: "transparent",
    border: "none",
    borderBottom: "1px solid #ffffff26",
    color: T.mist,
    fontSize: 16,
    padding: "13px 2px",
    fontFamily: "inherit",
    boxSizing: "border-box",
  },
  submit: {
    marginTop: 26,
    width: "100%",
    padding: "14px 0",
    borderRadius: 3,
    border: `1px solid ${T.jade}59`,
    background: `${T.jade}14`,
    color: T.jade,
    fontSize: 14,
    letterSpacing: "0.04em",
    fontFamily: "inherit",
    cursor: "pointer",
  },
  // 텍스트 모드의 전환 링크 — 주 버튼 바로 아래라 폭을 맞춰 가운데 정렬한다.
  // 색은 FYM 값(T.muted)을 쓴다. 전에는 #ffffff55로 대비 2.99:1이었고 FYM은
  // 같은 링크에 T.muted(6.28:1)를 쓴다 — 더 밝은 쪽이 이미 검증된 값이라
  // 새로 고르지 않고 그것을 가져왔다. 선택 모드의 되돌아가기(back)와도 같아진다.
  switch: {
    display: "block",
    margin: "18px auto 0",
    background: "none",
    border: "none",
    color: T.muted,
    fontSize: 12.5,
    cursor: "pointer",
  },

  // 선택 모드의 되돌아가기 링크 — **좌측 정렬이다** (FYM과 같다).
  // 위에 있는 것이 좌측 정렬된 칩 그리드라 그 왼쪽 끝에 맞춰야 줄이 선다.
  // 텍스트 모드처럼 가운데 두면 칩 어디에도 걸리지 않는 자리에 뜬다.
  back: {
    marginTop: 26,
    padding: 0,
    background: "none",
    border: "none",
    color: T.muted,
    fontSize: 13,
    cursor: "pointer",
  },
  // 헤더 아래 본문 블록. 두 모드가 같은 값을 쓴다 — 모드를 바꿔도 아래 내용이
  // 시작하는 높이가 같아야 헤더만 남고 아래만 갈리는 것으로 보인다.
  modeBlock: { marginTop: 30 },

  // 선택 모드의 질문. **헤더와 달리 좌측 정렬이고 작다** (FYM과 같다).
  // 헤더는 말을 거는 자리라 중앙·명조·25px이고, 이쪽은 목록을 안내하는
  // 라벨이라 좌측·고딕·13px이다. 둘을 같은 격으로 그리면 인사와 안내가
  // 서로 자리를 다툰다 — 앞서 SERIF 16.5px이었던 것을 FYM 값으로 되돌렸다.
  selectLead: { fontSize: 13, color: T.muted, margin: "0 0 16px" },
  grid: { display: "flex", flexWrap: "wrap", gap: 8 },

  // [라운드 언어는 요소마다 다르다 — 2026-08-19]
  //   선택 칩      pill (radius 99)   ← FYM 카테고리 화면과 같다
  //   입력·주 버튼·카드  각진 3~4px      ← FYM 입력 화면과 같다
  //
  // 앞서 "pill을 걷어내라"는 지시가 있었는데, 그건 **구절 카드 안의 pill 버튼**을
  // 두고 한 말이었다(카드 상자 위에 pill이 얹혀 면이 겹쳐 보였다). 그것을 칩까지
  // 일괄 적용해 radius 3의 각진 사각형이 됐고, 선택지가 딱딱해졌다.
  // 칩은 "고르는 것"이라 손에 닿는 느낌이 필요하고, 입력·버튼은 "쓰는 것"이라
  // 각진 편이 화면과 어울린다. FYM이 두 언어를 나눠 쓰는 이유가 그것이다.
  // ⚠ 다음에 라운드를 손볼 때 이 구분을 지울 것 — 또 일괄 적용하지 말 것.
  chip: {
    padding: "9px 15px",
    borderRadius: 99,
    border: "1px solid #ffffff1f",
    background: "transparent",
    color: T.mist,
    fontSize: 14,
    fontFamily: "inherit",
    cursor: "pointer",
  },
  // 구절과 영상 사이의 다리. 구절보다 작고 조용해야 한다 —
  // 같은 크기면 두 문장이 서로 자리를 다툰다.
  empathy: {
    fontFamily: SERIF,
    // fontSize는 구절 크기에 연동된다 — empathyFontSize() 참조
    lineHeight: 1.85,
    color: T.muted,
    /**
     * 아래 여백 26px — 탭 줄 위 구분선까지의 거리다.
     *
     * [세 번 만에 맞췄다. 앞의 둘은 실패였다 — HANDOFF 2.36]
     *   문제   공감 문구(읽는 글)와 비선택 탭(누르는 것)이 같은 T.muted라
     *          문구가 탭 줄의 일부처럼 읽혔다.
     *   1차    탭 색을 85%로 내렸다. 대비는 6.28 → 4.91로 움직였지만
     *          **눈으로는 구분되지 않았다.** 더 내릴 길도 없다 —
     *          탭 라벨은 읽는 글자라 AA 4.5:1에 걸려 80%가 4.53이다.
     *   2차    여백을 24/56으로 벌려 구절 쪽에 붙였다. 그랬더니 구절 블록이
     *          무거워지고, 벌어진 자리는 위계가 아니라 **그냥 빈 공간**으로
     *          읽혔다. 되돌렸다.
     *   3차    탭 줄 위에 1px 구분선을 놓았다(ResultTabs.jsx). 이것이 답이었다.
     *
     * [왜 선이어야 했나]
     *   탭 줄에는 **컨트롤이라는 표시가 아무것도 없었다.** 배경도 테두리도
     *   없이 글자만 나란히 있고 선택된 것에만 1px 밑줄이 있을 뿐이다.
     *   그래서 색을 어떻게 바꾸든 위의 문장과 같은 종류로 읽혔다.
     *   빠진 것은 네 번째 밝기 층이 아니라 **"여기서 읽는 구간이 끝난다"는
     *   구조 신호**였고, 그 일은 여백이 아니라 선이 한다.
     *
     * ⚠ 이 값을 30px(원래)로 되돌리지 말 것. 구분선이 생기면서 이 여백의
     *   뜻이 "탭까지의 거리"에서 "선까지의 거리"로 바뀌었다.
     */
    margin: "0 0 26px",
    wordBreak: "keep-all",
  },
  loadingWrap: {
    height: 330,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  orb: {
    width: 130,
    height: 130,
    borderRadius: "50%",
    background: `radial-gradient(circle, ${T.jade}66 0%, ${T.jade}00 70%)`,
    animationDuration: "2.6s",
  },
  loadingText: {
    marginTop: 26,
    fontSize: 14,
    color: T.muted,
    letterSpacing: "0.05em",
  },
  about: {
    display: "block",
    margin: "34px auto 0",
    background: "none",
    border: "none",
    color: "#ffffff33",
    fontSize: 11.5,
    cursor: "pointer",
  },
};
