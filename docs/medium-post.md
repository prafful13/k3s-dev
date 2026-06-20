# One Command to Supercharge Your Local Kubernetes Dev Environment

Every time I start a new project that deploys to Kubernetes, I repeat the same ritual. Create a namespace. Install the Bitnami Sealed Secrets controller. Provision a Postgres instance — PVC, Secret, Deployment, Service. Wire up secrets between macOS Keychain and the cluster. Write the same five YAML files I wrote for the last project.

It's not hard. It's just tedious. And it's the kind of work that feels like it should already be solved.

So I built **k3s-dev** — a CLI that does all of it in one command. The code is on [GitHub](https://github.com/prafful13/k3s-dev) and the docs are at [prafful13.github.io/k3s-dev](https://prafful13.github.io/k3s-dev/).

## The Problem with Local Kubernetes Dev

If you run [Rancher Desktop](https://rancherdesktop.io/) on macOS (which gives you a local k3s cluster for free), you already have a great local production replica. The problem is bootstrapping it for each new project.

Every project I work on needs roughly the same infrastructure:

- A **namespace** to isolate resources
- A **Sealed Secrets controller** so I can encrypt k8s Secrets and commit them to git safely
- A **Postgres instance** with persistent storage, a k8s Secret containing the credentials, and NodePort access for local psql
- Optionally, macOS **LaunchAgents** for host-level background services that can't run inside k3s itself

None of this is novel. None of it changes between projects. But there's no standard tool that does it — you end up maintaining a folder of YAML files and a handful of shell scripts in every repo, or just re-inventing it from memory each time.

## What k3s-dev Does

`k3s-dev` is a single CLI built in Python with [Typer](https://typer.tiangolo.com/) that bootstraps your entire local k3s dev stack and tracks what it provisioned in `~/.k3s-dev/state.json`.

```bash
k3s-dev init
```

That one command:

1. Runs **pre-flight checks** — verifies kubectl is installed, the cluster is reachable, and kubeseal is available
2. Downloads and applies the **Bitnami Sealed Secrets controller** to `kube-system`
3. Creates your **namespace**
4. Provisions a **Postgres instance** — PVC, k8s Secret with an auto-generated password, Deployment running `postgres:16-alpine`, NodePort Service starting at port 30432

![k3s-dev demo](demo.gif)

After that, `k3s-dev status` gives you a live view of everything managed:

```
                         k3s-dev status
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Component       ┃ Status      ┃ Details                               ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Cluster         │ reachable   │                                       │
│ Sealed Secrets  │ running     │ v0.27.3                               │
│ Namespace/myapp │ tracked     │                                       │
│ Postgres/myapp  │ provisioned │ myapp • localhost:30432 • myapp@myapp │
└─────────────────┴─────────────┴───────────────────────────────────────┘
```

## The Secrets Model

This is the part I'm most opinionated about, and for good reason — I've been burned by secrets in git before.

k3s-dev uses a three-layer secrets strategy:

**Layer 1 — macOS Keychain.** Every auto-generated password is stored in the macOS Keychain immediately, under service `k3s-dev` with key `postgres/<name>`. This is the source of truth for all secrets on the host. No `.env` files, no hardcoded credentials.

**Layer 2 — k8s Secret.** The Postgres Secret is created directly in the cluster with three keys: `password`, `db_url` (the in-cluster connection URL), and `local_url` (the NodePort URL for local psql access). Since this is a local dev cluster and the password lives in Keychain, there's no need to seal it — k3s-dev owns it.

**Layer 3 — Pod env vars.** Application deployments consume the Secret via `secretKeyRef` — they never touch the Keychain, never know how the password was generated. In-cluster, the app just reads `DB_URL` from its environment.

For *application* secrets (OAuth tokens, API keys), I use [Bitnami Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) — which is exactly why k3s-dev installs the controller as part of init. You encrypt your Secrets with `kubeseal`, commit the encrypted `SealedSecret` YAML to git, and the controller decrypts it inside the cluster. Safe to commit, zero secrets in plain text.

## It's Project-Agnostic by Design

Here's the key insight: k3s-dev is intentionally *not* part of any individual project. It's a shared CLI that sits above all your projects.

Instead of each project managing its own Postgres YAML files, they delegate:

```bash
k3s-dev postgres add robinhood \
  --namespace robinhood-trader \
  --user trader \
  --db robinhood_trader \
  --secret-name postgres-credentials \
  --backup
```

That creates a `postgres-credentials` Secret in the `robinhood-trader` namespace. The project's Deployment just mounts it:

```yaml
env:
  - name: DB_URL
    valueFrom:
      secretKeyRef:
        name: postgres-credentials
        key: db_url
```

The project has no idea how Postgres was provisioned, what password was generated, or where it's stored. It just works. And when you spin up a second project, you run `k3s-dev postgres add` again with a different name — it auto-allocates the next NodePort (30433) and tracks both instances in state.

I use this pattern in my [robinhood-pilot](https://github.com/prafful13/robinhood-pilot) project — an automated trading bot that deploys to the local k3s cluster. All the postgres boilerplate that used to live in `k8s/` is gone. The project only owns its application secrets and manifests.

## Step-by-Step Setup

**Install:**

```bash
git clone https://github.com/prafful13/k3s-dev
cd k3s-dev
uv venv --python 3.13 && uv sync --all-groups
uv pip install -e .
```

**Bootstrap a new project:**

```bash
# One-shot: Sealed Secrets + namespace + Postgres
k3s-dev init --namespace myapp --postgres-name myapp

# Or step by step
k3s-dev sealed-secrets install
k3s-dev namespace add myapp
k3s-dev postgres add myapp \
  --namespace myapp \
  --user myapp \
  --db myapp_db \
  --backup
```

**Connect locally:**

```bash
# Password is in Keychain — retrieve it
k3s-dev postgres connect myapp
# prints local_url: postgresql+psycopg2://myapp:...@localhost:30432/myapp_db

psql "postgresql://myapp@localhost:30432/myapp_db"
```

**Tear down when done:**

```bash
k3s-dev postgres remove myapp --yes
```

## LaunchAgents Too

One more thing: k3s-dev also manages macOS LaunchAgents for processes that genuinely need to run on the host — things like k3s itself if you're not using Rancher Desktop, or a tunnel process.

```bash
k3s-dev launch-agent add my-tunnel \
  /usr/local/bin/cloudflared tunnel run
```

This writes a properly structured `~/Library/LaunchAgents/dev.k3s.my-tunnel.plist` with `KeepAlive.Crashed = true` and loads it immediately. If the process crashes, launchd restarts it automatically. No more forgetting to restart background services after a reboot.

## Try It Yourself

The code is at [github.com/prafful13/k3s-dev](https://github.com/prafful13/k3s-dev) and the full docs are at [prafful13.github.io/k3s-dev](https://prafful13.github.io/k3s-dev/). It's opinionated toward the stack I use (Rancher Desktop, Bitnami Sealed Secrets, Postgres), but the architecture is simple enough to fork and adapt.

If you've ever copy-pasted the same `postgres-deployment.yaml` between projects, this is for you.

*Built with Python 3.13, Typer, Rich, and a lot of frustration at YAML boilerplate.*
