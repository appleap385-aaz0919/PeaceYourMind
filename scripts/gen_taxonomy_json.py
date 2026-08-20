#!/usr/bin/env python
"""taxonomy.yaml -> app/src/data/taxonomy.json (앱 번들). API 소모 0.

앱이 쓰는 것만 담는다. 큐레이션 메타(선정 근거 주석·검토 이력)는 YAML에 남고
번들에는 나가지 않는다 — 앱이 안 쓰는 데이터를 매 방문 내려받게 할 이유가 없다.

**빼는 것과 그 이유**
    blocklist_tiers   배치가 쓰는 사전이다. 앱은 영상을 거르지 않는다
                      (거를 것이 있으면 배치에서 이미 걸렀어야 한다)
    safety.crisis_response.content_policy
                      배치·운영 정책이다. 앱이 쓰는 건 message·resources뿐
    tone              문구 작성 지침이다. 화면에 나가지 않는다

**남기는 것** — 분류에 필요한 최소 집합 + 화면 문구
    categories[].subcategories[]  id·label·keywords·empathy·closing
    safety.crisis_keywords        위기 우선 검사 (분류보다 먼저)
    safety.crisis_response        상담 안내 문구·연락처·마무리 문구
    normalization                 앱과 배치가 같은 규칙을 쓰는지 대조하는 근거
    ui                            인사·플레이스홀더·로딩·선택 UI 문구

게이트 — 하나라도 어긋나면 파일을 쓰지 않는다.
    1. 세분류 24개, id 중복 없음
    2. 모든 세분류에 keywords·empathy_messages·closing_messages가 있다
       (빈 목록이면 화면에 아무 문장도 못 띄운다)
    3. 위기 키워드가 비어 있지 않다 — 비면 위기 검사가 통째로 무력화된다
    4. themes.yaml mapping과 세분류 집합이 일치한다
    5. 문구가 작성 원칙을 지킨다 (scripts/messages_test.py와 같은 검사)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "taxonomy.yaml"
THEMES = ROOT / "themes.yaml"
OUT = ROOT / "app" / "src" / "data" / "taxonomy.json"

EXPECTED_SUBCATEGORIES = 24
EXIT_OK, EXIT_FAIL = 0, 1


class GenError(RuntimeError):
    """게이트 위반. 산출물을 쓰지 않는다."""


def build(tax: dict[str, Any]) -> dict[str, Any]:
    categories = []
    for category in tax["categories"]:
        subs = []
        for sub in category["subcategories"]:
            subs.append(
                {
                    "id": sub["id"],
                    "label": sub["label"],
                    "keywords": list(sub.get("keywords") or []),
                    "empathy_messages": list(sub.get("empathy_messages") or []),
                    "closing_messages": list(sub.get("closing_messages") or []),
                }
            )
        categories.append(
            {
                "id": category["id"],
                "label": category["label"],
                "keywords": list(category.get("keywords") or []),
                "subcategories": subs,
            }
        )

    crisis = tax["safety"]["crisis_response"]
    policy = crisis.get("content_policy") or {}
    return {
        "version": str(tax.get("meta", {}).get("version", "")),
        "categories": categories,
        "safety": {
            "crisis_keywords": list(tax["safety"]["crisis_keywords"]),
            # 단독 입력일 때만 위기인 말 — 부분 문자열로 쓰면 사별("할머니가
            # 죽어서 슬퍼요")·관용구·타인 지향 분노를 통째로 빨아들인다.
            # 근거는 taxonomy.yaml [단독 입력] 절에 있다.
            "crisis_exact": list(tax["safety"].get("crisis_exact") or []),
            "crisis_response": {
                "message": " ".join(str(crisis["message"]).split()),
                "resources": [
                    {"name": r["name"], "number": str(r["number"])}
                    for r in crisis["resources"]
                ],
                "closing_messages": list(policy.get("closing_messages") or []),
                # 앱이 위기 화면에서 토글·폴백을 쓰지 않는다는 사실을 데이터에도 남긴다.
                # 코드가 강제하고(components/CrisisScreen), 테스트가 다시 확인한다.
                "media_type_toggle": bool(policy.get("media_type_toggle", False)),
                "fallback": bool(policy.get("fallback", False)),
            },
        },
        "normalization": tax.get("normalization", {}),
        "ui": build_ui(tax.get("ui", {})),
        # 형식 기본값은 themes.yaml에서 온다 (감정 체계가 아니라 매핑 정책이다).
        # 앱이 파일 하나만 읽게 하려고 여기 합치되, 키 이름으로 출처를 남긴다.
        "media_defaults": {},
    }


def build_ui(ui: dict[str, Any]) -> dict[str, Any]:
    """화면이 쓰는 모양으로 정리한다 — rule 같은 작성 지침은 번들에 넣지 않는다.

    {rule, items} 형태를 목록으로 편다. 앱에서 `ui.placeholders.items`를 매번
    쓰게 하면, 나중에 다른 키를 추가할 때 화면 코드가 YAML 구조에 끌려다닌다.
    """
    return {
        "placeholders": list(ui.get("placeholders", {}).get("items", [])),
        "empty_input": list(ui.get("empty_input", {}).get("items", [])),
        "no_match": str(ui.get("no_match", {}).get("message", "")),
        "loading": {
            "min_duration_ms": int(ui.get("loading", {}).get("min_duration_ms", 1000)),
            "messages": list(ui.get("loading", {}).get("messages", [])),
        },
        "select_mode": {
            k: v
            for k, v in (ui.get("select_mode") or {}).items()
            if k != "rule"
        },
        "entry_greetings": {
            k: v
            for k, v in (ui.get("entry_greetings") or {}).items()
            if k != "rule" and isinstance(v, list)
        },
        "revisit": {
            k: v
            for k, v in (ui.get("revisit") or {}).items()
            if isinstance(v, list)
        },
    }


def validate(data: dict[str, Any], mapping_ids: set[str]) -> None:
    problems: list[str] = []
    subs = [s for c in data["categories"] for s in c["subcategories"]]
    ids = [s["id"] for s in subs]

    if len(ids) != EXPECTED_SUBCATEGORIES:
        problems.append(f"세분류가 {len(ids)}개다 (기대 {EXPECTED_SUBCATEGORIES})")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"세분류 id 중복 — {', '.join(duplicates)}")

    ui = data["ui"]
    for field in ("placeholders", "empty_input", "loading", "select_mode"):
        if not ui.get(field):
            problems.append(f"ui.{field}가 비어 있다 — 화면에 띄울 문구가 없다")
    if not ui["loading"]["messages"]:
        problems.append("ui.loading.messages가 비어 있다")
    if ui["loading"]["min_duration_ms"] < 1000:
        # FYM Phase 0.5에서 즉답→800ms→1000ms를 비교해 1000ms로 확정했다.
        # 낮추는 변경은 그 검토를 되돌리는 것이므로 여기서 막는다.
        problems.append(
            f"로딩 최소 노출이 {ui['loading']['min_duration_ms']}ms다 — 확정값은 1000ms"
        )
    if set(data["media_defaults"]) != mapping_ids:
        problems.append("media_defaults 세분류 집합이 mapping과 다르다")

    for sub in subs:
        for field in ("keywords", "empathy_messages", "closing_messages"):
            if not sub[field]:
                problems.append(f"{sub['id']}에 {field}가 비어 있다")

    if not data["safety"]["crisis_keywords"]:
        problems.append("위기 키워드가 비어 있다 — 위기 검사가 무력화된다")
    if not data["safety"]["crisis_exact"]:
        problems.append('단독 입력 위기어가 비어 있다 — "죽어"만 적은 입력을 놓친다')
    overlap = set(data["safety"]["crisis_exact"]) & set(
        data["safety"]["crisis_keywords"]
    )
    if overlap:
        problems.append(
            f"단독 입력 위기어가 부분 문자열 목록에도 있다: {sorted(overlap)} — "
            "부분 문자열로 쓰이는 순간 사별·관용구가 위기로 간다"
        )
    if not data["safety"]["crisis_response"]["resources"]:
        problems.append("상담 연락처가 비어 있다")
    if data["safety"]["crisis_response"]["media_type_toggle"]:
        problems.append("위기 화면에 토글이 켜져 있다 (PLAN.md 7절 위반)")
    if data["safety"]["crisis_response"]["fallback"]:
        problems.append("위기 화면에 폴백이 켜져 있다 (PLAN.md 7절 위반)")

    if set(ids) != mapping_ids:
        only_tax = sorted(set(ids) - mapping_ids)
        only_map = sorted(mapping_ids - set(ids))
        problems.append(
            "themes.yaml mapping과 세분류 집합이 다르다 — "
            f"taxonomy에만 {only_tax or '없음'} / mapping에만 {only_map or '없음'}"
        )

    if problems:
        raise GenError("게이트 실패:\n  " + "\n  ".join(problems))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    tax = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))
    themes = yaml.safe_load(THEMES.read_text(encoding="utf-8"))
    mapping_ids = set(themes["mapping"])

    data = build(tax)
    data["media_defaults"] = dict(themes.get("media_defaults") or {})
    try:
        validate(data, mapping_ids)
    except GenError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_FAIL

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    OUT.write_text(payload + "\n", encoding="utf-8")

    subs = [s for c in data["categories"] for s in c["subcategories"]]
    keywords = sum(len(s["keywords"]) for s in subs)
    messages = sum(len(s["empathy_messages"]) + len(s["closing_messages"]) for s in subs)
    print(
        f"{OUT.relative_to(ROOT)} 기록 — {len(payload):,}바이트 / "
        f"세분류 {len(subs)} · 키워드 {keywords} · 문구 {messages} · "
        f"위기 키워드 {len(data['safety']['crisis_keywords'])}"
        f" (+단독 {len(data['safety']['crisis_exact'])})"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
