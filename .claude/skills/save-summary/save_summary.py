#!/usr/bin/env python3
"""Save the previous Claude Code reply as HTML that looks exactly like the CLI.

The reply's markdown is read verbatim from the session transcript
(~/.claude/projects/<cwd-slug>/<session>.jsonl). Rendering is done by
render.mjs, a port of the CLI's own markdown renderer built on the same
libraries the CLI bundles, so colors and layout match the terminal.

Usage:
    save_summary.py [OUT.html] [-n N] [--turn] [--width W] [--raw] [--ansi]
                    [--list] [--stdout]

    OUT.html   output path (default: ~/log/claude/claude-summary-<ts>.html)
    -n N       Nth reply from the end (default 1 = the previous reply)
    --turn     save the whole turn, not only its final message
    --width W  layout width for tables (default 100)
    --raw      save the source markdown instead of HTML
    --ansi     save raw ANSI instead of HTML
    --list     list saveable replies and exit
    --stdout   print to stdout instead of writing a file
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = Path.home() / "log" / "claude"


def project_dir(cwd: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return Path.home() / ".claude" / "projects" / slug


def latest_transcript(cwd: Path) -> Path:
    pdir = project_dir(cwd)
    files = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no transcript found under {pdir}")
    return files[-1]


def turns(transcript: Path) -> list[list[dict]]:
    """Split the transcript into finished turns.

    A turn is the assistant activity between two real user prompts. Each
    entry kept is {"text": str} or {"tool": True}. The trailing unfinished
    turn (the /save-summary invocation itself) is dropped.
    """
    finished: list[list[dict]] = []
    current: list[dict] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("isSidechain"):
            continue
        kind = obj.get("type")
        message = obj.get("message") or {}
        content = message.get("content")
        if kind == "user":
            is_prompt = isinstance(content, str) or (
                isinstance(content, list)
                and any(b.get("type") == "text" for b in content if isinstance(b, dict))
            )
            if is_prompt and current:
                finished.append(current)
                current = []
        elif kind == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text", "").strip():
                    current.append({"text": block["text"]})
                elif block.get("type") == "tool_use":
                    current.append({"tool": True})
    return [t for t in finished if any("text" in e for e in t)]


def pick(all_turns: list[list[dict]], n: int, whole_turn: bool) -> str:
    if n < 1 or n > len(all_turns):
        sys.exit(f"reply -n {n} not found ({len(all_turns)} available)")
    turn = all_turns[-n]
    texts = [e["text"] for e in turn if "text" in e]
    if whole_turn:
        return "\n\n".join(texts)
    tail: list[str] = []
    for entry in reversed(turn):
        if "tool" in entry:
            break
        tail.append(entry["text"])
    return "\n\n".join(reversed(tail)) if tail else texts[-1]


def render(markdown: str, width: int, ansi: bool) -> str:
    cmd = ["node", str(SKILL_DIR / "render.mjs"), "--width", str(width)]
    if ansi:
        cmd.append("--ansi")
    env = dict(os.environ, FORCE_COLOR="3")
    result = subprocess.run(cmd, input=markdown, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        sys.exit(f"render.mjs failed: {result.stderr.strip()}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(prog="save-summary", description=__doc__)
    parser.add_argument("out", nargs="?", default=None)
    parser.add_argument("-n", type=int, default=1)
    parser.add_argument("--turn", action="store_true")
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--ansi", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    transcript = latest_transcript(Path.cwd())
    all_turns = turns(transcript)
    if args.list:
        for i, turn in enumerate(reversed(all_turns), 1):
            texts = [e["text"] for e in turn if "text" in e]
            head = texts[-1].strip().splitlines()[0][:80]
            print(f"-n {i}: {sum(len(t) for t in texts):>6} chars  {head}")
        return 0

    markdown = pick(all_turns, args.n, args.turn)
    if args.raw:
        output = markdown + "\n"
        suffix = ".md"
    elif args.ansi:
        output = render(markdown, args.width, ansi=True)
        suffix = ".ansi"
    else:
        output = render(markdown, args.width, ansi=False)
        suffix = ".html"

    if args.stdout:
        sys.stdout.write(output)
        return 0

    if args.out:
        out = Path(args.out).expanduser()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = DEFAULT_OUT_DIR / f"claude-summary-{stamp}{suffix}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
