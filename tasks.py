"""Task runner for k3s-dev. Usage: uv run inv <task>"""

from __future__ import annotations

from invoke import task


@task
def install(c):
    c.run("uv sync --all-groups")


@task(name="lock-update")
def lock_update(c):
    c.run("uv export --no-dev --format requirements-txt --no-hashes > requirements.lock")
    c.run("sed -i '' '/^-e \\./d' requirements.lock")
    print("✓ requirements.lock updated")


@task
def test(c):
    c.run("uv run pytest -v")


@task
def build(c):
    c.run("bazelisk build //...")


@task
def run(c, args="--help"):
    c.run(f"uv run k3s-dev {args}", pty=True)


@task
def check(c):
    """Ruff lint + format check + pytest. Required gate before any release."""
    c.run("uv run ruff check .", echo=True)
    c.run("uv run ruff format --check .", echo=True)
    c.run("uv run pytest -x -q --tb=short", echo=True)


@task(name="project-check")
def project_check(c, path="."):
    """Run k3s-dev convention linter against a project directory (default: current)."""
    c.run(f"uv run k3s-dev project check {path}")
