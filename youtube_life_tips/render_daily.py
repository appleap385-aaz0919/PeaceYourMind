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
from editorial import validate_script


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work" / "daily"
VENDOR = ROOT / "work" / "vendor"
WIDTH, HEIGHT, FPS = 720, 1280, 15
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


async def synthesize_segments(scenes: list[dict[str, str]], output_paths: list[Path]) -> None:
    if not VENDOR.is_dir():
        raise RuntimeError("local TTS package folder work/vendor is missing")
    sys.path.insert(0, str(VENDOR))
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Edge TTS is not installed in work/vendor; daily run skipped") from exc
    for scene, output in zip(scenes, output_paths, strict=True):
        await edge_tts.Communicate(
            scene["narration"], VOICE, rate="+8%", pitch="+1Hz"
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
    if width < 768 or height < 1152 or height / width < 1.35:
        raise ValueError("storyboard must be a high-resolution portrait grid")
    gutter_x, gutter_y = max(4, round(width * 0.008)), max(4, round(height * 0.005))
    boxes = [(col * width // columns + (gutter_x if col else 0),
              row * height // rows + (gutter_y if row else 0),
              (col + 1) * width // columns - (gutter_x if col < columns - 1 else 0),
              (row + 1) * height // rows - (gutter_y if row < rows - 1 else 0))
             for row in range(rows) for col in range(columns)]
    panels = []
    for box in boxes:
        panel = storyboard.crop(box)
        # Keep every part of the generated panel visible. A center crop can hide
        # hands, tools, or the result that the narration asks viewers to inspect.
        foreground = ImageOps.contain(panel, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 20))
        canvas.paste(foreground, ((WIDTH - foreground.width) // 2, (HEIGHT - foreground.height) // 2))
        panels.append(canvas)
    return panels


def fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    regular, bold = Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf")
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError("Korean Malgun fonts are required for readable captions")
    return (
        ImageFont.truetype(str(bold), 42),
        ImageFont.truetype(str(bold), 34),
        ImageFont.truetype(str(regular), 25),
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


def validate_layout(content):
    draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, HEIGHT)))
    hook_font, caption_font, _ = fonts()
    fitted_text(draw, content["hook"], hook_font, 630, 2, 36, "hook")
    for i, scene in enumerate(content["scenes"]):
        fitted_text(draw, scene["caption"], caption_font, 575, 3, 30, f"scene {i + 1} caption")
    grid = content.get("storyboard_grid", {"columns": 2, "rows": math.ceil(len(content["scenes"]) / 2)})
    if any(type(grid.get(key)) is not int or grid[key] < 1 for key in ("columns", "rows")):
        raise ValueError("storyboard_grid dimensions must be positive integers")
    for i, scene in enumerate(content["scenes"]):
        index = scene.get("panel_index", i)
        if type(index) is not int or not 0 <= index < grid["columns"] * grid["rows"]:
            raise ValueError("Every scene must have an existing storyboard panel")


def overlay_for_scene(
    scene_image: Image.Image,
    caption: str,
    hook: str,
    index: int,
    hook_font: ImageFont.FreeTypeFont,
    caption_font: ImageFont.FreeTypeFont,
    small_font: ImageFont.FreeTypeFont,
    scene_count: int = 4,
) -> Image.Image:
    image = scene_image.copy().convert("RGBA")
    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for y in range(0, 360, 4):
        alpha = max(0, int(180 * (1 - y / 430)))
        shade_draw.rectangle((0, y, WIDTH, y + 3), fill=(8, 14, 22, alpha))
    for y in range(790, HEIGHT, 4):
        alpha = min(220, int(215 * (y - 790) / 250))
        shade_draw.rectangle((0, y, WIDTH, y + 3), fill=(8, 14, 22, alpha))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((36, 38, 260, 84), radius=22, fill=(13, 23, 36, 210))
    draw.text((55, 47), "생활꿀팁  ·  오늘의 한 가지", font=small_font, fill="#ffffff")
    if index == 0:
        y = 126
        hook_lines, hook_font = fitted_text(draw, hook, hook_font, 630, 2, 36, "hook")
        for line in hook_lines:
            draw.text((38, y), line, font=hook_font, fill="#fff3a1", stroke_width=2, stroke_fill="#101820")
            y += 54

    caption_lines, caption_font = fitted_text(draw, caption, caption_font, 575, 3, 30, f"scene {index + 1} caption")
    box_height = max(154, 46 + 52 * len(caption_lines))
    top = HEIGHT - 212 - box_height
    draw.rounded_rectangle(
        (34, top, WIDTH - 34, top + box_height), radius=26,
        fill=(8, 16, 25, 222), outline=(255, 255, 255, 65), width=2,
    )
    y = top + (box_height - 52 * len(caption_lines)) // 2 - 2
    for line in caption_lines:
        draw.text((61, y), line, font=caption_font, fill="#ffffff", stroke_width=1, stroke_fill="#111922")
        y += 52
    draw.text((38, HEIGHT - 78), f"{index + 1} / {scene_count}", font=small_font, fill="#e4eef2")
    return image.convert("RGB")


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
    if total <= 0 or total > 55:
        raise ValueError(f"narration duration {total:.1f}s is outside the 1-55s Short limit")

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
    grid = content.get("storyboard_grid", {"columns": 2, "rows": math.ceil(scene_count / 2)})
    panels = load_panels(day_dir / "storyboard.png", grid["columns"], grid["rows"])
    hook_font, caption_font, small_font = fonts()
    frames = [
        overlay_for_scene(panels[scene.get("panel_index", i)], scene["caption"], content["hook"], i,
                          hook_font, caption_font, small_font, scene_count)
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
            if scene_index > 0 and transition < 0.28:
                current = Image.blend(frames[scene_index - 1], current, max(0.0, min(1.0, transition / 0.28)))
            ffmpeg.stdin.write(current.tobytes())
    finally:
        ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise RuntimeError("FFmpeg could not encode today's video")

    actual_width, actual_height = dimensions(output)
    actual_duration = media_duration(output)
    if actual_width != WIDTH or actual_height != HEIGHT or actual_duration > 55.5 or not has_audio(output):
        raise RuntimeError("render validation failed: incorrect dimensions/duration or missing audio")
    title = content["title"].strip()
    if "#Shorts" not in title:
        title += " #Shorts"
    source_lines = [f"- {item['title']}: {item['url']}" for item in content["sources"]]
    description = content.get("description", "오늘 바로 써볼 수 있는 생활꿀팁을 전해드립니다.").strip()
    description += "\n\n참고 자료\n" + "\n".join(source_lines)
    metadata = {
        "date": content["date"], "slot": content.get("slot", "am"),
        "release_key": release_key(content["date"], content.get("slot", "am")),
        "topic": content["topic"], "title": title,
        "season": content.get("season"), "topic_strategy": content.get("topic_strategy"),
        "fallback_reason": content.get("fallback_reason"),
        "description": description, "duration_seconds": round(actual_duration, 2),
        "width": actual_width, "height": actual_height, "voice": VOICE,
        "narration_seconds": [round(value, 2) for value in lengths], "sources": content["sources"],
        "screen_text": {"hook": content["hook"], "captions": [scene["caption"] for scene in content["scenes"]]},
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
    asyncio.run(synthesize_segments(content["scenes"], voice_paths))
    render_video(day_dir, content, voice_paths, day_dir / f"life-tip-{today.isoformat()}.mp4")


if __name__ == "__main__":
    main()
