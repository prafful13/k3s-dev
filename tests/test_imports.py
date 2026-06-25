"""Smoke tests: all k3s-dev modules import cleanly."""

from __future__ import annotations


def test_cli_imports():
    from k3s_dev import cli  # noqa: F401


def test_state_imports():
    from k3s_dev.state import PostgresInstance, State  # noqa: F401

    s = State()
    assert isinstance(s.postgres_instances, dict)


def test_postgres_module_imports():
    from k3s_dev import postgres  # noqa: F401


def test_project_check_imports():
    from k3s_dev import project  # noqa: F401
