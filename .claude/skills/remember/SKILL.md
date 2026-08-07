---
name: remember
description: Save the previous Claude reply as a markdown note in the second brain (/src/2brain/notes). Use when the user asks to remember something, save a note, or add a reply to their second brain.
argument-hint: "[title | out.md] [-n N] [--turn]"
---

The canonical script lives in the dotfiles repo at
`/src/dotclaude/.claude/skills/remember/remember.py`;
`~/.claude/skills/remember/remember.py` must resolve to it (currently the
whole `~/.claude/skills/remember` directory is a symlink into the repo). If
the link is missing, link it — but never symlink the repo file onto itself:

```bash
canon=/src/dotclaude/.claude/skills/remember/remember.py
home=~/.claude/skills/remember/remember.py
[ "$(readlink -f "$home")" = "$canon" ] || ln -sf "$canon" "$home"
```

Then run the script — do not rewrite or regenerate the reply yourself; it
copies the markdown verbatim from the session transcript:

```bash
python3 ~/.claude/skills/remember/remember.py $ARGUMENTS
```

Naming follows /save-summary:

- No argument: `/src/2brain/notes/claude-note-<YYYYmmdd-HHMMSS>.md`.
- A single word containing `/` or ending in `.md` is the output path itself
  (relative names land in the notes dir).
- Any other words are the note title -> `notes/YYYY-MM-DD-<title-slug>.md`.
- `-n N` picks the Nth reply from the end (default: the previous one).
- `--turn` saves every text message of the turn, not only the final one.
- `--list` shows what can be saved.

The script prints the saved note path. Report that path back, one line, and
mention the note can be viewed in the browser with `2brain <name>`, with an
optional `--theme` from: gruvbox, tokyonight, catppuccin-mocha, nord,
onedark, dracula, kanagawa, everforest, rose-pine, solarized-dark.
If it exits non-zero, show its stderr as-is.
