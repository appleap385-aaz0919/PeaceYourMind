/**
 * 감정 분류 — emotion-prototype.jsx의 classify()를 taxonomy 기반으로 옮긴 것.
 *
 * 위기 검사가 항상 먼저다 (taxonomy.yaml safety: "분류보다 항상 먼저 검사").
 * 감정 매칭 코드에 닿기 전에 반환하므로, 아래 점수 계산이 어떻게 바뀌어도
 * 위기 경로가 영향을 받지 않는다.
 *
 * Phase 2(온디바이스 모델)는 2026-08-18에 **검토 후 보류**됐다. 미착수가 아니다 —
 * 모델은 "모르겠다"를 말하지 못하는데, 아래 NO_MATCH → 선택 UI 경로가 이 서비스의
 * 안전 장치이기 때문이다. 상세는 taxonomy.yaml의 [결정 기록] Phase 2.
 *
 * 그래도 두 단계를 분리해 둔 것은 유지한다. 나중에 재검토 조건이 충족되면
 * 임베딩 유사도를 scoreSubcategories() **뒤**(사전이 못 잡았을 때)에 끼우고,
 * 임계값에 못 미치면 지금처럼 NO_MATCH로 떨어뜨린다.
 * ⚠ 어느 경우에도 위기 검사보다 앞에 두지 않는다.
 */

import { normalize } from "./normalize.js";

export const RESULT = {
  EMPTY: "empty",
  CRISIS: "crisis",
  OK: "ok",
  CATEGORY: "category", // 대분류까지만 확실하다 — 세분류는 사용자가 고른다
  NO_MATCH: "nomatch",
};

/**
 * @returns {{kind: string, subcategory?, category?, hits?: string[]}}
 */
export function classify(text, taxonomy) {
  const input = normalize(text);
  if (!input) return { kind: RESULT.EMPTY };

  // --- 위기 검사: 무조건 먼저 ---------------------------------------------
  // 두 층이다. 부분 문자열(crisis_keywords)과 단독 입력(crisis_exact).
  // 층을 나눈 이유는 taxonomy.yaml [단독 입력]에 있다 — "죽어"는 문장 안에서는
  // 사별일 수 있지만("할머니가 죽어서 슬퍼요") 그 말만 적혔으면 위기다.
  for (const keyword of taxonomy.safety.crisis_keywords) {
    const needle = normalize(keyword);
    if (needle && input.includes(needle)) {
      // 어떤 키워드에 걸렸는지는 반환하지 않는다. 화면에 표시할 일이 없고,
      // 로그로도 남기지 않는다 (입력은 기기 밖으로 나가지 않는다).
      return { kind: RESULT.CRISIS };
    }
  }
  if (isCrisisAlone(input, taxonomy.safety.crisis_exact)) {
    return { kind: RESULT.CRISIS };
  }

  const best = scoreSubcategories(input, taxonomy);
  if (best) return { kind: RESULT.OK, ...best };

  // --- 대분류 폴백 ---------------------------------------------------------
  // "답답해"처럼 대분류 이름만 말한 입력은 세분류를 특정할 근거가 없다.
  // 임의로 하나를 고르면 틀린 공감 문장을 먼저 내밀게 되므로,
  // 여기까지만 알아들었다고 하고 세분류는 사용자에게 묻는다.
  // 세분류가 먼저 걸리면 그쪽이 이긴다 — 이 층은 폴백이다.
  const category = matchCategory(input, taxonomy);
  if (category) return { kind: RESULT.CATEGORY, ...category };

  return { kind: RESULT.NO_MATCH };
}

// 한글 자모만으로 된 문자(ㅠㅋㅎ…). 감정 표시일 뿐 뜻을 바꾸지 않는다.
// ⚠ normalize()에서 지우지 않는다 — scripts/lib/normalize.py와 문자 단위로
//   같아야 하고, 배치의 blocklist 매칭이 그 동일성에 걸려 있기 때문이다.
//   자모 제거는 이 검사 안에서만 한다.
const JAMO_ONLY = /[\u3131-\u318e]/gu;

/**
 * 입력이 그 말 **하나뿐**인가 (crisis_exact).
 *
 * 정규화가 공백·문장부호를 이미 지우므로 "죽 어" · "죽어..." 도 여기 걸리고,
 * 자모를 걷어내므로 "죽어ㅠㅠ" 도 걸린다. 반대로 "할머니가 죽어서 슬퍼요"는
 * 남는 글자가 있어 걸리지 않는다 — 그 입력은 sadness.loss로 가야 한다.
 */
function isCrisisAlone(input, exactWords) {
  if (!exactWords || !exactWords.length) return false;
  const bare = input.replace(JAMO_ONLY, "");
  if (!bare) return false;
  return exactWords.some((word) => bare === normalize(word).replace(JAMO_ONLY, ""));
}

/** 대분류 keywords만 본다 (taxonomy.yaml categories[].keywords). */
function matchCategory(input, taxonomy) {
  let best = null;
  for (const category of taxonomy.categories) {
    const hits = (category.keywords || []).filter((k) => {
      const needle = normalize(k);
      return needle && input.includes(needle);
    });
    if (!hits.length) continue;

    const score = hits.length * 1000 + hits.reduce((sum, k) => sum + k.length, 0);
    if (!best || score > best.score) best = { score, category, hits };
  }
  return best;
}

/**
 * 정규화된 입력에 대해 세분류별 점수를 매겨 최상위를 고른다.
 *
 * 점수 규칙은 taxonomy.yaml normalization.matching 그대로:
 *   (1) 매칭된 키워드 수  (2) 키워드 길이 합(긴 키워드 우선)
 * 두 번째 항이 필요한 이유: "불안"과 "가슴이답답하고불안"이 함께 걸리면
 * 더 구체적으로 서술한 쪽이 사용자의 상태에 가깝다.
 */
function scoreSubcategories(input, taxonomy) {
  let best = null;
  for (const category of taxonomy.categories) {
    for (const subcategory of category.subcategories) {
      const hits = subcategory.keywords.filter((k) => {
        const needle = normalize(k);
        return needle && input.includes(needle);
      });
      if (!hits.length) continue;

      const score =
        hits.length * 1000 + hits.reduce((sum, k) => sum + k.length, 0);
      if (!best || score > best.score) {
        best = { score, subcategory, category, hits };
      }
    }
  }
  return best;
}

/** 대분류 id로 세분류 목록을 얻는다 (선택 UI용). */
export function subcategoriesOf(taxonomy, categoryId) {
  const category = taxonomy.categories.find((c) => c.id === categoryId);
  return category ? category.subcategories : [];
}

/** 세분류 id로 {category, subcategory}를 찾는다. */
export function findSubcategory(taxonomy, subcategoryId) {
  for (const category of taxonomy.categories) {
    const subcategory = category.subcategories.find((s) => s.id === subcategoryId);
    if (subcategory) return { category, subcategory };
  }
  return null;
}
