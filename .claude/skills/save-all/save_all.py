#!/usr/bin/env python3
"""Save one complete Claude Code turn as HTML, as it looks in the CLI.

Unlike save-summary (final reply only), this saves everything the CLI
showed for the turn: every text message, every tool call with its
result, in order. Text is rendered by save-summary's render.mjs (the
CLI's own markdown renderer). Tool calls use the CLI's presentation:
"●" header line, dim "⎿" results. Edit/Write results are rebuilt as a
unified diff from the transcript and piped through diff-so-fancy.

Usage:
    save_all.py [OUT.html] [-n N] [--width W] [--raw] [--ansi]
                [--list] [--stdout] [--full-results]

    OUT.html        output path (default: /tmp/log/claude/claude-all-<ts>.html)
    -n N            Nth turn from the end (default 1 = the previous turn)
    --width W       layout width for tables (default 100)
    --raw           save plain text (ANSI stripped)
    --ansi          save raw ANSI instead of HTML
    --list          list saveable turns and exit
    --stdout        print instead of writing a file
    --full-results  do not collapse long results/diffs
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
RENDER_MJS = SKILL_DIR.parent / "save-summary" / "render.mjs"
DSF = SKILL_DIR / "node_modules" / ".bin" / "diff-so-fancy"
DEFAULT_OUT_DIR = Path("/tmp/log/claude")

DIM = "\x1b[2m"
UNDIM = "\x1b[22m"
FG = "\x1b[39m"
# Dark-theme colors lifted from the CLI's theme table.
SUCCESS = "\x1b[38;2;78;186;101m"
ERROR = "\x1b[38;2;255;107;128m"

RESULT_LINES_SHOWN = 4
DIFF_LINES_SHOWN = 20


def project_dir(cwd: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return Path.home() / ".claude" / "projects" / slug


def latest_transcript(cwd: Path) -> Path:
    pdir = project_dir(cwd)
    files = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no transcript found under {pdir}")
    return files[-1]


def result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        text = ""
    # Control characters (binary output) break the ANSI-to-HTML parser.
    return re.sub(r"[\x00-\x06\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]", "", text)


def turns(transcript: Path) -> list[list[dict]]:
    """Split the transcript into finished turns of display entries.

    Entries: {"text": md} | {"tool", "input", "id"} |
    {"result", "error", "meta", "for"}. The trailing unfinished turn is
    dropped.
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
            if is_prompt:
                if current:
                    finished.append(current)
                    current = []
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        current.append(
                            {
                                "result": result_text(block),
                                "error": bool(block.get("is_error")),
                                "meta": obj.get("toolUseResult"),
                                "for": block.get("tool_use_id"),
                            }
                        )
        elif kind == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text", "").strip():
                    current.append({"text": block["text"]})
                elif block.get("type") == "tool_use":
                    current.append(
                        {
                            "tool": block.get("name", "?"),
                            "input": block.get("input") or {},
                            "id": block.get("id"),
                        }
                    )
    return [t for t in finished if any("text" in e or "tool" in e for e in t)]


# The CLI shows Edit as "Update".
TOOL_LABELS = {"Edit": "Update", "NotebookEdit": "Update"}


def tool_arg(name: str, inp: dict) -> str:
    """The one argument the CLI shows in the Tool(...) header line."""
    if name == "Bash":
        return (inp.get("command") or "").strip().splitlines()[0][:120] if inp.get("command") else ""
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        return inp.get("file_path", "")
    if name in ("Grep", "Glob"):
        return inp.get("pattern", "")
    if name in ("Task", "Agent"):
        return inp.get("description", "")
    if name == "Skill":
        return inp.get("skill", "")
    if name == "WebFetch":
        return inp.get("url", "")
    if name == "WebSearch":
        return inp.get("query", "")
    if name == "TodoWrite":
        todos = inp.get("todos") or []
        return f"{len(todos)} todos"
    if name == "SendUserFile":
        return ", ".join(inp.get("files") or [])
    for value in inp.values():
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0][:120]
    return ""


def render_markdown(markdown: str, width: int) -> str:
    env = dict(os.environ, FORCE_COLOR="3")
    result = subprocess.run(
        ["node", str(RENDER_MJS), "--width", str(width), "--ansi"],
        input=markdown,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        sys.exit(f"render.mjs failed: {result.stderr.strip()}")
    return result.stdout.rstrip("\n")


def ansi_to_html(ansi: str, width: int) -> str:
    env = dict(os.environ, FORCE_COLOR="3")
    result = subprocess.run(
        ["node", str(RENDER_MJS), "--width", str(width), "--from-ansi"],
        input=ansi,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        sys.exit(f"render.mjs failed: {result.stderr.strip()}")
    return result.stdout


def connect(lines: list[str]) -> str:
    """Join result lines under the CLI's dim "⎿" connector."""
    out = [f"  {DIM}⎿ {UNDIM} {lines[0]}"]
    out.extend(f"     {line}" for line in lines[1:])
    return "\n".join(out)


def collapse(lines: list[str], limit: int, full: bool) -> list[str]:
    if full or len(lines) <= limit:
        return lines
    hidden = len(lines) - limit
    note = f"{DIM}… +{hidden} line{'s' if hidden != 1 else ''} (ctrl+o to expand){UNDIM}"
    return lines[:limit] + [note]


def unified_diff(meta: dict) -> str:
    """Rebuild a unified diff from the transcript's structuredPatch."""
    path = meta.get("filePath", "")
    old = "/dev/null" if meta.get("type") == "create" else f"a/{path}"
    lines = [f"--- {old}", f"+++ b/{path}"]
    for hunk in meta["structuredPatch"]:
        lines.append(
            f"@@ -{hunk['oldStart']},{hunk['oldLines']} +{hunk['newStart']},{hunk['newLines']} @@"
        )
        lines.extend(hunk.get("lines", []))
    return "\n".join(lines) + "\n"


def fancy_diff(meta: dict, full: bool) -> list[str]:
    diff = unified_diff(meta)
    try:
        result = subprocess.run([str(DSF)], input=diff, capture_output=True, text=True)
        fancy = result.stdout if result.returncode == 0 and result.stdout.strip() else None
    except OSError:
        fancy = None
    lines = (fancy or diff).rstrip("\n").splitlines()
    return collapse(lines, DIFF_LINES_SHOWN, full)


def format_result(entry: dict, tool: dict | None, full: bool) -> str:
    name = (tool or {}).get("tool", "")
    meta = entry.get("meta")

    if isinstance(meta, dict) and meta.get("structuredPatch") and name in ("Edit", "NotebookEdit", "Write"):
        return connect(fancy_diff(meta, full))
    if name == "Read" and isinstance(meta, dict) and isinstance(meta.get("file"), dict):
        n = meta["file"].get("numLines") or len(str(meta["file"].get("content", "")).splitlines())
        return connect([f"Read {n} line{'s' if n != 1 else ''} {DIM}(ctrl+o to expand){UNDIM}"])
    if name == "Write" and isinstance(meta, dict) and meta.get("type") == "create":
        n = len(str(meta.get("content", "")).splitlines())
        return connect([f"Wrote {n} line{'s' if n != 1 else ''} to {meta.get('filePath', '')}"])
    if name == "TodoWrite" and isinstance(meta, dict) and meta.get("newTodos"):
        items = []
        for todo in meta["newTodos"]:
            if todo.get("status") == "completed":
                items.append(f"{SUCCESS}☒{FG} \x1b[9m{todo.get('content', '')}\x1b[29m")
            else:
                items.append(f"☐ {todo.get('content', '')}")
        return connect(collapse(items, RESULT_LINES_SHOWN, full))

    text = entry["result"].strip("\n") or "(no content)"
    lines = text.splitlines() or ["(no content)"]
    if entry["error"]:
        lines = [f"{ERROR}{line}{FG}" for line in lines]
    return connect(collapse(lines, RESULT_LINES_SHOWN, full))


def format_turn(turn: list[dict], width: int, full: bool) -> str:
    tools_by_id = {e["id"]: e for e in turn if "tool" in e and e.get("id")}
    parts: list[str] = []
    for entry in turn:
        if "text" in entry:
            parts.append(render_markdown(entry["text"], width))
        elif "tool" in entry:
            label = TOOL_LABELS.get(entry["tool"], entry["tool"])
            arg = tool_arg(entry["tool"], entry["input"])
            head = f"{SUCCESS}●{FG} {label}({arg})" if arg else f"{SUCCESS}●{FG} {label}"
            parts.append(head)
        elif "result" in entry:
            block = format_result(entry, tools_by_id.get(entry.get("for")), full)
            if parts and parts[-1].startswith(f"{SUCCESS}●"):
                parts[-1] = parts[-1] + "\n" + block
            else:
                parts.append(block)
    return "\n\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(prog="save-all", description=__doc__)
    parser.add_argument("out", nargs="?", default=None)
    parser.add_argument("-n", type=int, default=1)
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--ansi", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--full-results", action="store_true")
    args = parser.parse_args()

    transcript = latest_transcript(Path.cwd())
    all_turns = turns(transcript)
    if args.list:
        for i, turn in enumerate(reversed(all_turns), 1):
            texts = [e["text"] for e in turn if "text" in e]
            tools = sum(1 for e in turn if "tool" in e)
            head = texts[0].strip().splitlines()[0][:70] if texts else "(no text)"
            print(f"-n {i}: {tools:>3} tool call(s)  {head}")
        return 0

    if args.n < 1 or args.n > len(all_turns):
        sys.exit(f"turn -n {args.n} not found ({len(all_turns)} available)")
    ansi = format_turn(all_turns[-args.n], args.width, args.full_results)

    if args.raw:
        output = re.sub(r"\x1b\[[0-9;]*m|\x1b\]8;;.*?\x07", "", ansi) + "\n"
        suffix = ".txt"
    elif args.ansi:
        output = ansi + "\n"
        suffix = ".ansi"
    else:
        output = ansi_to_html(ansi, args.width)
        suffix = ".html"

    if args.stdout:
        sys.stdout.write(output)
        return 0

    if args.out:
        out = Path(args.out).expanduser()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = DEFAULT_OUT_DIR / f"claude-all-{stamp}{suffix}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
