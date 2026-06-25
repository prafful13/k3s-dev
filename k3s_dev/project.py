"""Convention linter for all-src projects."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

# Sections every CLAUDE.md must contain (case-insensitive heading match)
_REQUIRED_SECTIONS = [
    "Status",
    "Architecture",
    "Entry Points",
    "Key Files",
    "Gotchas",
    "Next Tasks",
]

# Standard invoke tasks every project's tasks.py must define
_REQUIRED_TASKS = ["install", "run", "lock-update"]

# Patterns that indicate an unpinned image tag
_LATEST_RE = re.compile(r"image:\s+\S+:latest\b|FROM\s+\S+:latest\b|FROM\s+\S+\s*$", re.MULTILINE)

# Stack divergence section heading in CLAUDE.md
_DIVERGENCE_HEADING = re.compile(r"^##\s+Stack Divergences", re.MULTILINE | re.IGNORECASE)


class Violation:
    def __init__(self, category: str, message: str, fixable: bool = False):
        self.category = category
        self.message = message
        self.fixable = fixable


def _read_claude_md(path: Path) -> str | None:
    f = path / "CLAUDE.md"
    return f.read_text() if f.exists() else None


def _has_divergence(claude_md: str, key: str) -> bool:
    """Return True if key appears in the Stack Divergences section."""
    m = _DIVERGENCE_HEADING.search(claude_md)
    if not m:
        return False
    after = claude_md[m.end():]
    next_h2 = re.search(r"^##\s", after, re.MULTILINE)
    divergence_block = after[: next_h2.start()] if next_h2 else after
    return key.lower() in divergence_block.lower()


def check(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    claude_md = _read_claude_md(path)

    # ── CLAUDE.md ──────────────────────────────────────────────────────────────
    if claude_md is None:
        violations.append(Violation("CLAUDE.md", "CLAUDE.md is missing — create it from the canonical schema in global CLAUDE.md §5.4"))
        return violations  # can't check sections without the file

    for section in _REQUIRED_SECTIONS:
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE | re.IGNORECASE)
        if not pattern.search(claude_md):
            violations.append(Violation("CLAUDE.md", f"Missing required section: ## {section}"))

    # ── pyproject.toml ─────────────────────────────────────────────────────────
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        violations.append(Violation("Python", "pyproject.toml missing — run: uv init"))
    else:
        content = pyproject.read_text()
        if "requires-python" not in content:
            violations.append(Violation("Python", "pyproject.toml has no requires-python — add requires-python = '>=3.13'"))
        if "uv" not in content and "hatchling" not in content and "setuptools" not in content:
            violations.append(Violation("Python", "pyproject.toml has no recognized build backend"))

    # ── tasks.py ───────────────────────────────────────────────────────────────
    tasks_py = path / "tasks.py"
    if not tasks_py.exists():
        if _has_divergence(claude_md, "Makefile") or _has_divergence(claude_md, "tasks.py"):
            pass  # declared divergence
        else:
            violations.append(Violation("Tasks", "tasks.py missing — create it with standard invoke tasks"))
    else:
        content = tasks_py.read_text()
        for task_name in _REQUIRED_TASKS:
            # match @task\ndef <name>( or name="<name>"
            if not re.search(rf'(def {re.escape(task_name)}\(|name="{re.escape(task_name)}")', content):
                violations.append(Violation("Tasks", f"tasks.py missing standard task: {task_name}"))

    # ── MODULE.bazel ───────────────────────────────────────────────────────────
    module_bazel = path / "MODULE.bazel"
    workspace = path / "WORKSPACE"
    if not module_bazel.exists():
        if _has_divergence(claude_md, "Bazel") or _has_divergence(claude_md, "MODULE.bazel"):
            pass  # declared divergence
        else:
            violations.append(Violation("Bazel", "MODULE.bazel missing — use Bzlmod, never legacy WORKSPACE"))
    if workspace.exists():
        violations.append(Violation("Bazel", "Legacy WORKSPACE file found — migrate to MODULE.bazel (Bzlmod)"))

    # ── from __future__ import annotations ────────────────────────────────────
    for py_file in path.rglob("*.py"):
        if any(part in (".venv", "__pycache__", ".git", "build", "dist") for part in py_file.parts):
            continue
        content = py_file.read_text(errors="replace")
        if "from __future__ import annotations" not in content:
            rel = py_file.relative_to(path)
            violations.append(Violation("Python", f"{rel}: missing 'from __future__ import annotations'", fixable=True))

    # ── unpinned image tags ───────────────────────────────────────────────────
    for dockerfile in path.glob("Dockerfile*"):
        content = dockerfile.read_text(errors="replace")
        if _LATEST_RE.search(content):
            violations.append(Violation("Docker", f"{dockerfile.name}: unpinned image tag (:latest or untagged FROM)"))

    for yaml_file in (path / "k8s").glob("**/*.yaml") if (path / "k8s").exists() else []:
        content = yaml_file.read_text(errors="replace")
        if re.search(r"image:\s+\S+:latest\b", content):
            rel = yaml_file.relative_to(path)
            violations.append(Violation("k8s", f"{rel}: unpinned image tag (:latest)"))

    return violations


def report(path: Path, violations: list[Violation]) -> int:
    """Print the check results. Returns exit code (0 = clean, 1 = violations)."""
    if not violations:
        console.print(f"[green]✓[/green] [bold]{path.name}[/bold] passes all convention checks")
        return 0

    table = Table(title=f"Convention violations: {path.name}", show_lines=True)
    table.add_column("Category", style="bold", width=12)
    table.add_column("Violation")
    table.add_column("Fix?", width=6)
    for v in violations:
        table.add_row(
            v.category,
            v.message,
            "[green]auto[/green]" if v.fixable else "[dim]manual[/dim]",
        )
    console.print(table)
    console.print(f"[red]{len(violations)} violation(s)[/red] in [bold]{path.name}[/bold]")
    return 1
