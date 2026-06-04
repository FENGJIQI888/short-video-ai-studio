#!/usr/bin/env python3
"""Generate a vertical short video from a YAML project file."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import AudioClip, ImageClip, concatenate_videoclips


Color = Tuple[int, int, int]


def parse_color(value: str) -> Color:
    value = value.strip()
    if not value.startswith("#") or len(value) != 7:
        raise ValueError(f"Invalid color {value!r}; expected #RRGGBB")
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for char in text:
        trial = current + char
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def text_block(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: Color,
    max_width: int,
    line_gap: int,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += bbox[3] - bbox[1] + line_gap
    return y


def make_scene_image(scene: Dict[str, Any], index: int, total: int, size: Sequence[int]) -> Image.Image:
    width, height = int(size[0]), int(size[1])
    bg = parse_color(scene.get("background", "#171717"))
    accent = parse_color(scene.get("accent", "#FFFFFF"))

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    title_font = load_font(88, bold=True)
    body_font = load_font(48)
    meta_font = load_font(32)

    margin = 88
    max_text_width = width - margin * 2

    # Subtle geometric background.
    for step in range(0, height, 180):
        alpha = step / max(height, 1)
        color = tuple(int(bg[i] * (1 - alpha * 0.18) + accent[i] * alpha * 0.18) for i in range(3))
        draw.rectangle((0, step, width, step + 120), fill=color)

    draw.rounded_rectangle((margin, 150, margin + 170, 162), radius=6, fill=accent)
    draw.text((margin, 190), f"{index + 1:02d}/{total:02d}", font=meta_font, fill=(235, 235, 235))

    y = 520
    y = text_block(draw, (margin, y), scene.get("headline", ""), title_font, (255, 255, 255), max_text_width, 24)
    y += 60
    text_block(draw, (margin, y), scene.get("body", ""), body_font, (238, 238, 238), max_text_width, 18)

    bar_top = height - 170
    draw.rounded_rectangle((margin, bar_top, width - margin, bar_top + 16), radius=8, fill=(255, 255, 255))
    progress_width = int((width - margin * 2) * ((index + 1) / total))
    draw.rounded_rectangle((margin, bar_top, margin + progress_width, bar_top + 16), radius=8, fill=accent)

    draw.text((margin, height - 120), "自动生成短视频", font=meta_font, fill=(225, 225, 225))
    return image


def sine_music(duration: float, volume: float) -> AudioClip:
    def make_frame(t: Any) -> Any:
        arr = np.array(t, dtype=float)
        tone = np.sin(2 * math.pi * 220 * arr) * 0.45
        pulse = np.sin(2 * math.pi * 2 * arr) * 0.15
        audio = (tone + pulse) * volume
        return np.column_stack([audio, audio]) if audio.ndim else [float(audio), float(audio)]

    return AudioClip(make_frame, duration=duration, fps=44100)


def build_video(project: Dict[str, Any]) -> Path:
    scenes = project.get("scenes") or []
    if not scenes:
        raise ValueError("Project must contain at least one scene")

    size = project.get("size", [1080, 1920])
    fps = int(project.get("fps", 30))
    clips = []

    for index, scene in enumerate(scenes):
        duration = float(scene.get("duration", 3.0))
        frame = np.array(make_scene_image(scene, index, len(scenes), size))
        clip = ImageClip(frame).set_duration(duration).fadein(0.18).fadeout(0.18)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    music = project.get("music", {})
    if music.get("enabled", True):
        video = video.set_audio(sine_music(video.duration, float(music.get("volume", 0.08))))

    output = Path(project.get("output", "output/generated.mp4"))
    output.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(str(output), fps=fps, codec="libx264", audio_codec="aac")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a short video from YAML.")
    parser.add_argument("project", type=Path, help="Path to project YAML")
    args = parser.parse_args()

    with args.project.open("r", encoding="utf-8") as file:
        project = yaml.safe_load(file)

    output = build_video(project)
    print(f"Generated: {output}")


if __name__ == "__main__":
    main()
