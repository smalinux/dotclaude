#!/usr/bin/env node
// Port of Claude Code's internal markdown->ANSI token renderer (function `A4`
// in the bundled CLI, v2.1.209), using the same libraries the CLI bundles:
// marked (lexer), chalk (styling), cli-highlight (hljs code blocks),
// string-width / wrap-ansi (table layout). ANSI -> HTML via ansi_up.
//
// stdin:  markdown
// stdout: HTML document (default) or raw ANSI with --ansi
// flags:  --width N   layout width for tables (default 100)
//         --ansi      emit ANSI instead of HTML
//         --no-marker do not prefix the message with the CLI's "●" marker

import { marked } from "marked";
import { Chalk } from "chalk";
import cliHighlight from "cli-highlight";
import stringWidth from "string-width";
import wrapAnsi from "wrap-ansi";
import stripAnsi from "strip-ansi";
import { AnsiUp } from "ansi_up";

const chalk = new Chalk({ level: 3 });
const { highlight, supportsLanguage } = cliHighlight;

const NL = "\n";
const BLOCKQUOTE_BAR = "▎"; // dim vertical bar, as in the CLI
// Default dark theme colors lifted from the CLI's theme table.
const THEME = {
  permission: [87, 105, 247], // inline code
};
const OSC_OPEN = "\x1B]8;;";
const OSC_CLOSE = "\x07";

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const opt = (name, dflt) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : dflt;
};
const WIDTH = parseInt(opt("--width", "100"), 10) || 100;

// --- list numbering (CLI: numbers, then letters, then roman) ---------------

function letters(n) {
  let t = "";
  while (n > 0) {
    n--;
    t = String.fromCharCode(97 + (n % 26)) + t;
    n = Math.floor(n / 26);
  }
  return t;
}

const ROMAN = [[1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"], [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]];

function roman(n) {
  let t = "";
  for (const [v, s] of ROMAN) while (n >= v) { t += s; n -= v; }
  return t;
}

function listNumber(depth, n) {
  switch (depth) {
    case 0:
    case 1:
      return String(n);
    case 2:
      return letters(n);
    case 3:
      return roman(n);
    default:
      return String(n);
  }
}

// CLI glues "12." after a space with nbsp so numbers don't orphan-wrap.
function glue(s) {
  return s.replace(/ (\d{1,9}[.)])(?!\w)/g, "\xA0$1");
}

function hyperlink(href, text) {
  return OSC_OPEN + href + OSC_CLOSE + chalk.blueBright(text) + OSC_OPEN + OSC_CLOSE;
}

// --- the A4 port ------------------------------------------------------------

function render(token, ctx = {}) {
  const { listDepth = 0, orderedListNumber = null, parent = null, glueProse = false } = ctx;
  const kids = (tokens, over = {}) =>
    (tokens ?? []).map((t) => render(t, { listDepth: 0, orderedListNumber: null, parent: null, ...over })).join("");

  switch (token.type) {
    case "blockquote": {
      const body = kids(token.tokens);
      const bar = chalk.dim(BLOCKQUOTE_BAR);
      return body
        .split(NL)
        .map((line) => (stripAnsi(line).trim() ? `${bar} ${chalk.italic(line)}` : line))
        .join(NL);
    }
    case "code": {
      const lang = token.lang ?? "";
      const base = lang.match(/^[\w.+#-]+/)?.[0] ?? "";
      const pick = lang && supportsLanguage(lang) ? lang : base && supportsLanguage(base) ? base : "plaintext";
      const label = lang && !supportsLanguage(lang) ? chalk.dim(lang) + NL : "";
      try {
        return label + highlight(token.text, { language: pick }) + NL;
      } catch {
        return label + token.text + NL;
      }
    }
    case "codespan":
      return chalk.rgb(...THEME.permission)(token.text);
    case "em":
      return chalk.italic(kids(token.tokens, { parent, glueProse }));
    case "strong":
      return chalk.bold(kids(token.tokens, { parent, glueProse }));
    case "del":
      return chalk.strikethrough(kids(token.tokens, { parent, glueProse }));
    case "heading": {
      const body = kids(token.tokens);
      const style = token.depth === 1 ? chalk.bold.italic.underline : chalk.bold;
      return style(body) + NL + NL;
    }
    case "hr":
      return "---";
    case "image": {
      if (!token.text && !token.title) return token.href;
      const alt = token.text ? `${token.text} ` : "";
      const title = token.title ? ` "${token.title}"` : "";
      return `${alt}(${token.href}${title})`;
    }
    case "link": {
      const title = token.title ? ` ("${token.title}")` : "";
      if (token.href.startsWith("mailto:")) {
        const addr = token.href.replace(/^mailto:/, "");
        return (token.text && token.text !== addr ? `${token.text} (${addr})` : addr) + title;
      }
      const body = kids(token.tokens, { parent: token }) || token.href;
      return hyperlink(token.href, body) + title;
    }
    case "list":
      return token.items
        .map((item, i) =>
          render(item, {
            listDepth,
            orderedListNumber: token.ordered ? token.start + i : null,
            parent: token,
          })
        )
        .join("");
    case "list_item":
      return (token.tokens ?? [])
        .filter((child) => child.type !== "checkbox")
        .map((child) => {
          const body = render(child, { listDepth: listDepth + 1, orderedListNumber, parent: token });
          if (["code", "blockquote", "hr", "table"].includes(child.type)) return body;
          return "  ".repeat(listDepth) + body;
        })
        .join("");
    case "paragraph":
      return kids(token.tokens) + NL;
    case "space":
      return NL;
    case "br":
      return NL;
    case "text": {
      if (parent?.type === "link") return token.text;
      if (parent?.type === "list_item") {
        const body = token.tokens
          ? glue((token.tokens ?? []).map((t) => render(t, { listDepth, orderedListNumber, parent: token, glueProse: true })).join(""))
          : glue(token.text);
        const marker = orderedListNumber === null ? "-" : `${listNumber(listDepth, orderedListNumber)}.`;
        const first = parent.tokens?.filter((t) => t.type !== "checkbox")[0] === token;
        const task = parent.task && first ? `[${parent.checked ? "x" : " "}] ` : "";
        return `${marker} ${task}${body}${NL}`;
      }
      return glueProse ? glue(token.text) : token.text;
    }
    case "table":
      return renderTable(token) + NL;
    case "escape":
    case "html":
      return token.text;
    case "def":
      return "";
  }
  return token.raw ?? "";
}

// --- tables (port of the CLI's boxed-table layout) --------------------------

const MIN_COL = 3;
const MAX_ROWS = 200;
const MAX_CELL_LINES = 4;

function wrapCell(text, width, hard) {
  if (width <= 0) return [text];
  const lines = wrapAnsi(text.trimEnd(), width, { hard: hard ?? false, trim: false, wordWrap: true })
    .split(NL)
    .filter((l) => l.length > 0);
  return lines.length > 0 ? lines : [""];
}

function pad(text, textWidth, width, align) {
  const extra = Math.max(0, width - textWidth);
  if (align === "center") {
    const left = Math.floor(extra / 2);
    return " ".repeat(left) + text + " ".repeat(extra - left);
  }
  if (align === "right") return " ".repeat(extra) + text;
  return text + " ".repeat(extra);
}

function renderTable(token) {
  const hidden = Math.max(0, token.rows.length - MAX_ROWS);
  const rows = hidden > 0 ? token.rows.slice(0, MAX_ROWS) : token.rows;
  const cache = new Map();
  const cell = (tokens) => {
    if (cache.has(tokens)) return cache.get(tokens);
    const out = (tokens ?? []).map((t) => render(t, {})).join("");
    cache.set(tokens, out);
    return out;
  };
  const plain = (tokens) => stripAnsi(cell(tokens));
  const moreNote = (n) => `… ${n.toLocaleString()} more row${n === 1 ? "" : "s"} not shown`;

  const wordWidth = (tokens) => {
    const words = plain(tokens).split(/\s+/).filter((w) => w.length > 0);
    if (words.length === 0) return MIN_COL;
    return Math.max(...words.map((w) => stringWidth(w)), MIN_COL);
  };
  const fullWidth = (tokens) => Math.max(stringWidth(plain(tokens)), MIN_COL);

  const cols = token.header.length;
  const minWidths = token.header.map((h, i) => {
    let w = wordWidth(h.tokens);
    for (const r of rows) w = Math.max(w, wordWidth(r[i]?.tokens));
    return w;
  });
  const natWidths = token.header.map((h, i) => {
    let w = fullWidth(h.tokens);
    for (const r of rows) w = Math.max(w, fullWidth(r[i]?.tokens));
    return w;
  });

  const chrome = 1 + cols * 3;
  const budget = Math.max(WIDTH - chrome - 4, cols * MIN_COL);
  const natSum = natWidths.reduce((a, b) => a + b, 0);
  const minSum = minWidths.reduce((a, b) => a + b, 0);
  let hard = false;
  let widths;
  if (natSum <= budget) widths = natWidths;
  else if (minSum <= budget) {
    const spare = budget - minSum;
    const gaps = natWidths.map((w, i) => w - minWidths[i]);
    const gapSum = gaps.reduce((a, b) => a + b, 0);
    widths = minWidths.map((w, i) => (gapSum === 0 ? w : w + Math.floor((gaps[i] / gapSum) * spare)));
  } else {
    hard = true;
    const scale = budget / minSum;
    widths = minWidths.map((w) => Math.max(Math.floor(w * scale), MIN_COL));
  }

  let tallest = 1;
  for (let i = 0; i < cols; i++) tallest = Math.max(tallest, wrapCell(cell(token.header[i].tokens), widths[i], hard).length);
  for (const r of rows)
    for (let i = 0; i < r.length; i++) tallest = Math.max(tallest, wrapCell(cell(r[i]?.tokens), widths[i], hard).length);

  if (tallest > MAX_CELL_LINES) return verticalTable(token, rows, hidden, plain, cell);

  const border = (kind) => {
    const [l, m, x, r] = { top: ["┌", "─", "┬", "┐"], middle: ["├", "─", "┼", "┤"], bottom: ["└", "─", "┴", "┘"] }[kind];
    let line = l;
    widths.forEach((w, i) => {
      line += m.repeat(w + 2) + (i < widths.length - 1 ? x : r);
    });
    return line;
  };

  const rowLines = (cells, isHeader) => {
    const wrapped = cells.map((c, i) => wrapCell(cell(c.tokens), widths[i], hard));
    const height = Math.max(...wrapped.map((w) => w.length), 1);
    const offsets = wrapped.map((w) => Math.floor((height - w.length) / 2));
    const out = [];
    for (let y = 0; y < height; y++) {
      let line = "│";
      for (let i = 0; i < cells.length; i++) {
        const rel = y - offsets[i];
        const text = rel >= 0 && rel < wrapped[i].length ? wrapped[i][rel] : "";
        const align = isHeader ? "center" : token.align?.[i] ?? "left";
        line += " " + pad(text, stringWidth(stripAnsi(text)), widths[i], align) + " │";
      }
      out.push(line);
    }
    return out;
  };

  const lines = [];
  lines.push(border("top"));
  lines.push(...rowLines(token.header, true));
  lines.push(border("middle"));
  rows.forEach((r, i) => {
    lines.push(...rowLines(r, false));
    if (i < rows.length - 1) lines.push(border("middle"));
  });
  lines.push(border("bottom"));

  let widest = 0;
  for (const l of lines) widest = Math.max(widest, stringWidth(stripAnsi(l)));
  if (widest > WIDTH - 4) return verticalTable(token, rows, hidden, plain, cell);

  if (hidden > 0) lines.push(moreNote(hidden));
  return lines.join(NL);
}

function verticalTable(token, rows, hidden, plain, cell) {
  const rule = "─".repeat(Math.min(WIDTH - 1, 40));
  const blocks = [];
  for (const r of rows) {
    const lines = [];
    r.forEach((c, i) => {
      const head = plain(token.header[i]?.tokens ?? []);
      const value = cell(c?.tokens).trimEnd().replace(/\n+/g, " ").replace(/\s+/g, " ").trim();
      if (!head && !value) return;
      lines.push(head ? `${chalk.bold(head)}: ${value}` : value);
    });
    if (lines.length) blocks.push(lines.join(NL));
  }
  if (hidden > 0) blocks.push(`… ${hidden.toLocaleString()} more row${hidden === 1 ? "" : "s"} not shown`);
  return blocks.join(NL + rule + NL);
}

// --- message assembly -------------------------------------------------------

function renderMessage(markdown) {
  const tokens = marked.lexer(markdown);
  let out = tokens.map((t) => render(t, {})).join("");
  out = out.replace(/\n{3,}/g, "\n\n").replace(/\n+$/, "");
  if (flag("--no-marker")) return out;
  const marker = "●";
  return out
    .split(NL)
    .map((line, i) => (i === 0 ? `${marker} ${line}` : line ? `  ${line}` : line))
    .join(NL);
}

// --- ANSI -> HTML (ansi_up does the styling; we only add the page shell) ----

function toHtml(ansi, title) {
  // ansi_up drops SGR 9/29 (strikethrough); tunnel it through private-use chars.
  const S_OPEN = "";
  const S_CLOSE = "";
  ansi = ansi.replace(/\x1B\[9m/g, S_OPEN).replace(/\x1B\[29m/g, S_CLOSE);
  const up = new AnsiUp();
  up.use_classes = false;
  const parts = [];
  const re = /\x1B\]8;;(.*?)\x07([\s\S]*?)\x1B\]8;;\x07/g;
  let last = 0;
  let m;
  while ((m = re.exec(ansi)) !== null) {
    parts.push(up.ansi_to_html(ansi.slice(last, m.index)));
    const href = m[1].replace(/"/g, "&quot;");
    parts.push(`<a href="${href}" style="color:inherit">` + up.ansi_to_html(m[2]) + "</a>");
    last = re.lastIndex;
  }
  parts.push(up.ansi_to_html(ansi.slice(last)));
  const body = parts
    .join("")
    .replaceAll(S_OPEN, '<span style="text-decoration:line-through">')
    .replaceAll(S_CLOSE, "</span>");
  return [
    "<!doctype html>",
    '<html><head><meta charset="utf-8">',
    `<title>${title.replace(/</g, "&lt;")}</title></head>`,
    '<body style="background:#1e1e1e;color:#d4d4d4">',
    '<pre style="font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;word-wrap:break-word;padding:1em">',
    body,
    "</pre></body></html>",
  ].join("\n");
}

// --- main -------------------------------------------------------------------

let markdown = "";
process.stdin.setEncoding("utf-8");
for await (const chunk of process.stdin) markdown += chunk;
markdown = markdown.trim();
if (!markdown) {
  console.error("render.mjs: empty input");
  process.exit(1);
}

const ansi = renderMessage(markdown);
if (flag("--ansi")) {
  process.stdout.write(ansi + NL);
} else {
  const title = stripAnsi(ansi).split(NL)[0].replace(/^● /, "").slice(0, 80) || "claude summary";
  process.stdout.write(toHtml(ansi, title));
}
