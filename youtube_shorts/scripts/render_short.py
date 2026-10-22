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
VOICE_NAME = os.environ.get("PYM_TTS_VOICE", "ko-KR-Neural2-C")


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
    for index, count in enumerate((0, 2, 4, 6, 8, 10, len(emotion))):
        image = Image.open(input_screen).convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((45, 815, 1035, 945), fill=image.getpixel((10, 900)))
        typed = emotion[:count]
        draw.text((60, 845), typed, font=input_font, fill=(235, 239, 235))
        if index == 6:
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
    select_reading_tab(image, reading_screen)
    path = work / "app-verse.png"
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


def select_reading_tab(result: Image.Image, reader_screen: Path) -> None:
    """Keep the result page intact while borrowing its real selected-tab state."""
    tabs = Image.open(reader_screen).convert("RGB").crop((0, 480, WIDTH, 570))
    target_y = 1136

    # Remove the old praise underline while preserving the result screenshot's background.
    for y in range(1217, 1224):
        for x in range(500, 636):
            result.putpixel((x, y), result.getpixel((x, 1210)))

    # Copy only visible tab pixels; the result page and video recommendations stay intact.
    for y in range(tabs.height):
        for x in range(WIDTH):
            pixel = tabs.getpixel((x, y))
            if max(pixel) > 44:
                result.putpixel((x, target_y + y), pixel)


def synthesize_text(text: str, output: Path, voice_name: str, speaking_rate: float = 0.9) -> None:
    try:
        from google.cloud import texttospeech
    except ImportError as error:
        raise RuntimeError(
            "Install youtube_shorts/requirements.txt to use Google Cloud Text-to-Speech"
        ) from error

    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=" ".join(text.splitlines()).strip()),
        voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name=voice_name),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
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


def render_mp4(images: list[Path], durations: list[float], audio_clips: list[tuple[Path, float]],
               output: Path, ffmpeg: str, transition: float = 0.16) -> None:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for image, duration in zip(images, durations):
        command += ["-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", str(image)]
    audio_base = len(images)
    for audio, _ in audio_clips:
        command += ["-i", str(audio)]
    filters = [f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS,setsar=1[v{i}]"
               for i in range(len(images))]
    current = "v0"
    for index in range(1, len(images)):
        offset = sum(durations[:index]) - transition * index
        output_label = f"xf{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=fade:duration={transition}:offset={offset:.3f}[{output_label}]"
        )
        current = output_label
    total = sum(durations) - transition * (len(images) - 1)
    filters.append(f"[{current}]format=yuv420p[vout]")
    audio_labels = []
    for index, (_, offset) in enumerate(audio_clips):
        delay = round(offset * 1000)
        label = f"a{index}"
        filters.append(f"[{audio_base + index}:a]adelay={delay}|{delay},asetpts=PTS-STARTPTS[{label}]")
        audio_labels.append(f"[{label}]")
    filters.append(
        f"{''.join(audio_labels)}amix=inputs={len(audio_clips)}:duration=longest:normalize=0[mix]"
    )
    filters.append(f"[mix]apad,atrim=duration={total:.3f},asetpts=PTS-STARTPTS[aout]")
    command += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.3f}", "-movflags", "+faststart",
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
    prompts = work / "narration"
    prompts.mkdir(parents=True, exist_ok=True)
    intro_text = "\uC9C0\uAE08 \uB9C8\uC74C\uC740 \uC5B4\uB5A0\uC138\uC694? \uB204\uAD6C\uC5D0\uAC8C\uB3C4 \uB9D0\uD558\uC9C0 \uBABB\uD55C \uB9C8\uC74C\uC774 \uC788\uB2E4\uBA74, \uC5EC\uAE30\uC5D0 \uD3B8\uD558\uAC8C \uC801\uC5B4\uC8FC\uC138\uC694."
    verse_text = f"{manifest['reference']}. {' '.join(manifest['text'].splitlines()).strip()}"
    video_text = "\uC774 \uB9C8\uC74C\uC5D0 \uC5B4\uC6B8\uB9AC\uB294 \uCC2C\uC591 \uC601\uC0C1\uC744 \uD568\uAED8 \uCC3E\uC544\uBCFC\uAC8C\uC694."
    intro_audio, verse_audio, video_audio = prompts / "input.mp3", prompts / "verse.mp3", prompts / "videos.mp3"
    synthesize_text(intro_text, intro_audio, args.voice, speaking_rate=0.94)
    synthesize_text(verse_text, verse_audio, args.voice, speaking_rate=0.88)
    synthesize_text(video_text, video_audio, args.voice, speaking_rate=0.94)
    intro_time = media_duration(intro_audio, args.ffprobe)
    verse_time = media_duration(verse_audio, args.ffprobe)
    video_time = media_duration(video_audio, args.ffprobe)
    pages, player_pages = app_scenes(manifest, work)
    typing_pages = pages[:-2]
    verse_page, video_page = pages[-2:]
    image_paths = [*typing_pages, verse_page, video_page, *player_pages]
    transition = 0.16
    intro_duration = max(5.8, intro_time + 1.0)
    # The video list starts about two seconds after the verse audio ends.
    verse_duration = verse_time + 2.0 + transition
    video_duration = max(4.0, math.ceil(video_time + 0.9))
    durations = ([intro_duration / len(typing_pages)] * len(typing_pages)
                 + [verse_duration, video_duration, 1.2, 1.2, 1.2])
    if sum(durations) > 60:
        raise ValueError(f"Narration is too long for a Short: estimated {sum(durations)} seconds")

    def scene_start(index: int) -> float:
        return sum(durations[:index]) - transition * index

    audio_clips = [(intro_audio, 0.0), (verse_audio, scene_start(len(typing_pages))),
                   (video_audio, scene_start(len(typing_pages) + 1))]

    output = args.output or work / "short-draft.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    render_mp4(image_paths, durations, audio_clips, output, args.ffmpeg, transition=transition)
    rendered_time = sum(durations) - transition * (len(image_paths) - 1)
    print(f"Rendered app walkthrough with {args.voice} ({rendered_time:.1f} seconds): {output}")
    print("Review the verse, three narration parts, transitions, and YouTube handoff before publishing.")


if __name__ == "__main__":
    main()
