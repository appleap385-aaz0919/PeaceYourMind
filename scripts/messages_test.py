#!/usr/bin/env python
"""문구 점검 — 공감·마무리 문구가 작성 원칙을 지키는지 전수 확인. 네트워크 없음.

    python scripts/messages_test.py

**문구는 코드가 아니라 사람이 읽는 문장이지만, 원칙 위반은 기계로 걸러진다.**
480건을 매번 눈으로 다시 읽을 수는 없고, 한 건만 새어도 그 화면을 본 사람에게는
그것이 서비스의 전부가 된다.

[작성 원칙 4종 — taxonomy.yaml 헤더와 같은 목록]
  정죄    "믿음이 부족해서" 계열. 감정을 신앙의 문제로 돌리지 않는다
  요구    "기도하세요" 같은 지시. 명령형을 쓰지 않는다
  단정    "하나님이 다 아세요" 같은 확언. 억울함·상실에서 반발을 부른다
  사실판정 "당신 탓이 아니에요" 계열. **앱은 사용자가 겪은 일을 모른다.**
          감정은 인정하되 상황의 옳고 그름은 말하지 않는다.
          편들어 주는 문장은 사실이 아닐 때 나머지 문구의 신뢰까지 함께 무너뜨린다.

[추가 점검]
  증폭    부정 감정 세분류에 감정을 키우는 문구가 섞이지 않았는가
          (긍정 감정 tone=증폭 세분류에서만 허용)
  전역 금지어  themes.yaml과 같은 목록 — 번영신학·자극 서사를 부르는 어휘
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "taxonomy.yaml"
EXIT_OK, EXIT_FAIL = 0, 1

# 부정 감정 대분류 — 증폭 방향 문구가 들어가면 안 된다 (FYM 원칙 승계).
NEGATIVE_PARENTS = {"anxiety", "anger", "frustration", "sadness", "exhaustion"}

# 위기 인접 세분류 — 표현을 특히 보수적으로 본다.
CRISIS_ADJACENT = {
    "sadness.sorrow",
    "sadness.lonely",
    "sadness.loss",
    "exhaustion.listless",
    "frustration.suppressed",
}

VIOLATIONS: dict[str, tuple[str, ...]] = {
    "정죄": (
        r"믿음이\s*(부족|약)",
        r"기도가\s*부족",
        r"의지가\s*약",
        r"게을러",
        r"노력이\s*부족",
        r"당신\s*잘못",
        r"탓이에요",
    ),
    "요구": (
        r"하세요",
        r"하십시오",
        r"해야\s*(해요|합니다|돼요)",
        r"하셔야",
        r"기도하(세요|십시오)",
        r"믿으세요",
        r"참으세요",
        r"힘내세요",
    ),
    "단정": (
        r"하나님이\s*\S*\s*(아세요|아십니다|주십니다|하십니다|해주세요)",
        r"반드시\s*(이루|응답|회복)",
        r"틀림없",
        r"분명히\s*(좋아|나아)",
    ),
    "사실판정": (
        r"탓이\s*아니",
        r"잘못이\s*아니었",
        r"당신이\s*옳",
        r"그\s*사람이\s*(틀렸|잘못)",
        r"억울한\s*게\s*맞",
        r"당연히\s*화날\s*만",
    ),
}

# 부정 감정에서 금지 — 감정을 키우는 방향
AMPLIFY = (
    r"실컷\s*(울|화)",
    r"마음껏\s*(화|분노|미워)",
    r"더\s*(울어|화내)",
    r"소리\s*질러",
    r"터뜨려",
)

# themes.yaml 전역 금지어와 같은 목록
FORBIDDEN_WORDS = ("치유", "축복", "간증", "기적", "기도응답")


def _check(failures: list[str], ok: bool, label: str, detail: str = "") -> None:
    print(f"{'   ' if ok else 'X  '}{label}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def scan(messages: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    """(세분류, 슬롯, 문구) 목록에서 원칙 위반을 찾는다."""
    hits: dict[str, list[str]] = {}
    for kind, patterns in VIOLATIONS.items():
        for sub, slot, text in messages:
            for pattern in patterns:
                if re.search(pattern, text):
                    hits.setdefault(kind, []).append(f"[{sub}/{slot}] {text}  ← /{pattern}/")
    return hits


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    failures: list[str] = []
    tax = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))
    subs = [(c["id"], s) for c in tax["categories"] for s in c["subcategories"]]

    messages: list[tuple[str, str, str]] = []
    for _parent, sub in subs:
        for text in sub.get("empathy_messages") or []:
            messages.append((sub["id"], "공감", text))
        for text in sub.get("closing_messages") or []:
            messages.append((sub["id"], "마무리", text))
    crisis = tax["safety"]["crisis_response"]["content_policy"]["closing_messages"] or []
    for text in crisis:
        messages.append(("crisis", "마무리", text))

    print(f"문구 {len(messages)}건 (세분류 {len(subs)}개 + 위기 {len(crisis)}건)")

    print("\n1. 개수 — 세분류마다 공감 10 · 마무리 10")
    print("-" * 76)
    short = [
        f"{s['id']}({len(s.get('empathy_messages') or [])}/{len(s.get('closing_messages') or [])})"
        for _p, s in subs
        if len(s.get("empathy_messages") or []) < 10 or len(s.get("closing_messages") or []) < 10
    ]
    _check(failures, not short, "모든 세분류가 10건씩 채워졌다", ", ".join(short))
    _check(failures, len(crisis) >= 3, "위기 화면 마무리 문구가 있다", f"{len(crisis)}건")

    print("\n2. 작성 원칙 4종 위반")
    print("-" * 76)
    hits = scan(messages)
    for kind in VIOLATIONS:
        found = hits.get(kind, [])
        _check(failures, not found, f"{kind} 없음", f"{len(found)}건" if found else "")
        for line in found[:5]:
            print(f"      {line}")

    print("\n3. 부정 감정에 증폭 방향이 섞이지 않았는가")
    print("-" * 76)
    amplified = [
        f"[{sub}/{slot}] {text}"
        for sub, slot, text in messages
        if sub.split(".")[0] in NEGATIVE_PARENTS
        for pattern in AMPLIFY
        if re.search(pattern, text)
    ]
    _check(failures, not amplified, "부정 감정 세분류에 증폭 문구 없음", ", ".join(amplified[:3]))

    print("\n4. 전역 금지어 (themes.yaml과 같은 목록)")
    print("-" * 76)
    forbidden = [
        f"[{sub}/{slot}] {text}"
        for sub, slot, text in messages
        for word in FORBIDDEN_WORDS
        if word in text
    ]
    _check(failures, not forbidden, "전역 금지어 없음", ", ".join(forbidden[:3]))

    print("\n5. 위기 인접 세분류 — 보수성 점검")
    print("-" * 76)
    # 위기 인접에서는 "괜찮아질 것"이라는 약속과 행동 재촉을 특히 피한다.
    #
    # **부정형은 위반이 아니다.** "이겨내는 게 아니라 지나가는 거예요"는 극복
    # 프레임을 거부하는 문장이고, 그것이 이 자리에서 쓰고 싶은 방향이다.
    # 부정을 못 가리는 검사는 오탐을 계속 내다가 결국 무시당하거나,
    # 그걸 피하려고 문장을 어색하게 비틀게 만든다.
    RISKY = (r"곧\s*(좋아|나아)질", r"금방\s*(지나|괜찮)", r"이겨\s*내", r"극복")
    NEGATION = re.compile(r"(아니|않|말고|못|없)")
    risky = [
        f"[{sub}/{slot}] {text}"
        for sub, slot, text in messages
        if sub in CRISIS_ADJACENT
        for pattern in RISKY
        for m in [re.search(pattern, text)]
        if m and not NEGATION.search(text[m.end() : m.end() + 12])
    ]
    _check(failures, not risky, "회복 약속·극복 요구 없음", ", ".join(risky[:3]))
    covered = {s for s in CRISIS_ADJACENT if any(m[0] == s for m in messages)}
    _check(
        failures,
        covered == CRISIS_ADJACENT,
        "위기 인접 5개 세분류가 모두 작성됐다",
        f"{len(covered)}/5",
    )

    print("\n6. 중복 — 같은 문구가 여러 세분류에 재사용되지 않았는가")
    print("-" * 76)
    seen: dict[str, list[str]] = {}
    for sub, slot, text in messages:
        seen.setdefault(text, []).append(f"{sub}/{slot}")
    dupes = {t: w for t, w in seen.items() if len(w) > 1}
    # 완전 동일 문구의 재사용은 허용하지 않는다 — 다른 감정에 같은 말을 하면
    # 문구가 감정을 읽고 쓴 것이 아니라는 인상을 준다.
    _check(
        failures,
        not dupes,
        "중복 문구 없음",
        "; ".join(f"{t} ({', '.join(w)})" for t, w in list(dupes.items())[:3]),
    )

    print("\n" + "=" * 76)
    if failures:
        print(f"실패 {len(failures)}건:")
        for f in failures:
            print(f"  - {f}")
        return EXIT_FAIL
    print("전부 통과")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
