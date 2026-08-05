---
name: save-all
description: Save one complete Claude turn — every text message, tool call, and collapsed tool result, exactly as the CLI showed it — as an HTML file. Use when the user asks to save/export the whole response or turn, not just the final reply.
argument-hint: "[out.html] [-n N] [--full-results]"
---

Run the script — do not rewrite or regenerate anything yourself; it copies
the turn verbatim from the session transcript and renders it with the CLI's
own renderer:

```bash
python3 ~/.claude/skills/save-all/save_all.py $ARGUMENTS
```

- No argument: writes `/tmp/log/claude/claude-all-<timestamp>.html`.
- An argument like `/tmp/log/claude/file.html` is the output path.
- `-n N` picks the Nth turn from the end (default: the previous one).
- `--full-results` keeps whole tool outputs instead of the CLI's 4-line collapse.
- `--raw` saves plain text, `--ansi` saves ANSI, `--list` shows saveable turns.

The script prints the saved file path. Report that path back, one line.
If it exits non-zero, show its stderr as-is.
