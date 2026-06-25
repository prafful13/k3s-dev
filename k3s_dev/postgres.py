"""Postgres instance provisioning on k3s."""

from __future__ import annotations

import base64
import secrets
import string
from datetime import UTC, datetime

import keyring
from rich.console import Console

from k3s_dev import kubectl, namespace
from k3s_dev.state import PostgresInstance, State

console = Console()

_IMAGE = "postgres:16-alpine"
_KEYCHAIN_SERVICE = "k3s-dev"
_BASE_NODE_PORT = 30432


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


def _next_port(state: State) -> int:
    used = {i.node_port for i in state.postgres_instances.values()}
    port = _BASE_NODE_PORT
    while port in used:
        port += 1
    return port


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _pvc_manifest(name: str, ns: str, storage: str) -> str:
    return f"""\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}-data
  namespace: {ns}
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: {storage}
"""


def _secret_manifest(
    name: str, ns: str, secret_name: str, user: str, db: str, pw: str, node_port: int
) -> str:
    cluster_url = f"postgresql+psycopg2://{user}:{pw}@{name}:{5432}/{db}"
    local_url = f"postgresql+psycopg2://{user}:{pw}@localhost:{node_port}/{db}"
    return f"""\
apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: {ns}
type: Opaque
data:
  password: {_b64(pw)}
  db_url: {_b64(cluster_url)}
  local_url: {_b64(local_url)}
"""


def _deployment_manifest(name: str, ns: str, secret_name: str, user: str, db: str) -> str:
    return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {ns}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: postgres
          image: {_IMAGE}
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: {db}
            - name: POSTGRES_USER
              value: {user}
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {secret_name}
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "{user}", "-d", "{db}"]
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            exec:
              command: ["pg_isready", "-U", "{user}", "-d", "{db}"]
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 6
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {name}-data
      restartPolicy: Always
"""


def _service_manifest(name: str, ns: str, node_port: int) -> str:
    return f"""\
apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {ns}
spec:
  type: NodePort
  selector:
    app: {name}
  ports:
    - port: 5432
      targetPort: 5432
      nodePort: {node_port}
"""


def _backup_pvc_manifest(name: str, ns: str, storage: str) -> str:
    return f"""\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}-backup
  namespace: {ns}
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: {storage}
"""


def _backup_cronjob_manifest(
    name: str, ns: str, secret_name: str, user: str, db: str, schedule: str
) -> str:
    return f"""\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {name}-backup
  namespace: {ns}
spec:
  schedule: "{schedule}"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: {_IMAGE}
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: {secret_name}
                      key: password
              command:
                - sh
                - -c
                - |
                  set -e
                  FILE="/backups/{db}_$(date +%Y%m%d_%H%M%S).sql.gz"
                  pg_dump -h {name} -U {user} {db} | gzip > "$FILE"
                  SIZE=$(du -h "$FILE" | cut -f1)
                  echo "Backup: $FILE ($SIZE)"
                  ls -t /backups/*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -v
              volumeMounts:
                - name: backup-storage
                  mountPath: /backups
          volumes:
            - name: backup-storage
              persistentVolumeClaim:
                claimName: {name}-backup
"""


def add(
    name: str,
    ns: str,
    state: State,
    *,
    user: str | None = None,
    db: str | None = None,
    secret_name: str | None = None,
    storage: str = "5Gi",
    backup: bool = False,
    backup_schedule: str = "0 5 * * *",
    backup_storage: str = "5Gi",
) -> tuple[PostgresInstance, str]:
    user = user or name
    db = db or name
    secret_name = secret_name or f"{name}-postgres-secret"
    node_port = _next_port(state)
    pw = _password()

    namespace.create(ns)
    kubectl.apply(_pvc_manifest(name, ns, storage))
    kubectl.apply(_secret_manifest(name, ns, secret_name, user, db, pw, node_port))
    kubectl.apply(_deployment_manifest(name, ns, secret_name, user, db))
    kubectl.apply(_service_manifest(name, ns, node_port))

    if backup:
        kubectl.apply(_backup_pvc_manifest(name, ns, backup_storage))
        kubectl.apply(_backup_cronjob_manifest(name, ns, secret_name, user, db, backup_schedule))

    keyring.set_password(_KEYCHAIN_SERVICE, f"postgres/{name}", pw)
    console.print(f"[green]Password stored in Keychain (k3s-dev / postgres/{name})[/green]")

    return PostgresInstance(
        namespace=ns,
        node_port=node_port,
        user=user,
        db=db,
        secret_name=secret_name,
        backup=backup,
        created_at=datetime.now(UTC).isoformat(),
    ), pw


def remove(name: str, instance: PostgresInstance) -> None:
    ns = instance.namespace
    for kind, resource_name in [
        ("service", name),
        ("deployment", name),
        ("pvc", f"{name}-data"),
        ("secret", instance.secret_name),
    ]:
        kubectl.run(["delete", kind, resource_name, "-n", ns, "--ignore-not-found"], check=False)
    if instance.backup:
        kubectl.run(
            ["delete", "cronjob", f"{name}-backup", "-n", ns, "--ignore-not-found"], check=False
        )
        kubectl.run(
            ["delete", "pvc", f"{name}-backup", "-n", ns, "--ignore-not-found"], check=False
        )
    try:
        keyring.delete_password(_KEYCHAIN_SERVICE, f"postgres/{name}")
    except Exception:
        pass


def local_url(name: str, instance: PostgresInstance) -> str:
    pw = keyring.get_password(_KEYCHAIN_SERVICE, f"postgres/{name}") or "<password>"
    return (
        f"postgresql+psycopg2://{instance.user}:{pw}@localhost:{instance.node_port}/{instance.db}"
    )


def cluster_url(name: str, instance: PostgresInstance) -> str:
    pw = keyring.get_password(_KEYCHAIN_SERVICE, f"postgres/{name}") or "<password>"
    return f"postgresql+psycopg2://{instance.user}:{pw}@{name}:{5432}/{instance.db}"
