#!/usr/bin/env python
"""HANDOFF.md의 규모 수치를 **실측해서 채운다** — 네트워크·API 호출 없음.

    python scripts/stats.py            실측값을 표로 출력한다
    python scripts/stats.py --write    HANDOFF.md의 표시 구간을 갱신한다
    python scripts/stats.py --check    문서와 실측이 다르면 종료 코드 1  ← 게이트

[왜 만들었나 — 2026-08-24]
    같은 수치가 HANDOFF 1절과 3절에 손으로 두 번 적혀 있었고, 갈라졌다.

        장 본문   1절 174개 장 4,283절 · 3절 178개 장      실측 178개 장 4,442절
        앱 테스트  1절 105건(+Phase 3줄 61건) · 3절 110건   실측 110건
        구절      양쪽 다 "293 (감정 283 + 위기 10)"        실측 감정 293 + 위기 10 = 303

    구절은 **양쪽이 똑같이 틀렸다.** 한쪽을 고치고 다른 쪽을 잊은 것이 아니라,
    한 번 잘못 적힌 값이 복사돼 두 곳에 남은 것이다. 어느 쪽이 최신인지
    문서만 봐서는 가릴 수 없었고, 그래서 "3절이 최신으로 보인다"는 추정이 나왔다.
    **추정이 필요했다는 것 자체가 결함이다.**

[그래서 여기서 정하는 것과 정하지 않는 것을 가른다]
    여기서 정한다       저장소 파일만 읽으면 언제나 같은 답이 나오는 것
                       (구절·장·어휘·채널·테스트 수)
    여기서 정하지 않는다  코퍼스에 따라 매일 달라지는 것
                       (주제별 풀 크기 · 폴백 비율 · 총 노출)
                       이런 값은 **적는 순간 낡는다.** 문서에는 숫자 대신
                       측정 명령과 "언제 어느 코퍼스로 쟀는지"를 남긴다.
                       근거는 HANDOFF 2.42절(retag --screens의 유효 범위)이다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.allowlist import MIN_ALLOWLIST_SIZE, load_allowlist  # noqa: E402
from lib.channel_blocklist import load_channel_blocklist  # noqa: E402
from lib.krv_source import KrvBible, parse_ref  # noqa: E402
from lib.reviewed_out import load_reviewed_out  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "HANDOFF.md"
APP_TEST_DIR = ROOT / "app" / "test"
EXIT_OK, EXIT_FAIL = 0, 1

BEGIN_FMT = "<!-- STATS:BEGIN {} -->"
BEGIN = BEGIN_FMT.format("규모")  # 표지 형식을 설명하는 주석들이 이 이름을 인용한다
END = "<!-- STATS:END -->"
NOTE = "<!-- scripts/stats.py --write 로 생성한다. 손으로 고치지 말 것. -->"

# 파이썬 게이트 — 이 목록이 곧 "게이트 N종"의 근거다.
PY_GATES = (
    "verify_verses.py --check",
    "fill_verses.py --verify",
    "tagging_test.py",
    "spread_test.py",
    "messages_test.py",
)
# 줄 첫머리의 test( 만 센다. **선언 수이지 실행 수가 아니다.**
#
# ⚠ 2026-08-24 재대조: 정적 140 · 러너 150. 처음 적을 때는 같았으나(110=110)
#   그 뒤로 **반복문이 test()를 여러 번 부르는 자리**가 생겨 갈라졌다 —
#   verses.test.js의 AD_FREE_SCREENS(1→2) · ads.test.js의 실측 분포표(1→10).
#   정적 검사로는 반복 횟수를 알 수 없고, 알려면 node를 띄워야 하는데 그러면
#   "저장소 파일만 읽어 같은 커밋이면 같은 답"이라는 이 스크립트의 성질이 깨진다.
#
# ★ 2026-08-25 확정 — **선언 수로 둔다. 러너 집계로 바꾸지 않는다.**
#   근거 두 가지다.
#     1. 러너 집계로 바꾸면 node 실행이 필요해져, "저장소 파일만 읽어
#        같은 커밋이면 같은 답"이라는 이 스크립트의 성질이 깨진다.
#     2. 실행 수는 이미 게이트가 검증한다 — 여기서 또 셀 이유가 없다.
#   ⛔ "정적과 러너가 다르다"를 결함으로 보고 다시 열지 말 것. 세는 대상이
#     다를 뿐이고, 그 차이는 위에 적힌 그대로다.
#   실행 수가 필요하면 app 디렉터리에서 npm test 를 돌려 그 집계를 볼 것.
_APP_TEST = re.compile(r"^\s*test\(", re.MULTILINE)


def _is_psalm(ref: str) -> bool:
    return ref.startswith("시편")


def measure() -> dict[str, Any]:
    """저장소 파일만 읽어 규모를 잰다. 같은 커밋이면 언제나 같은 답이다."""
    raw = yaml.safe_load((ROOT / "verses.yaml").read_text(encoding="utf-8"))
    emotion, crisis = raw["verses"], raw["crisis"]
    every = emotion + crisis

    bible = KrvBible(ROOT / "data" / "krv" / "bible_1961_krv.json")
    chapters: dict[tuple[str, int], int] = {}
    for verse in emotion:  # 장 본문은 감정 풀에서만 뽑는다 (gen_krv_chapters.py 참조)
        ref = parse_ref(verse["ref"])
        key = (ref.book_key, ref.start[0])
        chapters[key] = len(bible.chapter_verses(ref.book_key, ref.start[0]))

    themes = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    theme_kw = sum(len(t.get("title_keywords") or []) for t in themes["themes"])
    media_kw = sum(len(m.get("title_keywords") or []) for m in themes["media_types"])

    taxonomy = yaml.safe_load((ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))
    subs = [s for c in taxonomy["categories"] for s in (c.get("subcategories") or [])]
    emotion_kw = sum(len(s.get("keywords") or []) for s in subs)

    allowlist = load_allowlist(ROOT / "channel_allowlist.yaml")
    blocklist = load_channel_blocklist(ROOT / "channel_blocklist.yaml")
    reviewed = load_reviewed_out(ROOT / "channel_reviewed_out.yaml")

    app_tests = sum(
        len(_APP_TEST.findall(path.read_text(encoding="utf-8")))
        for path in sorted(APP_TEST_DIR.glob("*.test.js"))
    )

    return {
        "emotion": len(emotion),
        "crisis": len(crisis),
        "verses": len(every),
        "excluded": len(raw.get("excluded") or []),
        # 시편 비율은 **감정 풀 기준**이다 — 2.39·2.41절의 장르 분포 논의가
        # 감정 화면을 대상으로 하고, 위기 풀은 화면 구성이 다르기 때문이다.
        "psalms": sum(1 for v in emotion if _is_psalm(v["ref"])),
        "read_from": sum(1 for v in every if v.get("read_from")),
        "chapters": len(chapters),
        "chapter_verses": sum(chapters.values()),
        "books": len({book for book, _ in chapters}),
        "themes": len(themes["themes"]),
        "theme_kw": theme_kw,
        "media_kw": media_kw,
        "categories": len(taxonomy["categories"]),
        "subcategories": len(subs),
        "emotion_kw": emotion_kw,
        "allowlist": allowlist.size,
        "blocklist": len(blocklist.channels),
        "reviewed_out": len(reviewed.channels),
        "py_gates": len(PY_GATES),
        "app_tests": app_tests,
    }


def render(m: dict[str, Any]) -> str:
    """HANDOFF에 넣을 블록. 서식의 정의는 여기 한 곳뿐이다."""
    psalm_rate = m["psalms"] / m["emotion"] * 100
    room = m["allowlist"] - MIN_ALLOWLIST_SIZE
    tail = (
        " = MIN_ALLOWLIST_SIZE (한 건만 빠져도 경보)"
        if room == 0
        else f" (하한 {MIN_ALLOWLIST_SIZE}까지 여유 {room})"
    )
    lines = [
        BEGIN_FMT.format("규모"),
        NOTE,
        "```",
        f"구절       {m['verses']}  = 감정 {m['emotion']} + 위기 {m['crisis']}",
        f"           감정 중 시편 {m['psalms']} ({psalm_rate:.1f}%)"
        f" · 비시편 {m['emotion'] - m['psalms']}",
        f"           read_from 지정 {m['read_from']}건"
        f" · 검토 후 제외 {m['excluded']}건",
        f"장 본문     {m['chapters']}개 장 {m['chapter_verses']:,}절 ({m['books']}권)"
        " — 감정 구절이 닿는 장만",
        "           app/public/krv/ · .gitignore 대상 · 매 빌드 재생성",
        f"주제       {m['themes']}개 · 제목 어휘 {m['theme_kw']}"
        f" · 형식 어휘 {m['media_kw']}",
        f"감정 분류   대분류 {m['categories']} · 세분류 {m['subcategories']}"
        f" · 키워드 {m['emotion_kw']}",
        f"채널       allowlist {m['allowlist']}{tail}",
        f"           blocklist {m['blocklist']} · reviewed_out {m['reviewed_out']}",
        f"게이트      파이썬 {m['py_gates']}종 + 앱 {m['app_tests']}건",
        "```",
        END,
    ]
    return "\n".join(lines)


# --- 앱 사실 --------------------------------------------------------------
#
# ⛔ **저장소에 커밋된 파일만 읽는다.** node_modules·빌드 산출물은 보지 않는다 —
#   같은 커밋이면 언제나 같은 답이 나와야 --check가 게이트로 성립한다.
#   그래서 플러그인이 병합해 넣는 권한은 여기 없다. 병합 결과는 APK로 확인하고
#   그 기록은 HANDOFF 2.92절에 있다.
#
# [왜 이 블록이 생겼나 — 2026-08-31]
#   같은 병이 다섯 번 났다. 코드가 앞서가고 HANDOFF가 안 따라온 것이다.
#     About 상수 3건이 "비어 있다"로 일주일 남았고, 문의처는 낡은 주소였다.
#   값은 코드에 있으니 **기계가 잡을 수 있다.** 상태("완료/미착수")는 사람의
#   판단이라 여기서 다루지 않는다 — 그 경계가 이 블록의 설계다.


def _grab(text: str, pattern: str, what: str) -> str:
    """정규식 첫 그룹을 뽑는다. 못 찾으면 세운다 — 조용히 빈 값을 넣지 않는다."""
    hit = re.search(pattern, text)
    if not hit:
        raise ValueError(f"{what}를 찾지 못했다 — 소스가 바뀌었으면 stats.py도 고칠 것")
    return hit.group(1)


def measure_app() -> dict[str, Any]:
    """앱의 확정 사실을 코드에서 읽는다. 손으로 적힌 값과 갈라지지 않게 한다."""
    app = ROOT / "app"
    cap = json.loads((app / "capacitor.config.json").read_text(encoding="utf-8"))
    pkg = json.loads((app / "package.json").read_text(encoding="utf-8"))
    gradle = (app / "android" / "variables.gradle").read_text(encoding="utf-8")
    manifest = (
        app / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    notify = (app / "src" / "lib" / "notify.js").read_text(encoding="utf-8")
    select = (app / "src" / "lib" / "notifySelect.js").read_text(encoding="utf-8")
    about = (app / "src" / "components" / "About.jsx").read_text(encoding="utf-8")

    # versionCode 계산식의 정의는 vite.config.js에 있다. 여기 것과 갈라지면
    # appbuild.test.js가 잡는다 — 그쪽이 산출물을 직접 보기 때문이다.
    major, minor, patch = (int(n) for n in pkg["version"].split("."))

    # createChannel에 **실제로 넘기는 인자**만 본다. 주석은 지운다 —
    # 주석에 적힌 값으로 문서가 채워지면 이 블록이 거짓말을 하게 된다.
    raw_args = _grab(
        notify, r"createChannel\(\{([\s\S]*?)\n\s*\}\);", "createChannel 호출"
    )
    channel_args = "\n".join(line.split("//")[0] for line in raw_args.splitlines())

    declared = re.findall(r'uses-permission[^>]*android:name="([^"]+)"', manifest)
    removed = re.findall(
        r'uses-permission\s+android:name="([^"]+)"[^>]*tools:node="remove"', manifest
    )

    return {
        "app_id": cap["appId"],
        "app_name": cap["appName"],
        "version_name": pkg["version"],
        "version_code": major * 10000 + minor * 100 + patch,
        "min_sdk": _grab(gradle, r"minSdkVersion\s*=\s*(\d+)", "minSdkVersion"),
        "compile_sdk": _grab(gradle, r"compileSdkVersion\s*=\s*(\d+)", "compileSdkVersion"),
        "target_sdk": _grab(gradle, r"targetSdkVersion\s*=\s*(\d+)", "targetSdkVersion"),
        "perm_declared": [p for p in declared if p not in removed],
        "perm_removed": removed,
        "channel_id": _grab(notify, r'CHANNEL_ID = "([^"]+)"', "CHANNEL_ID"),
        "channel_importance": _grab(channel_args, r"importance:\s*(\d+)", "채널 importance"),
        "channel_vibration": _grab(channel_args, r"vibration:\s*(\w+)", "채널 vibration"),
        "channel_sound": "지정 안 함" if not re.search(r"\bsound\s*:", channel_args) else "지정",
        "id_base": int(_grab(notify, r"ID_BASE = (\d+)", "ID_BASE")),
        # ⚠ 가 없으면 SEEN_WINDOW_DAYS(30)를 먼저 문다 — 2026-08-31에 실제로 물었다.
        #   조용히 틀린 값이 문서에 박히는 것이 이 블록이 막으려던 바로 그 일이다.
        "window_days": int(_grab(select, r"\bWINDOW_DAYS = (\d+)", "WINDOW_DAYS")),
        "notify_default_on": _grab(notify, r"DEFAULT_ON = (\w+)", "DEFAULT_ON"),
        "notify_default_time": _grab(notify, r'DEFAULT_TIME = "([^"]+)"', "DEFAULT_TIME"),
        "operator": _grab(about, r'OPERATOR = "([^"]*)"', "OPERATOR"),
        "contact": _grab(about, r'CONTACT = "([^"]*)"', "CONTACT"),
    }


def render_app(m: dict[str, Any]) -> str:
    """HANDOFF에 넣을 앱 블록. 서식의 정의는 여기 한 곳뿐이다."""
    last = m["id_base"] + m["window_days"] - 1
    short = [p.rsplit(".", 1)[-1] for p in m["perm_declared"]]
    gone = [p.rsplit(".", 1)[-1] for p in m["perm_removed"]]
    lines = [
        BEGIN_FMT.format("앱"),
        NOTE,
        "```",
        f"앱 아이디    {m['app_id']}",
        f"표시 이름    {m['app_name']}",
        f"버전        {m['version_name']}  (versionCode {m['version_code']})",
        f"SDK        min {m['min_sdk']} · compile {m['compile_sdk']} · target {m['target_sdk']}",
        f"권한 선언    {' · '.join(short)}",
        f"권한 제거    {' · '.join(gone)}   (tools:node=remove)",
        "           ⛔ **이 줄은 우리가 선언한 것만이다.**",
        "             SDK·플러그인이 병합하는 권한은 여기 보이지 않는다 —",
        "             전부로 읽지 말 것. 실제 목록은 APK로 확인한다(2.92·2.98)",
        f"알림 채널    id {m['channel_id']} · importance {m['channel_importance']}"
        f" · vibration {m['channel_vibration']} · sound {m['channel_sound']}",
        "           ⛔ 채널은 한 번 만들어지면 코드로 못 바꾼다(2.94)",
        f"알림 예약    id {m['id_base']}~{last} ({m['window_days']}일 창)"
        f" · 기본 시각 {m['notify_default_time']} · 기본값 켜짐 {m['notify_default_on']}",
        f"운영자       {m['operator']}",
        f"문의처       {m['contact']}",
        "```",
        END,
    ]
    return "\n".join(lines)


# 표지는 **줄 전체**일 때만 인정한다.
#   2026-08-24: 2.43절 본문이 표지 문자열을 인용했더니 파서가 그것을 구간 시작으로
#   잡아 문서 90줄을 통째로 삼켰다. 문서가 자기 표지를 설명하는 것은 정상이므로
#   파서 쪽을 조인다. 회귀는 --check가 잡는다 — HANDOFF 2.43절이 지금도 표지를
#   본문에서 인용하고 있어서, 이 정규식이 느슨해지면 --check가 바로 깨진다.
_END_LINE = re.compile(rf"^{re.escape(END)}$", re.MULTILINE)


def _begin_line(name: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(BEGIN_FMT.format(name))}$", re.MULTILINE)


def _regions(text: str, name: str) -> list[tuple[int, int]]:
    """이름이 같은 표시 구간을 전부 찾는다. 여러 곳에 같은 블록을 둘 수 있다."""
    begin_line = _begin_line(name)
    spans, at = [], 0
    while True:
        begin = begin_line.search(text, at)
        if not begin:
            return spans
        end = _END_LINE.search(text, begin.end())
        if not end:
            raise ValueError(f"{BEGIN_FMT.format(name)} 뒤에 {END} 줄이 없다")
        spans.append((begin.start(), end.end()))
        at = end.end()


def _apply(text: str, name: str, block: str) -> str:
    for start, stop in reversed(_regions(text, name)):
        text = text[:start] + block + text[stop:]
    return text


# 블록 목록. 새 블록을 만들려면 여기 한 줄을 더한다 — main()은 안 고친다.
BLOCKS: tuple[tuple[str, Any], ...] = (
    ("규모", lambda: render(measure())),
    ("앱", lambda: render_app(measure_app())),
)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="HANDOFF 실측 블록 생성")
    parser.add_argument("--write", action="store_true", help="HANDOFF.md를 갱신한다")
    parser.add_argument("--check", action="store_true", help="다르면 종료 코드 1")
    args = parser.parse_args(argv)

    rendered = [(name, build()) for name, build in BLOCKS]
    if not (args.write or args.check):
        print("\n\n".join(block for _, block in rendered))
        return EXIT_OK

    text = HANDOFF.read_text(encoding="utf-8")

    # ⛔ 표지가 없는 블록은 **실패다.** 조용히 건너뛰면 게이트가 아니라 장식이 된다.
    missing = [name for name, _ in rendered if not _regions(text, name)]
    if missing:
        for name in missing:
            print(
                f"{HANDOFF.name}에 {BEGIN_FMT.format(name)} 구간이 없다",
                file=sys.stderr,
            )
        return EXIT_FAIL

    updated, counts = text, {}
    for name, block in rendered:
        counts[name] = len(_regions(updated, name))
        updated = _apply(updated, name, block)

    tally = " · ".join(f"{name} {n}개" for name, n in counts.items())
    if args.write:
        if updated == text:
            print(f"{HANDOFF.name} 변경 없음 — 이미 실측과 같다 (구간 {tally})")
        else:
            HANDOFF.write_text(updated, encoding="utf-8")
            print(f"{HANDOFF.name} 갱신 — 구간 {tally}")
        return EXIT_OK

    if updated != text:
        # 어느 블록이 어긋났는지 짚어 준다 — 문서가 길어서 눈으로 못 찾는다.
        stale = [
            name
            for name, block in rendered
            if _apply(text, name, block) != text
        ]
        print(f"문서와 실측이 다르다 — 어긋난 블록: {' · '.join(stale)}", file=sys.stderr)
        print("  python scripts/stats.py --write  로 맞춘다.", file=sys.stderr)
        print("\n[실측]")
        for name, block in rendered:
            if name in stale:
                print(block)
        return EXIT_FAIL

    print(f"실측과 일치 — 구간 {tally}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
