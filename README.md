# k3s-dev

A CLI that bootstraps a full local k3s development environment on macOS in one command — namespaces, Bitnami Sealed Secrets controller, Postgres instances, and macOS LaunchAgents.

The problem it solves: every project that deploys to k3s requires the same boilerplate — provision a namespace, install the Sealed Secrets controller, stand up a Postgres database, wire up secrets. This tool does all of it idempotently and tracks what it provisioned in `~/.k3s-dev/state.json` so you can inspect, update, or tear it down later.

**Prerequisites:** [Rancher Desktop](https://rancherdesktop.io/) (provides k3s + kubectl on macOS). Optional: `brew install kubeseal` for Sealed Secrets workflows.

---

## Demo

![k3s-dev demo](docs/demo.gif)

---

## Install

```bash
# Clone and install globally
git clone https://github.com/prafful13/k3s-dev
cd k3s-dev
uv venv --python 3.13 && uv sync --all-groups
uv pip install -e .

# Or run directly without installing
uv run k3s-dev --help
```

---

## Quick start

```bash
# Bootstrap everything (Sealed Secrets + namespace + Postgres) in one command
k3s-dev init

# Or step by step
k3s-dev sealed-secrets install
k3s-dev namespace add myapp
k3s-dev postgres add myapp --namespace myapp --user myapp --db myapp --backup
```

`postgres add` creates:
- A **PVC** for data storage
- A **k8s Secret** with auto-generated password (also stored in macOS Keychain)
- A **Deployment** running `postgres:16-alpine`
- A **NodePort Service** on the next available port starting at `30432`
- Optionally a **backup PVC + daily CronJob** with `--backup`

---

## Commands

### Top-level

| Command | Description |
|---|---|
| `k3s-dev init` | Full bootstrap: pre-flight checks → Sealed Secrets → namespace → Postgres |
| `k3s-dev status` | Rich table showing cluster, Sealed Secrets, namespaces, Postgres instances, LaunchAgents |
| `k3s-dev teardown` | Remove all managed Postgres instances |

### `k3s-dev init` options

```
--namespace, -n TEXT        Namespace to create  [default: dev]
--ss-version TEXT           Sealed Secrets version  [default: v0.27.3]
--skip-postgres             Skip Postgres provisioning
--postgres-name TEXT        Name for the Postgres instance  [default: dev]
```

### `k3s-dev postgres`

```bash
k3s-dev postgres add <name> [OPTIONS]
  --namespace, -n TEXT      Kubernetes namespace  [default: dev]
  --user TEXT               Postgres user  [default: <name>]
  --db TEXT                 Database name  [default: <name>]
  --secret-name TEXT        k8s Secret name  [default: <name>-postgres-secret]
  --storage TEXT            PVC size  [default: 5Gi]
  --backup / --no-backup    Enable daily backup CronJob  [default: no-backup]
  --backup-schedule TEXT    Cron schedule for backups  [default: 0 5 * * *]

k3s-dev postgres list
k3s-dev postgres connect <name>    # print local and in-cluster URLs
k3s-dev postgres remove <name>
k3s-dev postgres backup <name>     # trigger immediate backup job
```

The Secret created by `postgres add` contains three keys:
- `password` — the Postgres password
- `db_url` — in-cluster connection string (`postgresql+psycopg2://user:pw@<name>:5432/db`)
- `local_url` — local connection string via NodePort (`postgresql+psycopg2://user:pw@localhost:<port>/db`)

Password is also stored in macOS Keychain under service `k3s-dev`, key `postgres/<name>`.

### `k3s-dev sealed-secrets`

```bash
k3s-dev sealed-secrets install [--version v0.27.3]
k3s-dev sealed-secrets upgrade  [--version v0.27.3]
k3s-dev sealed-secrets status
```

### `k3s-dev namespace`

```bash
k3s-dev namespace add <name>
k3s-dev namespace list
k3s-dev namespace remove <name>
```

### `k3s-dev launch-agent`

Manages macOS LaunchAgents for background services that cannot run in k3s (e.g. k3s/Rancher Desktop itself, host-level daemons).

```bash
k3s-dev launch-agent add <name> <program> [args...] [--no-keep-alive]
k3s-dev launch-agent list
k3s-dev launch-agent remove <name>
```

LaunchAgents are written to `~/Library/LaunchAgents/dev.k3s.<name>.plist` with `KeepAlive.Crashed = true` by default. Logs go to `~/.k3s-dev/logs/`.

---

## Integration with a project

For a project that needs Postgres in `robinhood-trader` namespace:

```bash
# One-time bootstrap (shared across projects)
k3s-dev sealed-secrets install

# Per-project: provision Postgres with the secret name your app expects
k3s-dev postgres add robinhood \
  --namespace robinhood-trader \
  --user trader \
  --db robinhood_trader \
  --secret-name postgres-credentials \
  --backup

# Your app's k8s Deployment can now reference the Secret directly:
#   secretKeyRef: { name: postgres-credentials, key: db_url }
```

The project no longer needs postgres k8s manifests or a postgres password in its own secrets workflow. `k3s-dev` owns the postgres lifecycle; projects consume the Secret.

---

## State

All provisioned resources are tracked in `~/.k3s-dev/state.json`:

```json
{
  "initialized": true,
  "sealed_secrets_version": "v0.27.3",
  "namespaces": ["robinhood-trader"],
  "postgres_instances": {
    "robinhood": {
      "namespace": "robinhood-trader",
      "node_port": 30432,
      "user": "trader",
      "db": "robinhood_trader",
      "secret_name": "postgres-credentials",
      "backup": true,
      "created_at": "2026-06-20T..."
    }
  }
}
```

---

## Project structure

```
k3s-dev/
├── k3s_dev/
│   ├── cli.py              # Typer app, all commands
│   ├── checks.py           # Pre-flight checks (kubectl, cluster reachability, kubeseal)
│   ├── postgres.py         # PVC + Secret + Deployment + Service + backup CronJob manifests
│   ├── sealed_secrets.py   # Download and apply Sealed Secrets controller
│   ├── namespace.py        # Namespace create/delete
│   ├── launch_agent.py     # macOS plist management via launchctl
│   ├── kubectl.py          # subprocess wrapper for kubectl
│   └── state.py            # ~/.k3s-dev/state.json read/write
├── pyproject.toml
├── MODULE.bazel
├── tasks.py                # inv install, test, lock-update
└── requirements.lock       # pinned for Bazel pip.parse()
```

---

## Development

```bash
uv sync --all-groups
uv run inv test
uv run inv lock-update   # after adding deps
```
