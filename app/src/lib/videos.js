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
 * unknown이 양쪽에 들어가므로 [말씀] 합계 + [찬양] 합계는 전체보다 클 수 있다.
 * 그게 정상이다 — 개수를 맞추려고 unknown을 한쪽에만 넣으면 반대쪽 화면이 빈다.
 */
export function visibleVideos(videos, mediaType) {
  if (!Array.isArray(videos)) return [];
  return videos.filter(
    (v) => v.media_type === mediaType || v.media_type === MEDIA.UNKNOWN,
  );
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
