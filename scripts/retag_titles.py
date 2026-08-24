#!/usr/bin/env python
"""제목 덤프(dist/titles.json)로 주제 사전을 다시 태깅해 본다 — **API를 부르지 않는다.**

    python scripts/retag_titles.py                 현재 사전의 태깅 현황
    python scripts/retag_titles.py --probe 사랑하   후보 어간이 무엇을 잡는지
    python scripts/retag_titles.py --songs         찬양 곡명 단위 적중/미적중
    python scripts/retag_titles.py --screens       세분류 화면 조립 (폴백 비율)

[왜 드라이런이 아니라 이 도구인가]
    `build_videos.py --dry-run`의 제목은 사전에서 합성한 것이라 당연히 걸린다.
    사전을 고쳤을 때 정말 알아야 하는 것은 "**실제 제목**을 몇 건 더 잡는가"와
    "잡지 말아야 할 것을 잡는가"이고, 그 답은 실측 제목에만 있다.
    titles.json은 배치가 --dump-titles로 남긴 그 실측 자료다(1,067건).

[themes.yaml 키워드 설계 원칙 3의 집행 도구다]
    "한글은 음절 단위다. 어간을 줄일 때마다 활용형을 실측한다."
    어간을 줄이면 미탐은 줄고 오탐은 는다. 어느 쪽이 큰지는 세어 봐야 알고,
    --probe가 그 저울이다. **판정은 사람이 한다** — 이 도구는 걸린 제목을
    전부 보여줄 뿐 좋고 나쁨을 정하지 않는다.

[사전을 고쳤을 때 정말 봐야 하는 것은 화면이다 — --screens]
    태깅 건수가 늘어도 그것이 폴백을 밀어내지 못하면 사용자가 보는 것은
    그대로다. 폴백 비율은 세분류 화면 단위에서만 정해지므로(HANDOFF 2.14),
    배치의 조립 함수를 그대로 불러 화면을 다시 짠다. **배치 코드를 복제하지
    않는다** — build_videos.build_subcategories를 직접 부른다. 그 함수는
    태깅 이후 단계라 API를 부르지 않는다.

    ⚠ 위기 풀 제외(exclude)는 비워 둔다. 지금 위기 풀이 0건이라 실제와 같지만,
      위기 채널이 승인되면 이 재현은 화면당 최대 20건만큼 낙관적이 된다.

[곡명 분해는 lib/tagging.py에 있다]
    2026-08-24부터 형식 판별의 동점 처리가 같은 분해를 쓴다. 두 벌을 두면
    한쪽만 고쳐져 조용히 갈라지므로 lib으로 옮기고 여기서는 부른다.

[곡명을 따로 보는 이유 — --songs]
    찬양 콘티 제목은 곡명을 +·/로 이어붙인 목록이다.
    "성도여 다 함께 + Jehovah + 하나님의 부르심 + 푯대를 향하여 | 오륜교회 …"
    제목 단위로 세면 한 곡만 걸려도 태깅 1건이라 사전의 실제 적중률이 가려진다.
    곡명 단위로 갈라야 무엇을 놓치고 있는지가 보인다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_videos import build_subcategories
from lib.allowlist import Allowlist, load_allowlist
from lib.filters import Video
from lib.results import BuildContext, TaggedVideo
from lib.tagging import (
    WORSHIP,
    classify_media_type,
    matches_keyword,
    song_names,
    tag_themes,
)
from lib.taxonomy import load_subcategory_ids
from lib.themes import (
    FALLBACK_HEAVY_RATIO,
    SUBCATEGORY_MIN_VIDEOS,
    THEME_MAX_VIDEOS,
    Themes,
    load_themes,
)

ROOT = Path(__file__).resolve().parents[1]
THEMES_PATH = ROOT / "themes.yaml"
TAXONOMY_PATH = ROOT / "taxonomy.yaml"
ALLOWLIST_PATH = ROOT / "channel_allowlist.yaml"
TITLES_PATH = ROOT / "dist" / "titles.json"
EXIT_OK, EXIT_FAIL = 0, 1

def load_titles(path: Path) -> list[dict[str, Any]]:
    """제목 덤프를 읽는다. 배치가 남긴 형식을 그대로 쓴다."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    videos = raw.get("videos")
    if not isinstance(videos, list) or not videos:
        raise ValueError(f"{path}: videos 배열이 비어 있다")
    return videos


def retag(
    videos: list[dict[str, Any]], themes: Themes, allowlist: Allowlist
) -> list[dict[str, Any]]:
    """현재 themes.yaml로 주제와 **형식**을 다시 판별한다. 원본은 고치지 않는다.

    형식(media_type)도 다시 계산하는 이유 — 2026-08-24
        덤프의 mediaType은 **덤프를 뜬 날의 판정**이다. 판별 규칙을 고쳤을 때
        저장값을 읽으면 도구가 개정을 보여주지 못한다. 실제로 동점 처리를 넣은 날
        [형식별]이 개정 전 수치를 그대로 찍었다. 주제는 이미 재태깅하고 있었으므로
        형식만 저장값을 읽고 있던 셈이다.

        ⚠ 채널 content_type이 덤프에 없다. allowlist에서 channelId로 채워야
          채널 단계(판별 3순위)가 살아나 배치와 같은 결과가 나온다. 채우지 않으면
          sermon이 730건이 아니라 671건으로 보인다 (실측 2026-08-24).
    """
    content_types = {c.channel_id: c.content_type for c in allowlist.channels}
    rows = []
    for v in videos:
        title = v.get("title", "")
        matches = tag_themes(title, themes, v.get("channel"))
        media = classify_media_type(
            title,
            int(v.get("durationSeconds") or 0),
            content_types.get(v.get("channelId")),
            themes,
        )
        rows.append(
            {
                **v,
                "retagThemes": [m.theme_id for m in matches],
                "retagHits": sorted({h for m in matches for h in m.hits}),
                "retagMedia": media.media_type,
                "retagMediaReason": media.reason,
            }
        )
    return rows


def _rate(n: int, total: int) -> str:
    return f"{n / total * 100:5.1f}%" if total else "    -"


def report_summary(rows: list[dict[str, Any]], themes: Themes) -> None:
    total = len(rows)
    tagged = [r for r in rows if r["retagThemes"]]
    print(
        f"제목 {total}건 · 태깅 {len(tagged)}건 ({_rate(len(tagged), total)})"
        f" · 미태깅 {total - len(tagged)}건"
    )

    moved = [
        r for r in rows if sorted(r.get("themes") or []) != sorted(r["retagThemes"])
    ]
    if moved:
        gained = sum(1 for r in moved if not (r.get("themes") or []))
        lost = sum(1 for r in moved if r.get("themes") and not r["retagThemes"])
        print(
            f"덤프 시점 대비 변화 {len(moved)}건"
            f" — 신규 태깅 {gained} · 태깅 상실 {lost}"
        )

    print("\n[주제별]  덤프 -> 재태깅")
    before = Counter(t for r in rows for t in (r.get("themes") or []))
    after = Counter(t for r in rows for t in r["retagThemes"])
    for theme in themes.taggable:
        b, a = before[theme.id], after[theme.id]
        mark = "" if a == b else f"  {a - b:+d}"
        print(f"  {theme.id:16s} {theme.label:10s} {b:5d} -> {a:5d}{mark}")

    print("\n[채널별]  수집 / 태깅")
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        slot = per[r.get("channel", "?")]
        slot[0] += 1
        if r["retagThemes"]:
            slot[1] += 1
    for ch, (n, t) in sorted(per.items(), key=lambda kv: -kv[1][0]):
        print(f"  {n:5d} {t:5d} {_rate(t, n)}  {ch}")

    print("\n[형식별]  덤프 -> 재판별")
    for kind in ("sermon", "worship", "unknown"):
        sub = [r for r in rows if r.get("retagMedia") == kind]
        was = sum(1 for r in rows if r.get("mediaType") == kind)
        hit = sum(1 for r in sub if r["retagThemes"])
        delta = f"  {len(sub) - was:+d}" if len(sub) != was else ""
        print(
            f"  {kind:8s} {was:5d} -> {len(sub):5d}{delta:6s}"
            f" · 태깅 {hit:4d} ({_rate(hit, len(sub))})"
        )
    shifted = [r for r in rows if r.get("mediaType") != r.get("retagMedia")]
    if shifted:
        by_reason = Counter(r["retagMediaReason"] for r in shifted)
        detail = " · ".join(f"{k} {n}" for k, n in by_reason.most_common())
        print(f"  형식이 바뀐 제목 {len(shifted)}건 — 새 판정 근거: {detail}")


def report_probe(rows: list[dict[str, Any]], keywords: list[str], limit: int) -> None:
    """후보 키워드가 무엇을 잡는지 전부 보여준다 — 오탐 판정은 사람이 한다."""
    for kw in keywords:
        hits = [r for r in rows if matches_keyword(r.get("title", ""), kw)]
        fresh = [r for r in hits if not r["retagThemes"]]
        print(
            f'\n=== "{kw}"  적중 {len(hits)}건'
            f" (그중 현재 미태깅 {len(fresh)}건 = 순증) ==="
        )
        if not hits:
            print("  없음")
            continue
        for r in hits[:limit]:
            tags = ",".join(r["retagThemes"]) or "-"
            flag = "+" if not r["retagThemes"] else " "
            print(f"  {flag} [{tags:22s}] {r.get('title', '')[:88]}")
        if len(hits) > limit:
            print(f"  … 외 {len(hits) - limit}건 (--limit 로 늘린다)")


def report_songs(rows: list[dict[str, Any]], themes: Themes, limit: int) -> None:
    """곡명 단위 적중률 — 콘티 제목을 갈라서 센다."""
    songs: Counter[str] = Counter()
    for r in rows:
        if r.get("retagMedia") != WORSHIP:
            continue
        for s in song_names(r.get("title", "")):
            songs[s] += 1

    hit: list[tuple[str, int, list[str]]] = []
    miss: list[tuple[str, int]] = []
    for s, n in songs.items():
        matches = tag_themes(s, themes)
        if matches:
            hit.append((s, n, [m.theme_id for m in matches]))
        else:
            miss.append((s, n))

    total = len(songs)
    print(
        f"찬양 제목에서 갈라낸 곡명 {total}종 (연 {sum(songs.values())}회)"
        f" · 사전 적중 {len(hit)}종 ({_rate(len(hit), total)})"
    )

    print(f"\n[적중 {len(hit)}종]")
    for s, n, ts in sorted(hit, key=lambda x: -x[1]):
        print(f"  {n:3d}회  [{','.join(ts):20s}] {s}")

    print(f"\n[미적중 {len(miss)}종 — 빈도순 상위 {limit}]")
    for s, n in sorted(miss, key=lambda x: -x[1])[:limit]:
        print(f"  {n:3d}회  {s}")


def _tagged_pool(
    videos: list[dict[str, Any]], themes: Themes, allowlist: Any
) -> list[TaggedVideo]:
    """제목 덤프를 배치의 태깅 결과(TaggedVideo)로 되돌린다.

    media_type도 **다시 판별한다** — 덤프에 적힌 값을 믿으면 그 덤프를 뜬
    시점의 사전에 결과가 묶인다. 채널 content_type이 필요하므로 승인 목록을
    같이 읽는다(배치와 같은 경로).
    """
    index = {c.channel_id: c for c in allowlist.channels}
    pool: list[TaggedVideo] = []
    for v in videos:
        title = v.get("title", "")
        channel = index.get(v.get("channelId", ""))
        video = Video(
            video_id=v.get("videoId", ""),
            title=title,
            channel=v.get("channel", ""),
            channel_id=v.get("channelId", ""),
            published_at=v.get("publishedAt", ""),
            duration=v.get("duration", ""),
            duration_seconds=int(v.get("durationSeconds") or 0),
            description="",
            tags=(),
            comments_disabled=False,
        )
        matches = tag_themes(title, themes)
        pool.append(
            TaggedVideo(
                video=video,
                themes=tuple(m.theme_id for m in matches),
                hits=tuple(h for m in matches for h in m.hits),
                media=classify_media_type(
                    title,
                    video.duration_seconds,
                    channel.content_type if channel else None,
                    themes,
                ),
            )
        )
    return pool


def report_screens(
    videos: list[dict[str, Any]], themes: Themes, allowlist: Any, day: int
) -> None:
    """세분류 화면을 배치와 같은 함수로 다시 조립한다."""
    pool = _tagged_pool(videos, themes, allowlist)
    ctx = BuildContext(
        themes=themes,
        client=None,  # type: ignore[arg-type]  조립 단계는 API를 부르지 않는다
        budget=None,  # type: ignore[arg-type]
        previous={},
        allowlist=allowlist,
    )
    results = build_subcategories(ctx, pool, exclude=set(), day_of_year=day)

    print(f"\n[세분류 화면 {len(results)}개]  day_of_year={day}")
    print("  화면                   기본형식  주제  폴백   계  폴백비율")
    for r in sorted(results, key=lambda x: -x.fallback_ratio):
        flags = []
        if r.fallback_ratio > FALLBACK_HEAVY_RATIO:
            flags.append("폴백과다")
        if r.count < SUBCATEGORY_MIN_VIDEOS:
            flags.append("성립불가")
        mark = ("  " + " ".join(flags)) if flags else ""
        print(
            f"  {r.id:22s} {r.media_default:8s} {len(r.theme_videos):4d}"
            f" {len(r.fallback_videos):5d} {r.count:4d}"
            f"  {r.fallback_ratio * 100:5.1f}%{mark}"
        )

    theme_n = sum(len(r.theme_videos) for r in results)
    fb_n = sum(len(r.fallback_videos) for r in results)
    total = theme_n + fb_n
    filled = sum(1 for r in results if r.count == THEME_MAX_VIDEOS)
    heavy = sum(1 for r in results if r.fallback_ratio > FALLBACK_HEAVY_RATIO)
    too_few = sum(1 for r in results if r.count < SUBCATEGORY_MIN_VIDEOS)
    print(
        f"\n총 노출 {total}건 (주제분 {theme_n} + 폴백 {fb_n}"
        f" · 폴백 {_rate(fb_n, total).strip()})"
    )
    print(
        f"{THEME_MAX_VIDEOS}건 달성 {filled}/{len(results)}"
        f" · 최소 {min(r.count for r in results)}건"
        f" · 폴백과다 {heavy}건 · 성립불가 {too_few}건"
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="titles.json 재태깅 분석 (API 호출 없음)")
    p.add_argument("--themes", type=Path, default=THEMES_PATH)
    p.add_argument("--titles", type=Path, default=TITLES_PATH)
    p.add_argument(
        "--probe",
        nargs="+",
        metavar="KEYWORD",
        help="후보 키워드가 잡는 제목을 전부 본다 (오탐 실측)",
    )
    p.add_argument(
        "--songs",
        action="store_true",
        help="찬양 콘티를 곡명 단위로 갈라 적중률을 본다",
    )
    p.add_argument(
        "--screens",
        action="store_true",
        help="세분류 화면을 배치와 같은 함수로 조립해 폴백 비율을 본다",
    )
    p.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    p.add_argument("--allowlist", type=Path, default=ALLOWLIST_PATH)
    p.add_argument(
        "--day",
        type=int,
        default=231,
        help="회전 시드(day_of_year). 개정 전후를 비교하려면 같은 값을 쓴다 "
        "(기본 231 = 덤프를 뜬 2026-08-19)",
    )
    p.add_argument("--limit", type=int, default=40, help="목록 출력 상한 (기본 40)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.titles.exists():
        print(f"제목 덤프가 없다: {args.titles}", file=sys.stderr)
        print("배치를 --dump-titles 로 한 번 돌려야 한다.", file=sys.stderr)
        return EXIT_FAIL

    themes = load_themes(args.themes, taxonomy_ids=load_subcategory_ids(args.taxonomy))
    videos = load_titles(args.titles)

    if args.screens:
        report_screens(videos, themes, load_allowlist(args.allowlist), args.day)
        return EXIT_OK

    rows = retag(videos, themes, load_allowlist(args.allowlist))
    if args.probe:
        report_probe(rows, args.probe, args.limit)
    elif args.songs:
        report_songs(rows, themes, args.limit)
    else:
        report_summary(rows, themes)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
