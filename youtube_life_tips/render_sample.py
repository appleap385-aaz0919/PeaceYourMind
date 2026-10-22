"""Render a local, original-motion-graphics life-tip Short for review."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work" / "sample"
VENDOR = ROOT / "work" / "vendor"
WIDTH, HEIGHT, FPS = 720, 1280, 15
VOICE = "ko-KR-InJoonNeural"
SOURCES = [
    "https://www.samsung.com/us/support/answer/ANS10004814/",
    "https://producthelp.whirlpool.com/Cooking/Microwaves/Countertop_Microwave/Cleaning/Interior/Cleaning_the_Interior_or_Cavity_-_Countertop_Microwave",
]
PHRASES = [
    ("전자레인지 얼룩, 매번 힘줘서 닦으셨죠? 오늘은 이 방법 써보세요!", "얼룩, 힘줘서 닦지 마세요"),
    ("전자레인지용 그릇에 물 두 컵과 레몬즙 조금을 담아주세요.", "물 두 컵과 레몬즙 조금"),
    ("강으로 5분 또는 물이 끓을 때까지 돌리고, 1분에서 2분 그대로 둬요.", "강으로 5분 · 1~2분 기다리기"),
    ("수증기로 얼룩이 불면, 뜨거운 그릇을 조심히 꺼내고 행주로 쓱 닦아주세요.", "뜨거운 그릇은 조심히 꺼내기"),
    ("아직 남은 얼룩은 한 번 더! 사용 중인 제품 설명서도 확인하세요.", "남은 얼룩은 한 번 더 반복"),
]


def run(args: list[str], *, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(args, input=input_data, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout


def duration(path: Path) -> float:
    value = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(value.decode().strip())


async def synthesize(audio_paths: list[Path]) -> None:
    sys.path.insert(0, str(VENDOR))
    import edge_tts

    for index, (text, _) in enumerate(PHRASES):
        await edge_tts.Communicate(
            text,
            VOICE,
            rate="+8%",
            pitch="+1Hz",
        ).save(str(audio_paths[index]))


def fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    regular = Path("C:/Windows/Fonts/malgun.ttf")
    bold = Path("C:/Windows/Fonts/malgunbd.ttf")
    return (
        ImageFont.truetype(str(bold), 46),
        ImageFont.truetype(str(bold), 34),
        ImageFont.truetype(str(regular), 24),
    )


def load_scenes() -> list[Image.Image]:
    storyboard = Image.open(WORK / "storyboard.png").convert("RGB")
    width, height = storyboard.size
    cells = [
        (0, 0, width // 2 - 5, height // 2 - 6),
        (width // 2 + 5, 0, width, height // 2 - 6),
        (0, height // 2 + 6, width // 2 - 5, height),
        (width // 2 + 5, height // 2 + 6, width, height),
    ]
    return [storyboard.crop(box) for box in cells]


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int] | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_scene(index: int, photos: list[Image.Image], title_font: ImageFont.FreeTypeFont, caption_font: ImageFont.FreeTypeFont, small_font: ImageFont.FreeTypeFont) -> Image.Image:
    photo_index = [0, 0, 1, 2, 3][index]
    source = photos[photo_index]
    image = ImageOps.fit(source, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")

    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(0, 380, 2):
        alpha = int(190 * (1 - y / 440))
        sd.line((0, y, WIDTH, y), fill=(9, 17, 27, max(alpha, 0)), width=2)
    for y in range(850, HEIGHT, 2):
        alpha = int(185 * min(1, (y - 850) / 190))
        sd.line((0, y, WIDTH, y), fill=(9, 17, 27, alpha), width=2)
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)

    rounded(draw, (38, 44, 278, 92), 24, (18, 29, 43, 205))
    draw.text((58, 54), "생활꿀팁  ·  01", font=small_font, fill="#ffffff")
    draw.text((40, 130), "전자레인지 얼룩,", font=title_font, fill="#ffffff", stroke_width=2, stroke_fill="#111922")
    draw.text((40, 190), "힘줘서 닦지 마세요", font=title_font, fill="#ffe36a", stroke_width=2, stroke_fill="#111922")

    rounded(draw, (36, 928, 684, 1100), 28, (9, 17, 27, 205), outline=(255, 255, 255, 65), width=2)
    words = PHRASES[index][1].split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=caption_font)[2] > 580 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    y = 968 if len(lines) == 1 else 946
    for line in lines[:2]:
        draw.text((66, y), line, font=caption_font, fill="#ffffff", stroke_width=1, stroke_fill="#111922")
        y += 54
    draw.text((42, 1155), "필요할 때 다시 보도록 저장해두세요", font=small_font, fill="#ffffff")
    return image.convert("RGB")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    audio_paths = [WORK / f"voice_{i+1}.mp3" for i in range(len(PHRASES))]
    asyncio.run(synthesize(audio_paths))

    phrase_durations = [duration(path) for path in audio_paths]
    gap = 0.16
    starts: list[float] = []
    cursor = 0.0
    for length in phrase_durations:
        starts.append(cursor)
        cursor += length + gap
    total = cursor - gap
    voice = WORK / "narration.mp3"
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for path in audio_paths:
        args.extend(["-i", str(path)])
    filters = []
    labels = []
    for i in range(len(audio_paths)):
        filters.append(f"[{i}:a]apad=pad_dur={gap}[a{i}]")
        labels.append(f"[a{i}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    args.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "3", str(voice)])
    run(args)

    title_font, caption_font, small_font = fonts()
    photos = load_scenes()
    video = WORK / "life_tip_sample.mp4"
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
            "-i", str(voice), "-t", f"{total:.3f}", "-shortest",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(video),
        ],
        stdin=subprocess.PIPE,
    )
    assert ffmpeg.stdin is not None
    frame_count = math.ceil(total * FPS)
    for frame in range(frame_count):
        t = frame / FPS
        scene = max(i for i, start in enumerate(starts) if start <= t)
        image = draw_scene(scene, photos, title_font, caption_font, small_font)
        transition = t - starts[scene]
        if scene > 0 and transition < 0.32:
            previous = draw_scene(scene - 1, photos, title_font, caption_font, small_font)
            image = Image.blend(previous, image, transition / 0.32)
        ffmpeg.stdin.write(image.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise RuntimeError("ffmpeg could not encode the sample video")

    metadata = {
        "title": "전자레인지 얼룩, 힘줘서 닦지 마세요 #생활꿀팁 #Shorts",
        "description": "전자레인지에 눌어붙은 얼룩은 물을 데워 생긴 수증기로 불린 뒤 닦을 수 있습니다. 뜨거운 그릇은 조심해서 꺼내고, 사용 중인 제품 설명서를 확인하세요.\n\n참고 자료:\n" + "\n".join(SOURCES),
        "script": [text for text, _ in PHRASES],
        "voice_preview": {"provider": "Microsoft Edge Neural TTS", "voice": VOICE, "production_voice": "Microsoft Edge Neural TTS"},
        "visuals": "AI-generated original still images with stable framing and short cross-fades",
        "voice_segments_seconds": [round(value, 2) for value in phrase_durations],
        "duration_seconds": round(duration(video), 2),
        "sources": SOURCES,
    }
    (WORK / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
