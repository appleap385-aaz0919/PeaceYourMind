/**
 * videos.json 접근 — 감정 화면 목록과 위기 풀을 읽는 유일한 지점.
 *
 * ⚠ 이 파일의 존재 이유는 격리다 (FYM 승계).
 *
 *   위기 영상은 최상위 `crisis` 객체에만 있고 `subcategories` 배열에는 없다.
 *   배치가 빌드 시점에 두 집합이 서로소임을 단언하고, 워크플로가 배포 전에 다시
 *   확인한다. 앱 쪽 규칙: 두 함수는 서로의 데이터에 접근하지 않는다.
 *
 * [PYM 고유 — 두 개의 축]
 *   media_type   sermon / worship / unknown. 사용자가 [말씀]/[찬양] 토글로 고른다.
 *                unknown은 **양쪽 모두에 노출한다** — 판별 실패로 영상이 사라지는
 *                것보다 낫다 (PLAN.md 3.4).
 *   source       theme / fallback. 주제 태깅분과 폴백이다.
 *                **섞지 않는다.** 근거의 강도가 다르고, 섞으면 사용자가
 *                "이게 왜 내 감정에 맞지?"라고 느끼는 순간 화면 전체를 의심한다.
 *                그래서 이 파일은 하나의 평평한 목록을 돌려주지 않고 층을 나눠 준다.
 */

// 위기 화면 노출 개수 — taxonomy.yaml content_policy.framing
// "노출 개수 4~6개로 제한(선택 부담 최소화)"
const CRISIS_MIN_SHOWN = 4;
const CRISIS_MAX_SHOWN = 6;

export const MEDIA = { SERMON: "sermon", WORSHIP: "worship", UNKNOWN: "unknown" };
export const SOURCE = { THEME: "theme", FALLBACK: "fallback" };

/** 세분류 화면 데이터. crisis에는 접근하지 않는다. */
export function screenFor(data, subcategoryId) {
  if (!data || !Array.isArray(data.subcategories)) return null;
  return data.subcategories.find((s) => s.id === subcategoryId) || null;
}

/**
 * 토글 한쪽에 실제로 보이는 영상.
 *
 * ★★ 2026-08-28 — **unknown은 어느 탭에도 넣지 않는다** (사용자 결정).
 *   ⚠ 배치의 `lib/selection.visible_count()`와 **같은 기준이어야 한다.**
 *     둘이 어긋나면 배치가 세는 수와 사용자가 보는 수가 달라진다.
 *
 * [원래는 양쪽에 넣었다 — 전제가 달라져 뒤집혔다]
 *   "판별 실패로 영상이 사라지는 것보다 양쪽에 보이는 편이 낫다"(PLAN.md 3.4)는
 *   판단은 unknown이 많던 시절의 것이다.
 *     2026-08-26  unknown 79건(4.5%) → 빼면 주제분 −39
 *     2026-08-28  unknown 25건(1.4%) → 빼면 주제분 −6
 *   얻는 것은 그대로다 — 탭이 정확히 20건이 되고, [말씀]을 눌러도 [찬양]을 눌러도
 *   같은 영상이 나오던 화면(11/24개)이 사라진다.
 *
 * ⚠ 배포된 캐시·번들 시드에는 unknown이 남아 있을 수 있다(시드 13건).
 *   그것들은 이제 어느 탭에도 안 보인다 — 데이터가 아니라 **표시 규칙**이
 *   바뀐 것이므로 캐시를 비울 필요는 없다. 다음 배치부터는 애초에 안 담긴다.
 */
export function visibleVideos(videos, mediaType) {
  if (!Array.isArray(videos)) return [];
  return videos.filter((v) => v.media_type === mediaType);
}

/**
 * 화면에 그릴 두 층을 만든다. **여기서 합치지 않는다.**
 *
 * @returns {{theme: object[], fallback: object[]}}
 */
export function layersFor(videos, mediaType) {
  const visible = visibleVideos(videos, mediaType);
  return {
    theme: visible.filter((v) => v.source !== SOURCE.FALLBACK),
    fallback: visible.filter((v) => v.source === SOURCE.FALLBACK),
  };
}

/**
 * 씨앗 하나로 결정되는 난수 — 같은 씨앗이면 언제나 같은 순열이다 (mulberry32).
 *
 * Math.random()을 직접 쓰지 않는 이유: 스크롤·탭 전환으로 리렌더될 때마다
 * 순서가 바뀌면 안 된다. 씨앗을 화면 진입 때 한 번 뽑고, 섞기는 그 씨앗에 대해
 * **순수 함수**여야 몇 번을 다시 계산해도 같은 목록이 나온다.
 */
function seededRandom(seed) {
  let a = (seed >>> 0) || 1;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * 주제분을 **개별 영상 단위로** 섞는다 (2026-08-28 · 사용자 결정).
 *
 * [왜 — 배치가 주는 순서는 채널 묶음이다]
 *   videos.json의 주제분은 "채널 묶음 + 채널 안에서만 최신순"으로 온다.
 *   배치가 채널을 차례로 돌며 수집하기 때문이다(lib/selection.fill_balanced 주석).
 *   실측(anger.irritation [찬양] 2026-08-27): ANOINTING 3건 → 옹기장이 1건 →
 *   택피아노 3건 → mini Music 3건 … 한 채널이 연속으로 3건씩 붙어 나왔다.
 *   사용자에게는 "이 채널 것만 계속 나온다"로 읽힌다.
 *
 * [언제 섞는가 — 화면에 들어갈 때 한 번]
 *   씨앗은 결과 화면이 뜰 때 한 번 뽑는다(App.jsx의 Result). 그래서
 *     · 스크롤해도 안 바뀐다
 *     · [말씀]↔[찬양] 토글을 오가도 각 탭의 순서는 그대로다
 *     · 감정을 다시 입력하면 Result가 새로 떠서 새 씨앗을 받는다
 *   ⛔ 이 함수 안에서 Math.random()을 부르지 말 것. 그 순간 위 세 가지가 깨진다.
 *
 * [같은 채널이 연속으로 붙지 않게]
 *   섞은 뒤 인접한 같은 채널을 한 번 흩는다. 완전히 없애지는 못한다 —
 *   한 채널이 목록의 절반을 차지하면 어디엔가는 붙는다. 그때는 **그대로 둔다**
 *   (억지로 떼려고 순서를 더 흔들면 무작위성의 의미가 없다).
 *
 * ⚠ 폴백 층에는 쓰지 않는다. 그쪽은 배치가 **전체 최신순**으로 주고
 *   "요즘 올라온 것들"이라는 헤더가 그 순서를 약속한다.
 */
export function shuffleThemeLayer(videos, seed) {
  if (!Array.isArray(videos) || videos.length < 2) return videos || [];
  const rnd = seededRandom(seed);
  const out = videos.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rnd() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  // 인접 중복 흩기 — 섞인 순서를 지키되 다음 자리에 직전과 다른 채널을 놓는다.
  //
  // ★ **남은 개수가 많은 채널을 먼저 낸다.** 그냥 "직전과 다른 첫 번째"를 집으면
  //   많이 남은 채널이 끝에 몰려 마지막에 붙는다 (실측: 8건 표본 씨앗 4에서
  //   `CBCBADAA` — 끝의 AA가 그것이다). 많은 쪽을 먼저 흘려보내야 끝까지 풀린다.
  //   한 채널이 과반이 아니면 이 방식은 인접 중복을 0으로 만든다.
  //
  // ⚠ 동률이면 **섞인 순서**가 가른다 — 그래서 씨앗이 여전히 순서를 정한다.
  // ⚠ 한 채널이 목록의 절반을 넘으면 어떻게 놓아도 붙는다. 그때는 감수한다.
  const rest = out.map((v, i) => ({ v, i }));
  const left = new Map();
  for (const { v } of rest) left.set(v.channel, (left.get(v.channel) || 0) + 1);

  const spread = [];
  while (rest.length) {
    const prev = spread.length ? spread[spread.length - 1].channel : null;
    let best = -1;
    for (let k = 0; k < rest.length; k += 1) {
      const ch = rest[k].v.channel;
      if (ch === prev) continue;
      if (best < 0 || left.get(ch) > left.get(rest[best].v.channel)) best = k;
    }
    if (best < 0) best = 0; // 남은 것이 전부 직전과 같은 채널이다
    const [taken] = rest.splice(best, 1);
    left.set(taken.v.channel, left.get(taken.v.channel) - 1);
    spread.push(taken.v);
  }
  return spread;
}

/**
 * 이 세분류에서 각 토글에 몇 건이 보이는가.
 *
 * 한쪽이 0이어도 **버튼을 비활성화하지 않는다** (PLAN.md 3.4).
 * 비활성 버튼은 "고장"으로 읽히고, 문장은 상황 설명으로 읽힌다.
 * 화면은 이 값을 보고 "지금은 말씀 영상만 있어요"를 띄운다.
 */
export function toggleCounts(videos) {
  return {
    [MEDIA.SERMON]: visibleVideos(videos, MEDIA.SERMON).length,
    [MEDIA.WORSHIP]: visibleVideos(videos, MEDIA.WORSHIP).length,
  };
}

/**
 * 위기 영상. data.crisis만 읽는다.
 *
 * 매 방문 풀에서 4~6개를 랜덤으로 고른다(같은 영상이 고정되지 않게).
 * 채널이 겹치지 않게 담되, 채널 종류가 모자라면 개수를 우선한다 — 노출 개수는
 * 정책값이고 채널 중복 회피는 개선이다 (FYM 판단 승계).
 *
 * **토글도 폴백도 적용하지 않는다.** 위기 화면은 상담 안내가 최상단인 단일
 * 목록이다. media_type으로 거르지 않는 이유도 같다 — 형식 선택은 감정 화면의
 * 기능이고, 여기서 거르면 안 그래도 얇은 풀이 더 얇아진다.
 */
export function getCrisisVideos(data) {
  const pool = data?.crisis?.videos;
  if (!Array.isArray(pool) || pool.length === 0) return [];

  const count = Math.min(
    pool.length,
    CRISIS_MIN_SHOWN +
      Math.floor(Math.random() * (CRISIS_MAX_SHOWN - CRISIS_MIN_SHOWN + 1)),
  );
  return takeDistinctChannels(shuffle(pool), count);
}

function takeDistinctChannels(list, count) {
  const picked = [];
  const seen = new Set();
  const skipped = [];
  for (const video of list) {
    if (picked.length >= count) break;
    if (seen.has(video.channel)) {
      skipped.push(video);
      continue;
    }
    seen.add(video.channel);
    picked.push(video);
  }
  for (const video of skipped) {
    if (picked.length >= count) break;
    picked.push(video);
  }
  return picked;
}

function shuffle(list) {
  const copy = [...list];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

/** ISO 8601 duration -> "12:34". 파싱 실패는 빈 문자열(배지를 안 그린다). */
export function formatDuration(iso) {
  const match = /^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(iso || "");
  if (!match) return "";
  const [, d, h, m, s] = match.map((x) => (x ? Number(x) : 0));
  const total = d * 86400 + h * 3600 + m * 60 + s;
  if (!total) return "";
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

/** 썸네일 URL — videoId로 조립한다 (배치가 URL을 담지 않는 이유). */
export function thumbnailUrl(videoId) {
  return `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
}

export function watchUrl(videoId) {
  return `https://www.youtube.com/watch?v=${videoId}`;
}
