/**
 * 이어서 읽기 — 장 본문을 받아 오고, 페이지로 자른다.
 *
 * 이 모듈은 **장 하나만 안다.** 구절 데이터도, 감정 세분류도, 위기 풀도 모른다.
 * 받는 것은 {book, chapter, from} 세 값이고 그것은 verses.json이 들고 있다
 * (gen_verses_json.py의 read 필드 — ref 파싱은 빌드 타임에 끝난다).
 *
 * [왜 원문을 번들에 넣지 않는가 — 2026-08-20 실측]
 *   전문 66권      gzip +1,254,618   앱 전체(98,225)의 12.8배
 *   닿는 장 174개  gzip   +165,904   1.7배
 *   장 단위 요청   gzip 장당 1,234(중앙값) · 최대 4,616 (시편 119편)
 *   번들에 넣는 두 안은 **탭을 한 번도 열지 않는 사용자가 비용을 전부 낸다.**
 *
 *   ⚠ 대신 오프라인 첫 방문에서는 못 받는다. 그때 화면이 하는 말은
 *     ChapterReader가 정하고, **실패로 말하지 않는다** — 구절 화면 자체는
 *     번들이라 멀쩡하고, 여기서 못 받은 것은 곁가지 하나다.
 *     이 앱의 오프라인 원칙("네트워크가 없어도 구절 화면은 떠야 한다",
 *     vite.config.js)이 본문까지 확장되는지는 아직 판단하지 않았다.
 *     확장한다고 정하면 174개 장을 지연 청크로 번들에 넣는 안이 대기 중이다.
 */

/**
 * 한 페이지에 몇 절인가 — 4절.
 *
 * [실측으로 정했다. 근거는 VerseCard가 남긴 기준선이다]
 *   VerseCard.jsx가 360×640에서 131자 / 18px / 행간 1.95 → 211px(6줄)을 재 뒀다.
 *   거기서 줄당 21.8자를 얻어 174개 장 4,283절 전부에 적용했다.
 *
 *   절 길이 분포   최소 4자 · p25 35 · 중앙값 45 · p75 62 · p90 82 · 최대 166
 *
 *   ★ 중앙값 45자가 줄바꿈 경계에 정확히 걸린다 — 이것이 크기를 정했다.
 *       18px  줄당 21.8자 → 45자 = 3줄     4절 페이지 442px
 *       17px  줄당 23.1자 → 45자 = 2줄     4절 페이지 294px   1px 차이로 33% 준다
 *
 *   그래서 17px을 쓰고(ChapterReader), 그 크기에서 페이지를 정했다.
 *              중앙값 본문   상위 10% 본문
 *     3절         217px         405px    이동이 잦다 (장 중앙값이 6→8페이지)
 *     4절         294px         545px    ← 채택
 *     5절         370px         685px    상위 10%에서 640px를 넘긴다
 *
 * ⚠ 이 값을 바꾸면 위 수치부터 다시 잰다. 그리고 initialCursor의 "뒤로 당기기"가
 *   페이지 크기에 걸려 있어 첫 페이지 위치가 함께 바뀐다.
 */
export const PAGE_SIZE = 4;

/**
 * 장 파일 경로. gen_krv_chapters.py가 app/public/krv/에 같은 구조로 만든다.
 *
 * typeof 가드는 노드 테스트용이다 — vite define은 빌드에서만 치환되고,
 * 테스트는 이 모듈을 그대로 import한다 (About.jsx가 __APP_VERSION__에
 * 쓰는 것과 같은 장치).
 */
const KRV_BASE = typeof __KRV_BASE__ === "string" ? __KRV_BASE__ : "/krv/";

export function chapterPath(book, chapter) {
  return `${KRV_BASE}${book}/${chapter}.json`;
}

/**
 * 받아 온 장을 기억한다.
 *
 * 원문은 바뀌지 않으므로 무효화가 필요 없다. 같은 세션에서 "다른 구절"을
 * 눌러 같은 장으로 돌아오는 경우가 흔한데(한 세분류에 같은 편이 여러 번
 * 있다 — HANDOFF 2.24 편중 자료), 그때 다시 받지 않는다.
 *
 * 실패는 캐시하지 않는다. 오프라인에서 한 번 실패한 장이 연결된 뒤에도
 * 계속 실패하면, 그건 캐시가 만든 고장이다.
 */
const cache = new Map();

/**
 * 장 본문을 받는다. 실패하면 null이다 — 던지지 않는다.
 *
 * 호출부가 try/catch를 잊는 것이 곧 흰 화면이기 때문이다. sync.js가 배경
 * 갱신 실패를 조용히 false로 돌려주는 것과 같은 판단이다.
 */
export async function loadChapter(book, chapter) {
  const key = `${book}/${chapter}`;
  if (cache.has(key)) return cache.get(key);

  try {
    const response = await fetch(chapterPath(book, chapter));
    if (!response.ok) return null;
    const data = await response.json();
    if (!data || !Array.isArray(data.verses) || data.verses.length === 0) return null;
    cache.set(key, data);
    return data;
  } catch {
    return null;
  }
}

/** 테스트·개발용. 화면 코드에서는 쓰지 않는다. */
export function __clearChapterCache() {
  cache.clear();
}

/**
 * 장의 절 배열을 **그릴 단위**로 바꾼다.
 *
 * 보통은 절 하나가 단위 하나다. 예외가 하나 있다 —
 *
 * [합본 구간 — 원문을 그대로 보여줄 때만 드러나는 함정]
 *   개역한글은 여러 절을 나누지 않고 합쳐 싣는 구간이 있고, 원문 데이터는
 *   절 수(31,102)를 맞추려고 그 합본 본문을 **각 절 번호에 똑같이 복제**한다.
 *   지금까지 화면에 나온 적이 없는 이유는 krv_source.verses_in_range가 그런
 *   ref를 거부해서다(수록 대상에서 뺐다). 장 전체를 그리면 막을 것이 없다.
 *
 *   174개 장 전수 조사 결과 해당 장은 둘이다.
 *     이사야 30장   1·2절이 같은 본문
 *     시편 92편     1·2·3절이 같은 본문
 *
 *   그래서 연속으로 같은 본문이면 절 번호를 묶어("1-3") 한 번만 그린다.
 *   동일성유지권 문제는 없다 — 본문을 한 글자도 바꾸지 않고, 오히려 원문의
 *   원래 제시 방식으로 되돌리는 것이다(대한성서공회도 "1-3"으로 표시한다).
 *
 * ⚠ **떨어져 있는 반복은 절대 합치지 않는다.** 같은 조사에서 5개 장이
 *   걸렸는데 전부 후렴이었다 — 원문이 의도적으로 반복하는 것이다.
 *     시편 46:7·11 · 시편 57:5·11 · 시편 107:8·15·21·31
 *     열왕기상 19:10·14 · 민수기 6:1·22
 *   판별은 **절 번호가 붙어 있는가** 하나로 갈린다. 그래서 이 함수는
 *   Set이나 Map으로 중복을 세지 않고 이웃만 본다 — 집합으로 세는 순간
 *   후렴이 함께 걸린다.
 *
 * [페이지를 절이 아니라 단위로 세는 이유]
 *   묶인 구간이 페이지 경계에 걸치면 같은 본문이 두 페이지에 나뉘어 두 번
 *   보인다. 단위로 세면 그 일이 구조적으로 생기지 않는다. 지금 데이터에서는
 *   두 구간 모두 1절에서 시작하고 3절 이하라 걸칠 일이 없지만, 걸치지 않는
 *   것이 **우연이어서는 안 된다.**
 */
export function chapterUnits(verses) {
  const units = [];
  let index = 0;
  while (index < verses.length) {
    let end = index;
    while (end + 1 < verses.length && verses[end + 1] === verses[index]) end += 1;
    units.push({
      from: index + 1,
      to: end + 1,
      label: end > index ? `${index + 1}-${end + 1}` : `${index + 1}`,
      text: verses[index],
    });
    index = end + 1;
  }
  return units;
}

/** 마지막 페이지의 커서. 장이 한 페이지보다 짧으면 0이다. */
export function lastCursor(units) {
  return Math.max(0, units.length - PAGE_SIZE);
}

/** 커서를 장 안으로 가둔다. */
export function clampCursor(cursor, units) {
  if (!Number.isFinite(cursor)) return 0;
  return Math.min(Math.max(0, Math.trunc(cursor)), lastCursor(units));
}

/**
 * 탭을 처음 열 때의 커서.
 *
 * @param from 인용한 구절의 **다음 절 번호** (verses.json의 read.from)
 *
 * [세 갈래다. 289건에 돌려 보고 정했다]
 *   남은 절이 한 페이지 이상   240건   그 자리에서 시작한다
 *   남은 절이 1~2건            29건   장 끝에 맞춰 뒤로 당긴다
 *   이어 읽을 절이 없다        20건   장 처음부터 연다
 *
 * ★ 세 번째가 없으면 시편 23:6·로마서 8:38-39 같은 대표 구절에서 빈 화면이
 *   된다. 로마서 8장은 39절로 끝나므로 "38-39 다음"은 존재하지 않는다.
 *
 * ⚠ 세 갈래 중 어디로 갔는지 화면에서 말하지 않는다(2026-08-20 결정 D).
 *   장 머리("로마서 8장")와 절 번호가 이미 위치를 알려준다. 굳이 설명하면
 *   "원래는 뒤부터여야 하는데"라는 없던 기대를 만든다.
 */
export function initialCursor(from, units) {
  if (units.length === 0) return 0;

  // 인용이 장의 마지막이라 이어 읽을 것이 없다 → 장 처음.
  const lastVerse = units[units.length - 1].to;
  if (!Number.isFinite(from) || from > lastVerse) return 0;

  const index = units.findIndex((unit) => unit.to >= from);
  if (index < 0) return 0;
  return clampCursor(index, units);
}

/** 커서 위치의 한 페이지. */
export function pageUnits(units, cursor) {
  const start = clampCursor(cursor, units);
  return units.slice(start, start + PAGE_SIZE);
}
