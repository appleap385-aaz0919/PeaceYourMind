#!/usr/bin/env python
"""채널 화이트리스트 후보 수집 — 일회성 도구 (월 1회 수준).

    ⚠ 배치·워크플로에 넣지 않는다.
      채널은 한 번 정하면 거의 안 바뀌고, 661 units를 쓰며, 결과는 사람이 읽고
      판단해야 하는 검토 시트다. 자동화할 수 있는 성격이 아니다.

    ⚠ **PYM에서 search.list를 쓰는 유일한 스크립트다.**
      일상 배치는 전면 화이트리스트라 검색을 하지 않는다(PLAN.md 5절).
      검색은 "후보를 찾는" 이 도구에서만 쓰고, 찾은 채널은 사람이 승인해야
      비로소 서비스에 들어온다. 이 경계가 이단 유입을 막는 구조의 핵심이다.

하는 일
    1. 발굴 검색어 6개로 검색 (600 units)
    2. 결과 영상의 채널을 등장 횟수 순으로 집계
       (search.list 응답의 snippet.channelId를 쓰므로 집계에는 추가 쿼터가 없다)
    3. 상위 N개 채널의 구독자 수·총 영상 수·최근 업로드일 조회
    4. uploads 재생목록에서 최근 영상 10개의 제목·길이 수집
    5. 자동 점검 — 최근 업로드 지속성, 쇼츠 비중, 채널 blocklist, 성격 신호어
    6. 검토 시트 생성 — 요약표 + 채널별 상세 + 붙여넣기용 YAML 블록

**자동 점검이 판단할 수 없는 것**
    승인 기준 1(정체 확인)과 2(이단 배제)는 기계가 못 한다. 검색은 이단 채널도
    똑같이 데려온다 — 그들도 "주일예배 설교"를 올린다. 그래서 검토 시트에
    `교단/소속 확인` 열을 두고 비워둔 채 내보낸다. 그 칸을 사람이 채우기 전에는
    어떤 채널도 승인되지 않는다.

쿼터 (기본 --top 30 기준)
    search.list         6회 × 100 = 600
    channels.list       1회 ×   1 =   1
    playlistItems.list 30회 ×   1 =  30   (채널당 1회)
    videos.list        30회 ×   1 =  30   (채널당 1회 — 10건씩이라 50건 배치로 안 묶인다)
    -------------------------------------
    합계                           =  661

    PYM 일일 배치는 약 150이므로 같은 날 돌려도 한도에 여유가 크다.
    (FYM은 배치가 7,900이라 같은 날 실행이 빠듯했다)

사용 예
    python scripts/suggest_channels.py --dry-run
    python scripts/suggest_channels.py --top 30 --reviewer jaehyuk.myung
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.actions_status import batch_succeeded_on
from lib.allowlist import NO_UPLOAD_DAYS, load_allowlist
from lib.channel_blocklist import load_channel_blocklist
from lib.normalize import matched_terms
from lib.quota import COST, QuotaBudget, QuotaExceeded
from lib.quota_log import (
    DAILY_CEILING,
    DEFAULT_LOG,
    QuotaBudgetExceeded,
    check as check_daily_quota,
    record as record_quota,
    table as quota_table,
)
from lib.youtube import Client, DryRunClient, YouTubeClient

logger = logging.getLogger("suggest_channels")

RECENT_VIDEO_COUNT = 10  # 채널당 살펴볼 최근 영상 수
DEFAULT_TOP = 30
DEFAULT_HARD_CAP = 1_200
MIN_DURATION_SECONDS = 180  # 쇼츠 판정 하한 (PLAN.md — 상한은 두지 않는다)

EXIT_OK = 0
EXIT_RETRYABLE = 1
EXIT_QUOTA = 2

# =============================================================================
# 발굴 검색어
# =============================================================================
#
# [왜 스크립트 안에 두는가]
#   FYM은 taxonomy.yaml에 뒀다. 거기서는 같은 검색어를 일일 배치도 썼기 때문이다.
#   PYM 배치는 검색을 하지 않으므로 이 목록을 쓰는 곳이 여기 한 곳뿐이다.
#   설계 근거(무엇을 피하려고 이 조합을 골랐는지)를 검색어 바로 옆에 두는 편이
#   별도 파일로 떼어 근거를 잃는 것보다 낫다고 판단했다.
#
# [설계 원칙 — themes.yaml 전역 금지어를 그대로 적용한다]
#   themes.yaml이 태깅에서 금지한 단어는 여기서도 쓰지 않는다.
#   태깅에서 장르를 잘못 부르는 단어는 발굴에서도 채널을 잘못 부른다.
#
#     은혜      제목의 절반에 들어간다. 변별력이 없어 아무 채널이나 올라온다
#     치유      극단적 신유 집회·안수 채널을 부른다 (승인 기준 3 위반 대상)
#     축복      번영신학 계열 채널 비중이 높다
#     간증      자극적 서사물 채널("암 말기에서…")이 주류다
#     기적      번영신학 + 자극 서사 양쪽을 부른다
#     기도응답  같은 이유
#
#   추가로 PYM 발굴에서만 피하는 것:
#     "설교" 단독   너무 넓다. 이단 채널도 설교를 대량 생산한다.
#                   예배 종류와 묶어 정기 예배를 올리는 기관 채널로 좁힌다.
#     "예언"·"환상" 신비주의 계열을 직접 부른다
#     "부흥회"      집회 중심 채널로 기울고 신유와 겹친다
#
# [이 검색어가 이단을 걸러주지 않는다 — 착각하지 말 것]
#   기관형 채널로 기울일 뿐이다. 이단 단체도 정기 예배를 올리고 총회도 있다.
#   걸러내는 것은 사람이며, 그 판단 근거를 남기는 칸이 검토 시트의
#   `교단/소속 확인` 열이다.
DISCOVERY_QUERIES: tuple[tuple[str, str], ...] = (
    ("주일예배 설교", "교회 공식 채널의 정기 콘텐츠. 기관형 채널이 상위에 온다"),
    ("성경 강해", "본문 중심 설교. 주제 설교보다 교리적 안정성이 높은 편이다"),
    ("새벽기도회 말씀", "매일 올리는 채널이라 업로드 지속성이 함께 확인된다"),
    ("수요예배 말씀", "주일과 다른 시간대. 주일만 올리는 채널과 구분된다"),
    ("찬양 예배 실황", "worship 갈래. CCM 단체·교회 찬양팀을 부른다"),
    ("매일성경 묵상", "devotion 갈래. 출판 사역(성서유니온·두란노) 계열 진입점"),
)

# =============================================================================
# 성격 신호어 — 차단이 아니라 사람에게 보여줄 표시
# =============================================================================
#
# PYM에는 아직 제목 blocklist 사전이 없다(FYM taxonomy.yaml의 tier_a/b/c에 해당).
# 만들 수도 있지만, 화이트리스트 전제에서는 제목 필터의 역할이 작고 사전을
# 잘못 만들면 정상 채널을 떨어뜨린다.
#
# 대신 **승인 기준 3(콘텐츠 성격)에 해당하는 신호어**를 세어 사람에게 보여준다.
# 걸렸다고 탈락시키지 않는다 — "이 채널의 최근 10건 중 3건에 신유 집회 어휘가
# 있다"는 사실을 표에 적어, 사람이 영상을 열어볼지 정하게 한다.
SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "신유·집회": ("신유", "안수", "치유집회", "부흥성회", "능력집회"),
    "번영신학": ("축복", "형통", "재물", "부자되는", "성공비결"),
    "자극 서사": ("간증", "기적", "충격", "소름", "실화"),
    "신비주의": ("예언", "환상", "계시받", "영분별"),
}


@dataclass
class RecentVideo:
    title: str
    duration_seconds: int
    published_at: str
    blocked_by: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        return self.duration_seconds < MIN_DURATION_SECONDS

    @property
    def duration_text(self) -> str:
        if self.duration_seconds <= 0:
            return "?"
        minutes, seconds = divmod(self.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


@dataclass
class Candidate:
    channel_id: str
    title: str
    appearances: int
    subscribers: int | None = None
    video_count: int | None = None
    last_upload_at: str | None = None
    days_since_upload: int | None = None
    recent: list[RecentVideo] = field(default_factory=list)
    already_listed: bool = False
    blocked: bool = False
    block_reason: str = ""
    alive: bool = True

    @property
    def short_ratio(self) -> float | None:
        if not self.recent:
            return None
        return sum(1 for v in self.recent if v.is_short) / len(self.recent)

    @property
    def signal_counts(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for video in self.recent:
            for label in set(video.signals):
                counts[label] += 1
        return counts

    @property
    def warnings(self) -> list[str]:
        """객관적으로 확인 가능한 실격 사유만 모은다.

        승인 기준 1(정체 확인)·2(이단 배제)·3(콘텐츠 성격)은 여기 없다.
        기계가 판단할 수 없기 때문이다 — 사람 몫으로 남긴다.
        """
        issues: list[str] = []
        if self.blocked:
            return [f"channel_blocklist 등재 ({self.block_reason[:40]})"]
        if not self.alive:
            return ["채널 조회 실패"]
        if not self.recent:
            return ["최근 영상을 가져오지 못함"]
        if self.days_since_upload is None or self.days_since_upload > NO_UPLOAD_DAYS:
            issues.append(f"{NO_UPLOAD_DAYS}일 내 업로드 없음")
        if (self.short_ratio or 0) >= 0.5:
            issues.append("최근 영상 절반 이상이 3분 미만")
        return issues

    @property
    def auto_ok(self) -> bool:
        return not self.warnings

    @property
    def name_for_yaml(self) -> str:
        """채널명에 콜론·따옴표가 들어가도 YAML이 깨지지 않게 감싼다."""
        return '"{}"'.format(self.title.replace('"', "'"))


# =============================================================================
# 수집
# =============================================================================


def collect_appearances(client: Client) -> tuple[Counter[str], dict[str, str]]:
    """발굴 검색어로 검색해 채널별 등장 횟수를 센다."""
    counter: Counter[str] = Counter()
    titles: dict[str, str] = {}
    for query, _why in DISCOVERY_QUERIES:
        items = client.search_items(query)
        for item in items:
            snippet = item.get("snippet") or {}
            channel_id = str(snippet.get("channelId", ""))
            if not channel_id:
                continue
            counter[channel_id] += 1
            titles.setdefault(channel_id, str(snippet.get("channelTitle", "")))
        logger.info("  %-16s → 영상 %d건", query, len(items))
    return counter, titles


def inspect_candidates(
    client: Client,
    counter: Counter[str],
    titles: dict[str, str],
    listed: set[str],
    blocked: dict[str, str],
    top: int,
    now: datetime,
) -> list[Candidate]:
    """상위 채널의 상세 정보와 최근 영상을 조사한다."""
    ranked = [cid for cid, _ in counter.most_common(top)]
    found = {str(item["id"]): item for item in client.channels(ranked)}

    candidates: list[Candidate] = []
    for channel_id in ranked:
        item = found.get(channel_id)
        candidate = Candidate(
            channel_id=channel_id,
            title=titles.get(channel_id, "(이름 미확인)"),
            appearances=counter[channel_id],
            already_listed=channel_id in listed,
            blocked=channel_id in blocked,
            block_reason=blocked.get(channel_id, ""),
            alive=item is not None,
        )
        if item is not None:
            _fill_channel_stats(candidate, item)
            _fill_recent_videos(candidate, client, item, now)
        candidates.append(candidate)
    return candidates


def _fill_channel_stats(candidate: Candidate, item: dict[str, Any]) -> None:
    stats = item.get("statistics") or {}
    candidate.title = str((item.get("snippet") or {}).get("title", candidate.title))
    if not stats.get("hiddenSubscriberCount") and "subscriberCount" in stats:
        candidate.subscribers = int(stats["subscriberCount"])
    if "videoCount" in stats:
        candidate.video_count = int(stats["videoCount"])


def _fill_recent_videos(
    candidate: Candidate, client: Client, item: dict[str, Any], now: datetime
) -> None:
    uploads = (
        (item.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
    )
    if not uploads:
        return
    video_ids = client.playlist_items(str(uploads), RECENT_VIDEO_COUNT)
    if not video_ids:
        return

    for video in client.videos(video_ids):
        snippet = video.get("snippet") or {}
        title = str(snippet.get("title", ""))
        signals = [
            label
            for label, terms in SIGNAL_TERMS.items()
            if matched_terms(title, terms)
        ]
        candidate.recent.append(
            RecentVideo(
                title=title,
                duration_seconds=_parse_duration(
                    str((video.get("contentDetails") or {}).get("duration", ""))
                ),
                published_at=str(snippet.get("publishedAt", "")),
                signals=signals,
            )
        )

    published = [v.published_at for v in candidate.recent if v.published_at]
    if published:
        candidate.last_upload_at = max(published)
        try:
            moment = datetime.fromisoformat(
                candidate.last_upload_at.replace("Z", "+00:00")
            )
            candidate.days_since_upload = (now - moment.astimezone(timezone.utc)).days
        except ValueError:
            candidate.days_since_upload = None


def _parse_duration(iso: str) -> int:
    """ISO 8601 duration → 초. 파싱 실패는 0을 반환해 '3분 미만'으로 걸러지게 한다."""
    import re

    match = re.match(
        r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", iso or ""
    )
    if not match:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


# =============================================================================
# 검토 시트 출력
# =============================================================================


def render_markdown(
    candidates: list[Candidate],
    *,
    now: datetime,
    spent: int,
    total_channels: int,
    total_videos: int,
    reviewer: str,
    dry_run: bool,
) -> str:
    lines = [
        "# PYM 채널 화이트리스트 후보 검토 시트",
        "",
        f"- 생성: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        + ("  **(드라이런 — 실제 데이터 아님)**" if dry_run else ""),
        f"- 검색어 {len(DISCOVERY_QUERIES)}개에서 영상 {total_videos}건 수집 → "
        f"채널 {total_channels}개 집계 → 상위 {len(candidates)}개 조사",
        f"- 소모 쿼터: {spent:,} units",
        "",
        _render_howto(),
        "",
        _render_queries(),
        "",
        "## 요약",
        "",
        "**`교단/소속 확인` 열은 비어 있습니다. 사람이 채우는 칸입니다.**",
        "",
        "| # | 채널명 | 교단/소속 확인 | 등장 | 구독자 | 총영상 | 최근 업로드 | 3분미만 | 성격 신호 | 자동 점검 |",
        "|---:|---|---|---:|---:|---:|---|---:|---|---|",
    ]
    for index, c in enumerate(candidates, start=1):
        lines.append(_render_summary_row(index, c))

    lines += ["", "## 채널별 최근 영상", ""]
    for index, c in enumerate(candidates, start=1):
        lines += _render_detail(index, c)

    lines += _render_yaml_block(candidates, now, reviewer)
    return "\n".join(lines) + "\n"


def _render_howto() -> str:
    return "\n".join(
        [
            "## 읽는 법",
            "",
            "**자동 점검은 객관적으로 확인 가능한 것만 봅니다.** 최근 업로드 지속성,",
            "영상 길이 분포, channel_blocklist 등재 여부입니다.",
            "",
            "`channel_allowlist.yaml`의 승인 기준 중 **1·2·3은 자동으로 판단할 수 없습니다.**",
            "",
            "1. **정체 확인** — 교단 총회/공식 미디어, 소속 교단이 확인되는 교회,",
            "   또는 법인·연혁이 공개된 초교파 방송인가. 채널 설명·교회 홈페이지·",
            "   교단 주소록 중 **2개 이상 교차 확인**하고 그 근거를 `교단/소속 확인` 열에 적습니다.",
            "2. **이단 배제 (절대 조건)** — 주요 교단이 이단·사이비로 규정한 단체 및",
            "   연계 채널인가. **판단이 애매하면 넣지 않습니다.**",
            "   위장 채널을 전제합니다 — 채널명·제목이 아니라 운영 주체를 확인합니다.",
            "3. **콘텐츠 성격** — 정치 시사, 이단 반박, 극단적 신유 집회, 번영신학이",
            "   주력이면 교리가 건전해도 제외합니다. `성격 신호` 열이 참고 자료입니다.",
            "",
            "> **검색은 이단 채널도 똑같이 데려옵니다.** 그들도 주일예배와 성경 강해를",
            "> 올리고 총회도 있습니다. 이 시트는 후보를 모아 사실을 정리해 줄 뿐이고,",
            "> 거르는 일은 사람이 합니다. `자동 점검: 통과`는 승인이 아니라",
            "> **객관적 실격 사유가 없다**는 뜻입니다.",
            "",
            "**썸네일은 자동 점검이 보지 못합니다** — 제목이 멀쩡해도 썸네일이 자극적인 채널이 있습니다.",
            "",
            "`성격 신호` 열은 차단이 아니라 표시입니다. 최근 10건 중 몇 건의 제목에",
            "해당 어휘가 있었는지만 셉니다. 숫자가 크면 영상을 직접 열어 보세요.",
        ]
    )


def _render_queries() -> str:
    lines = [
        "## 사용한 검색어",
        "",
        "themes.yaml 전역 금지어(은혜·치유·축복·간증·기적·기도응답)는 쓰지 않았습니다 —",
        "태깅에서 장르를 잘못 부르는 단어는 발굴에서도 채널을 잘못 부릅니다.",
        "",
        "| 검색어 | 고른 이유 |",
        "|---|---|",
    ]
    for query, why in DISCOVERY_QUERIES:
        lines.append(f"| `{query}` | {why} |")
    return "\n".join(lines)


def _render_summary_row(index: int, c: Candidate) -> str:
    subs = f"{c.subscribers:,}" if c.subscribers is not None else "비공개"
    videos = f"{c.video_count:,}" if c.video_count is not None else "-"
    upload = (
        f"{c.last_upload_at[:10]} ({c.days_since_upload}일 전)"
        if c.last_upload_at and c.days_since_upload is not None
        else "확인 불가"
    )
    short = f"{c.short_ratio:.0%}" if c.short_ratio is not None else "-"
    signals = c.signal_counts
    signal_text = (
        ", ".join(f"{label} {count}" for label, count in signals.most_common())
        if signals
        else "-"
    )
    if c.blocked:
        verdict = "차단 채널"
    elif c.already_listed:
        verdict = "이미 등록됨"
    elif c.auto_ok:
        verdict = "통과"
    else:
        verdict = " / ".join(c.warnings)
    return (
        f"| {index} | {_escape(c.title)} |  | {c.appearances} | {subs} | {videos} | "
        f"{upload} | {short} | {signal_text} | {verdict} |"
    )


def _render_detail(index: int, c: Candidate) -> list[str]:
    head = f"### {index}. {c.title}"
    if c.blocked:
        head += "  — channel_blocklist 등재"
    elif c.already_listed:
        head += "  — 이미 등록됨"
    elif not c.auto_ok:
        head += f"  — {' / '.join(c.warnings)}"
    lines = [head, "", f"`{c.channel_id}`", ""]
    if not c.recent:
        lines += ["최근 영상을 가져오지 못했습니다.", ""]
        return lines
    lines += ["| # | 제목 | 길이 | 성격 신호 |", "|---:|---|---:|---|"]
    for i, v in enumerate(c.recent, start=1):
        flag = ", ".join(v.signals)
        short = " (3분 미만)" if v.is_short else ""
        lines.append(f"| {i} | {_escape(v.title)} | {v.duration_text}{short} | {flag} |")
    lines.append("")
    return lines


def _render_yaml_block(
    candidates: list[Candidate], now: datetime, reviewer: str
) -> list[str]:
    ready = [c for c in candidates if c.auto_ok and not c.already_listed]
    skipped = [c for c in candidates if not c.auto_ok and not c.already_listed]
    today = now.strftime("%Y-%m-%d")

    lines = [
        "## channel_allowlist.yaml 붙여넣기용 블록",
        "",
        f"자동 점검을 통과한 {len(ready)}개만 담았습니다. "
        f"실격 사유가 있는 {len(skipped)}개는 제외했으니, 직접 확인 후 필요하면 손으로 추가하세요.",
        "",
        "**`affiliation`과 `affiliation_verified`가 비어 있습니다.**",
        "이 두 필드는 승인 기준 1·2를 통과한 근거이고, 비어 있으면 로더가 실패합니다",
        "(`scripts/lib/allowlist.py`). 채우지 않으면 배치가 돌지 않습니다 —",
        "근거 없는 승인을 구조로 막기 위한 것입니다.",
        "",
        "`note`도 자동 수집된 사실일 뿐 선정 이유가 아닙니다. 판단을 적어 주세요.",
        "",
        "```yaml",
    ]
    if not ready:
        lines += ["# 자동 점검을 통과한 후보가 없습니다.", "```", ""]
        return lines

    for c in ready:
        upload = c.last_upload_at[:10] if c.last_upload_at else "확인 불가"
        signals = c.signal_counts
        signal_text = (
            " / 성격 신호 " + ", ".join(f"{k} {v}" for k, v in signals.most_common())
            if signals
            else ""
        )
        lines += [
            "  # TODO(검토): 교단/소속을 2개 이상 교차 확인하고 아래 두 필드를 채울 것.",
            "  #             이단 규정 목록 대조 전에는 승인하지 않는다.",
            f"  - channel_id: {c.channel_id}",
            f"    channel_name: {c.name_for_yaml}",
            "    affiliation: ",
            "    affiliation_verified: ",
            "    content_type: mixed        # sermon / worship / devotion / mixed 중 확인 후 수정",
            f'    added_at: "{today}"',
            f'    last_reviewed_at: "{today}"',
            f"    reviewed_by: {reviewer}",
            "    note: >",
            f"      [자동 수집] 발굴 검색어에 {c.appearances}회 등장, "
            f"최근 영상 {len(c.recent)}건, 마지막 업로드 {upload}"
            f"{signal_text}.",
            "      선정 기준 1~3에 대한 판단을 여기에 적을 것.",
            "",
        ]
    lines += ["```", ""]
    return lines


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


# =============================================================================
# 진입점
# =============================================================================


def print_estimate(top: int, hard_cap: int) -> int:
    rows = [
        ("발굴 검색", "search.list", len(DISCOVERY_QUERIES)),
        ("후보 채널 조회", "channels.list", -(-top // 50)),
        ("채널별 최근 업로드", "playlistItems.list", top),
        ("최근 영상 상세", "videos.list", top),
    ]
    total = sum(COST[endpoint] * calls for _, endpoint, calls in rows)
    print("\n예상 쿼터 소모량 (실행 전 산정)")
    print("=" * 60)
    print(f"  {'항목':<28}{'호출':>8}{'units':>12}")
    print("-" * 60)
    for label, endpoint, calls in rows:
        print(f"  {label:<28}{calls:>8,}{COST[endpoint] * calls:>12,}")
    print("-" * 60)
    print(f"  {'합계':<28}{'':>8}{total:>12,}")
    print(f"  하드캡 {hard_cap:,} → 여유 {hard_cap - total:,} units")
    print("=" * 60)
    return total


def resolve_out_path(out: Path, dry_run: bool) -> Path:
    """산출물 경로를 정한다 — 드라이런이 실제 결과를 덮지 못하게.

    FYM에서 실제로 사고가 났다: 661 units로 만든 검토 시트를 배선 검증용
    드라이런이 합성 데이터로 교체했다. 채널 ID는 상세 섹션에만 있어서
    요약표를 따로 읽어뒀어도 화이트리스트에 넣을 수 없었고, 다시 661을 썼다.

    **드라이런은 "API를 안 부른다"는 뜻이지 "아무것도 안 건드린다"가 아니다.**
    산출물 경로가 같으면 공짜 실행이 비싼 결과를 지운다.

    PYM은 두 겹으로 막는다:
      1. 파일명에 타임스탬프를 넣어 실행끼리 서로 덮지 않는다
      2. 드라이런은 파일명에 .dry-run을 넣어 실제 결과와 섞이지 않는다
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = ".dry-run" if dry_run else ""
    return out.with_name(f"{out.stem}.{stamp}{suffix}{out.suffix}")


def run(args: argparse.Namespace, budget_box: dict[str, Any] | None = None) -> int:
    now = datetime.now(timezone.utc)
    allowlist = load_allowlist(args.allowlist)
    blocklist = load_channel_blocklist(args.blocklist)
    listed = set(allowlist.active_ids)
    blocked = {c.channel_id: c.reason for c in blocklist.channels}

    logger.info(
        "발굴 검색어 %d개로 후보를 모은다 (등록 %d개 / 차단 %d개는 표시만 한다)",
        len(DISCOVERY_QUERIES),
        len(listed),
        len(blocked),
    )
    if allowlist.size == 0:
        logger.info("화이트리스트가 비어 있다 — Phase 0 진행 중이면 정상이다")

    estimated = print_estimate(args.top, args.hard_cap)
    if estimated > args.hard_cap:
        logger.error("예상 소모량이 하드캡을 넘는다 — 중단한다")
        return EXIT_QUOTA

    # 하드캡은 "이번 실행 하나"의 상한, 아래는 "그날 전체"의 상한이다.
    # 둘 다 있어야 한다 — 이 스크립트는 하루에 여러 번 돌려볼 수 있다.
    if not args.dry_run and not args.no_quota_log:
        try:
            usage, reserve = check_daily_quota(
                args.quota_log,
                estimated,
                ceiling=args.daily_ceiling,
                reserve_actions_batch=args.reserve_actions_batch,
                batch_probe=batch_succeeded_on,
            )
        except QuotaBudgetExceeded as exc:
            logger.error("%s", exc)
            logger.error(
                "그날 이미 쓴 양을 포함한 판단이다. "
                "정말 실행하려면 --no-quota-log, 배치 몫을 빼려면 "
                "--no-reserve-actions-batch."
            )
            return EXIT_QUOTA
        print(quota_table(usage, estimated, reserve, args.daily_ceiling))

    budget = QuotaBudget(hard_cap=args.hard_cap)
    if budget_box is not None:
        budget_box["budget"] = budget  # 중단돼도 실제 소모량을 기록할 수 있게 공유

    if args.dry_run:
        # DryRunClient는 blocklist 용어 풀로 가짜 제목을 만든다.
        # PYM은 제목 blocklist 사전이 없으므로 성격 신호어를 넘겨,
        # 신호 집계 경로가 실제로 도는지 드라이런에서 확인되게 한다.
        pool = [term for terms in SIGNAL_TERMS.values() for term in terms]
        client: Client = DryRunClient(budget, pool)
        logger.info("드라이런 — API를 호출하지 않는다")
    else:
        client = YouTubeClient(os.environ.get("YOUTUBE_API_KEY", ""), budget)

    counter, titles = collect_appearances(client)
    total_videos = sum(counter.values())
    logger.info("영상 %d건에서 채널 %d개 집계", total_videos, len(counter))

    candidates = inspect_candidates(
        client, counter, titles, listed, blocked, args.top, now
    )
    ready = sum(1 for c in candidates if c.auto_ok and not c.already_listed)
    logger.info(
        "상위 %d개 조사 완료 — 자동 점검 통과 %d개, 실격 %d개, 이미 등록 %d개",
        len(candidates),
        ready,
        sum(1 for c in candidates if not c.auto_ok and not c.already_listed),
        sum(1 for c in candidates if c.already_listed),
    )

    markdown = render_markdown(
        candidates,
        now=now,
        spent=budget.spent,
        total_channels=len(counter),
        total_videos=total_videos,
        reviewer=args.reviewer,
        dry_run=args.dry_run,
    )

    out = resolve_out_path(args.out, args.dry_run)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8", newline="\n")

    logger.info("%s 기록 — 소모 %d units", out.name, budget.spent)
    logger.info(
        "사람이 읽고 판단할 차례다. `교단/소속 확인` 열과 affiliation 필드를 채워야 "
        "승인이 성립한다."
    )
    return EXIT_OK


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="PYM 채널 화이트리스트 후보 수집 (일회성 도구, 월 1회 수준)"
    )
    parser.add_argument(
        "--allowlist", type=Path, default=root / "channel_allowlist.yaml"
    )
    parser.add_argument(
        "--blocklist", type=Path, default=root / "channel_blocklist.yaml"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "channel_candidates.md",
        help="산출물 기본 경로. 실제 파일명에는 타임스탬프가 붙는다",
    )
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP, help=f"조사할 상위 채널 수 (기본 {DEFAULT_TOP})"
    )
    parser.add_argument(
        "--reviewer",
        default=os.environ.get("REVIEWER") or os.environ.get("USERNAME") or "TODO",
        help="YAML 블록의 reviewed_by 값",
    )
    parser.add_argument("--hard-cap", type=int, default=DEFAULT_HARD_CAP)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--quota-log",
        type=Path,
        default=root / DEFAULT_LOG,
        help=f"일일 소모 기록 파일 (기본 {DEFAULT_LOG}, 커밋하지 않는다)",
    )
    parser.add_argument("--daily-ceiling", type=int, default=DAILY_CEILING)
    parser.add_argument(
        "--no-quota-log", action="store_true", help="일일 누적 검사·기록을 건너뛴다"
    )
    parser.add_argument(
        "--no-reserve-actions-batch",
        dest="reserve_actions_batch",
        action="store_false",
        help="Actions 일일 배치 몫(200)을 미리 빼두지 않는다",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    budget_box: dict[str, Any] = {}
    exit_code = EXIT_RETRYABLE
    try:
        exit_code = run(args, budget_box)
        return exit_code
    except QuotaExceeded as exc:
        logger.error("쿼터 중단: %s", exc)
        exit_code = EXIT_QUOTA
        return EXIT_QUOTA
    except Exception as exc:  # noqa: BLE001
        logger.exception("후보 수집 실패: %s", exc)
        exit_code = EXIT_RETRYABLE
        return EXIT_RETRYABLE
    finally:
        budget = budget_box.get("budget")
        spent = budget.spent if budget is not None else 0
        if not args.dry_run and not args.no_quota_log and spent > 0:
            usage = record_quota(
                args.quota_log,
                script="suggest_channels",
                units=spent,
                exit_code=exit_code,
            )
            logger.info(
                "쿼터 기록 — 이번 %s units, 오늘(PT %s) 누적 %s units",
                f"{spent:,}", usage.date, f"{usage.spent:,}",
            )


if __name__ == "__main__":
    raise SystemExit(main())
