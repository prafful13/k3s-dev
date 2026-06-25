"""Persistent state tracking for provisioned resources."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_DIR = Path.home() / ".k3s-dev"
STATE_FILE = STATE_DIR / "state.json"


@dataclass
class PostgresInstance:
    namespace: str
    node_port: int
    user: str
    db: str
    secret_name: str
    backup: bool
    created_at: str


@dataclass
class State:
    initialized: bool = False
    sealed_secrets_version: str | None = None
    namespaces: list[str] = field(default_factory=list)
    postgres_instances: dict[str, PostgresInstance] = field(default_factory=dict)

    @classmethod
    def load(cls) -> State:
        if not STATE_FILE.exists():
            return cls()
        raw = json.loads(STATE_FILE.read_text())
        instances = {k: PostgresInstance(**v) for k, v in raw.get("postgres_instances", {}).items()}
        return cls(
            initialized=raw.get("initialized", False),
            sealed_secrets_version=raw.get("sealed_secrets_version"),
            namespaces=raw.get("namespaces", []),
            postgres_instances=instances,
        )

    def save(self) -> None:
        STATE_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(
                {
                    "initialized": self.initialized,
                    "sealed_secrets_version": self.sealed_secrets_version,
                    "namespaces": self.namespaces,
                    "postgres_instances": {
                        k: asdict(v) for k, v in self.postgres_instances.items()
                    },
                },
                indent=2,
            )
        )
