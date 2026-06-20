"""Kubernetes namespace management."""
from __future__ import annotations

from k3s_dev import kubectl


def manifest(name: str) -> str:
    return f"""\
apiVersion: v1
kind: Namespace
metadata:
  name: {name}
"""


def create(name: str) -> None:
    kubectl.apply(manifest(name))


def remove(name: str) -> None:
    kubectl.run(["delete", "namespace", name, "--ignore-not-found"], check=False)
