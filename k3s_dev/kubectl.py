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


def exists(kind: str, name: str, namespace: str) -> bool:
    """Return True if the k8s resource exists in the cluster."""
    r = subprocess.run(
        ["kubectl", "get", kind, name, "-n", namespace],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0
