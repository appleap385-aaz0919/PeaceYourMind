/**
 * 영상 목록 — 주제분과 폴백을 **층으로 나눠** 그린다.
 *
 * [두 층을 섞지 않는 이유 — UI 취향이 아니라 신뢰의 문제다]
 *   주제분은 제목이 그 감정의 주제 사전에 걸린 영상이고, 폴백은 형식(말씀/찬양)과
 *   채널만 보고 채운 영상이다. 근거의 강도가 다르다.
 *   섞어서 한 목록으로 내면 사용자가 "이게 왜 내 감정에 맞지?"라고 느끼는 순간
 *   화면 전체를 의심하게 된다. 못 맞췄다고 먼저 말하면 그 위험이 없다.
 *   (PLAN.md 3.3 — 앱은 두 층을 구분 없이 섞지 않는다)
 *
 *   그래서 이 컴포넌트는 videos 배열 하나를 받지 않고 {theme, fallback}을 받는다.
 *   합치려면 호출부가 의도적으로 합쳐야 하고, 그런 코드는 리뷰에서 보인다.
 *
 * [빈 쪽은 문장으로 말한다]
 *   토글의 한쪽이 비면 버튼을 끄지 않고 여기서 문장을 띄운다.
 */

import { Fragment } from "react";

import { adPositions, positionsWithin } from "../lib/ads.js";
import { formatDuration, thumbnailUrl, watchUrl, MEDIA } from "../lib/videos.js";
import { T, SERIF } from "../theme.js";
import { AdSlot } from "./AdSlot.jsx";

const OTHER_LABEL = { [MEDIA.SERMON]: "찬양", [MEDIA.WORSHIP]: "말씀" };
const SELF_LABEL = { [MEDIA.SERMON]: "말씀", [MEDIA.WORSHIP]: "찬양" };

export function VideoList({ layers, mediaType, otherCount }) {
  const { theme = [], fallback = [] } = layers || {};

  if (theme.length === 0 && fallback.length === 0) {
    return <EmptySide mediaType={mediaType} otherCount={otherCount} />;
  }

  /**
   * 광고 자리 — 두 층을 이어 붙인 통합 번호로 계산한 뒤 층별로 나눈다.
   * ⛔ 5·11·17을 여기에 박지 말 것. 폴백 시작 위치가 매일 달라
   *    층 경계와 겹친다(ads.js 머리말 · HANDOFF 2.51).
   */
  const slots = adPositions({ themeCount: theme.length, fallbackCount: fallback.length });

  return (
    <div>
      {theme.length > 0 ? (
        <Section
          title="이 마음에 맞춰 고른 영상"
          videos={theme}
          adsAfter={positionsWithin(slots, 0, theme.length)}
        />
      ) : null}
      {fallback.length > 0 ? (
        // 2026-08-19 문구 개정 — 정직성은 그대로, 톤만 부드럽게.
        //   이전: "주제까지는 못 맞췄지만, 최근 올라온 영상이에요"
        //   지금: "딱 맞는 건 아니지만, 요즘 올라온 것들도 놓고 갈게요"
        // "못 맞췄다"를 먼저 말하는 원칙은 유지한다(그래야 기대를 걸지 않는다).
        // 다만 "놓고 갈게요"는 위기 화면의 "짧은 구절 하나만 두고 갈게요"와 같은
        // 결이라, 앱 전체가 같은 어조로 말하게 된다.
        <Section
          title="딱 맞는 건 아니지만, 요즘 올라온 것들도 놓고 갈게요"
          videos={fallback}
          adsAfter={positionsWithin(slots, theme.length, fallback.length)}
          quiet
        />
      ) : null}
    </div>
  );
}

/**
 * 한쪽 토글이 비었을 때. **오류 화면이 아니라 상태 설명이다.**
 * 반대쪽에 영상이 있으면 그 사실을 알려 사용자가 토글을 누르면 된다는 걸 알게 한다.
 */
function EmptySide({ mediaType, otherCount }) {
  const other = OTHER_LABEL[mediaType] || "다른 형식";
  const self = SELF_LABEL[mediaType] || "이 형식";
  return (
    <p style={styles.empty}>
      {otherCount > 0
        ? `지금은 ${other} 영상만 있어요.`
        : `지금은 ${self} 영상이 준비되지 않았어요. 구절만 두고 가도 괜찮아요.`}
    </p>
  );
}

/**
 * @param {Set<number>} adsAfter 이 층에서 광고가 따라붙는 항목 번호(1부터).
 *   비어 있으면 광고가 없다 — 위기 화면과 "이어서 읽기"는 이 컴포넌트를
 *   아예 쓰지 않으므로(CrisisScreen·ChapterReader가 직접 그린다) 그쪽에는
 *   구조적으로 광고가 들어갈 수 없다. 방침 2절이 약속한 것이 그것이다.
 */
function Section({ title, videos, quiet, adsAfter }) {
  return (
    <section style={{ marginBottom: 30 }}>
      <h2 style={{ ...styles.heading, ...(quiet ? styles.headingQuiet : null) }}>
        {title}
      </h2>
      <ul style={styles.list}>
        {videos.map((video, index) => (
          /* key를 Fragment가 든다 — 목록이 다시 조립되면(감정 전환·토글·데이터
             갱신) 이 조각이 통째로 새로 마운트되고, 안의 <ins>도 함께 새로
             생겨 push가 정확히 한 번만 돈다. 같은 영상이 같은 자리에 남으면
             다시 마운트하지 않는다 — 이미 채워진 광고는 건드리지 않는 것이 맞다. */
          <Fragment key={video.videoId}>
            <li style={styles.item}>
              <a
                href={watchUrl(video.videoId)}
                target="_blank"
                rel="noreferrer noopener"
                style={styles.link}
              >
                <img
                  src={thumbnailUrl(video.videoId)}
                  alt=""
                  loading="lazy"
                  style={styles.thumb}
                />
                <span style={styles.meta}>
                  <span style={styles.title}>{video.title}</span>
                  <span style={styles.sub}>
                    {video.channel}
                    {formatDuration(video.duration)
                      ? ` · ${formatDuration(video.duration)}`
                      : ""}
                  </span>
                </span>
              </a>
            </li>
            {adsAfter?.has(index + 1) ? (
              <li style={styles.item}>
                <AdSlot />
              </li>
            ) : null}
          </Fragment>
        ))}
      </ul>
    </section>
  );
}

const styles = {
  // 층 헤더는 FYM의 라벨 언어를 그대로 쓴다 — 11.5px에 자간을 넓힌 캡션.
  // 구분선을 두지 않고 자간과 색으로만 층을 가른다.
  heading: {
    margin: "0 0 14px",
    fontSize: 11.5,
    fontWeight: 400,
    color: T.muted,
    letterSpacing: "0.2em",
  },
  /**
   * 폴백 층 헤더 — 조용한 것은 맞지만 **읽히지 않을 만큼은 아니다.**
   *
   * `#ffffff3d`는 실측 2.18:1이었다. 주제분 헤더(T.muted 6.28:1)의 3분의 1이고,
   * 비선택 탭(4.91:1)보다도 두 배 어둡다. 화면을 위에서 아래로 읽으면
   * 밝기가 14.41 → 6.28 → 4.91 → **2.18** → 14.41(영상 제목)로 튀어,
   * 층이 갈리는 게 아니라 뒤섞여 보였다.
   *
   * ⚠ 이 헤더는 장식이 아니라 **이 앱의 정직성 장치다.** "딱 맞는 건
   *   아니지만"을 먼저 말해서 사용자가 기대를 걸지 않게 하는 문장이다
   *   (위 Section 주석). 안 읽히면 그 장치가 작동하지 않는다.
   *   11.5px 작은 글자라 WCAG AA 4.5:1에 걸린다.
   *
   * `${T.muted}CC` = 4.53:1. 주제분 헤더(6.28)보다는 여전히 조용하고,
   * 자간도 0.2em → 0.14em으로 좁아 층 구분은 그대로다.
   * 비선택 탭(4.91)과 가까워지지만 헷갈리지 않는다 — 크기(11.5 / 14px)와
   * 자간(0.14em / 0.02em)이 다르고, 탭은 밑줄을 켜는 컨트롤이며 이쪽은
   * 목록 바로 위에 붙은 캡션이라 역할이 위치로 읽힌다.
   */
  headingQuiet: { color: `${T.muted}CC`, letterSpacing: "0.14em" },
  list: { listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 16 },
  item: { margin: 0 },
  link: {
    display: "flex",
    gap: 13,
    alignItems: "center",
    textDecoration: "none",
    color: "inherit",
  },
  // 카드 테두리를 두지 않는다. 썸네일 자체가 이미 시각적 블록이라
  // 테두리를 더하면 면이 겹친다 — 항목 사이는 여백(16px)이 가른다.
  // 크기·라운드는 FYM 카드(76x46, radius 2)의 언어를 따른다.
  thumb: {
    width: 92,
    height: 52,
    objectFit: "cover",
    borderRadius: 3,
    background: "#ffffff0d",
    flex: "0 0 auto",
  },
  meta: { display: "flex", flexDirection: "column", gap: 4, minWidth: 0 },
  title: {
    fontSize: 14,
    lineHeight: 1.5,
    color: T.mist,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
    wordBreak: "keep-all",
  },
  sub: { fontSize: 11, color: T.muted, letterSpacing: "0.01em" },
  empty: {
    margin: "2px 0 0",
    fontSize: 13.5,
    lineHeight: 1.8,
    color: T.muted,
  },
};
