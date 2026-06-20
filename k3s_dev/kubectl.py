"""Thin wrapper around kubectl subprocess calls."""
from __future__ import annotations

import subprocess


def run(
    args: list[str],
    *,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["kubectl"] + args,
        capture_output=capture,
        text=True,
        check=check,
    )


def apply(manifest: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        capture_output=True,
        check=True,
    )
