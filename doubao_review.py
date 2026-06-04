#!/usr/bin/env python3
"""Review short-video copy with Doubao through Volcengine Ark."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from openai import OpenAI


DEFAULT_MODEL = "doubao-seed-2-0-pro-260215"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


REVIEW_PROMPT = """你是抖音金融类短视频内容合规审查助手。
请检查下面这条短视频文案是否容易触发平台金融内容违规或限流风险。

重点检查：
1. 是否有承诺性表达
2. 是否有诱导借贷、夸大结果、低门槛暗示
3. 是否有金融敏感词
4. 哪些词建议不打字幕
5. 如何改得更利他、更像避坑科普

请按这个格式输出：
- 风险等级：低/中/高
- 风险词：
- 风险句：
- 修改建议：
- 优化后的合规版本：

文案如下：
{copy}
"""


def read_copy(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8").strip()
    if args.text:
        return args.text.strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("请通过 --text、--file 或 stdin 传入文案。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Use Doubao to review short-video copy compliance.")
    parser.add_argument("--text", help="Copy text to review.")
    parser.add_argument("--file", help="Path to a text/markdown file containing copy.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ark model name.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Ark API base URL.")
    args = parser.parse_args()

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        raise SystemExit("缺少 ARK_API_KEY。请先运行：export ARK_API_KEY='你的key'")

    copy = read_copy(args)
    if not copy:
        raise SystemExit("文案为空。")

    client = OpenAI(base_url=args.base_url, api_key=api_key)
    response = client.responses.create(
        model=args.model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": REVIEW_PROMPT.format(copy=copy),
                    }
                ],
            }
        ],
    )

    print(response.output_text)


if __name__ == "__main__":
    main()
