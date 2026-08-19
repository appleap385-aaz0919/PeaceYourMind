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

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "renotify_days": self.renotify_days,
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
