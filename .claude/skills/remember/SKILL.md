---
name: remember
description: Save the previous Claude reply as a markdown note in the second brain (/src/2brain/notes). Use when the user asks to remember something, save a note, or add a reply to their second brain.
argument-hint: "[title] [-n N] [--turn]"
---

Run the script — do not rewrite or regenerate the reply yourself; it copies
the markdown verbatim from the session transcript:

```bash
python3 ~/.claude/skills/remember/remember.py $ARGUMENTS
```

- No argument: the filename is derived from the reply's first line,
  e.g. `/src/2brain/notes/2026-08-07-<slug>.md`.
- Any non-flag words are used as the note title.
- `-n N` picks the Nth reply from the end (default: the previous one).
- `--turn` saves every text message of the turn, not only the final one.
- `--list` shows what can be saved.

The script prints the saved note path. Report that path back, one line, and
mention the note can be viewed in the browser with `2brain <name>`.
If it exits non-zero, show its stderr as-is.
