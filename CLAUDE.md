# k3s-dev

Shared CLI tool for bootstrapping and managing local k3s infrastructure on macOS (Rancher Desktop). Provisions namespaces, Postgres instances, Sealed Secrets controller, and macOS LaunchAgents. **This is infrastructure tooling — it does NOT scaffold new projects.**

## Status
- Deployed: N/A (CLI tool — run via `uv run k3s-dev`)
- Namespace: N/A (manages namespaces for other projects)
- Live URL: N/A
- Last known good: 2026-06-24
- Open P0 issues: None
- State file: `~/.k3s-dev/state.json` (not in repo)

Current provisioned resources:
| Resource | Namespace | NodePort | Notes |
|---|---|---|---|
| Postgres/robinhood | robinhood-trader | 30432 | user=trader, db=robinhood_trader, backup=true |
| Postgres/jarvis | jarvis | 30433 | user=jarvis, db=jarvis, backup=false |
| Sealed Secrets controller | kube-system | — | v0.27.3 |
| Namespace/robinhood-trader | — | — | tracked |
| Namespace/contracts-analysis | — | — | tracked |
| Namespace/jarvis | — | — | tracked |

(`initialized: false` in state.json is cosmetic — resources were added command-by-command, not via `k3s-dev init`. All resources exist and work.)

## Architecture

Single Typer CLI with four sub-apps:

```
k3s-dev
├── namespace   add / list / remove               → kubectl create/delete namespace
├── postgres    add / list / remove / connect      → PVC + Secret + Deployment + NodePort Service
├── sealed-secrets  install / upgrade / status    → Bitnami controller in kube-system
└── launch-agent    add / list / remove           → plist → ~/Library/LaunchAgents/
```

State persisted to `~/.k3s-dev/state.json` (dataclass in `k3s_dev/state.py`). State is write-only on create — does NOT reconcile against live cluster on read. This is the root cause of the state-desync gotcha below.

## Entry Points
```
uv run k3s-dev --help                            # all commands
uv run k3s-dev init                              # first-time full bootstrap
uv run k3s-dev status                            # show state.json contents
uv run k3s-dev postgres add <name> -n <ns>       # provision new Postgres
uv run k3s-dev postgres list                     # list provisioned instances
uv run k3s-dev postgres connect <name>           # print connection URLs
uv run k3s-dev postgres backup <name>            # trigger manual backup job
uv run k3s-dev namespace add <name>              # create + track namespace
uv run k3s-dev sealed-secrets install            # install Bitnami controller
uv run k3s-dev sealed-secrets status             # check controller health
uv run k3s-dev launch-agent add <name> <program> # register macOS LaunchAgent
uv run k3s-dev demo                              # demo run (no cluster needed)
uv run inv test                                  # run pytest
uv run inv lock-update                           # regenerate requirements.lock
```

## Infrastructure
- Keychain service name: `k3s-dev`
- Keychain key per Postgres instance: `postgres/<name>`
- Postgres image: `postgres:16-alpine`
- NodePort base: 30432; auto-increments per new instance. Next free: **30434**
- k8s Secret keys created by `postgres add`: `password`, `db_url` (cluster URL), `local_url` (localhost:NodePort URL)

## Secrets
| Instance | Keychain key | k8s Secret name | Namespace | Consumed by |
|---|---|---|---|---|
| robinhood | `postgres/robinhood` | `postgres-credentials` | robinhood-trader | robinhood-pilot bot |
| jarvis | `postgres/jarvis` | `postgres-secret` | jarvis | all Jarvis agents |

## Key Files
| File | Purpose |
|---|---|
| `k3s_dev/cli.py` | Typer CLI — all commands and sub-apps defined here |
| `k3s_dev/postgres.py` | Manifest generation + `add()` / `remove()` + URL helpers |
| `k3s_dev/state.py` | `State` + `PostgresInstance` dataclasses; load/save `~/.k3s-dev/state.json` |
| `k3s_dev/namespace.py` | `kubectl create namespace` wrapper |
| `k3s_dev/sealed_secrets.py` | Install Bitnami controller; `DEFAULT_VERSION` constant |
| `k3s_dev/launch_agent.py` | plist generation + launchctl load/unload/status |
| `k3s_dev/kubectl.py` | `kubectl apply` via stdin pipe |
| `k3s_dev/checks.py` | Preflight: kubectl on PATH, cluster reachable, kubeseal installed |
| `tasks.py` | invoke tasks: install, test, build, run, lock-update |
| `~/.k3s-dev/state.json` | Live state (NOT in repo) |

## Gotchas
- **State desync**: `state.json` tracks provisioned resources but does NOT query live cluster. If a resource is deleted outside k3s-dev (`kubectl delete deployment robinhood -n robinhood-trader`), state.json still shows it as provisioned. `k3s-dev status` reads state.json only — it does not cross-check the cluster. Symptom: `postgres add` exits 1 ("already exists") even though the k8s resource is gone. Workaround: manually edit `~/.k3s-dev/state.json` to remove the stale entry, then re-add. NEXT-3 tracks making this idempotent.
- **`postgres add` is not idempotent**: exits 1 if the name is already in state.json, regardless of cluster state. This is a known gap (NEXT-3).
- **kubectl PATH in Claude shell**: Claude's shell doesn't inherit zsh PATH. Prefix every kubectl command: `export PATH="$HOME/.rd/bin:$PATH" && kubectl ...`
- **No project scaffolding**: k3s-dev does NOT scaffold new project directories (no `project new`, no `project check`). NEXT-1 adds `k3s-dev project check`; LATER-1 adds `k3s-dev project new`.
- **backup=false for jarvis Postgres**: jarvis DB is not backed up. If the PVC is deleted, all task/decision/audit history is lost. Acceptable for now; re-enable if data becomes critical.

## Next Tasks
- [ ] Implement `k3s-dev project check <path>` — convention linter (NEXT-1; L effort)
- [ ] Make `postgres add` idempotent; add live-vs-state diff to `k3s-dev status` (NEXT-3; M effort)
- [ ] Add `CLAUDE.md` status section to NEXT tasks tracking (done — this file)
