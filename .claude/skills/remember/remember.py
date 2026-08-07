#!/usr/bin/env python3
"""Save the previous Claude Code reply as a markdown note in the second brain.

The reply's markdown is read verbatim from the session transcript
(~/.claude/projects/<cwd-slug>/<session>.jsonl) and written to
$BRAIN_DIR/notes (default /src/2brain/notes) with YAML frontmatter.
Browse the notes with Obsidian, or render one to CLI-style HTML in the
browser with the `2brain` script that lives next to them.

Usage:
    remember.py [TITLE...] [-n N] [--turn] [--list] [--stdout]

    TITLE      words for the note title -> notes/YYYY-MM-DD-<title-slug>.md
               (default: slug of the reply's first line)
    -n N       Nth reply from the end (default 1 = the previous reply)
    --turn     save every text message of the turn, not only its final one
    --list     list saveable replies and exit
    --stdout   print the note to stdout instead of writing a file
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

BRAIN_DIR = Path(os.environ.get("BRAIN_DIR", "/src/2brain"))
NOTES_DIR = BRAIN_DIR / "notes"


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
    turn (the /remember invocation itself) is dropped.
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


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "note"


def first_line_title(markdown: str) -> str:
    for line in markdown.splitlines():
        line = re.sub(r"[#*_`>\[\]]", "", line).strip()
        if line:
            return line
    return "note"


def compose_note(markdown: str, cwd: Path) -> str:
    created = time.strftime("%Y-%m-%dT%H:%M:%S")
    frontmatter = "\n".join(
        ["---", f"created: {created}", "source: claude-code", f"project: {cwd}", "---"]
    )
    return f"{frontmatter}\n\n{markdown.strip()}\n"


def note_path(title: str) -> Path:
    stem = f"{time.strftime('%Y-%m-%d')}-{slugify(title)}"
    out = NOTES_DIR / f"{stem}.md"
    i = 2
    while out.exists():
        out = NOTES_DIR / f"{stem}-{i}.md"
        i += 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="remember", description=__doc__)
    parser.add_argument("title", nargs="*", default=None)
    parser.add_argument("-n", type=int, default=1)
    parser.add_argument("--turn", action="store_true")
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
    note = compose_note(markdown, Path.cwd())

    if args.stdout:
        sys.stdout.write(note)
        return 0

    title = " ".join(args.title) if args.title else first_line_title(markdown)
    out = note_path(title)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(note, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
