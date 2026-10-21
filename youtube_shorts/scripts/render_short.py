#!/usr/bin/env python3
"""Render a reviewed verse manifest as a Korean-narrated vertical draft Short."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1080, 1920, 30
DURATION = 7
VOICE_NAME = os.environ.get("PYM_TTS_VOICE", "ko-KR-Neural2-A")
INK = (14, 25, 32)
PAPER = (245, 241, 231)
ACCENTS = ((186, 207, 196), (205, 183, 145), (166, 194, 211), (210, 170, 163))


def font_path() -> Path:
    choices = [
        os.environ.get("PYM_KOREAN_FONT"),
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunsl.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for choice in choices:
        if choice and Path(choice).is_file():
            return Path(choice)
    raise FileNotFoundError("Korean font not found; set PYM_KOREAN_FONT to a Korean font file")


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        line = ""
        for char in paragraph:
            candidate = line + char
            if line and font.getlength(candidate) > max_width:
                lines.append(line)
                line = char
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def multiline_center(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                     center_y: int, max_width: int, fill: tuple[int, int, int],
                     spacing: int = 30) -> None:
    lines = wrap(text, font, max_width)
    heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    total_height = sum(heights) + spacing * max(0, len(lines) - 1)
    y = center_y - total_height // 2
    for line, height in zip(lines, heights):
        draw.text((WIDTH // 2, y), line, font=font, fill=fill, anchor="mt")
        y += height + spacing


def card(title: str, body: str, footer: str, accent: tuple[int, int, int],
         output: Path, body_size: int = 68) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    draw.ellipse((650, -410, 1370, 310), fill=tuple(int(c * 0.46) for c in accent))
    draw.ellipse((-490, 1410, 330, 2230), fill=tuple(int(c * 0.27) for c in accent))
    draw.rounded_rectangle((80, 135, WIDTH - 80, HEIGHT - 135), radius=48,
                           outline=(55, 70, 76), width=2)

    korean_font = font_path()
    small = ImageFont.truetype(str(korean_font), 38)
    heading = ImageFont.truetype(str(korean_font), 55)
    main = ImageFont.truetype(str(korean_font), body_size)
    foot = ImageFont.truetype(str(korean_font), 34)
    draw.text((WIDTH // 2, 250), title, font=heading, fill=accent, anchor="mm")
    multiline_center(draw, body, main, 920, WIDTH - 190, PAPER, spacing=38)
    draw.rounded_rectangle((WIDTH // 2 - 44, 1490, WIDTH // 2 + 44, 1497),
                           radius=4, fill=accent)
    draw.text((WIDTH // 2, 1590), footer, font=small, fill=(192, 202, 201), anchor="mm")
    draw.text((WIDTH // 2, 1710), "Peace in Mind", font=foot, fill=(142, 161, 164), anchor="mm")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def synthesize_verse(manifest: dict, output: Path, voice_name: str) -> None:
    try:
        from google.cloud import texttospeech
    except ImportError as error:
        raise RuntimeError(
            "Install youtube_shorts/requirements.txt to use Google Cloud Text-to-Speech"
        ) from error

    client = texttospeech.TextToSpeechClient()
    # Only formatting line breaks are joined. The KRV verse's words are preserved.
    text = " ".join(manifest["text"].splitlines()).strip()
    reading = f"{manifest['reference']}. {text}"
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=reading),
        voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name=voice_name),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.88,
            pitch=-1.0,
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.audio_content)


def media_duration(path: Path, ffprobe: str) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def render_mp4(images: list[Path], output: Path, audio: Path, durations: list[int],
               ffmpeg: str) -> None:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for image, duration in zip(images, durations):
        command += ["-loop", "1", "-framerate", "1", "-t", str(duration), "-i", str(image)]
    audio_index = len(images)
    command += ["-i", str(audio)]
    filters = [f"[{i}:v]fps={FPS},setsar=1[v{i}]" for i in range(len(images))]
    joins = "".join(f"[v{i}]" for i in range(len(images)))
    total = sum(durations)
    filters.append(f"{joins}concat=n={len(images)}:v=1:a=0[vout]")
    delay = durations[0] * 1000
    filters.append(
        f"[{audio_index}:a]adelay={delay}|{delay},apad,atrim=duration={total},asetpts=N/SR/TB[aout]"
    )
    command += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-t", str(total), "-movflags", "+faststart",
                "-r", str(FPS), str(output)]
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Daily manifest generated by choose_verse.py")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--voice", default=VOICE_NAME,
                        help="Google Cloud TTS voice name (default: ko-KR-Neural2-A)")
    parser.add_argument("--output", type=Path, help="Output MP4 path")
    args = parser.parse_args()

    with args.manifest.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    for field in ("date_kst", "verse_id", "reference", "text", "translation"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"Manifest requires a non-empty '{field}'")
    work = Path(__file__).resolve().parents[1] / "work" / manifest["date_kst"]
    accent = ACCENTS[sum(manifest["verse_id"].encode("utf-8")) % len(ACCENTS)]
    image_paths = [work / f"card-{i + 1}.png" for i in range(4)]
    audio = work / "verse-reading.mp3"
    synthesize_verse(manifest, audio, args.voice)
    speaking_time = media_duration(audio, args.ffprobe)
    durations = [4, max(DURATION, math.ceil(speaking_time + 2)), 7, 7]
    if sum(durations) > 60:
        raise ValueError(f"Narration is too long for a Short: estimated {sum(durations)} seconds")

    card("오늘의 말씀", manifest["reference"], manifest["date_kst"], accent, image_paths[0])
    card(manifest["reference"], manifest["text"], manifest["translation"], accent,
         image_paths[1], body_size=59)
    card("이어서 읽어보세요", "이 구절이 담긴 성경 장 전체를 문맥에 따라 읽을 수 있어요.",
         "Peace in Mind · 이어 읽기", accent, image_paths[2], body_size=62)
    card("마음에 맞는 영상도 있어요", "말씀과 찬양 영상을 감정에 맞춰 살펴보세요.",
         manifest["profile_cta"], accent, image_paths[3], body_size=60)

    output = args.output or work / "short-draft.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    render_mp4(image_paths, output, audio, durations, args.ffmpeg)
    print(f"Rendered Korean-voice draft ({sum(durations)} seconds): {output}")
    print("This renderer does not upload or publish. Review the verse, Korean narration, and video first.")


if __name__ == "__main__":
    main()
