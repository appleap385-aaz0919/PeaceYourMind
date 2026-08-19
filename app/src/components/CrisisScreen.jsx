/**
 * 위기 화면 — 순서가 곧 안전 장치다.
 *
 *   1. 상담 안내 (최상단·최대 강조, 탭하면 바로 통화)
 *   2. 구절 (crisis 고정 풀. 감정 매핑을 타지 않는다)
 *   3. 영상 (있을 때만, 4~6개, "추천"이라는 단어 없이)
 *
 * [여기서 하지 않는 것 — 코드로 강제한다]
 *   · [말씀]/[찬양] 토글 없음. 형식 선택은 감정 화면의 기능이다
 *   · 폴백 없음. 주제 태깅이 안 된 영상을 위기 상태의 사용자에게
 *     형식만 보고 내놓을 수는 없다
 *   · 자동재생 없음, "추천" 표현 없음
 *   이 컴포넌트는 MediaToggle과 VideoList를 import하지 않는다. 목록을 직접 그린다 —
 *   나중에 누가 저 컴포넌트에 폴백·토글을 추가해도 이 화면은 영향을 받지 않는다.
 *   (taxonomy.json safety.crisis_response의 media_type_toggle/fallback이 false이고,
 *    테스트가 그 값과 이 파일의 import를 함께 확인한다)
 *
 * [구절도 감정 화면과 다른 풀을 쓴다]
 *   위기 상태에서 문제가 되는 표현은 감정 화면에서 문제가 되지 않는 것과 다르다.
 *   시편 34:18을 위기 풀에서 뺀 것이 그 사례다 — 후반부 "중심에 통회하는 자"가
 *   구원의 조건처럼 읽힐 여지가 있어 조건이 없는 시편 147:3으로 대체했다.
 */

import { formatDuration, thumbnailUrl, watchUrl } from "../lib/videos.js";
import { T, SERIF } from "../theme.js";

export function CrisisScreen({ response, verse, attribution, videos, closing, onBack }) {
  return (
    <div className="rise" style={{ paddingTop: 8 }}>
      {/* 1. 상담 안내 — 항상 최상단 */}
      <section style={styles.notice} aria-label="상담 안내">
        <p style={styles.message}>{response.message}</p>
        <div style={styles.resources}>
          {response.resources.map((r) => (
            <a key={r.number} href={`tel:${r.number}`} style={styles.call}>
              <span style={styles.callName}>{r.name}</span>
              <span style={styles.callNumber}>{r.number}</span>
            </a>
          ))}
        </div>
      </section>

      {/* 2. 구절 — crisis 고정 풀 */}
      {verse ? (
        <section style={styles.verse} aria-label="구절">
          <p style={styles.verseLead}>짧은 구절 하나만 두고 갈게요</p>
          <p style={styles.verseText}>{verse.text}</p>
          <p style={styles.verseRef}>{verse.ref}</p>
          <p style={styles.attribution}>{attribution}</p>
        </section>
      ) : null}

      {/* 3. 영상 — 있을 때만. 없으면 그 사실을 문장으로 말한다 */}
      {videos.length > 0 ? (
        <section style={{ marginTop: 26 }}>
          <h2 style={styles.heading}>지금 곁에 두면 좋을 것들</h2>
          <ul style={styles.list}>
            {videos.map((video) => (
              <li key={video.videoId}>
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
            ))}
          </ul>
        </section>
      ) : (
        <p style={styles.noVideos}>지금은 영상 없이, 위 연락처를 곁에 둬요.</p>
      )}

      {closing ? <p style={styles.closing}>{closing}</p> : null}

      <button type="button" onClick={onBack} style={styles.back}>
        돌아가기
      </button>
    </div>
  );
}

const styles = {
  notice: {
    background: "#ffffff0f",
    border: "1px solid #ffffff26",
    borderRadius: 16,
    padding: "20px 18px",
  },
  message: {
    margin: 0,
    fontFamily: SERIF,
    fontSize: 16.5,
    lineHeight: 1.8,
    color: T.mist,
    wordBreak: "keep-all",
  },
  resources: { display: "grid", gap: 8, marginTop: 16 },
  call: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "13px 16px",
    borderRadius: 10,
    background: T.jade,
    color: "#07110E",
    textDecoration: "none",
    fontSize: 14.5,
  },
  callName: { fontWeight: 500 },
  callNumber: { fontVariantNumeric: "tabular-nums", fontWeight: 700 },
  verse: {
    marginTop: 24,
    padding: "18px 16px",
    borderRadius: 14,
    background: "#ffffff08",
    border: "1px solid #ffffff14",
  },
  verseLead: { margin: "0 0 12px", fontSize: 12.5, color: T.muted },
  verseText: {
    margin: 0,
    fontFamily: SERIF,
    fontSize: 17,
    lineHeight: 1.75,
    color: T.mist,
    wordBreak: "keep-all",
  },
  verseRef: { margin: "14px 0 0", fontSize: 13, color: T.sand, fontFamily: SERIF },
  attribution: { margin: "14px 0 0", fontSize: 11, color: "#ffffff33" },
  heading: {
    margin: "0 0 12px",
    fontFamily: SERIF,
    fontSize: 13.5,
    fontWeight: 400,
    color: T.muted,
  },
  list: { listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 },
  link: { display: "flex", gap: 12, alignItems: "center", textDecoration: "none" },
  thumb: {
    width: 100,
    height: 56,
    objectFit: "cover",
    borderRadius: 8,
    background: "#ffffff0d",
    flex: "0 0 auto",
  },
  meta: { display: "flex", flexDirection: "column", gap: 4, minWidth: 0 },
  title: { fontSize: 13, lineHeight: 1.45, color: T.mist, wordBreak: "keep-all" },
  sub: { fontSize: 11.5, color: T.muted },
  noVideos: { marginTop: 26, fontSize: 13.5, color: T.muted, lineHeight: 1.7 },
  closing: {
    marginTop: 28,
    fontFamily: SERIF,
    fontSize: 14,
    color: T.muted,
    lineHeight: 1.8,
    textAlign: "center",
  },
  back: {
    display: "block",
    margin: "30px auto 0",
    background: "none",
    border: "none",
    color: "#ffffff40",
    fontSize: 12.5,
    cursor: "pointer",
  },
};
