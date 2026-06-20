"""Bitnami Sealed Secrets controller management."""
from __future__ import annotations

import httpx
from rich.console import Console

from k3s_dev import kubectl

console = Console()

DEFAULT_VERSION = "v0.27.3"
_MANIFEST_URL = (
    "https://github.com/bitnami-labs/sealed-secrets/releases/download"
    "/{version}/controller.yaml"
)


def install(version: str = DEFAULT_VERSION) -> None:
    url = _MANIFEST_URL.format(version=version)
    console.print(f"Downloading Sealed Secrets {version}...")
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    kubectl.apply(resp.text)
    console.print(f"[green]Sealed Secrets {version} installed in kube-system[/green]")


def ready_replicas() -> int:
    r = kubectl.run(
        [
            "get", "deployment", "sealed-secrets-controller",
            "-n", "kube-system",
            "-o", "jsonpath={.status.readyReplicas}",
        ],
        capture=True,
        check=False,
    )
    val = r.stdout.strip()
    return int(val) if val.isdigit() else 0
