#!/usr/bin/env python3
"""Render a reviewed verse manifest as a Korean-narrated vertical draft Short."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1080, 1920, 30
DURATION = 7
VOICE_NAME = os.environ.get("PYM_TTS_VOICE", "ko-KR-Neural2-C")
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


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                 x: int, y: int, max_width: int, fill: tuple[int, int, int],
                 line_gap: int = 24) -> None:
    for line in wrap(text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((x, y), line, font=font)[3] - y + line_gap


def fit_font(text: str, font_file: Path, start_size: int, min_size: int,
             max_width: int, max_height: int, line_gap: int) -> ImageFont.FreeTypeFont:
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_file), size)
        lines = wrap(text, font, max_width)
        line_height = max(ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line, font=font)[3]
                          for line in lines)
        if len(lines) * line_height + max(0, len(lines) - 1) * line_gap <= max_height:
            return font
    return ImageFont.truetype(str(font_file), min_size)


def app_scenes(manifest: dict, work: Path) -> tuple[list[Path], list[Path]]:
    """Create an app walkthrough from the actual Play Store screen captures."""
    assets = Path(__file__).resolve().parents[2] / "app" / "store" / "screenshots"
    input_screen, result_screen, reading_screen, videos_screen = (
        assets / "phone_1_input.png", assets / "phone_2_result.png",
        assets / "phone_4_chapter.png", assets / "phone_3_videos.png",
    )
    for path in (input_screen, result_screen, reading_screen, videos_screen):
        if not path.is_file():
            raise FileNotFoundError(f"Required app screenshot is missing: {path}")

    korean_font = font_path()
    title_font = ImageFont.truetype(str(korean_font), 40)
    verse_text = manifest["text"].strip()
    ref_font = ImageFont.truetype(str(korean_font), 34)
    muted, paper, gold, dark = (143, 165, 159), (235, 239, 235), (224, 196, 155), (16, 26, 31)
    pages: list[Path] = []

    input_font = ImageFont.truetype(str(korean_font), 48)
    emotion = "\uB9C8\uC74C\uC774 \uC790\uAFB8 \uC870\uAE09\uD574\uC838\uC694"
    for index, count in enumerate((0, 3, 8, len(emotion))):
        image = Image.open(input_screen).convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((45, 815, 1035, 945), fill=image.getpixel((10, 900)))
        typed = emotion[:count]
        draw.text((60, 845), typed, font=input_font, fill=(235, 239, 235))
        if index == 3:
            cursor_x = 60 + int(input_font.getlength(typed)) + 4
            draw.line((cursor_x, 850, cursor_x, 910), fill=(127, 179, 163), width=3)
            draw.ellipse((490, 1050, 590, 1150), outline=(127, 179, 163, 235), width=9)
            draw.ellipse((522, 1082, 558, 1118), fill=(127, 179, 163, 90))
        path = work / f"app-input-{index + 1}.png"
        image.save(path, optimize=True)
        pages.append(path)

    image = Image.open(result_screen).convert("RGB")
    draw = ImageDraw.Draw(image)
    result_top = image.getpixel((10, 300))
    result_lower = image.getpixel((10, 850))
    verse_font = fit_font(verse_text, korean_font, 61, 40, 940, 340, 22)
    draw.rectangle((35, 205, 1045, 610), fill=result_top)
    draw.rectangle((35, 620, 1045, 1040), fill=result_lower)
    draw_wrapped(draw, verse_text, verse_font, 60, 235, 940, paper, 22)
    draw.text((60, 635), manifest["reference"], font=ref_font, fill=gold)
    draw_wrapped(draw, "\uC624\uB298\uC758 \uB9C8\uC74C\uC5D0 \uBA38\uBB34\uB294 \uD55C \uAD6C\uC808", ref_font, 60, 825, 900, muted, 14)
    path = work / "app-verse.png"
    image.save(path, optimize=True)
    pages.append(path)

    image = Image.open(reading_screen).convert("RGB")
    draw = ImageDraw.Draw(image)
    reader_top = image.getpixel((10, 180))
    reader_body = image.getpixel((10, 900))
    verse_font = fit_font(verse_text, korean_font, 61, 40, 940, 455, 30)
    draw.rectangle((35, 35, 1045, 415), fill=reader_top)
    draw.rectangle((35, 605, 1045, 1815), fill=reader_body)
    draw.text((60, 135), "\uB9D0\uC500\uC744 \uCC9C\uCC9C\uD788 \uC774\uC5B4 \uC77D\uC5B4\uBCF4\uC138\uC694.", font=title_font, fill=muted)
    match = re.search(r"(.+?)\s+(\d+):(\d+)", manifest["reference"])
    chapter_label = f"{match.group(1)} {match.group(2)}\uC7A5 \u00B7 {match.group(3)}\uC808" if match else manifest["reference"]
    draw.text((60, 635), chapter_label, font=ref_font, fill=gold)
    draw_wrapped(draw, verse_text, verse_font, 60, 770, 940, paper, 30)
    draw.text((60, 1575), "\uC624\uB298\uC758 \uAD6C\uC808\uC744 \uB2E4 \uC77D\uC5C8\uC5B4\uC694", font=ref_font, fill=muted)
    path = work / "app-reading.png"
    image.save(path, optimize=True)
    pages.append(path)

    image = Image.open(videos_screen).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((130, 455, 260, 585), outline=(224, 196, 155, 240), width=10)
    draw.ellipse((174, 499, 216, 541), fill=(224, 196, 155, 95))
    path = work / "app-videos.png"
    image.save(path, optimize=True)
    pages.append(path)

    player_pages: list[Path] = []
    for index, progress in enumerate((0.08, 0.25, 0.43)):
        image = Image.new("RGB", (WIDTH, HEIGHT), (11, 18, 22))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((52, 180, 1028, 1740), radius=48, fill=(20, 30, 35), outline=(58, 76, 79), width=3)
        thumb = Image.open(videos_screen).convert("RGB").crop((60, 440, 336, 600)).resize((876, 506))
        image.paste(thumb, (102, 230))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((102, 230, 978, 736), radius=22, outline=(88, 107, 108), width=2)
        draw.ellipse((478, 426, 602, 550), fill=(210, 0, 0))
        draw.rounded_rectangle((520, 460, 538, 516), radius=4, fill=(255, 255, 255))
        draw.rounded_rectangle((547, 460, 565, 516), radius=4, fill=(255, 255, 255))
        draw.text((102, 805), "YouTube", font=title_font, fill=paper)
        draw.text((102, 885), "[1\uC2DC\uAC04] \uB0B4 \uC190\uC744 \uC8FC\uAED8 \uB192\uC774 \uB4ED\uB2C8\uB2E4", font=ref_font, fill=paper)
        draw.text((102, 945), "CCM \uD53C\uC544\uB178 \uCC2C\uC591 \uBB35\uC0C1 \uC5F0\uC8FC", font=ref_font, fill=muted)
        draw.rounded_rectangle((102, 1030, 978, 1042), radius=6, fill=(68, 78, 82))
        draw.rounded_rectangle((102, 1030, 102 + int(876 * progress), 1042), radius=6, fill=(255, 0, 0))
        draw.text((102, 1070), "Peace in Mind \uC571\uC758 \uCD94\uCC9C \uCC2C\uC591", font=ref_font, fill=muted)
        path = work / f"youtube-player-{index + 1}.png"
        image.save(path, optimize=True)
        player_pages.append(path)
    return pages, player_pages


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
            pitch=-3.0,
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


def render_mp4(images: list[Path], output: Path, audio: Path, durations: list[float],
               ffmpeg: str, narration_after_scenes: int = 1) -> None:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for image, duration in zip(images, durations):
        command += ["-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", str(image)]
    audio_index = len(images)
    command += ["-i", str(audio)]
    filters = [f"[{i}:v]fps={FPS},setsar=1[v{i}]" for i in range(len(images))]
    joins = "".join(f"[v{i}]" for i in range(len(images)))
    total = sum(durations)
    filters.append(f"{joins}concat=n={len(images)}:v=1:a=0[vout]")
    delay = round(sum(durations[:narration_after_scenes]) * 1000)
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
                        help="Google Cloud TTS voice name (default: ko-KR-Neural2-C, low male voice)")
    parser.add_argument("--output", type=Path, help="Output MP4 path")
    args = parser.parse_args()

    with args.manifest.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    for field in ("date_kst", "verse_id", "reference", "text", "translation"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"Manifest requires a non-empty '{field}'")
    work = Path(__file__).resolve().parents[1] / "work" / manifest["date_kst"]
    work.mkdir(parents=True, exist_ok=True)
    audio = work / "verse-reading.mp3"
    synthesize_verse(manifest, audio, args.voice)
    speaking_time = media_duration(audio, args.ffprobe)
    input_pages, player_pages = app_scenes(manifest, work)
    image_paths = [*input_pages[:4], input_pages[4], work / "app-reading.png",
                   input_pages[6], *player_pages]
    # Keep the continuation-reading tab visible throughout narration, then switch to praise.
    durations = [0.45, 0.45, 0.45, 0.45, 1.6,
                 max(DURATION, math.ceil(speaking_time + 1)), 3, 2, 2, 2]
    if sum(durations) > 60:
        raise ValueError(f"Narration is too long for a Short: estimated {sum(durations)} seconds")

    output = args.output or work / "short-draft.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    render_mp4(image_paths, output, audio, durations, args.ffmpeg, narration_after_scenes=5)
    print(f"Rendered app walkthrough with {args.voice} ({sum(durations)} seconds): {output}")
    print("Review the verse, low male narration, and YouTube handoff before publishing.")


if __name__ == "__main__":
    main()
