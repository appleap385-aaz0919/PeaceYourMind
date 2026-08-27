"""자동 경보 — 사람이 잊어도 시스템이 먼저 말한다 (FYM 이식 + PYM 고유 5종).

배치는 판정만 하고 Issue 생성은 워크플로가 한다. 판정 로직과 GitHub 의존성을
분리해야 로컬에서도 같은 경로로 검증된다 (FYM 승계).

title은 워크플로의 중복 Issue 판정 키다 — 같은 사유는 항상 같은 문자열이어야 한다.

[PYM 고유 경보 — 전면 화이트리스트·주제 태깅·media_type에서 새로 필요해진 것]
    channel_zero_yield   승인 채널인데 필터 후 잔존 0건.
                         목록에 있으나 실질적으로 없는 채널이며, 유효 채널 수가
                         MIN_ALLOWLIST_SIZE 아래로 떨어진 것과 같은 의미다.
    theme_empty          주제 풀이 0건. 그 주제로 오는 감정 화면이 빈다.
    media_type_gap       주제에 한쪽 형식이 0건. [말씀]/[찬양] 토글을 눌러도
                         빈 화면이 나온다 (PLAN.md 3.4·4.2).
    untagged_high        수집했지만 어느 주제에도 안 붙은 비율이 높다.
                         주제 사전의 구멍이거나, 채널 성격이 PYM과 맞지 않는다는 신호
                         (themes.yaml [채널 승인과 콘텐츠 태깅은 별개다]).
    crisis_no_channels   crisis_eligible 채널이 0개. 위기 풀을 만들 원천이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "warning", "info"]
Route = Literal["issue", "summary"]

# 경보를 어디로 보낼 것인가 — 2026-08-19 개정.
#
# [왜 갈랐는가]
#   첫 실행에서 Issue가 44건 생겼다. 경보 1건 = Issue 1건이라는 FYM 방식을
#   그대로 썼는데, PYM은 주제 23개마다 진단 경보가 붙어 수가 근본적으로 다르다.
#   그중 32건은 "지금 데이터가 이렇다"이지 "무엇을 하라"가 아니었다.
#   그런 것이 매일 쌓이면 auto 라벨 자체를 아무도 보지 않게 된다.
#
#   ISSUE    조치가 필요한 사건. 사람이 무언가 해야 끝난다
#   SUMMARY  지금 상태. 매 실행 Job Summary 표로 남고, 악화될 때만 주간 요약 Issue가 뜬다
ROUTE_ISSUE: Route = "issue"
ROUTE_SUMMARY: Route = "summary"

# Job Summary에만 남기는 진단 경보.
#   theme_low_yield       주제 풀이 얇다 — 채널 구성의 현재 상태다
#   media_type_gap        주제에 한쪽 형식이 없다 — 같은 이유
#   theme_fallback_heavy  폴백 비율이 높다 — 매일 같은 값이 뜬다
#   untagged_high         미태깅 비율 — 제목 관행이 바뀌지 않는 한 그대로다
#   crisis_no_channels    crisis_eligible 채널 0개 — 아래 참조 (2026-08-20)
# 이것들이 나쁘다는 사실은 이미 안다. 알아야 할 것은 **악화되는가**이고,
# 그 판정은 주간 비교로 한다 (워크플로의 진단 요약 단계).
#
# [2026-08-20] crisis_no_channels를 여기로 옮겼다.
#   이 경보의 본문이 스스로 "의도된 안전 동작이며 결함이 아닙니다"라고 말한다.
#   결함이 아닌 것을 매일 Issue로 내면 그것이 바로 2026-08-19에 막으려던
#   상태다 — auto 라벨이 쌓여 아무도 안 보게 된다.
#   조치(위기 전용 채널 승인)는 HANDOFF 3절 9번에 계획으로 있고, 사람이
#   승인하기 전까지 이 값은 매일 똑같다. **매일 같은 값이면 상태 보고다.**
#
#   ⚠ 위기 경보 4종을 한 덩어리로 보지 말 것. 나머지 셋은 Issue로 남는다 —
#     crisis_empty · crisis_carried_over  채널이 **있는데도** 비었다 = 사건
#     crisis_stale                        시간이 갈수록 악화된다 = 사건
#     채널이 0개인 동안에는 이 셋이 아예 발동하지 않는다(lib/crisis.py에서
#     파생 경보를 접는다). 그래서 지금 상태에서 Issue는 0건이 된다.
#   ⛔ [2026-08-27] tab_over_cap은 **여기 넣지 않았다. 옮기지 말 것.**
#     이웃 경보(theme_fallback_heavy)가 summary라 같이 묶고 싶어지지만 성격이 다르다.
#     저쪽은 매일 같은 값이 뜨는 상태 보고이고, 이쪽은 **임계를 오늘의 정상 범위
#     위(26)에 두어 평소에는 아예 울리지 않게** 만든 경보다(selection.py TAB_OVER_*).
#     울린다는 것은 곧 "어제까지와 달라졌다"는 뜻이므로 사건이다 → Issue.
#     summary로 옮기면 그 설계가 무의미해진다.
SUMMARY_ONLY_TYPES = frozenset(
    {
        "theme_low_yield",
        "media_type_gap",
        "theme_fallback_heavy",
        "untagged_high",
        "crisis_no_channels",
    }
)


def route_for(alert_type: str) -> Route:
    """이 경보를 Issue로 낼 것인가, Summary에만 남길 것인가."""
    return ROUTE_SUMMARY if alert_type in SUMMARY_ONLY_TYPES else ROUTE_ISSUE

DEFAULT_RENOTIFY_DAYS = 7
# 안전 관련은 더 자주 찌른다 — 감지 주기보다 알림 주기가 길면 경보의 의미가 없다.
SAFETY_RENOTIFY_DAYS = 2
# 안전 장치가 아예 없는 상태는 매일 알린다.
CRITICAL_RENOTIFY_DAYS = 1


@dataclass(frozen=True)
class Alert:
    type: str
    severity: Severity
    title: str
    body: str
    labels: tuple[str, ...] = ()
    renotify_days: int = DEFAULT_RENOTIFY_DAYS

    @property
    def route(self) -> Route:
        return route_for(self.type)

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "renotify_days": self.renotify_days,
            # 워크플로가 이 값으로 Issue 생성 여부를 가른다. 판정은 여기서 끝내고
            # 워크플로는 옮겨 적기만 한다 — 정책이 두 곳에 흩어지지 않게.
            "route": self.route,
        }


@dataclass
class AlertCollector:
    alerts: list[Alert] = field(default_factory=list)

    def add(
        self,
        *,
        type: str,
        severity: Severity,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
        renotify_days: int = DEFAULT_RENOTIFY_DAYS,
    ) -> None:
        self.alerts.append(
            Alert(
                type=type,
                severity=severity,
                title=title,
                body=body,
                labels=labels,
                renotify_days=renotify_days,
            )
        )

    def to_json(self) -> list[dict[str, Any]]:
        return [a.to_json() for a in self.alerts]

    def __len__(self) -> int:
        return len(self.alerts)

    @property
    def has_critical(self) -> bool:
        return any(a.severity == "critical" for a in self.alerts)

    @property
    def issues(self) -> list[Alert]:
        """Issue로 낼 경보만."""
        return [a for a in self.alerts if a.route == ROUTE_ISSUE]

    @property
    def diagnostics(self) -> list[Alert]:
        """Job Summary에만 남길 진단."""
        return [a for a in self.alerts if a.route == ROUTE_SUMMARY]


# --- 화이트리스트 ------------------------------------------------------------


def channel_dead(channel_id: str, name: str) -> dict[str, Any]:
    return {
        "type": "channel_dead",
        "severity": "critical",
        "title": f"[화이트리스트] 채널 접근 불가: {name} ({channel_id})",
        "body": (
            f"채널 `{channel_id}` ({name}) 이(가) channels.list 응답에 없습니다. "
            "삭제·비공개·차단 가능성이 있습니다.\n\n"
            "PYM은 전면 화이트리스트라 이 채널의 영상은 오늘 한 건도 수집되지 않았습니다.\n"
            "조치: 채널 상태를 확인하고 `channel_allowlist.yaml`에서 제외하거나 교체하세요 (PR 필수)."
        ),
        "labels": ("allowlist", "auto"),
    }


def channel_review_overdue(channel_id: str, name: str, days: int) -> dict[str, Any]:
    return {
        "type": "channel_review_overdue",
        "severity": "warning",
        "title": f"[화이트리스트] 재검토 기한 초과: {name} ({channel_id})",
        "body": (
            f"`last_reviewed_at` 이후 {days}일이 지났습니다 (기준 120일).\n\n"
            "조치: 최근 영상 성향을 확인한 뒤 `last_reviewed_at`과 `reviewed_by`를 "
            "갱신하세요 (PR 필수)."
        ),
        "labels": ("allowlist", "auto"),
    }


def channel_zero_yield(channel_id: str, name: str, collected: int) -> dict[str, Any]:
    return {
        "type": "channel_zero_yield",
        "severity": "warning",
        "title": f"[배치] 필터 후 잔존 0건: {name} ({channel_id})",
        "body": (
            f"업로드 {collected}건을 수집했지만 필터를 통과한 영상이 없습니다.\n\n"
            "쇼츠 위주로 전환됐거나 길이 하한(3분)에 전부 걸린 상태입니다. "
            "**목록에 있으나 실질적으로 없는 채널**이며, 유효 채널 수가 최소 기준 "
            "아래로 떨어진 것과 같은 의미입니다.\n\n"
            "조치: 며칠 반복되면 채널 성격 변화를 확인하고 교체를 검토하세요."
        ),
        "labels": ("allowlist", "batch", "auto"),
    }


def allowlist_undersized(size: int, minimum: int) -> dict[str, Any]:
    return {
        "type": "allowlist_undersized",
        "severity": "critical",
        "title": f"[화이트리스트] 채널 수 부족 ({size}/{minimum})",
        "body": (
            f"활성 채널이 {size}개로 최소 기준 {minimum}개를 밑돕니다.\n\n"
            "PYM은 전면 화이트리스트라 이 목록이 곧 영상 공급원 전부입니다. "
            "주제 풀이 얇아지면 감정 화면이 빕니다.\n\n"
            "조치: `suggest_channels.py`로 후보를 발굴하고 승인 절차를 거쳐 보충하세요."
        ),
        "labels": ("allowlist", "safety", "auto"),
        "renotify_days": SAFETY_RENOTIFY_DAYS,
    }


def allowlist_empty() -> dict[str, Any]:
    return {
        "type": "allowlist_empty",
        "severity": "critical",
        "title": "[화이트리스트] 승인 채널 0개 — 수집할 대상이 없다",
        "body": (
            "`channel_allowlist.yaml`에 활성 채널이 없어 배치가 수집할 영상이 없습니다.\n\n"
            "조치: Phase 0(채널 승인)을 먼저 끝내세요."
        ),
        "labels": ("allowlist", "safety", "auto"),
        "renotify_days": CRITICAL_RENOTIFY_DAYS,
    }


def allowlist_placeholders(count: int) -> dict[str, Any]:
    return {
        "type": "allowlist_placeholders",
        "severity": "warning",
        "title": f"[화이트리스트] 예시 항목이 남아 있음 ({count}건)",
        "body": (
            f"`channel_allowlist.yaml`에 스캐폴드 예시 항목이 {count}건 남아 있어 "
            "배치가 건너뛰었습니다.\n\n실제 채널로 교체하세요."
        ),
        "labels": ("allowlist", "auto"),
    }


# --- 위기 풀 -----------------------------------------------------------------


def crisis_no_channels() -> dict[str, Any]:
    return {
        "type": "crisis_no_channels",
        "severity": "warning",
        "title": "[위기 카테고리] crisis_eligible 채널 0개",
        "body": (
            "`crisis_eligible: true`인 채널이 없어 위기 영상 풀을 만들 원천이 없습니다.\n\n"
            "위기 풀은 일반 풀보다 좁은 기준(정신건강 전문 사역·상담 사역 중심, "
            "PLAN.md 7절)으로 별도 승인해야 합니다. 승인 전까지 위기 화면은 "
            "상담 안내만 표시합니다 — **의도된 안전 동작이며 결함이 아닙니다.**"
        ),
        "labels": ("safety", "auto"),
    }


def crisis_carried_over(kept: int, minimum: int) -> dict[str, Any]:
    return {
        "type": "crisis_carried_over",
        "severity": "critical",
        "title": "[위기 카테고리] 확보량 미달 — 직전 결과 유지",
        "body": (
            f"필터 통과 영상이 {kept}건으로 최소 {minimum}건에 미달했습니다.\n\n"
            "규칙대로 필터를 완화하지 않고 직전 배치 결과를 유지했습니다. "
            "`crisis.updated_at`이 갱신되지 않으므로 신선도 경보가 이어질 수 있습니다.\n\n"
            "조치: crisis_eligible 채널의 상태를 확인하세요."
        ),
        "labels": ("safety", "auto"),
    }


def crisis_stale(updated_at: str, days: int, threshold: int) -> dict[str, Any]:
    return {
        "type": "crisis_stale",
        "severity": "critical",
        "title": "[위기 카테고리] 풀이 갱신되지 않음",
        "body": (
            f"`crisis.updated_at`이 {updated_at}로 {days}일째 갱신되지 않았습니다 "
            f"(기준 {threshold}일).\n\n"
            "직전 결과 유지 규칙이 반복 발동 중입니다. crisis_eligible 채널 보충이 필요합니다."
        ),
        "labels": ("safety", "auto"),
        "renotify_days": SAFETY_RENOTIFY_DAYS,
    }


def crisis_empty() -> dict[str, Any]:
    return {
        "type": "crisis_empty",
        "severity": "critical",
        "title": "[위기 카테고리] 영상 0건 — 상담 안내만 노출됨",
        "body": (
            "필터를 통과한 영상이 없고 유지할 직전 결과도 없어 위기 카테고리 영상이 "
            "비어 있습니다.\n\n"
            "앱은 상담 안내만 표시합니다(의도된 안전 동작). "
            "crisis_eligible 채널을 승인해 정상화하세요."
        ),
        "labels": ("safety", "auto"),
        "renotify_days": CRITICAL_RENOTIFY_DAYS,
    }


# --- 주제 풀 · 형식 ----------------------------------------------------------


def theme_low_yield(theme_id: str, count: int, minimum: int) -> dict[str, Any]:
    return {
        "type": "theme_low_yield",
        "severity": "warning",
        "title": f"[배치] 주제 확보량 미달: {theme_id}",
        "body": (
            f"`{theme_id}` 확보 영상이 {count}건으로 목표 하한 {minimum}건에 미달합니다.\n\n"
            "원인은 셋 중 하나입니다 — 채널 수 부족, 그 주제의 title_keywords가 "
            "실제 제목과 어긋남, 길이 필터 과다. "
            "리포트의 `untagged_sample`을 먼저 보세요."
        ),
        "labels": ("batch", "auto"),
    }


def theme_empty(theme_id: str) -> dict[str, Any]:
    return {
        "type": "theme_empty",
        "severity": "critical",
        "title": f"[배치] 주제 풀 0건: {theme_id}",
        "body": (
            f"`{theme_id}`에 영상이 한 건도 없습니다. 이 주제가 붙은 감정 화면은 "
            "영상 목록이 빈 채로 나옵니다.\n\n"
            "조치: title_keywords를 실제 제목과 대조하거나, 이 주제를 다루는 채널을 "
            "보충하세요."
        ),
        "labels": ("batch", "auto"),
    }


def media_type_gap(theme_id: str, missing: str, present: str, count: int) -> dict[str, Any]:
    return {
        "type": "media_type_gap",
        "severity": "warning",
        "title": f"[배치] 형식 편중: {theme_id}에 {missing} 0건",
        "body": (
            f"`{theme_id}`의 영상 {count}건이 전부 {present} 쪽입니다 "
            f"({missing} 0건, unknown 포함해도 0건).\n\n"
            f"앱의 [말씀]/[찬양] 토글에서 {missing} 쪽을 누르면 빈 화면이 나옵니다. "
            "토글은 비활성화하지 않고 문장으로 상태를 보여주는 것이 정책이지만"
            "(PLAN.md 3.4), 계속되면 그 주제를 다루는 반대 형식 채널이 필요합니다."
        ),
        "labels": ("batch", "auto"),
    }


def untagged_high(ratio: float, untagged: int, kept: int) -> dict[str, Any]:
    return {
        "type": "untagged_high",
        "severity": "warning",
        "title": f"[배치] 주제 미태깅 비율 높음 ({ratio:.0%})",
        "body": (
            f"필터를 통과한 {kept}건 중 {untagged}건이 어느 주제에도 붙지 않았습니다.\n\n"
            "미태깅 자체는 정상 동작입니다(themes.yaml [채널 승인과 콘텐츠 태깅은 별개다]). "
            "다만 비율이 높으면 둘 중 하나입니다 — 주제 사전의 구멍이거나, "
            "채널 성격이 PYM 주제 체계와 맞지 않는 것입니다.\n\n"
            "리포트의 `untagged_by_channel`을 보면 어느 쪽인지 갈립니다. "
            "특정 채널에 몰려 있으면 그 채널의 승인 근거를 다시 보세요."
        ),
        "labels": ("batch", "auto"),
    }


def theme_fallback_heavy(
    subcategory: str, ratio: float, fallback: int, total: int
) -> dict[str, Any]:
    return {
        "type": "theme_fallback_heavy",
        "severity": "warning",
        "title": f"[배치] 폴백 과다: {subcategory}",
        "body": (
            f"`{subcategory}` 화면 {total}건 중 {fallback}건({ratio:.0%})이 폴백입니다 "
            "(기준 50%).\n\n"
            "**주제 사전이나 채널 구성이 그 감정을 못 받치고 있다는 신호입니다.** "
            "폴백은 형식(말씀/찬양)과 채널만 보고 채운 것이라, 이 비율이 높을수록 "
            "그 화면은 '이 감정에 맞춰 고른 목록'이 아니라 '채널 최신 목록'에 가까워집니다.\n\n"
            "조치: 이 세분류에 매핑된 주제의 `title_keywords`를 실제 제목과 대조하거나, "
            "그 주제를 다루는 채널을 보충하세요."
        ),
        "labels": ("batch", "auto"),
    }


def theme_too_few(
    subcategory: str, side: str, count: int, minimum: int, *, empty: bool
) -> dict[str, Any]:
    """토글 한쪽이 목록으로 성립하지 않는다.

    [2026-08-26 — 화면 단위에서 **탭 단위**로 옮겼다]
      전에는 화면 전체 건수(주제분+폴백)로 쟀다. 탭별 상한(2.64) 이후로는 그 수가
      **사용자가 보는 것과 다르다** — 사용자는 한 탭만 본다. 말씀 20 · 찬양 2인
      화면은 합계 22라 옛 기준(8)을 통과하지만 찬양 쪽 사용자에게는 빈 화면이다.

    ★ **탭 검사가 화면 검사를 포함한다.** unknown이 양쪽에 세이므로 각 탭의 노출
      건수는 화면 합계 이하다(vis <= count). 따라서 화면 합계가 minimum 미만이면
      두 탭 모두 반드시 걸린다 — 옛 검사가 잡던 것을 하나도 놓치지 않는다.

    [두 단계로 나눈 이유 — MEDIA_FLOOR를 여기로 흡수했다]
      empty=True   MEDIA_FLOOR 미만. 사실상 빈 탭이다 → critical
      empty=False  SUBCATEGORY_MIN_VIDEOS 미만. 얇다 → warning
      ⚠ 전에는 MEDIA_FLOOR가 logger.error로만 남아 **아무도 보지 않았다.**
        "있다고 믿는 검사가 없는 상태"를 만들지 않으려고 경보로 올렸다.
    """
    label = "사실상 빈 탭" if empty else "목록 성립 불가"
    return {
        "type": "theme_too_few",
        "severity": "critical" if empty else "warning",
        "title": f"[배치] {label}: {subcategory} [{side}] ({count}건)",
        "body": (
            f"`{subcategory}` 화면의 **[{side}] 토글**에 나갈 영상이 {count}건으로 "
            f"최소 {minimum}건에 미달합니다.\n\n"
            "폴백까지 동원하고도 이 수준이면 그 감정에 그 형식으로 내놓을 것이 "
            "실질적으로 없다는 뜻입니다.\n\n"
            "⚠ 이 값은 **그 탭에서 실제로 보이는 건수**입니다(unknown 포함). "
            "화면 합계가 아니라 사용자가 토글을 눌렀을 때 보는 수입니다.\n\n"
            "조치: 그 형식의 채널 보충이 가장 직접적입니다. 그 전에 이 세분류에 "
            "매핑된 주제들이 그 형식을 실제로 공급하는지 확인하세요 "
            "(진단의 `media_type_gaps`·`themes_empty`)."
        ),
        "labels": ("batch", "auto"),
        "renotify_days": SAFETY_RENOTIFY_DAYS,
    }


def tab_over_cap(
    subcategory: str, side: str, count: int, threshold: int, *, severe: bool
) -> dict[str, Any]:
    """탭 노출이 의도한 상한(20)을 크게 넘었다.

    [무엇을 재는가 — theme_too_few의 반대쪽 끝이다]
      theme_too_few  탭이 너무 얇다 (< 4 / < 8)
      tab_over_cap   탭이 너무 두껍다 (>= 26 / >= 30)
      둘 다 **그 탭에서 실제로 보이는 건수**를 본다(unknown 포함).

    [왜 20 초과를 바로 알리지 않는가 — 초과는 허용된 상태다]
      TAB_MAX_VIDEOS가 보장하는 것은 "한 탭이 20건 이하"가 아니라 "각 패스의
      기여가 20 이하"다. 두 패스가 하나의 목록에 쌓고 unknown이 양쪽 탭에
      보이므로, 뒷 패스의 unknown이 앞 패스의 탭에 더해져 20을 넘는다.
      2026-08-26 실측으로 15개 탭이 21~24였고, **사용자 결정(2026-08-27)으로
      이 초과를 허용했다**(D안, HANDOFF 2.72).

      그래서 이 경보는 초과를 잡는 것이 아니라 **정상 범위를 벗어난 것**을 잡는다.
      임계 근거는 selection.py의 TAB_OVER_* 주석에 있다.

    ★ 이 경보는 사실상 **unknown 급증 감지기**다. 초과분은 곧 뒷 패스가 담은
      unknown 수이므로, 울린다는 것은 미판별 영상이 늘었다는 뜻이다.
      진단의 `unknown_ratio`를 함께 볼 것 — 그쪽이 선행 지표다.

    ⛔ 이 경보에 대응한다고 B안(뒷 패스의 unknown 억제)이나 C안(사후 절단)으로
      가지 말 것. 둘 다 기각됐다(selection.py TAB_MAX_VIDEOS 주석).
      20으로 정확히 맞추는 길은 탭별 목록 분리(A안)뿐이다.
    """
    label = "탭 과다 노출" if severe else "탭 노출 상한 초과"
    return {
        "type": "tab_over_cap",
        "severity": "critical" if severe else "warning",
        "title": f"[배치] {label}: {subcategory} [{side}] ({count}건)",
        "body": (
            f"`{subcategory}` 화면의 **[{side}] 토글**에 {count}건이 노출됩니다 "
            f"(경보 임계 {threshold}건, 의도한 상한 20건).\n\n"
            "초과 자체는 허용된 상태입니다 — unknown(형식 미판별) 영상이 양쪽 탭에 "
            "모두 보이기 때문에 생기는 구조적 여유입니다. **다만 이 수치는 "
            "unknown이 늘면 함께 늘고, 구조적으로는 40건까지 벌어질 수 있습니다.**\n\n"
            "조치: 먼저 진단의 `unknown_ratio`를 보세요. 그쪽이 올랐다면 원인은 "
            "이 화면이 아니라 **형식 판별**입니다 — 곡명만 나열된 찬양 제목이 "
            "대표적입니다(HANDOFF 2.71 ⑤). 제목 어휘·곡명 사전을 보강하면 "
            "unknown이 줄어 이 수치도 함께 내려갑니다.\n\n"
            "⛔ 선정 로직을 부분 수정해 20에 맞추려 하지 마세요. 검토를 마치고 "
            "기각한 안이 둘 있습니다(HANDOFF 2.72) — 뒷 패스의 unknown 억제는 "
            "주제분이 얇은 탭을 다시 비게 만들고, 사후 절단은 반대 탭을 깎아 "
            "순환합니다."
        ),
        "labels": ("batch", "auto"),
    }
