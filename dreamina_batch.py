#!/usr/bin/env python3
"""Batch-submit Dreamina generation tasks from YAML."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


SUBMIT_ID_RE = re.compile(r'"?submit_id"?\s*[:=]\s*"?([A-Za-z0-9_.:-]+)"?')
STATUS_RE = re.compile(r'"?gen_status"?\s*[:=]\s*"?([A-Za-z_]+)"?')


def merge(defaults: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(defaults)
    merged.update(task)
    return merged


def add_flag(args: List[str], name: str, value: Any) -> None:
    if value is None or value == "":
        return
    args.append(f"--{name}={value}")


def build_command(task: Dict[str, Any]) -> List[str]:
    task_type = task.get("type")
    if task_type not in {"text2video", "image2video"}:
        raise ValueError(f"Unsupported task type {task_type!r}; use text2video or image2video")

    command = ["dreamina", task_type]
    add_flag(command, "prompt", task.get("prompt"))
    add_flag(command, "duration", task.get("duration"))
    add_flag(command, "video_resolution", task.get("video_resolution"))
    add_flag(command, "model_version", task.get("model_version"))
    add_flag(command, "session", task.get("session"))
    add_flag(command, "poll", task.get("poll"))

    if task_type == "text2video":
        add_flag(command, "ratio", task.get("ratio"))
    else:
        add_flag(command, "image", task.get("image"))

    return command


def parse_result(output: str) -> Dict[str, Optional[str]]:
    submit_match = SUBMIT_ID_RE.search(output)
    status_match = STATUS_RE.search(output)
    return {
        "submit_id": submit_match.group(1) if submit_match else None,
        "gen_status": status_match.group(1) if status_match else None,
    }


def run_command(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def submit_tasks(config: Dict[str, Any], dry_run: bool, log_path: Path) -> int:
    defaults = config.get("defaults") or {}
    tasks = config.get("tasks") or []
    if not tasks:
        raise ValueError("No tasks found in config")

    rows: List[Dict[str, Any]] = []
    failures = 0

    for index, raw_task in enumerate(tasks, start=1):
        task = merge(defaults, raw_task)
        name = task.get("name") or f"task_{index}"
        command = build_command(task)
        timestamp = datetime.now(timezone.utc).isoformat()

        if dry_run:
            print(shlex.join(command))
            rows.append(
                {
                    "time": timestamp,
                    "name": name,
                    "dry_run": True,
                    "command": command,
                }
            )
            continue

        print(f"[{index}/{len(tasks)}] submit {name}", flush=True)
        completed = run_command(command)
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        parsed = parse_result(output + "\n" + error)
        status = parsed.get("gen_status")

        if completed.returncode != 0 or status == "fail":
            failures += 1

        rows.append(
            {
                "time": timestamp,
                "name": name,
                "dry_run": False,
                "command": command,
                "returncode": completed.returncode,
                "submit_id": parsed.get("submit_id"),
                "gen_status": status,
                "stdout": output,
                "stderr": error,
            }
        )
        print(output or error or f"returncode={completed.returncode}")

    append_jsonl(log_path, rows)
    return failures


def query(config: Dict[str, Any], log_path: Path, download_dir: Optional[Path]) -> int:
    submit_ids: List[str] = []
    if "submit_ids" in config:
        submit_ids.extend(str(value) for value in config["submit_ids"])
    elif log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("submit_id"):
                submit_ids.append(row["submit_id"])

    if not submit_ids:
        print("No submit_id found. Submit tasks first or add submit_ids to YAML.", file=sys.stderr)
        return 1

    failures = 0
    rows = []
    for submit_id in submit_ids:
        command = ["dreamina", "query_result", f"--submit_id={submit_id}"]
        if download_dir:
            command.append(f"--download_dir={download_dir}")
        completed = run_command(command)
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        parsed = parse_result(output + "\n" + error)
        if completed.returncode != 0 or parsed.get("gen_status") == "fail":
            failures += 1
        print(output or error or f"returncode={completed.returncode}")
        rows.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "query": True,
                "command": command,
                "returncode": completed.returncode,
                "submit_id": submit_id,
                "gen_status": parsed.get("gen_status"),
                "stdout": output,
                "stderr": error,
            }
        )
    append_jsonl(log_path, rows)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch automation for Dreamina CLI video generation.")
    parser.add_argument("config", type=Path, help="YAML file with defaults and tasks")
    parser.add_argument("--run", action="store_true", help="Submit real tasks. Without this, commands are only printed.")
    parser.add_argument("--query", action="store_true", help="Query submit_ids from the log or config.")
    parser.add_argument("--log", type=Path, default=Path("output/dreamina_tasks.jsonl"))
    parser.add_argument("--download-dir", type=Path, help="Download query results into this directory.")
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if args.query:
        raise SystemExit(query(config, args.log, args.download_dir))

    raise SystemExit(submit_tasks(config, dry_run=not args.run, log_path=args.log))


if __name__ == "__main__":
    main()
