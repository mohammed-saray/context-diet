"""Discover AI instruction files and lint them for token bloat."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .tokens import estimate

# file name -> tool that loads it on every turn
PROJECT_FILES = {
    "CLAUDE.md": "Claude Code", "CLAUDE.local.md": "Claude Code", ".claude/CLAUDE.md": "Claude Code",
    "AGENTS.md": "Codex / Copilot / Cursor / Jules", "AGENTS.override.md": "Codex",
    "GEMINI.md": "Gemini CLI", ".gemini/GEMINI.md": "Gemini CLI",
    ".cursorrules": "Cursor", ".windsurfrules": "Windsurf", ".clinerules": "Cline",
    ".github/copilot-instructions.md": "GitHub Copilot",
}
GLOBAL_FILES = {
    ".claude/CLAUDE.md": "Claude Code (global)", ".codex/AGENTS.md": "Codex (global)",
    ".gemini/GEMINI.md": "Gemini CLI (global)",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target"}
IMPORT_RE = re.compile(r"(?<![\w`])@((?:~|\.{1,2})?/?[\w./\-]+\.(?:md|txt|markdown))")


@dataclass
class Finding:
    rule: str
    message: str
    line: int = 0
    tokens: int = 0


@dataclass
class FileReport:
    path: Path
    tool: str
    lines: int
    tokens: int
    imported_by: Optional[Path] = None
    findings: List[Finding] = field(default_factory=list)

    def as_dict(self):
        return {"path": str(self.path), "tool": self.tool, "lines": self.lines, "tokens": self.tokens,
                "imported_by": str(self.imported_by) if self.imported_by else None,
                "findings": [f.__dict__ for f in self.findings]}


def discover(root: Path, include_global: bool = True, home: Optional[Path] = None,
             max_depth: int = 6) -> Dict[Path, str]:
    found: Dict[Path, str] = {}
    root = root.resolve()
    for rel, tool in PROJECT_FILES.items():
        p = root / rel
        if p.is_file():
            found[p] = tool
    # nested instruction files (loaded when the agent works in that folder)
    names = {Path(k).name for k in PROJECT_FILES if "/" not in k}
    for p in _walk(root, max_depth):
        if p.name in names and p.resolve() not in found:
            found[p.resolve()] = PROJECT_FILES[p.name] + " (nested)"
    if include_global:
        home = home or Path.home()
        for rel, tool in GLOBAL_FILES.items():
            p = home / rel
            if p.is_file():
                found.setdefault(p.resolve(), tool)
    return found


def _walk(root: Path, depth: int, top: bool = True):
    """Yield files in sub-folders of root (not root itself), skipping vendored dirs."""
    if depth < 0:
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for e in entries:
        if e.is_dir():
            if e.name not in SKIP_DIRS and not e.name.startswith("."):
                yield from _walk(e, depth - 1, top=False)
        elif e.is_file() and not top:
            yield e


def resolve_imports(path: Path, text: str, home: Path) -> List[Path]:
    """Claude Code `@path/to/file.md` imports (skipping ones inside code)."""
    out = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in IMPORT_RE.finditer(re.sub(r"`[^`]*`", "", line)):
            ref = m.group(1)
            target = (home / ref[2:]) if ref.startswith("~/") else (path.parent / ref)
            if target.is_file():
                out.append(target.resolve())
    return out


# --------------------------------------------------------------------------- lint

def lint(text: str, *, max_tokens: int = 2000, max_lines: int = 200, max_code_lines: int = 25,
         max_section_tokens: int = 600) -> List[Finding]:
    f: List[Finding] = []
    lines = text.splitlines()
    total = estimate(text)
    if total > max_tokens:
        f.append(Finding("file-too-big", f"{total} tokens on every message (target ≤ {max_tokens}). "
                         "Move reference material into docs or skills that load on demand.", tokens=total))
    if len(lines) > max_lines:
        f.append(Finding("too-many-lines", f"{len(lines)} lines (target ≤ {max_lines})."))

    # sections
    sections = _sections(lines)
    for title, start, body in sections:
        t = estimate(body)
        if title and t > max_section_tokens:
            f.append(Finding("big-section", f"section '{title}' is {t} tokens — link to a file instead of inlining it.",
                             line=start + 1, tokens=t))
        if title and re.search(r"(change ?log|history|release notes|status|progress|done|completed|session log)",
                               title, re.I):
            f.append(Finding("history-section", f"section '{title}' looks like a log/status — the agent does not "
                             "need history on every turn; keep it in git or CHANGELOG.md.", line=start + 1, tokens=t))

    # code blocks
    in_code, start = False, 0
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            if not in_code:
                in_code, start = True, i
            else:
                in_code = False
                n = i - start - 1
                if n > max_code_lines:
                    block = "\n".join(lines[start + 1:i])
                    f.append(Finding("long-code-block", f"{n}-line code block — reference the real file path instead.",
                                     line=start + 1, tokens=estimate(block)))

    # tables
    run = 0
    for i, line in enumerate(lines + [""]):
        if line.lstrip().startswith("|"):
            run += 1
        else:
            if run > 15:
                f.append(Finding("big-table", f"{run}-row table — big tables are expensive; consider a linked file.",
                                 line=i - run + 1))
            run = 0

    # repeated lines
    seen: Dict[str, int] = {}
    for i, line in enumerate(lines):
        s = line.strip()
        if len(s) < 25 or s.startswith(("|", "```", "#", "---")):
            continue
        if s in seen:
            f.append(Finding("duplicate-line", f"repeats line {seen[s] + 1}.", line=i + 1, tokens=estimate(s)))
        else:
            seen[s] = i

    # dates + "TODO" noise
    dated = sum(1 for l in lines if re.match(r"\s*[-*]?\s*\[?\d{4}-\d{2}-\d{2}", l))
    if dated >= 5:
        f.append(Finding("dated-entries", f"{dated} dated entries — journals belong in git history, not instructions."))
    urls = re.findall(r"https?://\S+", text)
    if len(urls) > 15:
        f.append(Finding("many-urls", f"{len(urls)} URLs — each costs ~10–20 tokens per message."))
    if re.search(r"\b(always|never|must|important)\b", text, re.I) and \
            len(re.findall(r"\b(IMPORTANT|CRITICAL|MUST|NEVER|ALWAYS)\b", text)) > 12:
        f.append(Finding("shouting", "many ALL-CAPS emphasis words — they cost tokens and dilute each other."))
    return f


def _sections(lines):
    out, title, start, buf = [], "", 0, []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            out.append((title, start, "\n".join(buf)))
            title, start, buf = m.group(2).strip(), i, []
        else:
            buf.append(line)
    out.append((title, start, "\n".join(buf)))
    return out


def cross_duplicates(reports: List[FileReport], texts: Dict[Path, str]) -> None:
    """Flag paragraphs that appear in more than one loaded file."""
    owner: Dict[str, Path] = {}
    for r in reports:
        for para in re.split(r"\n\s*\n", texts[r.path]):
            p = para.strip()
            if len(p) < 80:
                continue
            if p in owner and owner[p] != r.path:
                r.findings.append(Finding("cross-file-duplicate",
                                          f"paragraph also in {owner[p].name} — you pay for it twice.",
                                          tokens=estimate(p)))
            else:
                owner.setdefault(p, r.path)


def mcp_servers(root: Path, home: Path) -> Dict[str, List[str]]:
    """List MCP servers configured for the project/user (their tool schemas also cost tokens)."""
    out: Dict[str, List[str]] = {}
    for p in (root / ".mcp.json", home / ".claude.json", root / ".gemini" / "settings.json",
              home / ".gemini" / "settings.json", root / ".cursor" / "mcp.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if isinstance(servers, dict) and servers:
            out[str(p)] = sorted(servers)
    codex = home / ".codex" / "config.toml"
    try:
        names = set()
        for raw in re.findall(r"^\s*\[mcp_servers\.([^\]]+)\]", codex.read_text(encoding="utf-8"), re.M):
            raw = raw.strip()
            m = re.match(r'"([^"]+)"', raw)
            names.add(m.group(1) if m else raw.split(".")[0])  # drop sub-tables like name.env
        if names:
            out[str(codex)] = sorted(names)
    except OSError:
        pass
    return out


def analyze(root: Path, include_global=True, home: Optional[Path] = None, **lint_opts):
    home = home or Path.home()
    files = discover(root, include_global, home)
    queue = list(files.items())
    reports: List[FileReport] = []
    texts: Dict[Path, str] = {}
    seen = set()
    parents: Dict[Path, Path] = {}
    while queue:
        path, tool = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        texts[path] = text
        r = FileReport(path, tool, len(text.splitlines()), estimate(text), parents.get(path))
        r.findings = lint(text, **lint_opts)
        reports.append(r)
        if tool.startswith("Claude"):
            for imp in resolve_imports(path, text, home):
                if imp not in seen:
                    parents[imp] = path
                    queue.append((imp, tool + " via @import"))
    cross_duplicates(reports, texts)
    return reports
