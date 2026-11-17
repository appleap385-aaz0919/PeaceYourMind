"""Render one newly generated daily storyboard and Korean narration to a Short."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps
from life_schedule import release_key
from background_process import hidden_process_options
from editorial import STORYBOARD_MIN_ASPECT, demo_storyboard_grid, validate_script
from video_limits import MIN_DURATION_SECONDS, MAX_DURATION_SECONDS, validate_duration


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work" / "daily"
VENDOR = ROOT / "work" / "vendor"
WIDTH, HEIGHT, FPS = 720, 1280, 15
VISUAL_TOP, VISUAL_HEIGHT, VISUAL_WIDTH = 278, 672, 672
BACKGROUND = "#20281f"
VOICE = "ko-KR-InJoonNeural"


def run(args: list[str]) -> bytes:
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **hidden_process_options())
    return result.stdout


def media_duration(path: Path) -> float:
    value = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(value.decode("ascii").strip())


def dimensions(path: Path) -> tuple[int, int]:
    result = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(path),
    ])
    stream = json.loads(result)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def has_audio(path: Path) -> bool:
    result = run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "json", str(path),
    ])
    return bool(json.loads(result).get("streams"))


def load_content(path: Path, requested_date: date) -> dict[str, Any]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("date") != requested_date.isoformat():
        raise ValueError("content.json date must match the requested Korea date")
    scenes, sources = content.get("scenes"), content.get("sources")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("content.json must contain scenes matched to the script")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("content.json must contain at least two verified sources")
    for index, scene in enumerate(scenes, start=1):
        if not scene.get("narration", "").strip() or not scene.get("caption", "").strip():
            raise ValueError(f"scene {index} needs narration and caption")
    if not content.get("topic") or not content.get("hook") or not content.get("title"):
        raise ValueError("content.json needs topic, hook, and title")
    if any(not item.get("title") or not item.get("url", "").startswith("https://") for item in sources):
        raise ValueError("each source must have a title and https URL")
    validate_script(content)
    return content


async def synthesize_segments(
    scenes: list[dict[str, str]], output_paths: list[Path], *, rate: str = "+8%"
) -> None:
    if not VENDOR.is_dir():
        raise RuntimeError("local TTS package folder work/vendor is missing")
    sys.path.insert(0, str(VENDOR))
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Edge TTS is not installed in work/vendor; daily run skipped") from exc
    for scene, output in zip(scenes, output_paths, strict=True):
        await edge_tts.Communicate(
            scene["narration"], VOICE, rate=rate, pitch="+1Hz"
        ).save(str(output))


def load_panels(path: Path, columns: int = 2, rows: int = 2) -> list[Image.Image]:
    if not path.is_file():
        raise FileNotFoundError("today's newly generated storyboard.png is missing")
    sample_dir = (ROOT / "work" / "sample").resolve()
    if sample_dir in path.resolve().parents:
        raise ValueError("sample assets are not valid daily artwork")
    with Image.open(path) as opened:
        storyboard = opened.convert("RGB")
    width, height = storyboard.size
    if width < 768 or height < 1152 or height / width < STORYBOARD_MIN_ASPECT:
        raise ValueError("storyboard must be a high-resolution portrait grid")
    boundaries = [0]
    for row in range(1, rows):
        expected = row * height // rows
        search = max(12, height // rows // 5)
        step = max(1, width // 128)
        white_rows = []
        for y in range(max(1, expected - search), min(height - 1, expected + search)):
            samples = [storyboard.getpixel((x, y)) for x in range(0, width, step)]
            ratio = sum(min(pixel) >= 235 for pixel in samples) / len(samples)
            if ratio >= 0.9:
                white_rows.append(y)
        groups = []
        for y in white_rows:
            if not groups or y > groups[-1][-1] + 1:
                groups.append([y])
            else:
                groups[-1].append(y)
        seams = [group for group in groups if len(group) >= 3]
        if seams:
            seam = min(seams, key=lambda group: abs((group[0] + group[-1]) / 2 - expected))
            boundaries.append((seam[0] + seam[-1]) // 2)
        else:
            boundaries.append(expected)
    boundaries.append(height)
    gutter_x, gutter_y = max(4, round(width * 0.008)), max(4, round(height * 0.005))
    boxes = [(col * width // columns + (gutter_x if col else 0),
              boundaries[row] + (gutter_y if row else 0),
              (col + 1) * width // columns - (gutter_x if col < columns - 1 else 0),
              boundaries[row + 1] - (gutter_y if row < rows - 1 else 0))
             for row in range(rows) for col in range(columns)]
    panels = []
    for box in boxes:
        panel = storyboard.crop(box)
        # Keep every part of the generated panel visible. A center crop can hide
        # hands, tools, or the result that the narration asks viewers to inspect.
        # Keep the complete instruction above the caption box and below the headline.
        foreground = ImageOps.contain(panel, (VISUAL_WIDTH, VISUAL_HEIGHT), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        canvas.paste(foreground, ((WIDTH - foreground.width) // 2,
                                 VISUAL_TOP + (VISUAL_HEIGHT - foreground.height) // 2))
        panels.append(canvas)
    return panels


def fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    regular, bold = Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf")
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError("Korean Malgun fonts are required for readable captions")
    return (
        ImageFont.truetype(str(bold), 43),
        ImageFont.truetype(str(bold), 32),
        ImageFont.truetype(str(regular), 24),
    )


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            if draw.textlength(word, font=font) > max_width:
                raise ValueError(f"Text cannot fit without clipping: {word!r}")
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def checked_text_lines(draw, text, font, width, max_lines, label):
    lines = wrap_text(draw, text, font, width)
    if not lines or len(lines) > max_lines:
        raise ValueError(f"{label} needs {len(lines)} lines; maximum is {max_lines}. Shorten the wording; never truncate it.")
    return lines


def fitted_text(draw, text, font, width, max_lines, min_size, label):
    """Reflow and modestly resize; retain every word and a readable minimum."""
    error = None
    for size in range(font.size, min_size - 1, -2):
        candidate = font.font_variant(size=size)
        for wording in (text, " ".join(text.split())):
            try:
                return checked_text_lines(draw, wording, candidate, width, max_lines, label), candidate
            except ValueError as exc:
                error = exc
    raise error


def display_heading(hook, heading, index):
    """Show the approved hook first, then each scene's heading."""
    return hook if index == 0 else heading or hook


def validate_layout(content):
    draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, HEIGHT)))
    hook_font, caption_font, _ = fonts()
    fitted_text(draw, content["hook"], hook_font, 630, 2, 36, "hook")
    for i, scene in enumerate(content["scenes"]):
        fitted_text(draw, display_heading(content["hook"], scene.get("heading"), i), hook_font, 632, 2, 36, f"scene {i + 1} heading")
        fitted_text(draw, scene["caption"], caption_font, 632, 4, 30, f"scene {i + 1} caption")
    grid = content.get("storyboard_grid", demo_storyboard_grid(len(content["scenes"])))
    if any(type(grid.get(key)) is not int or grid[key] < 1 for key in ("columns", "rows")):
        raise ValueError("storyboard_grid dimensions must be positive integers")
    if grid["columns"] not in (2, 3) or grid["rows"] != math.ceil(len(content["scenes"]) / grid["columns"]):
        raise ValueError("storyboard_grid must have two or three columns and one panel per scene")
    for i, scene in enumerate(content["scenes"]):
        index = scene.get("panel_index", i)
        if type(index) is not int or index != i:
            raise ValueError("Every scene must use its own row-major storyboard panel")


def overlay_for_scene(
    scene_image: Image.Image,
    caption: str,
    hook: str,
    index: int,
    hook_font: ImageFont.FreeTypeFont,
    caption_font: ImageFont.FreeTypeFont,
    small_font: ImageFont.FreeTypeFont,
    scene_count: int = 4,
    heading: str | None = None,
) -> Image.Image:
    image = scene_image.copy().convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.text((44, 48), "살림 한 수", font=small_font, fill="#b9cdb0")
    draw.text((WIDTH - 44, 51), "AI 재현", font=small_font, fill="#bec8b9", anchor="ra")
    heading_lines, hook_font = fitted_text(draw, display_heading(hook, heading, index), hook_font, 632, 2, 36, "heading")
    for line_index, line in enumerate(heading_lines):
        draw.text((44, 112 + line_index * 57), line, font=hook_font, fill="#f9f6ee")
    caption_lines, caption_font = fitted_text(draw, caption, caption_font, 632, 4, 30, f"scene {index + 1} caption")
    y = 1074 - (len(caption_lines) - 1) * 24
    for line in caption_lines:
        draw.text((WIDTH // 2, y), line, font=caption_font, fill="#f9f6ee", anchor="mm")
        y += 48
    draw.text((44, 1194), f"{index + 1:02d} / {scene_count}", font=small_font, fill="#a5b39f")
    draw.rectangle((44, 1237, WIDTH - 44, 1241), fill="#495143")
    return image


def render_video(day_dir: Path, content: dict[str, Any], voice_paths: list[Path], output: Path) -> None:
    validate_script(content)
    validate_layout(content)
    lengths = [media_duration(path) for path in voice_paths]
    starts: list[float] = []
    cursor = 0.0
    for length in lengths:
        starts.append(cursor)
        cursor += length
    total = cursor
    validate_duration(total)

    voice = day_dir / "narration.mp3"
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for path in voice_paths:
        args.extend(["-i", str(path)])
    filters, labels = [], []
    for i in range(len(voice_paths)):
        filters.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
        labels.append(f"[a{i}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    args.extend([
        "-filter_complex", ";".join(filters), "-map", "[out]", "-threads", "1",
        "-c:a", "libmp3lame", "-q:a", "4", str(voice),
    ])
    run(args)

    scene_count = len(content["scenes"])
    grid = content.get("storyboard_grid", demo_storyboard_grid(scene_count))
    panels = load_panels(day_dir / "storyboard.png", grid["columns"], grid["rows"])
    hook_font, caption_font, small_font = fonts()
    frames = [
        overlay_for_scene(panels[scene.get("panel_index", i)], scene["caption"], content["hook"], i,
                          hook_font, caption_font, small_font, scene_count, scene.get("heading"))
        for i, scene in enumerate(content["scenes"])
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
            "-r", str(FPS), "-i", "-", "-i", str(voice), "-t", f"{total:.3f}", "-shortest",
            "-c:v", "libx264", "-preset", "veryfast", "-threads", "1", "-crf", "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output),
        ],
        stdin=subprocess.PIPE,
        **hidden_process_options(),
    )
    assert ffmpeg.stdin is not None
    try:
        for frame_number in range(math.ceil(total * FPS)):
            t = frame_number / FPS
            scene_index = max(i for i, start in enumerate(starts) if start <= t)
            transition = t - starts[scene_index]
            current = frames[scene_index]
            if scene_index > 0 and transition < 0.12:
                current = Image.blend(frames[scene_index - 1], current, max(0.0, min(1.0, transition / 0.12)))
            current = current.copy()
            ImageDraw.Draw(current).rectangle((44, 1237, 44 + round(632 * t / total), 1241), fill="#b9cdb0")
            ffmpeg.stdin.write(current.tobytes())
    finally:
        ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise RuntimeError("FFmpeg could not encode today's video")

    actual_width, actual_height = dimensions(output)
    actual_duration = media_duration(output)
    if (actual_width != WIDTH or actual_height != HEIGHT
            or not MIN_DURATION_SECONDS <= actual_duration <= MAX_DURATION_SECONDS
            or not has_audio(output)):
        raise RuntimeError("render validation failed: incorrect dimensions/duration or missing audio")
    title = content["title"].strip()
    if "#Shorts" not in title:
        title += " #Shorts"
    description = content.get("description", "오늘 바로 써볼 수 있는 생활꿀팁을 전해드립니다.").strip()
    metadata = {
        "date": content["date"], "slot": content.get("slot", "am"),
        "release_key": release_key(content["date"], content.get("slot", "am")),
        "topic": content["topic"], "title": title,
        "season": content.get("season"), "topic_strategy": content.get("topic_strategy"),
        "fallback_reason": content.get("fallback_reason"),
        "description": description, "duration_seconds": round(actual_duration, 2),
        "width": actual_width, "height": actual_height, "voice": VOICE,
        "voice_rate": content.get("voice_rate", "+8%"),
        "narration_seconds": [round(value, 2) for value in lengths], "sources": content["sources"],
        "render_style": "photoreal_demo",
        "screen_text": {"hook": content["hook"], "captions": [scene["caption"] for scene in content["scenes"]],
                        "headings": [display_heading(content["hook"], scene.get("heading"), i) for i, scene in enumerate(content["scenes"])], "ai_label": "AI 재현"},
    }
    (day_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=True, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Asia/Seoul date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--slot", choices=("am", "pm", "manual"), default="am")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Asia/Seoul")).date()
    day_dir = WORK / release_key(today, args.slot)
    content = load_content(day_dir / "content.json", today)
    if content.get("slot", "am") != args.slot:
        raise ValueError("content slot does not match the requested release")
    validate_layout(content)
    voice_paths = [day_dir / f"voice_{index + 1}.mp3" for index in range(len(content["scenes"]))]
    asyncio.run(synthesize_segments(content["scenes"], voice_paths, rate=content.get("voice_rate", "+8%")))
    render_video(day_dir, content, voice_paths, day_dir / f"life-tip-{today.isoformat()}.mp4")


if __name__ == "__main__":
    main()
