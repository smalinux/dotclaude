---
name: save-summary
description: Save the previous Claude reply as an HTML file that looks exactly like the CLI output (colors, tables, code highlighting). Use when the user asks to save/export the last summary or reply to a file.
argument-hint: "[out.html] [-n N] [--turn] [--raw]"
---

Run the script — do not rewrite or regenerate the reply yourself; it copies
the markdown verbatim from the session transcript and renders it with the
CLI's own renderer:

```bash
python3 ~/.claude/skills/save-summary/save_summary.py $ARGUMENTS
```

- No argument: writes `/tmp/log/claude/claude-summary-<timestamp>.html`.
- An argument like `/tmp/log/claude/file.html` is the output path.
- `-n N` picks the Nth reply from the end (default: the previous one).
- `--turn` saves the whole turn, `--raw` saves markdown, `--ansi` saves ANSI.
- `--list` shows what can be saved.

The script prints the saved file path. Report that path back, one line.
If it exits non-zero, show its stderr as-is.
