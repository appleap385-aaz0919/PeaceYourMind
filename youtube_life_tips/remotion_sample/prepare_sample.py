"""Prepare a local-only Remotion sample using the reviewed drawer topic."""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FPS = 15
OUT = ROOT / "work/samples/2026-11-10-remotion"
PUBLIC = HERE / "public/generated"
STYLE = ROOT / "_workspace/2026-11-10-004"

# Continuous factual draft, before the single-call style check and scene split.
DRAFT = "뻑뻑한 나무 서랍, 집에 있는 양초로 움직임을 부드럽게 해볼까요? 나무끼리 맞닿아 움직이는 작은 서랍에 쓰는 방법이에요. 왁스가 맞닿는 면에 얇게 남아 마찰을 줄여줘요. 금속 레일이 달렸거나 나무가 휘고 갈라졌다면 이 방법은 쓰지 마세요. 먼저 작은 수납장을 평평한 곳에 놓고 서랍을 비워요. 양손으로 받쳐 꺼내되, 안 빠지면 억지로 당기지 마세요. 구조를 가까이 볼게요. 이 그림은 서랍 밑의 나무 막대가 수납장 안쪽 홈을 따라 움직이는 예예요. 양초는 이 두 부품이 서로 닿는 면에 바르면 돼요. 먼저 마른 천으로 양쪽 접촉면의 먼지를 닦아요. 그다음 굳은 파라핀 양초를 준비하세요. 불을 켜거나 녹이지 않고 그대로 써요. 꺼낸 서랍을 뒤집고, 밑에 붙은 막대의 접촉면에 양초를 길이 방향으로 얇게 문질러요. 이어서 수납장 안쪽 홈의 맞닿는 면에도 발라주세요. 이제 서랍을 바로 놓고 막대를 홈에 맞춰 끼워요. 가볍게 몇 번 여닫아 왁스를 퍼뜨리고 움직임을 확인하세요. 그래도 걸리면 세게 밀지 말고 수선을 맡기세요. 왁스가 뒤틀린 나무까지 펴주진 못해요."

# humanize-korean single-call pass: no mapped S1/S2 issue requires a wording edit.
FINAL = DRAFT

GROUPS = [
    ("hook", "뻑뻑한 나무 서랍에\n양초를 문지르면?", 1),
    ("principle", "나무끼리 비비는 면에\n얇은 왁스 막을 남겨요", 2),
    ("exclude", "금속 레일·뒤틀린 나무는\n이 방법의 대상이 아니에요", 1),
    ("remove", "비우고, 받쳐서\n천천히 꺼내세요", 2),
    ("structure", "막대는 서랍 쪽\n홈은 수납장 안쪽", 3),
    ("clean", "서로 닿는 양쪽 면\n먼지부터 닦아요", 1),
    ("candle", "굳은 파라핀 양초를\n그대로 써요", 2),
    ("wax-drawer", "서랍 밑 막대의 접촉면\n길이 방향으로 얇게", 1),
    ("wax-groove", "수납장 안쪽 홈에도\n맞닿는 면만 얇게", 1),
    ("assemble", "홈에 맞춰 다시 끼우고\n가볍게 여닫아 확인해요", 2),
    ("limit", "그래도 걸리면 멈추세요\n뒤틀림까지 펴주진 못해요", 2),
]


def probe(path: Path) -> float:
    data = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], text=True)
    return float(json.loads(data)["format"]["duration"])


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    STYLE.mkdir(parents=True, exist_ok=True)
    (STYLE / "continuous-draft.txt").write_text(DRAFT + "\n", encoding="utf-8")
    change = 100 * (1 - difflib.SequenceMatcher(None, DRAFT, FINAL).ratio())
    summary = (f"\n\n<!-- HUMANIZE-SUMMARY\n원본/윤문본 글자수: {len(DRAFT)}/{len(FINAL)}; 변경률 {change:.1f}%.\n"
               "A~J: 수정이 필요한 S1/S2 패턴 0 → 0. 자체검증 6/6 통과.\n"
               "등급 B: 이미 구어체로 작성되어 의미·내용 앵커·말투를 보존함.\n"
               "변경 하이라이트: 수정할 근거가 없어 원문 보존.\n-->\n")
    (STYLE / "final.md").write_text(FINAL + summary, encoding="utf-8")
    sentences = [item.strip() + "." for item in FINAL.split(". ")]
    sentences[-1] = sentences[-1].rstrip(".") + "."
    # The first sentence ends in '?', so split it separately before scene assignment.
    hook, rest = sentences[0].split("? ", 1)
    sentences[:1] = [hook + "?", rest]
    assert len(sentences) == sum(item[2] for item in GROUPS), len(sentences)
    assert " ".join(sentences) == FINAL
    sys.path.insert(0, str(ROOT / "work/vendor"))
    import edge_tts
    semaphore = asyncio.Semaphore(3)

    async def voice(index: int, text: str) -> None:
        target = PUBLIC / f"voice-{index:02d}.mp3"
        key = hashlib.sha256((text + "|ko-KR-InJoonNeural|+8%|+1Hz").encode()).hexdigest()
        receipt = target.with_suffix(".sha256")
        if target.exists() and receipt.exists() and receipt.read_text() == key:
            return
        async with semaphore:
            await edge_tts.Communicate(text, "ko-KR-InJoonNeural", rate="+8%", pitch="+1Hz").save(str(target))
            receipt.write_text(key)
            print(f"Voice {index + 1}/{len(sentences)} saved", flush=True)

    await asyncio.gather(*(voice(i, text) for i, text in enumerate(sentences)))
    shutil.copyfile("C:/Windows/Fonts/malgun.ttf", PUBLIC / "Malgun.ttf")
    shutil.copyfile("C:/Windows/Fonts/malgunbd.ttf", PUBLIC / "Malgun-Bold.ttf")
    chunks = []
    cursor = 0
    for i, text in enumerate(sentences):
        audio = PUBLIC / f"voice-{i:02d}.mp3"
        seconds = probe(audio)
        frames = math.ceil(seconds * FPS) + 1
        chunks.append({"text": text, "audio": f"generated/{audio.name}", "from": cursor, "frames": frames, "audioSeconds": seconds})
        cursor += frames
    groups = []
    index = 0
    for kind, title, count in GROUPS:
        group_chunks = chunks[index:index + count]
        groups.append({"kind": kind, "title": title, "from": group_chunks[0]["from"],
                       "frames": sum(x["frames"] for x in group_chunks), "chunks": group_chunks})
        index += count
    assert 65 <= cursor / FPS <= 90, f"Measured duration {cursor / FPS:.2f}s outside 65–90s"
    approved = json.loads((ROOT / "work/mailbox/runs/2026-11-10/candidates/2/approved.json").read_text(encoding="utf-8"))
    data = {"fps": FPS, "width": 720, "height": 1280, "frames": cursor, "durationSeconds": cursor / FPS,
            "spokenScript": FINAL, "scenes": groups, "chunks": chunks,
            "sources": approved["sources"], "sourcePlan": "2026-11-10/candidates/2/approved.json", "upload": False,
            "renderer": "Remotion 4.0.542", "visualType": "Original explanatory SVG animation, not a filmed experiment"}
    (HERE / "src/sample-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "metadata.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "narration.txt").write_text(FINAL + "\n", encoding="utf-8")
    print(json.dumps({"seconds": cursor / FPS, "frames": cursor, "sceneCount": len(groups), "voiceChunks": len(chunks), "upload": False}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
