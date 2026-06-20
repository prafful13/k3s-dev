"""macOS LaunchAgent management for non-k8s background services."""
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
_LOG_DIR = Path.home() / ".k3s-dev" / "logs"
_PREFIX = "dev.k3s"


def _plist_path(name: str) -> Path:
    return _LAUNCH_AGENTS_DIR / f"{_PREFIX}.{name}.plist"


def add(name: str, program: str, args: list[str], *, keep_alive: bool = True) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": f"{_PREFIX}.{name}",
        "ProgramArguments": [program] + args,
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": keep_alive},
        "StandardOutPath": str(_LOG_DIR / f"{name}.out.log"),
        "StandardErrorPath": str(_LOG_DIR / f"{name}.err.log"),
    }
    path = _plist_path(name)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "load", str(path)], check=True)


def remove(name: str) -> None:
    path = _plist_path(name)
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], check=False)
        path.unlink()


def list_agents() -> list[str]:
    return [
        p.stem.removeprefix(f"{_PREFIX}.")
        for p in _LAUNCH_AGENTS_DIR.glob(f"{_PREFIX}.*.plist")
    ]


def agent_status(name: str) -> str:
    r = subprocess.run(
        ["launchctl", "list", f"{_PREFIX}.{name}"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return "not loaded"
    parts = r.stdout.strip().split("\t")
    pid = parts[0] if parts else "0"
    return f"running (PID {pid})" if pid not in ("0", "-") else "stopped"
