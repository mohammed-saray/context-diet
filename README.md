# context-diet 🥗

**Your `CLAUDE.md` is re-sent with every message. So is `AGENTS.md`, `GEMINI.md` and `.cursorrules`. context-diet shows you what that costs and what to cut.**

[![CI](https://github.com/mohammed-saray/context-diet/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammed-saray/context-diet/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

```text
$ context-diet
file                       tool                         lines  tokens  issues
──────────────────────────────────────────────────────────────────────────────
CLAUDE.md                  Claude Code                    412    6870  6
docs/architecture.md       Claude Code via @import        188    2950  2
AGENTS.md                  Codex / Copilot / Cursor / …    96    1410  1
~/.claude/CLAUDE.md        Claude Code (global)            11     221  0
──────────────────────────────────────────────────────────────────────────────
always loaded (excl. nested)                                    11451

≈ 11,451 tokens re-sent with every message → ≈ 1,145,100 tokens/day at 100 messages/day (before prompt caching).

CLAUDE.md
  [file-too-big] 6870 tokens on every message (target ≤ 2000). Move reference material into docs or skills that load on demand.
  [history-section]:212 section 'Session log' looks like a log/status — the agent does not need history on every turn; keep it in git or CHANGELOG.md.  (~1940 tok)
  [long-code-block]:88 61-line code block — reference the real file path instead.  (~710 tok)
  [big-table]:140 24-row table — big tables are expensive; consider a linked file.
  [cross-file-duplicate] paragraph also in AGENTS.md — you pay for it twice.  (~95 tok)

MCP servers configured: 9. Their tool definitions are also sent with every message — measure them with `mcp-token-audit`.
```

## The problem

Instruction files grow. A few rules become architecture notes, session logs, pasted
API docs and "IMPORTANT!!" reminders. Every one of those tokens goes out with
**every** message, and that's a big reason people hit their Claude Code / Codex /
Gemini CLI limits sooner than expected. Users report single files costing 5–20K
tokens per turn, and MCP tool schemas add even more.

`context-diet` finds those files, follows Claude Code's `@imports`, estimates their
token cost and points at the parts that don't need to be there on every turn.

## Install

```bash
pipx install git+https://github.com/mohammed-saray/context-diet
```

Optional: `pip install tiktoken` for a closer token count. Without it, a script-aware heuristic is used that handles Latin, Arabic, Cyrillic and CJK.

## Usage

```bash
context-diet                    # current project + your global files
context-diet path/to/repo
context-diet --no-global        # only the project
context-diet --max-tokens 1500  # stricter per-file budget
context-diet --messages 300     # project cost for your daily volume
context-diet --json             # machine-readable
context-diet --fail-over 4000   # exit 1 in CI if the always-loaded total grows past 4000 tokens
```

### Keep it lean in CI

```yaml
- run: pipx run --spec git+https://github.com/mohammed-saray/context-diet context-diet --no-global --fail-over 4000
```

## What it scans

| File | Loaded by |
|---|---|
| `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, `~/.claude/CLAUDE.md` + every `@import` | Claude Code |
| `AGENTS.md`, `AGENTS.override.md`, `~/.codex/AGENTS.md` | Codex CLI, Copilot, Cursor, Jules… |
| `GEMINI.md`, `.gemini/GEMINI.md`, `~/.gemini/GEMINI.md` | Gemini CLI |
| `.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md` | Cursor, Windsurf, Cline, Copilot |
| `.mcp.json`, `~/.claude.json`, `~/.codex/config.toml`, `.gemini/settings.json` | MCP servers (listed, not measured) |

Nested files (for example `packages/api/AGENTS.md`) are listed. They aren't counted in the always-loaded total because they only load when the agent works in that folder.

## Rules

| Rule | Why it matters |
|---|---|
| `file-too-big` | over the per-file token budget |
| `too-many-lines` | over 200 lines, a common guideline for instruction files |
| `big-section` | one section over 600 tokens, usually reference docs that should be linked instead |
| `history-section` | changelog / status / session-log sections the model doesn't need on every turn |
| `long-code-block` | big pasted code; point to the real file instead |
| `big-table` | tables over 15 rows |
| `duplicate-line` / `cross-file-duplicate` | the same text paid for twice |
| `dated-entries` | journal-style dated bullet lists |
| `many-urls` | lots of links, ~10–20 tokens each |
| `shouting` | lots of IMPORTANT/MUST/NEVER; it costs tokens and the emphasis cancels itself out |

## Limitations

- Token counts are **estimates**. Each vendor uses its own tokenizer.
- Prompt caching lowers the *price* of repeated context, but cached tokens still take up context window space and count toward many subscription limits.
- It doesn't rewrite your files. You decide what to move.

## Roadmap

- [ ] `--fix` mode that moves flagged sections into `docs/` and leaves a link
- [ ] Measure `.claude/skills` and slash-command descriptions
- [ ] Pre-commit hook

## Related tools in this suite

Small, dependency-free tools for people fighting AI usage limits:

| Tool | What it does |
|---|---|
| [burnrate](https://github.com/mohammed-saray/burnrate) | Forecast Claude Code / Codex limits from local logs |
| **context-diet** | Find the CLAUDE.md / AGENTS.md / GEMINI.md bloat you pay for on every message |
| [ai-handoff](https://github.com/mohammed-saray/ai-handoff) | Hit a limit? Move the task to another AI with a handoff file |
| [ai-error-decoder](https://github.com/mohammed-saray/ai-error-decoder) | Explain 429 / 529 / quota errors from Anthropic, OpenAI and Gemini |
| [ratelimit-retry](https://github.com/mohammed-saray/ratelimit-retry) | Retry that respects provider rate-limit headers (JS) |
| [chat-export-md](https://github.com/mohammed-saray/chat-export-md) | ChatGPT / Claude / Gemini exports → Markdown |
| [mcp-token-audit](https://github.com/mohammed-saray/mcp-token-audit) | Measure how many tokens each MCP server's tools cost |
| [logslim](https://github.com/mohammed-saray/logslim) | Shrink logs and stack traces before pasting them into a chat |
| [chunkwise](https://github.com/mohammed-saray/chunkwise) | Split big files into token-budgeted chunks with continuation prompts |
| [ai-reset-clock](https://github.com/mohammed-saray/ai-reset-clock) | When does my quota reset? A countdown in your timezone |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
