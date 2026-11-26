"""context-diet command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .scan import analyze, mcp_servers
from .tokens import method


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        home = Path.home()
        try:
            return "~" + os.sep + str(p.relative_to(home))
        except ValueError:
            return str(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="context-diet", description="Audit the AI instruction files "
                                 "(CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules...) that are re-sent on every message.")
    ap.add_argument("path", nargs="?", default=".", help="project root (default: current directory)")
    ap.add_argument("--no-global", action="store_true", help="skip ~/.claude, ~/.codex, ~/.gemini files")
    ap.add_argument("--max-tokens", type=int, default=2000, help="per-file token budget (default 2000)")
    ap.add_argument("--messages", type=int, default=100, help="messages per day for the cost projection (default 100)")
    ap.add_argument("--fail-over", type=int, metavar="TOKENS",
                    help="exit 1 if the total always-loaded tokens exceed TOKENS (for CI)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-q", "--quiet", action="store_true", help="only the summary table")
    ap.add_argument("--version", action="version", version=f"context-diet {__version__}")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = Path(a.path).resolve()
    reports = analyze(root, include_global=not a.no_global, max_tokens=a.max_tokens)
    total = sum(r.tokens for r in reports if "nested" not in r.tool)
    mcp = mcp_servers(root, Path.home())

    if a.json:
        print(json.dumps({"root": str(root), "estimator": method(), "always_loaded_tokens": total,
                          "files": [r.as_dict() for r in reports], "mcp_servers": mcp}, indent=2))
    else:
        if not reports:
            print("No AI instruction files found. 🎉 Nothing to trim.")
        else:
            w = max(len(_rel(r.path, root)) for r in reports)
            w = min(max(w, 10), 60)
            print(f"{'file':<{w}}  {'tool':<28}{'lines':>6}{'tokens':>8}  issues")
            print("─" * (w + 52))
            for r in sorted(reports, key=lambda r: -r.tokens):
                print(f"{_rel(r.path, root)[:w]:<{w}}  {r.tool[:27]:<28}{r.lines:>6}{r.tokens:>8}  {len(r.findings)}")
            print("─" * (w + 52))
            print(f"{'always loaded (excl. nested)':<{w + 34}}{total:>8}")
            per_day = total * a.messages
            print(f"\n≈ {total:,} tokens re-sent with every message → ≈ {per_day:,} tokens/day at "
                  f"{a.messages} messages/day (before prompt caching).")
            print(f"Estimator: {method()}.")
            if not a.quiet:
                for r in sorted(reports, key=lambda r: -r.tokens):
                    if not r.findings:
                        continue
                    print(f"\n{_rel(r.path, root)}")
                    for f in r.findings:
                        loc = f":{f.line}" if f.line else ""
                        cost = f"  (~{f.tokens} tok)" if f.tokens else ""
                        print(f"  [{f.rule}]{loc} {f.message}{cost}")
        if mcp:
            n = sum(len(v) for v in mcp.values())
            print(f"\nMCP servers configured: {n}. Their tool definitions are also sent with every message —"
                  " measure them with `mcp-token-audit` (github.com/mohammed-saray/mcp-token-audit).")
            for src, names in mcp.items():
                print(f"  {_rel(Path(src), root)}: {', '.join(names[:12])}{' …' if len(names) > 12 else ''}")
    if a.fail_over is not None and total > a.fail_over:
        print(f"\nFAIL: {total} always-loaded tokens > budget {a.fail_over}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
