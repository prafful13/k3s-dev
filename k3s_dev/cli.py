"""k3s-dev CLI — local k3s dev environment bootstrapper for macOS."""
from __future__ import annotations

import subprocess
import time
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from k3s_dev import checks, launch_agent, namespace, sealed_secrets
from k3s_dev import postgres as pg
from k3s_dev import project as proj
from k3s_dev.state import PostgresInstance, State

console = Console()

app = typer.Typer(
    help="Local k3s dev environment bootstrapper for macOS",
    no_args_is_help=True,
)
ns_app = typer.Typer(help="Manage Kubernetes namespaces", no_args_is_help=True)
pg_app = typer.Typer(help="Manage Postgres instances", no_args_is_help=True)
ss_app = typer.Typer(help="Manage Sealed Secrets controller", no_args_is_help=True)
la_app = typer.Typer(help="Manage macOS LaunchAgents", no_args_is_help=True)
project_app = typer.Typer(help="Convention linter for all-src projects", no_args_is_help=True)

app.add_typer(ns_app, name="namespace")
app.add_typer(pg_app, name="postgres")
app.add_typer(ss_app, name="sealed-secrets")
app.add_typer(la_app, name="launch-agent")
app.add_typer(project_app, name="project")


# ── top-level ────────────────────────────────────────────────────────────────

@app.command()
def init(
    namespace_name: Annotated[str, typer.Option("--namespace", "-n")] = "dev",
    ss_version: Annotated[str, typer.Option("--ss-version")] = sealed_secrets.DEFAULT_VERSION,
    skip_postgres: Annotated[bool, typer.Option("--skip-postgres")] = False,
    postgres_name: Annotated[str, typer.Option("--postgres-name")] = "dev",
) -> None:
    """Bootstrap the full local k3s dev stack."""
    if not checks.preflight():
        raise typer.Exit(1)

    state = State.load()

    console.print("\n[bold]Installing Sealed Secrets controller...[/bold]")
    sealed_secrets.install(ss_version)
    state.sealed_secrets_version = ss_version

    console.print(f"\n[bold]Creating namespace '{namespace_name}'...[/bold]")
    namespace.create(namespace_name)
    if namespace_name not in state.namespaces:
        state.namespaces.append(namespace_name)

    if not skip_postgres:
        console.print(f"\n[bold]Provisioning Postgres '{postgres_name}'...[/bold]")
        instance, _ = pg.add(postgres_name, namespace_name, state)
        state.postgres_instances[postgres_name] = instance
        _print_pg(postgres_name, instance)

    state.initialized = True
    state.save()
    console.print("\n[bold green]✓ k3s dev stack initialized[/bold green]")


@app.command()
def status() -> None:
    """Show status of all managed components (cross-checks live cluster state)."""
    from k3s_dev import kubectl as kctl
    state = State.load()
    table = Table(title="k3s-dev status", show_lines=True)
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    r = subprocess.run(["kubectl", "cluster-info"], capture_output=True)
    cluster_ok = r.returncode == 0
    table.add_row(
        "Cluster",
        "[green]reachable[/green]" if cluster_ok else "[red]unreachable[/red]",
        "",
    )

    if state.sealed_secrets_version:
        rr = sealed_secrets.ready_replicas()
        table.add_row(
            "Sealed Secrets",
            "[green]running[/green]" if rr > 0 else "[yellow]not ready[/yellow]",
            state.sealed_secrets_version,
        )

    for ns in state.namespaces:
        if cluster_ok:
            r2 = subprocess.run(["kubectl", "get", "namespace", ns], capture_output=True)
            ns_status = "[green]exists[/green]" if r2.returncode == 0 else "[red]MISSING in cluster[/red]"
        else:
            ns_status = "[dim]cluster unreachable[/dim]"
        table.add_row(f"Namespace/{ns}", ns_status, "")

    for name, inst in state.postgres_instances.items():
        detail = f"{inst.namespace} • localhost:{inst.node_port} • {inst.user}@{inst.db}"
        if inst.backup:
            detail += " • backup"
        if cluster_ok:
            live = kctl.exists("deployment", name, inst.namespace)
            pg_status = "[green]running[/green]" if live else "[red]MISSING in cluster[/red]"
            if not live:
                detail += " — run 'postgres add' to recreate"
        else:
            pg_status = "[dim]cluster unreachable[/dim]"
        table.add_row(f"Postgres/{name}", pg_status, detail)

    for name in launch_agent.list_agents():
        table.add_row(f"LaunchAgent/{name}", launch_agent.agent_status(name), "")

    console.print(table)


@app.command()
def teardown(
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove all managed Postgres instances."""
    if not yes:
        typer.confirm("Remove all k3s-dev managed Postgres instances?", abort=True)
    state = State.load()
    for name, instance in list(state.postgres_instances.items()):
        console.print(f"Removing Postgres '{name}'...")
        pg.remove(name, instance)
        del state.postgres_instances[name]
    state.save()
    console.print("[green]Done[/green]")


# ── namespace ────────────────────────────────────────────────────────────────

@ns_app.command("add")
def ns_add(name: str) -> None:
    """Create a Kubernetes namespace."""
    namespace.create(name)
    state = State.load()
    if name not in state.namespaces:
        state.namespaces.append(name)
        state.save()
    console.print(f"[green]Namespace '{name}' ready[/green]")


@ns_app.command("list")
def ns_list() -> None:
    """List tracked namespaces."""
    state = State.load()
    if not state.namespaces:
        console.print("[dim]No tracked namespaces[/dim]")
        return
    for ns in state.namespaces:
        console.print(f"  {ns}")


@ns_app.command("remove")
def ns_remove(name: str) -> None:
    """Delete a namespace and stop tracking it."""
    namespace.remove(name)
    state = State.load()
    state.namespaces = [n for n in state.namespaces if n != name]
    state.save()
    console.print(f"[green]Namespace '{name}' removed[/green]")


# ── postgres ─────────────────────────────────────────────────────────────────

@pg_app.command("add")
def pg_add(
    name: str,
    namespace_name: Annotated[str, typer.Option("--namespace", "-n")] = "dev",
    user: Annotated[Optional[str], typer.Option("--user")] = None,
    db: Annotated[Optional[str], typer.Option("--db")] = None,
    secret_name: Annotated[Optional[str], typer.Option("--secret-name")] = None,
    storage: Annotated[str, typer.Option("--storage")] = "5Gi",
    backup: Annotated[bool, typer.Option("--backup/--no-backup")] = False,
    backup_schedule: Annotated[str, typer.Option("--backup-schedule")] = "0 5 * * *",
) -> None:
    """Provision a new Postgres instance (idempotent — recreates if state exists but cluster resources are gone)."""
    from k3s_dev import kubectl as kctl
    state = State.load()
    if name in state.postgres_instances:
        inst = state.postgres_instances[name]
        # Check if the deployment actually exists in the cluster
        if kctl.exists("deployment", name, inst.namespace):
            console.print(f"[yellow]Postgres '{name}' already exists and is running — use 'remove' first to reprovision[/yellow]")
            _print_pg(name, inst)
            raise typer.Exit(0)
        console.print(f"[yellow]Postgres '{name}' in state.json but not found in cluster — recreating...[/yellow]")
        del state.postgres_instances[name]

    instance, _ = pg.add(
        name, namespace_name, state,
        user=user, db=db, secret_name=secret_name,
        storage=storage, backup=backup, backup_schedule=backup_schedule,
    )
    state.postgres_instances[name] = instance
    state.save()
    _print_pg(name, instance)


@pg_app.command("list")
def pg_list() -> None:
    """List all Postgres instances."""
    state = State.load()
    if not state.postgres_instances:
        console.print("[dim]No Postgres instances[/dim]")
        return
    table = Table()
    table.add_column("Name")
    table.add_column("Namespace")
    table.add_column("Port")
    table.add_column("User")
    table.add_column("DB")
    table.add_column("Backup")
    for name, inst in state.postgres_instances.items():
        table.add_row(
            name, inst.namespace, str(inst.node_port),
            inst.user, inst.db, "✓" if inst.backup else "",
        )
    console.print(table)


@pg_app.command("remove")
def pg_remove(
    name: str,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove a Postgres instance and all its data."""
    state = State.load()
    if name not in state.postgres_instances:
        console.print(f"[red]Postgres '{name}' not found[/red]")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Remove Postgres '{name}' and all its data?", abort=True)
    pg.remove(name, state.postgres_instances[name])
    del state.postgres_instances[name]
    state.save()
    console.print(f"[green]Postgres '{name}' removed[/green]")


@pg_app.command("connect")
def pg_connect(name: str) -> None:
    """Show connection URLs for a Postgres instance."""
    state = State.load()
    if name not in state.postgres_instances:
        console.print(f"[red]Postgres '{name}' not found[/red]")
        raise typer.Exit(1)
    _print_pg(name, state.postgres_instances[name])


@pg_app.command("backup")
def pg_backup(name: str) -> None:
    """Trigger an immediate backup job."""
    state = State.load()
    if name not in state.postgres_instances:
        console.print(f"[red]Postgres '{name}' not found[/red]")
        raise typer.Exit(1)
    inst = state.postgres_instances[name]
    if not inst.backup:
        console.print(f"[yellow]Backup not enabled for '{name}' — re-add with --backup[/yellow]")
        raise typer.Exit(1)
    job = f"{name}-backup-manual-{int(time.time())}"
    subprocess.run(
        ["kubectl", "create", "job", job, f"--from=cronjob/{name}-backup", f"-n={inst.namespace}"],
        check=True,
    )
    console.print(f"[green]Backup job '{job}' started[/green]")
    console.print(f"  Watch: kubectl logs job/{job} -n {inst.namespace} -f")


# ── sealed-secrets ───────────────────────────────────────────────────────────

@ss_app.command("install")
def ss_install(
    version: Annotated[str, typer.Option("--version")] = sealed_secrets.DEFAULT_VERSION,
) -> None:
    """Install the Sealed Secrets controller."""
    sealed_secrets.install(version)
    state = State.load()
    state.sealed_secrets_version = version
    state.save()


@ss_app.command("upgrade")
def ss_upgrade(
    version: Annotated[str, typer.Option("--version")] = sealed_secrets.DEFAULT_VERSION,
) -> None:
    """Upgrade the Sealed Secrets controller to a new version."""
    sealed_secrets.install(version)
    state = State.load()
    state.sealed_secrets_version = version
    state.save()


@ss_app.command("status")
def ss_status() -> None:
    """Show Sealed Secrets controller status."""
    rr = sealed_secrets.ready_replicas()
    if rr > 0:
        console.print(f"[green]Sealed Secrets running ({rr} replica{'s' if rr > 1 else ''})[/green]")
    else:
        console.print("[yellow]Sealed Secrets controller not ready[/yellow]")


# ── launch-agent ─────────────────────────────────────────────────────────────

@la_app.command("add")
def la_add(
    name: str,
    program: str,
    args: Annotated[Optional[list[str]], typer.Argument()] = None,
    no_keep_alive: Annotated[bool, typer.Option("--no-keep-alive")] = False,
) -> None:
    """Register a macOS LaunchAgent with crash-restart."""
    launch_agent.add(name, program, args or [], keep_alive=not no_keep_alive)
    console.print(f"[green]LaunchAgent dev.k3s.{name} loaded[/green]")


@la_app.command("list")
def la_list() -> None:
    """List managed LaunchAgents."""
    agents = launch_agent.list_agents()
    if not agents:
        console.print("[dim]No managed LaunchAgents[/dim]")
        return
    for name in agents:
        console.print(f"  {name}: {launch_agent.agent_status(name)}")


@la_app.command("remove")
def la_remove(name: str) -> None:
    """Unload and remove a LaunchAgent."""
    launch_agent.remove(name)
    console.print(f"[green]LaunchAgent dev.k3s.{name} removed[/green]")


# ── demo ─────────────────────────────────────────────────────────────────────

@app.command()
def demo() -> None:
    """Simulate a full init + status run for demos and screenshots (no cluster needed)."""
    import time

    def _sleep(s: float) -> None:
        time.sleep(s)

    console.print(Panel("[bold]Pre-flight checks[/bold]", expand=False))
    _sleep(0.3)
    console.print("  [green]✓[/green] kubectl found")
    _sleep(0.2)
    console.print("  [green]✓[/green] cluster reachable")
    _sleep(0.2)
    console.print("  [yellow]![/yellow] kubeseal not found — install with: brew install kubeseal")

    console.print("\n[bold]Installing Sealed Secrets v0.27.3...[/bold]")
    _sleep(0.4)
    console.print("Downloading Sealed Secrets v0.27.3...")
    _sleep(1.2)
    console.print("[green]Sealed Secrets v0.27.3 installed in kube-system[/green]")

    console.print("\n[bold]Creating namespace 'myapp'...[/bold]")
    _sleep(0.3)

    console.print("\n[bold]Provisioning Postgres 'myapp'...[/bold]")
    _sleep(0.3)
    console.print("  namespace/myapp configured")
    console.print("  persistentvolumeclaim/myapp-data created")
    console.print("  secret/myapp-postgres-secret created")
    console.print("  deployment.apps/myapp created")
    console.print("  service/myapp created")
    _sleep(0.3)
    console.print("[green]Password stored in Keychain (k3s-dev / postgres/myapp)[/green]")
    _sleep(0.2)

    console.print(Panel(
        "[bold]Local:[/bold]    postgresql+psycopg2://myapp:••••••••@localhost:30432/myapp\n"
        "[bold]Cluster:[/bold]  postgresql+psycopg2://myapp:••••••••@myapp:5432/myapp\n"
        "[bold]Secret:[/bold]   myapp-postgres-secret  (keys: password, db_url, local_url)",
        title="Postgres 'myapp'",
        expand=False,
    ))

    console.print("\n[bold green]✓ k3s dev stack initialized[/bold green]\n")
    _sleep(0.6)

    # Status table
    table = Table(title="k3s-dev status", show_lines=True)
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details")
    table.add_row("Cluster", "[green]reachable[/green]", "")
    table.add_row("Sealed Secrets", "[green]running[/green]", "v0.27.3")
    table.add_row("Namespace/myapp", "[green]tracked[/green]", "")
    table.add_row("Postgres/myapp", "[green]provisioned[/green]", "myapp • localhost:30432 • myapp@myapp")
    console.print(table)


# ── project ──────────────────────────────────────────────────────────────────

@project_app.command("check")
def project_check(
    path: Annotated[str, typer.Argument()] = ".",
    all_projects: Annotated[bool, typer.Option("--all", help="Check all projects under the all-src workspace")] = False,
) -> None:
    """Lint a project directory against all-src conventions."""
    from pathlib import Path as P
    import sys

    workspace = P("/Users/prafful/Documents/all-src")
    if all_projects:
        project_dirs = [d for d in workspace.iterdir() if d.is_dir() and not d.name.startswith(".")]
    else:
        project_dirs = [P(path).resolve()]

    total_violations = 0
    for project_dir in sorted(project_dirs):
        violations = proj.check(project_dir)
        code = proj.report(project_dir, violations)
        total_violations += len(violations)

    if all_projects and total_violations > 0:
        console.print(f"\n[red bold]{total_violations} total violation(s) across workspace[/red bold]")
        raise typer.Exit(1)
    elif total_violations > 0:
        raise typer.Exit(1)


# ── helpers ──────────────────────────────────────────────────────────────────

def _print_pg(name: str, instance: PostgresInstance) -> None:
    local = pg.local_url(name, instance)
    cluster = pg.cluster_url(name, instance)
    console.print(Panel(
        f"[bold]Local:[/bold]    {local}\n"
        f"[bold]Cluster:[/bold]  {cluster}\n"
        f"[bold]Secret:[/bold]   {instance.secret_name}  (keys: password, db_url, local_url)",
        title=f"Postgres '{name}'",
        expand=False,
    ))
