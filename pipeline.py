#!/usr/bin/env python3
"""Create copy, video config, Dreamina tasks, and cover briefs from one topic."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


def slugify(value: str) -> str:
    value = re.sub(r"\s+", "-", value.strip().lower())
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "", value)
    return value.strip("-") or "short-video"


def ensure_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def build_copy(config: Dict[str, Any]) -> Dict[str, Any]:
    topic = config["topic"]
    audience = config.get("audience", "普通短视频用户")
    persona = config.get("persona", "短视频运营顾问")
    pain_points = ensure_list(config.get("pain_points"))
    takeaways = ensure_list(config.get("takeaways"))
    call_to_action = config.get("call_to_action", "收藏起来，下次直接照着用。")

    pain = pain_points[0] if pain_points else "明明很努力，内容却没人看"
    core = takeaways[0] if takeaways else "把一个复杂问题拆成马上能执行的一步"

    hook = config.get("hook") or f"别再凭感觉做{topic}了，真正拉开差距的是这一步。"
    title = config.get("title") or f"{topic}的高转化做法"

    scenes = [
        {
            "duration": 2.8,
            "headline": hook,
            "body": f"如果你是{audience}，大概率遇到过：{pain}。",
            "background": "#101418",
            "accent": "#2DD4BF",
        },
        {
            "duration": 3.2,
            "headline": "先抓住一个问题",
            "body": f"不要一上来讲大道理。先点出观众最在意的结果：{core}。",
            "background": "#18202A",
            "accent": "#F5C542",
        },
        {
            "duration": 3.2,
            "headline": "再给一个动作",
            "body": (takeaways[1] if len(takeaways) > 1 else "把方法压缩成 1 个步骤、1 个判断、1 个案例。"),
            "background": "#241B2F",
            "accent": "#FF7A59",
        },
        {
            "duration": 2.8,
            "headline": "最后给明确反馈",
            "body": call_to_action,
            "background": "#153225",
            "accent": "#7DDC83",
        },
    ]

    return {
        "title": title,
        "topic": topic,
        "audience": audience,
        "persona": persona,
        "hook": hook,
        "scenes": scenes,
        "cover_title": config.get("cover_title") or title,
        "cover_subtitle": config.get("cover_subtitle") or hook,
    }


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_copy_markdown(path: Path, copy: Dict[str, Any]) -> None:
    lines = [
        f"# {copy['title']}",
        "",
        f"- 选题：{copy['topic']}",
        f"- 受众：{copy['audience']}",
        f"- 人设：{copy['persona']}",
        f"- 开场钩子：{copy['hook']}",
        "",
        "## 分镜文案",
    ]
    for index, scene in enumerate(copy["scenes"], start=1):
        lines.extend(
            [
                "",
                f"### {index}. {scene['headline']}",
                scene["body"],
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_video_project(copy: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    return {
        "title": copy["title"],
        "output": str(output_dir / "video.mp4"),
        "size": [1080, 1920],
        "fps": 30,
        "music": {"enabled": True, "volume": 0.08},
        "scenes": copy["scenes"],
    }


def build_dreamina_config(copy: Dict[str, Any]) -> Dict[str, Any]:
    tasks = []
    for index, scene in enumerate(copy["scenes"], start=1):
        tasks.append(
            {
                "name": f"scene_{index:02d}",
                "type": "text2video",
                "prompt": (
                    "竖屏短视频，真实商业知识分享风格，画面干净，有清晰字幕留白，"
                    f"主题是{copy['topic']}。分镜：{scene['headline']}。画面表达：{scene['body']}"
                ),
            }
        )
    return {
        "defaults": {
            "poll": 30,
            "session": 0,
            "model_version": "seedance2.0fast",
            "video_resolution": "720p",
            "ratio": "9:16",
            "duration": 5,
        },
        "tasks": tasks,
    }


def write_cover_brief(path: Path, copy: Dict[str, Any]) -> None:
    text = f"""# 封面设计 Brief

## 选题
{copy['topic']}

## 封面主标题
{copy['cover_title']}

## 封面副标题
{copy['cover_subtitle']}

## 设计方向
- 竖版 9:16，适配抖音/视频号/小红书首帧。
- 主标题 8-14 字，必须第一眼可读。
- 画面重点突出“问题 + 结果”，不要堆太多字。
- 色彩建议：深色背景 + 高亮强调色，和视频内字幕风格统一。

## 可交付物
- `cover.png`：1080x1920 成品封面。
- `cover_source.psd` 或可编辑源文件。
- 可选：2 个标题排版变体，方便 A/B 测试。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(config_path: Path) -> Path:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    copy = build_copy(config)
    slug = slugify(config.get("slug") or copy["topic"])
    output_dir = Path(config.get("output_root", "output/projects")) / slug

    write_copy_markdown(output_dir / "copy.md", copy)
    write_yaml(output_dir / "project.yaml", build_video_project(copy, output_dir))
    write_yaml(output_dir / "dreamina_batch.yaml", build_dreamina_config(copy))
    write_cover_brief(output_dir / "cover_brief.md", copy)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a short-video automation package from one topic.")
    parser.add_argument("config", type=Path, help="Pipeline YAML config")
    args = parser.parse_args()
    output_dir = run(args.config)
    print(f"Created automation package: {output_dir}")
    print(f"Next: python generate_video.py {output_dir / 'project.yaml'}")
    print(f"Dreamina preview: python dreamina_batch.py {output_dir / 'dreamina_batch.yaml'}")


if __name__ == "__main__":
    main()
