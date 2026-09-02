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
import { readFileSync, readdirSync } from "node:fs";
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
  shuffleThemeLayer,
  screenFor,
  toggleCounts,
  visibleVideos,
} from "../src/lib/videos.js";
import {
  ANSWER_ACTIONS,
  FLOW,
  MODE,
  PHASE,
  flowReducer,
  initialFlow,
  inputBoxVisible,
} from "../src/lib/flow.js";
import { isCompleteVideosPayload } from "../src/lib/payload.js";
import { revisitSlot, sameDayGreetingPool, visitNumberOf } from "../src/lib/messages.js";
import { withMinDuration } from "../src/lib/offline.js";
import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(here, "..", "src", "data", p), "utf8"));
const taxonomy = load("taxonomy.json");
const videos = load("seed-videos.json");
const verses = load("verses.json");

// 소스 검사는 전부 readSource()를 지난다 — 주석이 검사를 오염시킨다(helpers.js).
const crisisSrc = readSource("components", "CrisisScreen.jsx");

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


// -----------------------------------------------------------------------------
// 2026-08-20 — ★ 여기서부터가 실제 회귀 검사다
//
// 위의 "위기 키워드가 모두 crisis로 분류된다"는 **사전을 사전으로 검사한다.**
// 항상 통과하며, 사전에 없는 표현은 구조적으로 검사 대상이 되지 않는다.
// 그래서 `자살`이 55종 어디에도 없는 채로 운영에 나갔다 (taxonomy.yaml 2026-08-20).
//
// 아래 목록은 **taxonomy를 참조하지 않고 손으로 적은 것**이다. 사전이 줄거나
// 활용형이 어긋나면 여기서 깨진다. 표현을 지우지 말고 늘려 갈 것.
// -----------------------------------------------------------------------------

// 반드시 위기로 가야 하는 표현. 사전에서 유도하지 않았다.
const MUST_BE_CRISIS = [
  "자살", "자살하고 싶어", "자살할까", "자살 생각이 나요", "자살 충동이 들어요",
  "자살하려고요", "자살밖에 답이 없어",
  "죽어", "죽여", "죽음", "죽어버릴까", "죽어버리고 싶어", "죽어야겠다", "죽어야 하나",
  "나 좀 죽여줘", "목숨을 끊고 싶어요", "목숨 끊는 생각",
  "극단적인 생각이 들어요", "극단적인 선택을 생각해요",
  "그냥 죽고 싶어요", "사라지고 싶어", "없어지고 싶어요", "자해했어요",
  "더 이상 살고 싶지 않아요", "내가 없어야 다들 편할 것 같아",
  "살 자격이 없는 것 같아요", "내일 눈 뜨고 싶지 않아", "희망이 하나도 없어요",
];

// 위기가 **아니어야** 하는 표현. 위기로 새면 그 사람이 받을 것을 못 받는다.
const MUST_NOT_BE_CRISIS = [
  // 사별 — 상실 구절을 받아야 할 사람이다. 위기로 채가면 안 된다
  "할머니가 죽어서 너무 슬퍼요", "강아지가 죽어서 눈물이 나요",
  // 관용구 — 강조 표현일 뿐이다
  "배고파 죽겠다", "웃겨 죽겠어", "힘들어 죽겠어요", "짜증나 죽겠어",
  "죽어라 일했어요", "좋아 죽겠어",
  // 타인 지향 분노 — anger로 가야 한다
  "저 인간 죽여버리고 싶다", "죽여버릴까 진짜",
  // 사물·뉴스 어휘
  "자살골 넣었어요", "자살률 기사 봤어요", "자살 예방 강의 들었어요",
  "극단적인 디자인이 마음에 들어요", "그 사람은 극단적인 성격이야",
  // 자책 — 경계선 원칙: 결과를 탓하는 것은 위기가 아니다
  "내가 다 망쳤어", "나 때문이야", "자책하게 돼요",
];

test("위기 표현은 사전을 참조하지 않고도 전부 위기로 간다", () => {
  const missed = MUST_BE_CRISIS.filter(
    (s) => classify(s, taxonomy).kind !== RESULT.CRISIS
  );
  assert.deepEqual(missed, [], `위기를 놓쳤다: ${missed.join(" · ")}`);
});

test("사별·관용구·타인 지향 분노는 위기로 새지 않는다", () => {
  const leaked = MUST_NOT_BE_CRISIS.filter(
    (s) => classify(s, taxonomy).kind === RESULT.CRISIS
  );
  assert.deepEqual(leaked, [], `위기로 샜다: ${leaked.join(" · ")}`);
});

test("사별은 슬픔 계열로 간다 — 위기가 아닌 것으로는 부족하다", () => {
  for (const input of ["할머니가 죽어서 너무 슬퍼요", "강아지가 죽어서 눈물이 나요"]) {
    const r = classify(input, taxonomy);
    assert.equal(r.kind, RESULT.OK, input);
    assert.equal(r.category.id, "sadness", `${input} → ${r.subcategory?.id}`);
  }
});

test("단독 입력 위기어는 단독일 때만 위기다", () => {
  for (const word of taxonomy.safety.crisis_exact) {
    assert.equal(classify(word, taxonomy).kind, RESULT.CRISIS, `단독: ${word}`);
  }
  // 같은 말이 문장 안에 있으면 단독 층은 작동하지 않는다
  assert.notEqual(
    classify("할머니가 죽어서 너무 슬퍼요", taxonomy).kind,
    RESULT.CRISIS
  );
});

test("단독 입력은 자모·문장부호·공백이 붙어도 단독으로 본다", () => {
  for (const input of ["죽어ㅠㅠ", "죽어...", "죽 어", "죽어!!!", "자살ㅠㅠㅠ"]) {
    assert.equal(classify(input, taxonomy).kind, RESULT.CRISIS, `입력: ${input}`);
  }
});

test("단독 입력 위기어를 부분 문자열 목록으로 옮기지 않았다", () => {
  // 옮기는 순간 사별·관용구가 전부 위기로 빨려 들어간다.
  // 생성기도 막지만(gen_taxonomy_json.validate) 앱 쪽에서도 고정해 둔다.
  const overlap = taxonomy.safety.crisis_exact.filter((w) =>
    taxonomy.safety.crisis_keywords.includes(w)
  );
  assert.deepEqual(overlap, []);
});

// -----------------------------------------------------------------------------
// 2026-08-20 — 긍정 표현 커버리지 (긴급 수정)
//
// "기분이 좋아"가 미분류였다. `기분좋`은 있는데 조사 '이'가 끼면 깨진다 —
// 위기 사전의 `죽어버리`/`죽어버릴까`와 같은 유형이다.
//
// ⚠ **NO_MATCH 화면이 정상 동작인 것과 분류가 정상인 것은 별개다.**
//   "일이 너무 많아서 정신이 없었어요"는 감정어가 없어 NO_MATCH가 맞지만
//   "기분이 좋아"는 감정을 직접 말한 입력이다. 화면이 안 깨진다고 결함이
//   아닌 것이 아니다 — 그 구분을 놓쳐 발견이 늦었다.
//
// 아래 목록은 taxonomy를 참조하지 않고 손으로 적었다. 위기 목록과 같은 원칙이다.
// -----------------------------------------------------------------------------

const MUST_BE_POSITIVE = [
  "기분이 좋아", "기분 좋아", "기분이 좋아요", "기분좋다",
  "좋다", "너무 좋아", "참 좋다", "진짜 좋았어",
  "오늘 하루 좋았어요", "좋은 하루였어요",
  "행복해", "행복해요", "신나요", "재밌었어요", "웃음이 났어요",
  "뿌듯해요", "감사해요",
];
const MUST_BE_CALM_OR_FLUTTER = [
  ["설레요", "flutter"], ["두근거려요", "flutter"], ["기대돼요", "flutter"],
  ["편안해요", "calm"], ["평온해요", "calm"], ["차분해요", "calm"],
  ["여유로워요", "calm"], ["홀가분해요", "calm"], ["마음이 놓여요", "calm"],
  ["마음이 가볍다", "calm"],
];
// ⛔ 긍정 어휘를 넓히다 여기를 깨뜨리기 쉽다. `좋아`를 통째로 넣으면 전부 걸린다.
const MUST_NOT_BE_JOY = [
  "기분이 안 좋아", "기분이 좋지 않아요", "안 좋은 일이 있었어요",
  "마음이 안 좋아요", "하나도 안 좋아", "그다지 좋지 않다",
];

test("긍정 표현은 감정 계열로 분류된다", () => {
  const missed = MUST_BE_POSITIVE.filter((s) => {
    const r = classify(s, taxonomy);
    if (r.kind === RESULT.OK) return r.category.id !== "joy";
    return r.kind !== RESULT.CATEGORY || r.category.id !== "joy";
  });
  assert.deepEqual(missed, [], `긍정 표현을 놓쳤다: ${missed.join(" · ")}`);
});

test("설렘·평온 표현도 제 계열로 간다", () => {
  const missed = MUST_BE_CALM_OR_FLUTTER.filter(([s, cat]) => {
    const r = classify(s, taxonomy);
    const got = r.kind === RESULT.OK ? r.category.id
      : r.kind === RESULT.CATEGORY ? r.category.id : null;
    return got !== cat;
  }).map(([s]) => s);
  assert.deepEqual(missed, [], `놓쳤다: ${missed.join(" · ")}`);
});

test("부정 표현이 긍정으로 새지 않는다", () => {
  const leaked = MUST_NOT_BE_JOY.filter((s) => {
    const r = classify(s, taxonomy);
    return r.kind === RESULT.OK && r.category.id === "joy";
  });
  assert.deepEqual(leaked, [], `긍정으로 샜다: ${leaked.join(" · ")}`);
});

// -----------------------------------------------------------------------------
// 2026-08-20 — [7] 부정 표현. **긍정 계열에만** 건다
// -----------------------------------------------------------------------------
// "재미있는 게 하나도 없어요"가 joy.delight로 갔다. 방향이 정반대다.
// ⛔ 부정 계열에까지 걸면 이중 부정이 된다 — "슬픔이 가시지 않아요"는 슬픔이
//    **계속된다**는 뜻이다. 그 6건이 통째로 죽는 것을 실측으로 확인했다.
// -----------------------------------------------------------------------------

const NEGATED_POSITIVE = [
  "재미있는 게 하나도 없어요", "즐거운 일이 없어요", "기쁜 일이 하나도 없어",
  "행복하지 않아요", "설레지 않아요", "편안하지가 않아요", "여유가 없어요",
];
// ⛔ 이중 부정 — 부정 계열은 "않/없"이 붙어도 감정이 유지된다. 죽이면 안 된다
const DOUBLE_NEGATION = [
  ["슬픔이 가시지 않아요", "sadness"], ["외로움이 사라지지 않아요", "sadness"],
  ["걱정이 떠나지 않아요", "anxiety"], ["짜증이 가시질 않아", "anger"],
  // ⚠ "화가 가라앉지 않아요"는 여기 넣지 않았다 — sadness.sorrow로 간다.
  //   `가라앉`이 sadness 키워드라 그렇고, **부정 처리와 무관한 별개 문제다**
  //   (규칙을 끄면 결과가 같다). 감정 어휘 소속의 문제이지 [7]의 문제가 아니다.
];

// =============================================================================
// 2026-08-20 — 부정 표현 커버리지 (실사용 제보: "기분이 나빠"가 미분류)
// =============================================================================
//
// 900개 키워드에 `나쁘`·`나빠`·`나뻐`가 **하나도 없었다.** 조사가 낀 형태만
// 깨진 것이 아니라 "기분 나빠"·"기분나쁘다"도 전부 미분류였다 —
// 2.31절(긍정)과 같은 물음이 답이다:
//   "사전에 있는 것이 걸리는가"가 아니라 **"있어야 할 것이 사전에 있는가"**.
//
// ⚠ **부정을 놓치는 것은 긍정을 놓치는 것보다 비싸다.** 긍정을 놓치면 선택
//   화면이 나올 뿐이지만, 부정을 놓치면 도움이 필요한 사람이 아무것도 못 받은
//   채 한 번 더 움직여야 한다.
//
// 재점검 48건 중 17건이 미분류였고 13건을 고쳤다(20종 추가). 남은 4건은
// 아래 [고치지 않은 것]에 근거를 적었다.
//
// 아래 목록은 taxonomy를 참조하지 않고 손으로 적었다. 위기·긍정 목록과 같은
// 원칙이다 — 사전을 읽어 만들면 사전이 틀렸을 때 테스트도 같이 틀린다.
// -----------------------------------------------------------------------------

const NEGATIVE_CATEGORIES = ["anxiety", "anger", "frustration", "sadness", "exhaustion"];

const MUST_BE_NEGATIVE = [
  // 제보 유형 — 조사 유무로 갈린다
  "기분이 나빠", "기분 나빠", "기분나쁘다", "기분이 나쁘다",
  "기분이 안 좋아", "마음이 안 좋아", "기분이 별로야",
  // 흔한 오타·구어
  "기분이 나뻐", "기분 나뻐", "기분이 않좋아", "힘드러",
  // 일상 부정 감정
  "마음이 무거워", "마음이 아파", "마음이 복잡해",
  "속상해", "속상해요", "서운해", "섭섭해", "억울해",
  "짜증이 나", "짜증나", "화가 나", "화가 치밀어",
  "울고 싶어", "눈물이 나", "눈물만 나", "슬퍼", "우울해",
  "지쳤어", "힘들어", "너무 힘들어", "외로워", "혼자인 것 같아",
  "불안해", "답답해", "무기력해", "의욕이 없어", "아무것도 하기 싫어",
  "스트레스 받아", "빡쳐", "우울해요ㅠㅠ", "짜증나ㅡㅡ",
];

// ⛔ 부정 어휘를 넓히다 깨뜨리기 쉬운 자리. 전부 **실측으로 걸렸던** 함정이다.
//
// ⚠ 함정마다 **어느 계열로 가면 안 되는지**를 따로 적는다. "부정이면 무조건
//   실패"로 적었다가 이 테스트가 거짓 실패를 냈다 — "별로 야근이 많아"는
//   기존 키워드 `야근`에 걸려 exhaustion.tired로 가고, 그건 이 변경과 무관하며
//   틀린 결과도 아니다. 막아야 하는 것은 `별로야`가 만들던 **짜증** 오분류다.

// `별로야` 함정 (2026-08-18 기각). 정규화가 공백을 지워 "별로 야~"가 붙는다.
const MUST_NOT_BE_IRRITATION = [
  "별로 야근이 많아", "별로 야한 장면 없어", "별로 야식 안 먹어",
];
// `분해` 함정. 넣었다면 평온·중립 표현이 억울함으로 갔다.
const MUST_NOT_BE_UNFAIR = [
  "차분해요", "충분해요", "넉넉하고 충분해", "성분 분해가 잘 돼",
];
// 긍정·평온·해소 표현이 부정 계열로 새면 안 된다.
const MUST_NOT_BE_NEGATIVE = [
  "기분이 좋아", "마음이 편해", "여유로워", "스트레스가 풀렸어요",
];

test("부정 표현은 부정 계열로 분류된다", () => {
  const missed = MUST_BE_NEGATIVE.filter((s) => {
    const r = classify(s, taxonomy);
    const cat = r.kind === RESULT.OK ? r.category.id
      : r.kind === RESULT.CATEGORY ? r.category.id : null;
    return !NEGATIVE_CATEGORIES.includes(cat);
  });
  assert.deepEqual(missed, [], `부정 표현을 놓쳤다: ${missed.join(" · ")}`);
});

function subcategoryOf(input) {
  const r = classify(input, taxonomy);
  return r.kind === RESULT.OK ? r.subcategory.id : null;
}

test("부정 어휘가 긍정·평온 표현을 삼키지 않는다", () => {
  const leaked = MUST_NOT_BE_NEGATIVE.filter((s) => {
    const r = classify(s, taxonomy);
    const cat = r.kind === RESULT.OK ? r.category.id
      : r.kind === RESULT.CATEGORY ? r.category.id : null;
    return NEGATIVE_CATEGORIES.includes(cat);
  });
  assert.deepEqual(leaked, [], `부정으로 샜다: ${leaked.join(" · ")}`);
});

test("⛔ `별로야` 함정 — 짜증으로 가지 않는다", () => {
  const leaked = MUST_NOT_BE_IRRITATION.filter((s) => subcategoryOf(s) === "anger.irritation");
  assert.deepEqual(leaked, [], `짜증으로 샜다: ${leaked.join(" · ")}`);
});

test("⛔ `분해` 함정 — 억울함으로 가지 않는다", () => {
  const leaked = MUST_NOT_BE_UNFAIR.filter((s) => subcategoryOf(s) === "anger.unfair");
  assert.deepEqual(leaked, [], `억울함으로 샜다: ${leaked.join(" · ")}`);
});

test('"기분이 별로야"가 상실감으로 가지 않는다 (어절 경계 오탐)', () => {
  // 정규화가 공백을 지우면 "기분이별로야"에 `이별`이 들어 있다.
  // 상실감(sadness.loss) 화면은 사별·이별을 다루는 자리라 방향이 정반대다.
  // `기분이별로`(5자)가 `이별`(2자)보다 길어 점수 규칙에서 이긴다.
  const r = classify("기분이 별로야", taxonomy);
  assert.equal(r.kind, RESULT.OK);
  assert.notEqual(r.subcategory.id, "sadness.loss");
});

// [고치지 않은 것 — 되돌리려는 시도를 막기 위해 근거를 남긴다]
//
//   분해       ⛔ `분해`를 넣으면 **차분해·충분해**가 걸린다. 평온한 사람이
//              억울함 화면으로 간다. taxonomy.yaml의 `분한` 기각(2026-08-14,
//              차분하다·충분하다)과 같은 자리다. 억울함은 `억울`이 이미 잡는다.
//   실타·시러   의도적 구어 표기다. 대응을 시작하면 끝이 없다(시로·시러여·실쿠나).
//              2.31절이 "괜찮아요"에 선을 그은 것과 같은 판단이다.
//   현타 왔어   신조어이고 감정 방향이 갈린다(허무·자괴·무기력). 넣는다면
//              exhaustion.listless지만 근거가 약해 미룬다.
//
// [알고 두는 것 — 이중 부정]
//   "기분이 나쁘지 않아요" · "섭섭하지 않아요"는 부정 계열로 분류된다.
//   부정 계열에 부정 무효화를 걸지 않는 설계의 결과다(classify.js 주석 —
//   "슬픔이 가시지 않아요"가 슬픔의 **지속**을 뜻하기 때문).
//   ⚠ 새로 생긴 결함이 아니다. 기존 키워드로 같은 검사를 하면 9건 중 8건이
//     똑같이 걸린다("화나지 않아요" · "우울하지 않아요" · "억울하지 않아요" …).

test("부정된 긍정 표현은 긍정 계열로 가지 않는다", () => {
  const leaked = NEGATED_POSITIVE.filter((s) => {
    const r = classify(s, taxonomy);
    const cat = r.kind === RESULT.OK ? r.category.id
      : r.kind === RESULT.CATEGORY ? r.category.id : null;
    return ["joy", "flutter", "calm"].includes(cat);
  });
  assert.deepEqual(leaked, [], `긍정으로 샜다: ${leaked.join(" · ")}`);
});

test("대분류 폴백에서도 부정이 되살아나지 않는다", () => {
  // "설레지 않아요"가 flutter 세분류에서 걸러졌는데 대분류 폴백이 다시 집었다.
  const r = classify("설레지 않아요", taxonomy);
  assert.notEqual(r.kind === RESULT.CATEGORY ? r.category.id : null, "flutter");
});

test("이중 부정 — 부정 계열 감정어는 '않/없'이 붙어도 살아 있다", () => {
  const lost = DOUBLE_NEGATION.filter(([s, cat]) => {
    const r = classify(s, taxonomy);
    const got = r.kind === RESULT.OK ? r.category.id
      : r.kind === RESULT.CATEGORY ? r.category.id : null;
    return got !== cat;
  }).map(([s]) => s);
  assert.deepEqual(lost, [], `감정을 잃었다: ${lost.join(" · ")}`);
});

test("같은 키워드가 두 번 나오면 부정 안 된 자리를 살린다", () => {
  // "재미있는 건 없지만 그래도 재미있었어요" — 뒤쪽 자리는 부정이 아니다
  const r = classify("재미있는 건 없지만 그래도 재미있었어요", taxonomy);
  assert.equal(r.kind, RESULT.OK);
  assert.equal(r.category.id, "joy");
});

test("⚠ 알려진 한계 — 창 안의 무관한 부정어를 가르지 못한다", () => {
  // "재미있었고 후회도 없어요"에서 없는 것은 후회인데, 창(8글자) 안에 `없`이
  // 있어 `재미있`이 무효화된다. 문법적으로 가르려면 파싱이 필요하다.
  // 결과는 NO_MATCH → 선택 화면이라 **안전한 방향의 오탐**이고, 빈도가 낮아
  // 감수한다. 이 검사는 그 한계를 **기록으로 고정**하는 것이다 —
  // 나중에 고쳤다면 여기가 깨지고, 그때 이 주석을 지우면 된다.
  assert.equal(classify("재미있었고 후회도 없어요", taxonomy).kind, RESULT.NO_MATCH);
});

test("같은 표현이 두 세분류에 갈리면 짧은 쪽이 죽는다 — 손에안잡 중복 정리", () => {
  // `손에안잡`(anxiety.restless)과 `손에안잡혀`(exhaustion.listless)가 함께
  // 있으면 길이 합에서 긴 쪽이 항상 이겨 짧은 쪽이 죽은 키워드가 된다.
  const all = taxonomy.categories.flatMap((c) => c.subcategories);
  const listless = all.find((s) => s.id === "exhaustion.listless");
  assert.ok(!listless.keywords.includes("손에안잡혀"), "중복을 되돌리지 말 것");
  const r = classify("계속 걱정이 돼서 아무것도 손에 안 잡혀요", taxonomy);
  assert.equal(r.kind, RESULT.OK);
  assert.equal(r.category.id, "anxiety");
});

test("좋아하는 사람 = 설렘이지 즐거움이 아니다", () => {
  const r = classify("좋아하는 사람이 생겼어요", taxonomy);
  assert.equal(r.kind, RESULT.OK);
  assert.equal(r.category.id, "flutter");
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

test("위기 화면 컴포넌트가 토글·폴백·본문 컴포넌트를 import하지 않는다 (코드)", () => {
  // 데이터 플래그만으로는 부족하다. 컴포넌트가 직접 목록을 그리므로,
  // 누가 ResultTabs나 VideoList를 여기에 끌어오면 이 검사가 잡는다.
  assert.ok(!crisisSrc.includes("ResultTabs"), "위기 화면에 탭이 들어왔다");
  assert.ok(!crisisSrc.includes("MediaToggle"), "위기 화면에 옛 토글이 들어왔다");
  assert.ok(!crisisSrc.includes("VideoList"), "위기 화면에 일반 목록 컴포넌트가 들어왔다");
  assert.ok(!crisisSrc.includes("layersFor"), "위기 화면에 층 분리 로직이 들어왔다");
  // [2026-08-20] 위기 구절의 앞뒤에 무엇이 있는지 통제할 수 없다.
  //   데이터 쪽은 이미 막혀 있지만(위기 풀에 read가 없다 — chapters.test.js),
  //   화면 쪽도 함께 막는다. 두 겹 중 하나만 뚫려도 이 기능은 위기 화면에
  //   닿지 못한다.
  assert.ok(!crisisSrc.includes("ChapterReader"), "위기 화면에 이어서 읽기가 들어왔다");
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

// ★★ 2026-08-28 뒤집힌 결정 — 전에는 "unknown은 양쪽에 모두 노출된다"였다.
//   unknown이 79건(4.5%)이던 시절엔 빼면 주제분을 39건 잃었다. 25건(1.4%)이 된
//   지금은 −6건뿐이고, 얻는 것(탭 정확히 20 · 양쪽 탭 중복 0)은 그대로다.
//   ⚠ 배치의 lib/selection.visible_count()와 **같은 기준이어야 한다.**
test("★ unknown은 어느 토글에도 노출되지 않는다", () => {
  const sermon = visibleVideos(sample, MEDIA.SERMON).map((v) => v.videoId);
  const worship = visibleVideos(sample, MEDIA.WORSHIP).map((v) => v.videoId);
  assert.ok(!sermon.includes("u1"), "말씀 쪽에 unknown이 남아 있다");
  assert.ok(!worship.includes("u1"), "찬양 쪽에 unknown이 남아 있다");
});

test("★ 두 탭은 겹치는 영상을 갖지 않는다 (말씀 + 찬양 = 전체)", () => {
  const sermon = visibleVideos(sample, MEDIA.SERMON).map((v) => v.videoId);
  const worship = visibleVideos(sample, MEDIA.WORSHIP).map((v) => v.videoId);
  assert.equal(sermon.filter((id) => worship.includes(id)).length, 0, "겹치는 영상이 있다");
});

test("반대 형식은 노출되지 않는다", () => {
  const worship = visibleVideos(sample, MEDIA.WORSHIP).map((v) => v.videoId);
  assert.ok(!worship.includes("s1"));
  assert.ok(!worship.includes("s2"));
});

test("★ 토글 건수에서 unknown을 빼고 센다", () => {
  const counts = toggleCounts(sample);
  assert.equal(counts[MEDIA.SERMON], 2); // s1 s2  (u1은 안 센다)
  assert.equal(counts[MEDIA.WORSHIP], 1); // w1
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
  // u1(unknown)은 2026-08-28부터 어느 탭에도 안 들어간다
  assert.deepEqual(theme.map((v) => v.videoId), ["s1"]);
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
  const src = readSource("components", "VideoList.jsx");
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
  //
  // [2026-08-20 — 검사 범위를 넓혔다]
  //   ResultTabs(옛 MediaToggle)만 보던 검사다. 이어서 읽기의 [이전]/[다음]도
  //   같은 구조로 밑줄을 켜고 끄므로 같은 함정에 걸릴 자리다. 실제로 초안이
  //   그 실수를 그대로 반복했다 — 한 곳만 지키는 검사는 다음 컴포넌트를
  //   막지 못한다.
  for (const file of ["ResultTabs.jsx", "ChapterReader.jsx"]) {
    const src = readSource("components", file);
    const styles = src.slice(src.indexOf("const styles"));
    assert.ok(
      !/borderBottom:\s*"/.test(styles),
      `${file}: borderBottom 단축이 돌아왔다 — 꺼진 쪽에 검은 밑줄이 다시 생긴다`,
    );
    assert.ok(
      /borderBottomColor:/.test(styles),
      `${file}: 밑줄 색을 개별 속성으로 지정하지 않는다`,
    );
  }

  const tabs = readSource("components", "ResultTabs.jsx");
  const tabStyles = tabs.slice(tabs.indexOf("const styles"));
  assert.ok(
    /borderBottomColor:\s*"transparent"/.test(tabStyles),
    "기본 상태가 borderBottomColor를 지정하지 않는다",
  );
  assert.ok(
    /active:\s*\{[^}]*borderBottomColor/.test(tabStyles),
    "선택된 탭에 밑줄 색이 없다",
  );
});

test("떠 있는 버튼은 Shell에서만 그린다 (.rise 안에 두면 fixed가 죽는다)", () => {
  // [2026-08-19 — 넣었다 빼고 다시 넣었다. HANDOFF 2.22]
  //   처음엔 Result 안 .rise 내부에 렌더했다. .rise의 transform이 fixed 자손의
  //   containing block을 만들어(HANDOFF 4.8) 버튼이 뷰포트가 아니라 그 div에
  //   붙었고, 화면에 떠 있지 않고 문서와 함께 흘러갔다.
  //   실측으로 확인했다 — 스크롤 +310px에 뷰포트 위치가 −310px 움직였다.
  //
  //   그래서 렌더 위치를 Shell 한 곳으로 고정한다. 이 검사는 "있는가"가 아니라
  //   **"어디서 그리는가"**를 본다 — 있어도 자리가 틀리면 동작하지 않는다.
  const src = readSource("App.jsx");

  const shell = src.slice(src.indexOf("function Shell("));
  const outside = src.slice(0, src.indexOf("function Shell("));

  // 떠 있는 버튼이 늘어날 때마다 여기에 추가한다. 하나만 자리가 틀려도
  // 그 버튼만 조용히 고장난다 — 화면에서는 "있긴 있는데" 로 보인다.
  for (const tag of ["<FloatingRestart", "<FloatingBack"]) {
    assert.ok(shell.includes(tag), `Shell이 ${tag}를 그리지 않는다`);
    assert.ok(
      !outside.includes(tag),
      `${tag}를 화면 컴포넌트 안에서 그린다 — .rise의 transform 때문에 fixed가 죽는다`,
    );
  }
  assert.ok(src.includes("<Closing"), "하단 마무리 문구·되돌아가기가 없다");
});

test("떠 있는 돌아가기는 하단 버튼과 같은 복귀 함수를 쓴다", () => {
  // 경로가 둘로 갈리면 한쪽만 고쳐지는 날이 온다.
  const src = readSource("App.jsx");
  assert.ok(src.includes("const closeAbout ="), "복귀 함수를 따로 두지 않았다");
  // ⚠ prop **순서**에 묶지 않는다. 지키려는 것은 "같은 함수를 쓰는가"이지
  //   "onAboutBack이 첫 prop인가"가 아니다. 2026-09-02에 bottomInset이 앞에
  //   붙으면서 이 회귀가 뜻과 무관하게 깨졌다.
  assert.ok(
    /<Shell[^>]*onAboutBack=\{closeAbout\}/.test(src),
    "떠 있는 버튼이 closeAbout을 쓰지 않는다",
  );
  assert.ok(
    /<About [^>]*onBack=\{closeAbout\}/s.test(src),
    "하단 버튼이 closeAbout을 쓰지 않는다",
  );
});

test("떠 있는 돌아가기는 하단 버튼이 보이면 숨는다 (중복 노출 방지)", () => {
  const src = readSource("components", "common.jsx");
  const block = src.slice(src.indexOf("export function FloatingBack"));
  assert.ok(block.includes("anchorId"), "하단 버튼을 참조하지 않는다");
  assert.ok(
    block.includes("getBoundingClientRect"),
    "하단 버튼이 화면에 있는지 재지 않는다",
  );
  assert.ok(/setShown\(scrolled && !anchorVisible\)/.test(block), "겹침 회피 조건이 없다");
  const about = readSource("components", "About.jsx");
  assert.ok(
    about.includes("id={ABOUT_BACK_ID}"),
    "하단 버튼에 id가 없다 — 떠 있는 버튼이 찾지 못한다",
  );
});

test("소스를 읽는 테스트는 전부 readSource()를 지난다 (같은 함정 4회차 방지)", () => {
  // 주석이 검사를 오염시킨 사건이 세 번 있었다(helpers.js 상단).
  // 세 번째는 **거짓 통과**였다 — 실제 렌더 문구를 XXX로 바꿔도 통과했다.
  // 그래서 규칙을 기계로 고정한다: test/ 안에서 .jsx/.js 소스를 readFileSync로
  // 직접 읽으면 그 자리가 다음 사건의 자리다.
  const dir = join(here);
  for (const file of readdirSync(dir).filter((f) => f.endsWith(".test.js"))) {
    const body = readFileSync(join(dir, file), "utf8");
    const direct = body.match(/readFileSync\([^)]*\.(?:jsx|js)"/g) || [];
    assert.deepEqual(
      direct,
      [],
      `${file}이 소스를 직접 읽는다 — readSource()를 쓸 것: ${direct.join(", ")}`,
    );
  }
});

/* --- 입력창을 비우는 규칙 — **동작으로 검사한다** (2026-08-28 개정) ---------
 *
 * 마음이 힘들어 적은 문장이 화면에 그대로 남아 있는 것이 이 앱에 맞지 않다
 * (2026-08-25 사용자 결정).
 *
 * ⚠⚠ **여기 있던 검사는 소스 문자열을 봤고, 그래서 결함을 놓쳤다.**
 *   `setText("")`가 한 곳인지, `onBack={resetToPicker}`인지를 확인했다.
 *   전부 통과한 채로 **세 번째 경로**가 고장나 있었다 — 분류가 대분류까지만
 *   맞으면(RESULT.CATEGORY) 결과 화면을 거치지 않고 곧장 고르는 화면으로
 *   되묻는데, 그 경로에는 비우는 코드가 아예 없었다. 검사가 볼 수 있는 것은
 *   "어떻게 적혀 있는가"였고 결함은 "어디를 안 지나는가"였다.
 *
 * ★ 그래서 이동을 값으로 꺼냈다(src/lib/flow.js). 아래 검사는 상태 기계를
 *   **실제로 걸어 다니며** 불변식을 확인한다. 새 경로가 생겨도 함께 검사된다.
 * ⛔ 이 자리에 소스 문자열 검사를 다시 넣지 말 것 — 그것이 놓친 결함이다.
 */

const appSrc = readSource("App.jsx");

const CATEGORY = taxonomy.categories[0];
const ACTIONS = [
  { type: FLOW.TYPE, text: "오늘 너무 힘들어" },
  { type: FLOW.SWITCH_TO_PICKER },
  { type: FLOW.PICK_CATEGORY, category: CATEGORY },
  { type: FLOW.BACK },
  { type: FLOW.SUBMIT },
  { type: FLOW.ANSWER, outcome: { kind: RESULT.OK }, category: null },
  { type: FLOW.ANSWER, outcome: { kind: RESULT.CRISIS }, category: null },
  { type: FLOW.ANSWER, outcome: { kind: RESULT.EMPTY }, category: null },
  { type: FLOW.ANSWER, outcome: { kind: RESULT.NO_MATCH }, category: null },
  // ★ 놓쳤던 경로 — 대분류까지만 맞으면 결과 화면 없이 되묻는다.
  { type: FLOW.ANSWER, outcome: { kind: RESULT.CATEGORY }, category: CATEGORY },
  { type: FLOW.RESET },
  { type: FLOW.RESET_TO_PICKER },
];

/**
 * 도달 가능한 상태를 넓이 우선으로 전부 모은다.
 * `answered`는 "앱이 한 번 응답한 뒤"라는 표시다 — TYPE이 그 표를 지운다
 * (그때부터 글자는 다시 사용자가 직접 넣은 것이다).
 */
function walkFlow(seed) {
  const key = (s, answered) =>
    [s.phase, s.mode, s.text, s.result ? s.result.kind : "-",
     s.selectedCategory ? s.selectedCategory.id : "-", answered].join("|");
  const first = { state: seed, answered: false };
  const seen = new Map([[key(seed, false), first]]);
  const queue = [first];
  while (queue.length) {
    const node = queue.shift();
    for (const action of ACTIONS) {
      const next = flowReducer(node.state, action);
      const answered =
        action.type === FLOW.TYPE
          ? false
          : node.answered || ANSWER_ACTIONS.includes(action.type);
      const k = key(next, answered);
      if (seen.has(k)) continue;
      const entry = { state: next, answered };
      seen.set(k, entry);
      queue.push(entry);
    }
  }
  return [...seen.values()];
}

test("앱이 응답한 뒤에는 입력창이 보이는 어느 상태에서도 글자가 남지 않는다", () => {
  const nodes = walkFlow(initialFlow("여기에 적어보세요"));
  const leaks = nodes.filter(
    (n) => n.answered && inputBoxVisible(n.state) && n.state.text !== "",
  );
  assert.equal(
    leaks.length,
    0,
    `응답 뒤 입력창에 글자가 남는 상태 ${leaks.length}개 — 예: ${JSON.stringify(leaks[0])}`,
  );
  // 검사가 실제로 그래프를 걷고 있는지 본다. 상태가 몇 개뿐이면 아무것도 못 봤다.
  assert.ok(nodes.length > 20, `걸은 상태가 ${nodes.length}개뿐이다 — 그래프를 못 걷고 있다`);
  assert.ok(
    nodes.some((n) => n.answered && inputBoxVisible(n.state)),
    "응답 뒤에 입력창이 보이는 상태를 하나도 안 지났다 — 검사가 헛돌고 있다",
  );
});

test("★ 대분류까지만 맞았을 때 — 되묻는 화면을 거쳐 돌아와도 비어 있다", () => {
  // 2026-08-28 이전에 실제로 고장나 있던 경로다. 한 걸음씩 그대로 밟는다.
  let s = flowReducer(initialFlow(""), { type: FLOW.TYPE, text: "불안해" });
  s = flowReducer(s, { type: FLOW.SUBMIT });
  s = flowReducer(s, {
    type: FLOW.ANSWER,
    outcome: { kind: RESULT.CATEGORY },
    category: CATEGORY,
  });
  assert.equal(s.mode, MODE.SELECT, "세분류를 고르는 화면으로 가지 않았다");
  assert.equal(s.selectedCategory.id, CATEGORY.id, "고른 대분류가 화면에 안 실렸다");
  s = flowReducer(s, { type: FLOW.BACK }); // 2단계 → 1단계
  s = flowReducer(s, { type: FLOW.BACK }); // 1단계 → 직접 적기
  assert.ok(inputBoxVisible(s), "직접 적기 화면으로 돌아오지 않았다");
  assert.equal(s.text, "", "되묻고 돌아왔는데 친 글자가 남아 있다");
});

test("고장 주입: 되묻기가 비우지 않으면 불변식이 실제로 깨진다", () => {
  // 검사가 살아 있는지 본다 — 2026-08-28 이전 동작을 그대로 재현한다.
  const broken = (state, action) =>
    action.type === FLOW.ANSWER && action.outcome.kind === RESULT.CATEGORY
      ? { ...state, phase: PHASE.INPUT, mode: MODE.SELECT, selectedCategory: action.category }
      : flowReducer(state, action);
  let s = broken(initialFlow(""), { type: FLOW.TYPE, text: "불안해" });
  s = broken(s, { type: FLOW.SUBMIT });
  s = broken(s, { type: FLOW.ANSWER, outcome: { kind: RESULT.CATEGORY }, category: CATEGORY });
  s = broken(s, { type: FLOW.BACK });
  s = broken(s, { type: FLOW.BACK });
  assert.equal(s.text, "불안해", "고장을 주입했는데도 비어 있다 — 검사가 무엇도 못 본다");
});

test("결과·위기·빈 입력·분류 실패 — 네 복귀 경로가 모두 비운다", () => {
  for (const kind of [RESULT.OK, RESULT.CRISIS, RESULT.EMPTY, RESULT.NO_MATCH]) {
    let s = flowReducer(initialFlow(""), { type: FLOW.TYPE, text: "짜증나" });
    s = flowReducer(s, { type: FLOW.SUBMIT });
    s = flowReducer(s, { type: FLOW.ANSWER, outcome: { kind }, category: null });
    assert.equal(s.phase, PHASE.RESULT, `${kind}이 결과 화면으로 가지 않았다`);
    for (const back of [FLOW.RESET, FLOW.RESET_TO_PICKER]) {
      const done = flowReducer(s, { type: back });
      assert.equal(done.text, "", `${kind} → ${back}에서 글자가 남는다`);
      assert.equal(done.result, null, `${kind} → ${back}에서 결과가 안 지워진다`);
      assert.equal(done.selectedCategory, null, `${kind} → ${back}에서 대분류가 남는다`);
    }
  }
});

test("사용자가 직접 옮겨 다닌 것만으로는 자기 문장을 잃지 않는다", () => {
  // 치고 → 고르는 화면 구경 → 되돌아오면 그대로 있어야 한다. 앱이 응답한 적이 없다.
  let s = flowReducer(initialFlow(""), { type: FLOW.TYPE, text: "불안해" });
  s = flowReducer(s, { type: FLOW.SWITCH_TO_PICKER });
  s = flowReducer(s, { type: FLOW.BACK });
  assert.equal(s.text, "불안해", "스스로 다녀온 것뿐인데 문장이 지워졌다");
  assert.ok(inputBoxVisible(s), "입력 화면으로 돌아오지 않았다");
});

test("App이 상태 기계를 우회하지 않는다 — 낱개 세터가 없다", () => {
  // ⚠ 이동이 흐름 밖에서 일어나면 위 그래프 검사가 그 경로를 못 본다.
  //   결함이 그렇게 생겼다 — 검사가 닿지 않는 경로가 하나 있었다.
  for (const setter of ["setText(", "setMode(", "setPhase(", "setResult(", "setSelectedCategory("]) {
    assert.ok(
      !appSrc.includes(setter),
      `${setter}가 App.jsx에 남아 있다 — flowReducer를 우회하는 경로다`,
    );
  }
  assert.ok(appSrc.includes("useReducer(flowReducer"), "App이 flowReducer를 쓰지 않는다");
});

test("복귀 함수는 인자를 받지 않는다 (onClick이 이벤트를 넘긴다)", () => {
  // ⚠ Msg·Closing이 onClick={onBack}으로 넘기므로 클릭 이벤트가 첫 인자로 들어온다.
  //   목적지를 인자로 받는 함수를 그대로 넘기면 그 자리에 이벤트 객체가 앉는다.
  for (const name of ["reset", "resetToPicker"]) {
    assert.ok(
      appSrc.includes(`const ${name} = useCallback(() =>`),
      `${name}이 인자를 받는다 — onBack에 그대로 넘길 수 없다`,
    );
  }
  assert.ok(
    !appSrc.includes("onBack={goInput}") && !appSrc.includes("onAlt={goInput}"),
    "목적지를 인자로 받는 goInput을 onBack/onAlt에 직접 넘겼다",
  );
});

test("분류 실패 화면이 인라인 핸들러가 아니라 resetToPicker를 쓴다", () => {
  const block = appSrc.slice(appSrc.indexOf("taxonomy.ui.no_match"));
  const msg = block.slice(0, block.indexOf("/>"));
  assert.ok(
    msg.includes("onBack={resetToPicker}"),
    "분류 실패 복귀가 resetToPicker가 아니다 — 입력창이 안 비워진다",
  );
  assert.ok(!msg.includes("dispatch("), "인라인 dispatch가 남아 있다 — 비우는 자리를 우회한다");
});

/* --- `구려`·`구질` 계열 — 어절 결합으로만 넣었다 (2026-08-25) ---------------
 *
 * 실사용 조사에서 "기분이 구려"·"기분이 구질구질해"가 미분류로 나왔다.
 * 매칭 실패가 아니라 **사전에 어휘가 아예 없었다** — 2026-08-20의 `나쁘` 사고와
 * 같은 유형이다.
 *
 * ⛔ 단독형을 넣지 않은 이유가 이 검사의 본체다. 실측으로 확인했다:
 *     `구려`      고구려 · 하시구려(예스러운 어미)가 걸린다
 *     `구질구질`   "날씨가 구질구질하다" — 감정 진술이 아니다
 *   그래서 `기분`이 붙은 형태로만 넣었다. `나빠` 계열과 같은 규칙이다.
 */
const MUST_BE_IRRITATION_GURYEO = [
  "기분이 구려",
  "기분 구려",
  "기분이구려",
  "오늘 기분이 구려",
  "기분이 구질구질해",
  "기분이 구질구질하다",
];

const MUST_NOT_MATCH_GURYEO = [
  "고구려 역사 공부가 안 돼",
  "그렇게 하시구려",
  "어서 오시구려",
  "날씨가 구질구질하다",
  "구질구질한 변명은 그만",
  "옷이 구려",
];

test("`구려`·`구질` 계열이 짜증으로 걸린다", () => {
  const missed = MUST_BE_IRRITATION_GURYEO.filter(
    (s) => subcategoryOf(s) !== "anger.irritation",
  );
  assert.deepEqual(missed, [], `짜증으로 안 걸렸다: ${missed.join(" · ")}`);
});

test("⛔ 단독 `구려`·`구질구질` 함정 — 감정이 아닌 문장이 걸리지 않는다", () => {
  // 이 목록이 통과하는 한 단독형을 넣지 않은 판단이 유지된다.
  // ⚠ 여기에 단독형을 추가하면 이 검사가 먼저 깨진다 — 그것이 목적이다.
  const leaked = MUST_NOT_MATCH_GURYEO.filter(
    (s) => subcategoryOf(s) === "anger.irritation",
  );
  assert.deepEqual(leaked, [], `짜증으로 샜다: ${leaked.join(" · ")}`);
});

/* --- 분류 실패 안내 문구와 경로가 함께 맞는가 (2026-08-25) ------------------
 *
 * ⚠ 문구가 "다른 말로 다시 적어 주셔도 좋아요"라고 말하면 **그 길이 한 번에
 *   닿아야 한다.** 전에는 고르는 화면으로 간 뒤 "직접 적기"를 또 눌러야 했다.
 *   문구만 고치고 버튼을 안 두면 화면이 거짓말을 한다 — 둘을 함께 고정한다.
 */
test("분류 실패 문구가 '아래에서'라고 말하지 않는다 (아래에 아무것도 없다)", () => {
  const [title, sub] = taxonomy.ui.no_match;
  assert.ok(title && sub, "no_match가 [제목, 부연] 두 줄이 아니다");
  assert.ok(
    !`${title}${sub}`.includes("아래에서"),
    "화면에 없는 것을 가리킨다 — 버튼 하나뿐이고 고르는 화면은 눌러야 나온다",
  );
});

test("'다시 적어도 된다'고 말하면 그 버튼이 그 화면에 있다", () => {
  const [, sub] = taxonomy.ui.no_match;
  const promises = /다시 적/.test(sub);
  const block = appSrc.slice(appSrc.indexOf("taxonomy.ui.no_match"));
  const msg = block.slice(0, block.indexOf("/>"));
  const hasAlt = /onAlt=\{reset\}/.test(msg) && /alt="다시 적기"/.test(msg);
  assert.equal(
    promises,
    hasAlt,
    promises
      ? "문구는 다시 적으라고 하는데 그 버튼이 없다 — 두 번 이동이라 문구가 거짓이 된다"
      : "버튼만 있고 문구가 안내하지 않는다",
  );
});

test("보조 버튼은 주 버튼과 위계가 갈린다", () => {
  const src = readSource("components", "common.jsx");
  const msg = src.slice(src.indexOf("export function Msg"));
  const body = msg.slice(0, msg.indexOf("export function", 10));
  assert.ok(/onAlt \? \(/.test(body), "보조 버튼이 조건부가 아니다 — 빈 입력 화면에도 뜬다");
  assert.ok(
    /#ffffff66/.test(body) && /fontSize: 12\.5/.test(body),
    "보조 버튼이 Closing의 조용한 텍스트 버튼과 같은 모양이 아니다",
  );
});

/* ===========================================================================
 * 주제분 섞기 (2026-08-28) — 화면 진입 때 한 번, 그 뒤로는 고정
 * ======================================================================== */

const shuffleSample = [
  { videoId: "a1", channel: "채널A", source: "theme" },
  { videoId: "a2", channel: "채널A", source: "theme" },
  { videoId: "a3", channel: "채널A", source: "theme" },
  { videoId: "b1", channel: "채널B", source: "theme" },
  { videoId: "b2", channel: "채널B", source: "theme" },
  { videoId: "c1", channel: "채널C", source: "theme" },
  { videoId: "c2", channel: "채널C", source: "theme" },
  { videoId: "d1", channel: "채널D", source: "theme" },
];

test("★ 같은 씨앗이면 언제나 같은 순서다 (스크롤·탭 전환에 안 흔들린다)", () => {
  const a = shuffleThemeLayer(shuffleSample, 12345).map((v) => v.videoId);
  const b = shuffleThemeLayer(shuffleSample, 12345).map((v) => v.videoId);
  assert.deepEqual(a, b, "같은 씨앗인데 순서가 달라졌다 — 리렌더마다 목록이 뒤집힌다");
});

test("씨앗이 다르면 순서가 달라진다 (감정을 다시 입력하면 새로 섞인다)", () => {
  const seen = new Set();
  for (const seed of [1, 2, 3, 4, 5, 6]) {
    seen.add(shuffleThemeLayer(shuffleSample, seed).map((v) => v.videoId).join(","));
  }
  assert.ok(seen.size > 1, "씨앗을 바꿔도 순서가 하나뿐이다 — 섞이지 않는다");
});

test("구성은 그대로다 — 섞기가 영상을 잃거나 더하지 않는다", () => {
  for (const seed of [7, 77, 777]) {
    const out = shuffleThemeLayer(shuffleSample, seed);
    assert.equal(out.length, shuffleSample.length);
    assert.deepEqual(
      out.map((v) => v.videoId).sort(),
      shuffleSample.map((v) => v.videoId).sort(),
    );
  }
});

test("★ 같은 채널이 연속으로 붙는 것을 줄인다", () => {
  // 배치가 주는 순서는 채널 묶음이다 — 그대로면 인접 중복이 4건이다
  const grouped = shuffleSample;
  let before = 0;
  for (let i = 1; i < grouped.length; i += 1) {
    if (grouped[i].channel === grouped[i - 1].channel) before += 1;
  }
  assert.equal(before, 4, "표본 전제가 바뀌었다");

  for (const seed of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) {
    const out = shuffleThemeLayer(grouped, seed);
    let after = 0;
    for (let i = 1; i < out.length; i += 1) {
      if (out[i].channel === out[i - 1].channel) after += 1;
    }
    assert.equal(after, 0, `씨앗 ${seed}에서 인접 중복이 ${after}건 남았다`);
  }
});

test("한 채널이 절반을 넘으면 붙는 것을 감수한다 (구성은 지킨다)", () => {
  // 6건 중 5건이 같은 채널이면 어떻게 놓아도 붙는다 — 그때 목록을 망가뜨리지 않는지
  const skewed = [
    { videoId: "x1", channel: "채널X" },
    { videoId: "x2", channel: "채널X" },
    { videoId: "x3", channel: "채널X" },
    { videoId: "x4", channel: "채널X" },
    { videoId: "x5", channel: "채널X" },
    { videoId: "y1", channel: "채널Y" },
  ];
  const out = shuffleThemeLayer(skewed, 42);
  assert.equal(out.length, 6, "영상이 사라졌다");
  assert.deepEqual(
    out.map((v) => v.videoId).sort(),
    skewed.map((v) => v.videoId).sort(),
    "구성이 바뀌었다",
  );
});

test("1건 이하는 그대로 돌려준다", () => {
  assert.deepEqual(shuffleThemeLayer([], 1), []);
  const one = [shuffleSample[0]];
  assert.deepEqual(shuffleThemeLayer(one, 1), one);
  assert.deepEqual(shuffleThemeLayer(null, 1), []);
});

test("⛔ 섞기 안에서 Math.random을 쓰지 않는다 (씨앗이 유일한 입력이다)", () => {
  // readSource()로 읽는다 — 주석에 Math.random이 인용돼 있어 원문으로 보면 거짓 실패한다
  const src = readSource("lib", "videos.js");
  const from = src.indexOf("export function shuffleThemeLayer");
  const next = src.indexOf("export function", from + 10);
  const body = src.slice(from, next < 0 ? undefined : next);
  assert.ok(
    !body.includes("Math.random"),
    "shuffleThemeLayer가 Math.random을 부른다 — 리렌더마다 순서가 바뀐다",
  );
});

test("폴백 층은 섞지 않는다 — 배치의 최신순을 그대로 쓴다", () => {
  const app = readSource("App.jsx");
  const call = app.slice(app.indexOf("const layers = useMemo"), app.indexOf("const layers = useMemo") + 400);
  assert.ok(call.includes("theme: shuffleThemeLayer"), "주제분에 섞기가 안 걸려 있다");
  assert.ok(!call.includes("fallback: shuffleThemeLayer"), "폴백까지 섞고 있다");
});

/* --- 키보드가 올라올 때 입력란을 끌어온다 (2026-09-02 · HANDOFF 2.107) ------
 *
 * ⚠⚠ **이 검사들이 지킬 수 있는 것과 못 하는 것을 먼저 적는다.**
 *   여기서 보는 것은 **소스의 모양**뿐이다. 이 기능의 성패는 레이아웃 값이라
 *   (뷰포트가 얼마나 줄고, 그때 셋이 보이는가) 노드 테스트로는 단언할 수 없다.
 *
 *   ✅ 단언할 수 있다
 *      · 훅이 있고 TextMode가 쓴다 (다른 화면으로 새지 않는다)
 *      · 방아쇠가 focus가 아니라 **축소**다 — 임계 상수와 resize 구독이 있다
 *      · visualViewport와 window를 **둘 다** 듣는다
 *      · 포커스가 그 입력란일 때만 움직인다
 *      · block "center"다 ("nearest"로 되돌아가면 「골라서 찾을래요」가 잘린다)
 *      · 커질 때는 아무것도 하지 않는다 (되돌리는 코드가 없다)
 *   ⛔ 단언할 수 없다 — **실측으로만 안다** (HANDOFF 2.107에 수치가 있다)
 *      · 키보드가 뜬 뒤 셋이 실제로 보이는가
 *      · 입력란이 화면 위로 사라지지 않는가
 *      · 갈래 A(WebView ≥140)에서 동작하는가  ← 시험할 방법이 없다
 *      · 뷰포트가 안 줄어드는 구성에서 조용히 아무 일도 안 하는 것
 */
test("키보드 훅이 입력 화면에만 있다", () => {
  // ⛔ 결과 화면·About으로 새면 안 된다. TextMode가 언마운트되면 리스너도 사라진다.
  const calls = appSrc.match(/useKeyboardReveal\(/g) || [];
  assert.equal(calls.length, 2, `정의 1 + 호출 1이어야 한다 (${calls.length}곳)`);
  const textMode = appSrc.slice(appSrc.indexOf("function TextMode("));
  assert.ok(
    textMode.slice(0, 400).includes("useKeyboardReveal(inputRef)"),
    "TextMode가 훅을 쓰지 않는다",
  );
});

test("방아쇠가 focus가 아니라 뷰포트 축소다", () => {
  // ⚠ focus 시점에는 뷰포트가 아직 안 줄어 스크롤할 것이 없다 — 그래서 resize다.
  const hook = appSrc.slice(appSrc.indexOf("function useKeyboardReveal("));
  assert.ok(!/onFocus|addEventListener\("focus"/.test(hook), "focus에 걸려 있다");
  assert.ok(hook.includes("KEYBOARD_SHRINK_MIN"), "축소 임계값이 없다");
  assert.ok(
    hook.includes('vp?.addEventListener("resize"') &&
      hook.includes('window.addEventListener("resize"'),
    "visualViewport와 window를 둘 다 듣지 않는다",
  );
});

test("포커스가 그 입력란일 때만 · 커질 때는 아무것도 안 한다", () => {
  const hook = appSrc.slice(appSrc.indexOf("function useKeyboardReveal("));
  assert.ok(
    hook.includes("document.activeElement !== el"),
    "포커스 확인이 없다 — 회전 같은 다른 축소에 끌려간다",
  );
  assert.ok(
    /if \(shrank < KEYBOARD_SHRINK_MIN\) return;/.test(hook),
    "축소량 판정이 없다 — 커질 때도 움직인다",
  );
  // ⛔ 되돌리는 코드를 넣지 않는다. 문서가 뷰포트만 해지면 브라우저가
  //   scrollY를 스스로 0으로 되돌린다 (실측 99 → 0).
  assert.ok(!/scrollTo\(0, *0\)/.test(hook), "되돌리는 코드가 들어왔다 — 브라우저가 한다");
});

test('block "center"다 — "nearest"로 내려가지 않는다', () => {
  // ⛔ "nearest"는 30px만 올려 「골라서 찾을래요」가 잘린 채 남는다. 그 버튼은
  //   자연어로 옮기기 어려운 사람이 키워드 선택으로 가는 통로다 (사용자 판단).
  const hook = appSrc.slice(appSrc.indexOf("function useKeyboardReveal("));
  assert.ok(hook.includes('block: "center"'), 'block "center"가 아니다');
  assert.ok(!hook.includes('block: "nearest"'), '"nearest"로 되돌아갔다');
});
