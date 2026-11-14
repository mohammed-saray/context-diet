import json
import tempfile
import unittest
from pathlib import Path

from context_diet.scan import analyze, discover, lint, mcp_servers, resolve_imports
from context_diet.tokens import estimate


class TokenTests(unittest.TestCase):
    def test_estimate_scripts(self):
        self.assertEqual(estimate(""), 0)
        latin = estimate("a" * 400, exact=False)
        arabic = estimate("ب" * 400, exact=False)
        cjk = estimate("中" * 300, exact=False)
        self.assertEqual(latin, 100)
        self.assertEqual(arabic, 160)
        self.assertEqual(cjk, 200)


class LintTests(unittest.TestCase):
    def rules(self, text, **kw):
        return {f.rule for f in lint(text, **kw)}

    def test_clean_file(self):
        self.assertEqual(self.rules("# Rules\n\n- Use pnpm.\n- Run tests before commits.\n"), set())

    def test_big_file_and_lines(self):
        text = "\n".join(f"- rule number {i} about something specific {i}" for i in range(300))
        r = self.rules(text, max_tokens=500)
        self.assertIn("file-too-big", r)
        self.assertIn("too-many-lines", r)

    def test_code_block_table_history_dupes(self):
        code = "```py\n" + "\n".join(f"x{i} = {i}" for i in range(40)) + "\n```\n"
        table = "\n".join(f"| a{i} | b |" for i in range(20))
        hist = "## Changelog\n- 2026-01-01 did a thing\n"
        dup = "Always run the full test suite before pushing.\n" * 2
        r = self.rules(code + table + "\n\n" + hist + dup)
        self.assertTrue({"long-code-block", "big-table", "history-section", "duplicate-line"} <= r)

    def test_dated_entries(self):
        text = "\n".join(f"- 2026-0{i}-01 shipped feature {i}" for i in range(1, 7))
        self.assertIn("dated-entries", self.rules(text))


class DiscoveryTests(unittest.TestCase):
    def test_discover_imports_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / "proj", Path(tmp) / "home"
            (root / "docs").mkdir(parents=True)
            (root / "pkg").mkdir()
            (home / ".claude").mkdir(parents=True)
            shared = ("This paragraph explains the deployment process in a lot of detail so that "
                      "it is long enough to count as a duplicate.")
            (root / "CLAUDE.md").write_text(f"# Project\nSee @docs/style.md\n\n{shared}\n", encoding="utf-8")
            (root / "AGENTS.md").write_text(f"# Agents\n\n{shared}\n", encoding="utf-8")
            (root / "docs" / "style.md").write_text("# Style\nUse tabs.\n", encoding="utf-8")
            (root / "pkg" / "AGENTS.md").write_text("nested rules\n", encoding="utf-8")
            (home / ".claude" / "CLAUDE.md").write_text("global rules\n", encoding="utf-8")
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"github": {}, "figma": {}}}),
                                            encoding="utf-8")

            found = discover(root, home=home)
            names = sorted(p.name for p in found)
            self.assertEqual(names, ["AGENTS.md", "AGENTS.md", "CLAUDE.md", "CLAUDE.md"])
            imports = resolve_imports(root / "CLAUDE.md", (root / "CLAUDE.md").read_text(), home)
            self.assertEqual([p.name for p in imports], ["style.md"])

            reports = analyze(root, home=home)
            by_name = {(r.path.parent.name, r.path.name): r for r in reports}
            self.assertIn(("docs", "style.md"), by_name)
            self.assertIn("@import", by_name[("docs", "style.md")].tool)
            rules = {f.rule for r in reports for f in r.findings}
            self.assertIn("cross-file-duplicate", rules)
            self.assertEqual(mcp_servers(root, home)[str(root / ".mcp.json")], ["figma", "github"])

    def test_cli_fail_over(self):
        from context_diet import cli
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "CLAUDE.md").write_text("word " * 2000, encoding="utf-8")
            self.assertEqual(cli.main([tmp, "--no-global", "--fail-over", "100", "-q"]), 1)
            self.assertEqual(cli.main([tmp, "--no-global", "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
