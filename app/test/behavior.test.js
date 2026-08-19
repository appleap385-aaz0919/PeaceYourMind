/**
 * 확정 사항이 실제로 지켜지는지 검사한다.
 * 여기가 깨지면 UI가 아니라 약속이 깨진 것이다.
 *
 * PYM 고유로 보는 것 (FYM에 없던 것)
 *   · 위기 화면에 토글·폴백이 없다 — 데이터·코드 양쪽에서 확인한다
 *   · 주제분과 폴백이 섞이지 않는다
 *   · 구절 풀이 감정용과 위기용으로 갈려 있다
 *   · verses.json·videos.json이 없거나 깨졌을 때 화면이 죽지 않는다
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { classify, RESULT, findSubcategory, subcategoriesOf } from "../src/lib/classify.js";
import { normalize } from "../src/lib/normalize.js";
import {
  MEDIA,
  SOURCE,
  formatDuration,
  getCrisisVideos,
  layersFor,
  screenFor,
  toggleCounts,
  visibleVideos,
} from "../src/lib/videos.js";
import { isCompleteVideosPayload } from "../src/lib/payload.js";
import { revisitSlot, sameDayGreetingPool, visitNumberOf } from "../src/lib/messages.js";
import { withMinDuration } from "../src/lib/offline.js";

const here = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(here, "..", "src", "data", p), "utf8"));
const taxonomy = load("taxonomy.json");
const videos = load("seed-videos.json");
const verses = load("verses.json");
const crisisSrcRaw = readFileSync(join(here, "..", "src", "components", "CrisisScreen.jsx"), "utf8");

/**
 * 주석을 걷어낸 소스.
 *
 * 소스 주석에는 "MediaToggle을 import하지 않는다", "추천 표현 없음" 같은
 * 문장이 있다. 원문 그대로 검사하면 **설명이 위반으로 잡힌다** — 첫 실행에서
 * 실제로 그렇게 걸렸다. 검사 대상은 실행되는 코드지 그것을 설명한 문장이 아니다.
 *
 * ⚠ 2026-08-19에 같은 함정에 두 번째로 걸렸다. 토글 밑줄 검사가 "전에는
 *   borderBottom 단축을 썼다"고 적은 주석을 위반으로 잡았다. 그래서 이걸
 *   crisisSrc 전용이 아니라 **함수로 빼 둔다** — 소스를 검사하는 새 테스트는
 *   전부 이걸 통과시켜서 읽는다.
 */
export function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const crisisSrc = stripComments(crisisSrcRaw);

// =============================================================================
// 위기 경로 — 분류보다 먼저, 화면에서는 상담 안내가 최상단
// =============================================================================

test("위기 키워드가 모두 crisis로 분류된다", () => {
  for (const keyword of taxonomy.safety.crisis_keywords) {
    assert.equal(classify(keyword, taxonomy).kind, RESULT.CRISIS, `키워드: ${keyword}`);
  }
});

test("감정 키워드와 위기 키워드가 함께 있으면 위기가 이긴다", () => {
  const input = "짜증나 짜증나 짜증나 진짜 죽고싶다";
  assert.equal(classify(input, taxonomy).kind, RESULT.CRISIS);
});

test("띄어쓰기·문장부호·반복으로 위기 키워드를 우회할 수 없다", () => {
  for (const input of ["죽 고 싶", "죽!고!싶!", "죽고싶ㅠㅠㅠㅠ", "자 해", "살기 싫어..."]) {
    assert.equal(classify(input, taxonomy).kind, RESULT.CRISIS, `입력: ${input}`);
  }
});

test("위기 결과는 어떤 키워드에 걸렸는지 돌려주지 않는다", () => {
  const outcome = classify("죽고싶다", taxonomy);
  assert.equal(outcome.kind, RESULT.CRISIS);
  assert.equal(outcome.hits, undefined);
  assert.equal(outcome.subcategory, undefined);
});

test("상담 안내 문구와 연락처가 있다", () => {
  const r = taxonomy.safety.crisis_response;
  assert.ok(r.message.length > 10);
  assert.ok(r.resources.length >= 2);
  for (const resource of r.resources) {
    assert.ok(resource.name && resource.number, "이름과 번호가 모두 있어야 한다");
  }
});

test("위기 화면에는 토글도 폴백도 없다 (데이터)", () => {
  const r = taxonomy.safety.crisis_response;
  assert.equal(r.media_type_toggle, false);
  assert.equal(r.fallback, false);
});

test("위기 화면 컴포넌트가 토글·폴백 컴포넌트를 import하지 않는다 (코드)", () => {
  // 데이터 플래그만으로는 부족하다. 컴포넌트가 직접 목록을 그리므로,
  // 누가 MediaToggle이나 VideoList를 여기에 끌어오면 이 검사가 잡는다.
  assert.ok(!crisisSrc.includes("MediaToggle"), "위기 화면에 토글이 들어왔다");
  assert.ok(!crisisSrc.includes("VideoList"), "위기 화면에 일반 목록 컴포넌트가 들어왔다");
  assert.ok(!crisisSrc.includes("layersFor"), "위기 화면에 층 분리 로직이 들어왔다");
});

test("위기 화면에서 상담 안내가 구절·영상보다 먼저 나온다", () => {
  const notice = crisisSrc.indexOf('aria-label="상담 안내"');
  const verse = crisisSrc.indexOf('aria-label="구절"');
  assert.ok(notice > 0 && verse > 0, "두 영역이 모두 있어야 한다");
  assert.ok(notice < verse, "상담 안내가 항상 먼저다");
});

test('위기 화면에 "추천"이라는 단어를 쓰지 않는다', () => {
  assert.ok(!crisisSrc.includes("추천"), "framing 원칙 위반");
});

// =============================================================================
// crisis / 일반 격리
// =============================================================================

test("crisis 영상과 세분류 영상이 서로소다", () => {
  const crisisIds = new Set(videos.crisis.videos.map((v) => v.videoId));
  const screenIds = new Set(
    videos.subcategories.flatMap((s) => s.videos.map((v) => v.videoId)),
  );
  const overlap = [...crisisIds].filter((id) => screenIds.has(id));
  assert.deepEqual(overlap, [], `겹치는 videoId: ${overlap}`);
});

test("감정 구절과 위기 구절이 서로소다", () => {
  const crisisIds = new Set(verses.crisis.map((v) => v.id));
  const emotionIds = new Set(verses.verses.map((v) => v.id));
  const overlap = [...crisisIds].filter((id) => emotionIds.has(id));
  assert.deepEqual(overlap, [], `겹치는 구절: ${overlap}`);
});

test("위기 구절에는 emotion_tags가 없다 (감정 매핑을 타지 않는다)", () => {
  for (const verse of verses.crisis) {
    assert.equal(verse.emotion_tags, undefined, `${verse.id}에 emotion_tags가 있다`);
  }
});

test("getCrisisVideos는 crisis 풀만 읽는다", () => {
  const fake = {
    subcategories: [{ id: "x", videos: [{ videoId: "SCREEN", channel: "a" }] }],
    crisis: { videos: [{ videoId: "CRISIS", channel: "b" }] },
  };
  const picked = getCrisisVideos(fake);
  assert.ok(picked.every((v) => v.videoId === "CRISIS"));
});

test("screenFor는 crisis에 접근하지 않는다", () => {
  const fake = { subcategories: [], crisis: { videos: [{ videoId: "CRISIS" }] } };
  assert.equal(screenFor(fake, "anything"), null);
});

// =============================================================================
// media_type 토글
// =============================================================================

const sample = [
  { videoId: "s1", media_type: MEDIA.SERMON, source: SOURCE.THEME },
  { videoId: "s2", media_type: MEDIA.SERMON, source: SOURCE.FALLBACK },
  { videoId: "w1", media_type: MEDIA.WORSHIP, source: SOURCE.THEME },
  { videoId: "u1", media_type: MEDIA.UNKNOWN, source: SOURCE.THEME },
];

test("unknown은 양쪽 토글에 모두 노출된다", () => {
  const sermon = visibleVideos(sample, MEDIA.SERMON).map((v) => v.videoId);
  const worship = visibleVideos(sample, MEDIA.WORSHIP).map((v) => v.videoId);
  assert.ok(sermon.includes("u1"), "말씀 쪽에 unknown이 없다");
  assert.ok(worship.includes("u1"), "찬양 쪽에 unknown이 없다");
});

test("반대 형식은 노출되지 않는다", () => {
  const worship = visibleVideos(sample, MEDIA.WORSHIP).map((v) => v.videoId);
  assert.ok(!worship.includes("s1"));
  assert.ok(!worship.includes("s2"));
});

test("토글 건수는 unknown을 양쪽에 센다", () => {
  const counts = toggleCounts(sample);
  assert.equal(counts[MEDIA.SERMON], 3); // s1 s2 u1
  assert.equal(counts[MEDIA.WORSHIP], 2); // w1 u1
});

test("모든 세분류에 형식 기본값이 있다", () => {
  const ids = taxonomy.categories.flatMap((c) => c.subcategories.map((s) => s.id));
  for (const id of ids) {
    const value = taxonomy.media_defaults[id];
    assert.ok(
      value === MEDIA.SERMON || value === MEDIA.WORSHIP,
      `${id}의 기본값이 이상하다: ${value}`,
    );
  }
});

// =============================================================================
// source 층 — 섞지 않는다
// =============================================================================

test("layersFor가 주제분과 폴백을 갈라서 돌려준다", () => {
  const { theme, fallback } = layersFor(sample, MEDIA.SERMON);
  assert.deepEqual(theme.map((v) => v.videoId), ["s1", "u1"]);
  assert.deepEqual(fallback.map((v) => v.videoId), ["s2"]);
});

test("layersFor는 하나의 합쳐진 배열을 돌려주지 않는다", () => {
  // 합치려면 호출부가 의도적으로 합쳐야 한다 — 그런 코드는 리뷰에서 보인다.
  const result = layersFor(sample, MEDIA.SERMON);
  assert.ok(!Array.isArray(result), "평평한 배열을 돌려주면 층 구분이 사라진다");
  assert.deepEqual(Object.keys(result).sort(), ["fallback", "theme"]);
});

test("배포 데이터의 모든 영상에 source와 media_type이 있다", () => {
  for (const screen of videos.subcategories) {
    for (const video of screen.videos) {
      assert.ok(
        [SOURCE.THEME, SOURCE.FALLBACK].includes(video.source),
        `${video.videoId} source: ${video.source}`,
      );
      assert.ok(
        [MEDIA.SERMON, MEDIA.WORSHIP, MEDIA.UNKNOWN].includes(video.media_type),
        `${video.videoId} media_type: ${video.media_type}`,
      );
    }
  }
});

test("배포 데이터에서 주제분이 폴백보다 앞에 온다", () => {
  for (const screen of videos.subcategories) {
    const sources = screen.videos.map((v) => v.source);
    const firstFallback = sources.indexOf(SOURCE.FALLBACK);
    if (firstFallback < 0) continue;
    assert.ok(
      !sources.slice(firstFallback).includes(SOURCE.THEME),
      `${screen.id}에서 폴백 뒤에 주제분이 나온다`,
    );
  }
});

test("VideoList가 두 층에 다른 제목을 붙인다", () => {
  const src = readFileSync(join(here, "..", "src", "components", "VideoList.jsx"), "utf8");
  assert.ok(src.includes("이 마음에 맞춰 고른 영상"));
  assert.ok(src.includes("딱 맞는 건 아니지만"), "폴백 헤더가 못 맞췄다는 사실을 먼저 말해야 한다");
});

// =============================================================================
// 깨진 데이터 — 화면이 죽지 않는다
// =============================================================================

test("videos.json이 없어도 화면 함수가 죽지 않는다", () => {
  assert.equal(screenFor(null, "anxiety.worry"), null);
  assert.deepEqual(getCrisisVideos(null), []);
  assert.deepEqual(layersFor(undefined, MEDIA.SERMON), { theme: [], fallback: [] });
  assert.deepEqual(toggleCounts(null), { [MEDIA.SERMON]: 0, [MEDIA.WORSHIP]: 0 });
});

test("깨진 payload는 캐시에 들어가지 못한다", () => {
  assert.equal(isCompleteVideosPayload(null), false);
  assert.equal(isCompleteVideosPayload({}), false);
  assert.equal(isCompleteVideosPayload({ version: "v", subcategories: [] }), false);
  assert.equal(
    isCompleteVideosPayload({ version: "v", subcategories: [{ id: "a", videos: [] }] }),
    false,
    "crisis가 없으면 거부",
  );
  assert.equal(
    isCompleteVideosPayload({
      version: "v",
      partial: true,
      subcategories: [{ id: "a", videos: [] }],
      crisis: { videos: [] },
    }),
    false,
    "부분 실행 산출물은 거부",
  );
});

test("옛 스키마(categories)는 거부한다", () => {
  const old = {
    version: "v",
    categories: [{ id: "a", videos: [] }],
    crisis: { videos: [] },
  };
  assert.equal(isCompleteVideosPayload(old), false);
});

test("실제 배포 스키마는 통과한다", () => {
  assert.equal(isCompleteVideosPayload(videos), true);
});

test("길이 표기가 깨진 값에도 죽지 않는다", () => {
  assert.equal(formatDuration(""), "");
  assert.equal(formatDuration(null), "");
  assert.equal(formatDuration("이상한값"), "");
  assert.equal(formatDuration("PT1H2M3S"), "1:02:03");
  assert.equal(formatDuration("PT12M34S"), "12:34");
});

// =============================================================================
// 분류·문구
// =============================================================================

test("세분류를 고르면 그 세분류가 나온다", () => {
  const found = findSubcategory(taxonomy, "anxiety.worry");
  assert.equal(found.subcategory.id, "anxiety.worry");
  assert.equal(found.category.id, "anxiety");
});

test("대분류만 말하면 세분류를 임의로 고르지 않는다", () => {
  const outcome = classify("답답해", taxonomy);
  assert.ok(
    outcome.kind === RESULT.CATEGORY || outcome.kind === RESULT.OK,
    `kind: ${outcome.kind}`,
  );
  if (outcome.kind === RESULT.CATEGORY) {
    assert.equal(outcome.subcategory, undefined);
    assert.ok(subcategoriesOf(taxonomy, outcome.category.id).length > 0);
  }
});

test("빈 입력은 empty로 떨어진다", () => {
  assert.equal(classify("", taxonomy).kind, RESULT.EMPTY);
  assert.equal(classify("   ", taxonomy).kind, RESULT.EMPTY);
});

test("모든 세분류에 공감·마무리 문구가 있다", () => {
  for (const category of taxonomy.categories) {
    for (const sub of category.subcategories) {
      assert.ok(sub.empathy_messages.length >= 10, `${sub.id} 공감 문구 부족`);
      assert.ok(sub.closing_messages.length >= 10, `${sub.id} 마무리 문구 부족`);
    }
  }
});

test("로딩 최소 노출은 1000ms다 (즉답 금지)", () => {
  assert.equal(taxonomy.ui.loading.min_duration_ms, 1000);
});

test("withMinDuration은 함수를 받는다 (프라미스를 넘기면 화면이 멈춘다)", async () => {
  // 첫 실행에서 프라미스를 넘겨 "work is not a function"으로 로딩 화면이
  // 영원히 도는 버그가 있었다. 테스트는 통과하는데 화면만 죽는 유형이라
  // 실제 실행으로만 잡혔다 — 그래서 여기에 못을 박는다.
  const started = Date.now();
  const value = await withMinDuration(() => "결과", 120);
  assert.equal(value, "결과");
  assert.ok(Date.now() - started >= 110, "최소 노출 시간을 지켜야 한다");

  await assert.rejects(
    () => withMinDuration(Promise.resolve("프라미스"), 10),
    /not a function/,
    "프라미스를 넘기면 실패해야 한다 (조용히 통과하면 안 된다)",
  );
});

test("재방문 인사가 방문 간격을 구분한다", () => {
  assert.equal(revisitSlot({ lastVisitAt: null }), "first_visit");
  const now = new Date("2026-08-19T10:00:00Z");
  assert.equal(
    revisitSlot({ lastVisitAt: "2026-08-19T02:00:00Z", visitCountToday: 1 }, now),
    "same_day",
  );
  assert.equal(
    revisitSlot({ lastVisitAt: "2026-08-01T10:00:00Z", visitCountToday: 0 }, now),
    "long_absence",
  );
});

test("횟수를 말하는 인사는 2회차에서만 쓴다", () => {
  const second = sameDayGreetingPool({ visitCountToday: 1 }, taxonomy);
  const third = sameDayGreetingPool({ visitCountToday: 2 }, taxonomy);
  assert.ok(second.length >= third.length);
  assert.equal(visitNumberOf({ visitCountToday: 1 }), 2);
});

test("반복 축약은 문자 단위다 (어절 반복은 대상이 아니다)", () => {
  // 2026-08-19 — FYM 주석의 예시("짜증나아아아 → 짜증나아")가 실제 동작과 달랐다.
  // 규칙(3회 이상 → 2회)이 맞고 예시가 틀렸다는 판단으로 예시를 고쳤고,
  // 다시 어긋나지 않게 실제 사용자가 칠 법한 입력으로 못을 박는다.
  assert.equal(normalize("ㅋㅋㅋㅋㅋ"), "ㅋㅋ");
  assert.equal(normalize("짜증나아"), "짜증나아", "2회는 그대로 둔다");
  assert.equal(normalize("짜증나아아"), "짜증나아아", "아 2개 — 축약 대상이 아니다");
  assert.equal(normalize("짜증나아아아"), "짜증나아아", "아 3개 → 2개");
  assert.equal(normalize("너무너무너무"), "너무너무너무", "어절 반복은 줄이지 않는다");
  assert.equal(normalize("괜찮아아아!!!"), "괜찮아아", "문장부호는 제거된다");
});

test("반복 입력이 분류 결과를 바꾸지 않는다", () => {
  // 축약의 목적은 "짜증나"와 "짜증나아아아"가 같은 화면으로 가게 하는 것이다.
  const pairs = [
    ["짜증나", "짜증나아아아"],
    ["외로워", "외로워어어어"],
    ["너무 힘들어", "너무너무너무 힘들어"],
  ];
  for (const [plain, repeated] of pairs) {
    const a = classify(plain, taxonomy);
    const b = classify(repeated, taxonomy);
    assert.equal(a.kind, b.kind, `${plain} vs ${repeated}`);
    if (a.kind === RESULT.OK) {
      assert.equal(a.subcategory.id, b.subcategory.id, `${plain} vs ${repeated}`);
    }
  }
  // 위기 키워드는 반복이 붙어도 위기다 (검사 순서가 먼저이므로 항상 성립한다)
  assert.equal(classify("죽고싶", taxonomy).kind, RESULT.CRISIS);
  assert.equal(classify("죽고싶ㅠㅠㅠㅠ", taxonomy).kind, RESULT.CRISIS);
});

test("정규화가 위기 우회를 막는 규칙 그대로다", () => {
  assert.equal(normalize("죽 고 싶"), normalize("죽고싶"));
  // 3회 이상 반복을 2회로 접는다. "나"는 별개 음절이므로 "짜증나" + "아아"다.
  // (Python lib/normalize.py와 문자 단위로 같은 결과여야 한다 — 배치와 앱이
  //  같은 규칙을 써야 위기 키워드 우회 방어가 한쪽에서만 작동하지 않는다)
  assert.equal(normalize("짜증나아아아"), "짜증나아아");
});

// --- 토글 밑줄 / 결과 화면 되돌아가기 ----------------------------------------

test("토글 밑줄은 개별 속성으로만 지정한다 (단축과 섞으면 비활성에 검은 선이 남는다)", () => {
  // [2026-08-19 회귀 방지]
  //   base가 `borderBottom: "1px solid transparent"` 단축이고 active만
  //   borderBottomColor를 얹으면, 선택이 옮겨갈 때 React가 이전 버튼에서
  //   개별 속성만 지운다. 그 자리가 transparent로 돌아가지 않고 불투명
  //   검정으로 해석돼 **비활성 탭에 검은 밑줄**이 남았고, 활성 탭의
  //   jade 60%보다 진하게 보여 "밑줄이 반대"로 읽혔다.
  //   양쪽 상태가 항상 같은 개별 속성을 지정해야 값이 교체되기만 한다.
  const src = stripComments(
    readFileSync(join(here, "..", "src", "components", "MediaToggle.jsx"), "utf8"),
  );
  const styles = src.slice(src.indexOf("const styles"));
  assert.ok(
    !/borderBottom:\s*"/.test(styles),
    "borderBottom 단축이 돌아왔다 — 비활성 탭에 검은 밑줄이 다시 생긴다",
  );
  assert.ok(
    /borderBottomColor:\s*"transparent"/.test(styles),
    "기본 상태가 borderBottomColor를 지정하지 않는다",
  );
  assert.ok(
    /active:\s*\{[^}]*borderBottomColor/.test(styles),
    "선택된 탭에 밑줄 색이 없다",
  );
});

test("결과 화면에 스크롤 후 돌아갈 길이 있다", () => {
  // 실측(360×640, 말씀 14건): 문서 1,686px에 하단 "다시 적어보기"가 1,573px —
  // 2.5화면을 내려야 닿는다. 그 사이 화면에는 돌아갈 길이 없었다.
  const src = readFileSync(join(here, "..", "src", "App.jsx"), "utf8");
  assert.ok(src.includes("<FloatingRestart"), "결과 화면에 FloatingRestart가 없다");
  assert.ok(src.includes("<Closing"), "하단 마무리 문구·되돌아가기가 없다");
});
