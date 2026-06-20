"""Pre-flight environment checks."""
from __future__ import annotations

import shutil
import subprocess

from rich.console import Console
from rich.panel import Panel

console = Console()


def preflight() -> bool:
    console.print(Panel("[bold]Pre-flight checks[/bold]", expand=False))
    ok = True

    if shutil.which("kubectl"):
        console.print("  [green]✓[/green] kubectl found")
    else:
        console.print("  [red]✗[/red] kubectl not found — install Rancher Desktop")
        ok = False

    if ok:
        r = subprocess.run(["kubectl", "cluster-info"], capture_output=True)
        if r.returncode == 0:
            console.print("  [green]✓[/green] cluster reachable")
        else:
            console.print("  [red]✗[/red] cluster not reachable — is Rancher Desktop running?")
            ok = False

    if shutil.which("kubeseal"):
        console.print("  [green]✓[/green] kubeseal found")
    else:
        console.print("  [yellow]![/yellow] kubeseal not found — install with: brew install kubeseal")

    return ok
