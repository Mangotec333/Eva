"""
EVA Diracatron — the data-driven agent registry
===============================================

The registry is the single source of truth for every lobe Diracatron can
orchestrate. It is declared as data (``agent_registry.json``), so **adding a
lobe is a config edit** — drop a new object in the JSON and Diracatron can
discover, reason about, and invoke it with no code change.

Each agent entry declares:

  * ``slug`` / ``name`` — identity,
  * ``port`` / ``host`` / ``health`` — where it lives,
  * ``role`` + ``capabilities`` — what it does, in plain language, so the LLM
    dispatch brain can decide *when* to invoke it,
  * ``actions`` — a map of ``action -> {method, route}`` (the invocation
    interface over HTTP),
  * ``cli`` (optional) — ``{cwd, entry}`` for the module's CLI fallback.

This module loads that config and exposes:

  * :class:`AgentRegistry` — typed access (``get``, ``all``, ``describe`` for
    the LLM prompt),
  * :class:`Invoker` — fires an agent action over HTTP (or, offline, records
    the call and fires nothing), with a stub for tests.

Stdlib only (``urllib``). Every network path degrades to an honest
``{"ok": False, ...}`` — a downstream agent being down never raises.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional, Protocol, runtime_checkable

REGISTRY_PATH = os.environ.get(
    "EVA_AGENT_REGISTRY",
    os.path.join(os.path.dirname(__file__), "agent_registry.json"),
)
MODULES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Agent:
    """One lobe in the registry (a thin, typed view over its config dict)."""

    def __init__(self, cfg: dict, host: str) -> None:
        self.slug: str = cfg["slug"]
        self.name: str = cfg.get("name", cfg["slug"])
        self.port: Optional[int] = cfg.get("port")
        self.host: str = (cfg.get("host") or host).rstrip("/")
        self.health: str = cfg.get("health", "/health")
        self.role: str = cfg.get("role", "")
        self.capabilities: str = cfg.get("capabilities", "")
        self.actions: dict = cfg.get("actions", {}) or {}
        self.default_action: str = cfg.get("default_action") or (
            next(iter(self.actions), ""))
        self.cli: Optional[dict] = cfg.get("cli")
        self._cfg = cfg

    def base_url(self, launcher_url: str = "http://localhost:8768") -> str:
        """Direct port when known; port-less agents route via the launcher."""
        return f"{self.host}:{self.port}" if self.port else launcher_url.rstrip("/")

    def resolve_action(self, action: Optional[str]) -> Optional[dict]:
        """A concrete ``{method, route}`` for an action name (or the default)."""
        key = action or self.default_action
        spec = self.actions.get(key)
        return {**spec, "action": key} if spec else None

    def as_dict(self) -> dict:
        return dict(self._cfg)


class AgentRegistry:
    """Loads the JSON config and offers typed lookup + an LLM-facing summary."""

    def __init__(self, path: str = REGISTRY_PATH) -> None:
        self.path = path
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.host: str = data.get("host", "http://localhost")
        self._agents: dict[str, Agent] = {}
        for cfg in data.get("agents", []):
            agent = Agent(cfg, self.host)
            self._agents[agent.slug] = agent

    def get(self, slug: str) -> Optional[Agent]:
        return self._agents.get(slug)

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def slugs(self) -> list[str]:
        return list(self._agents.keys())

    def describe(self) -> str:
        """A compact capability catalogue for the dispatch brain's prompt.

        One line per agent: ``slug (role) :port — capabilities [actions]``.
        This is what lets the LLM pick the *right* lobe from first principles.
        """
        lines = []
        for a in self._agents.values():
            acts = ", ".join(a.actions.keys())
            port = f":{a.port}" if a.port else " (via launcher)"
            lines.append(
                f"- {a.slug} ({a.role}){port} — {a.capabilities} "
                f"Actions: {acts}.")
        return "\n".join(lines)

    def to_catalog(self) -> list[dict]:
        """Machine-readable catalogue (for the /triage/registry route)."""
        return [
            {"slug": a.slug, "name": a.name, "port": a.port, "role": a.role,
             "health": a.health, "capabilities": a.capabilities,
             "actions": a.actions, "default_action": a.default_action,
             "cli": bool(a.cli)}
            for a in self._agents.values()
        ]


# ---------------------------------------------------------------------------
# Invoker (Protocol) — live HTTP/CLI + in-memory stub for tests.
# ---------------------------------------------------------------------------

@runtime_checkable
class Invoker(Protocol):
    def invoke(self, agent: Agent, *, action: Optional[str] = None,
               payload: Optional[dict] = None) -> dict: ...


class StubInvoker:
    """Offline invoker — records calls, fires nothing. Tests inject this."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke(self, agent: Agent, *, action: Optional[str] = None,
               payload: Optional[dict] = None) -> dict:
        spec = agent.resolve_action(action)
        self.calls.append({"agent": agent.slug, "action": action,
                           "resolved": spec, "payload": payload or {}})
        return {"ok": True, "stub": True, "agent": agent.slug,
                "action": (spec or {}).get("action", action)}


class HttpInvoker:
    """Live invoker — calls an agent action over HTTP, CLI as fallback.

    Port-less agents are delegated through the launcher (:8768), exactly like
    the launcher already fronts those gates. Any failure is returned as an
    honest ``{"ok": False, ...}`` so one dead lobe never breaks a dispatch.
    """

    def __init__(self, launcher_url: str = "http://localhost:8768",
                 timeout: float = 8.0, allow_cli: bool = True) -> None:
        self.launcher_url = launcher_url.rstrip("/")
        self.timeout = timeout
        self.allow_cli = allow_cli

    def invoke(self, agent: Agent, *, action: Optional[str] = None,
               payload: Optional[dict] = None) -> dict:
        spec = agent.resolve_action(action)
        if not spec:
            return {"ok": False, "agent": agent.slug,
                    "error": f"unknown action '{action}' for {agent.slug}"}
        method = spec.get("method", "POST").upper()
        url = f"{agent.base_url(self.launcher_url)}{spec['route']}"
        try:
            result = self._http(method, url, payload or {})
            return {**result, "agent": agent.slug, "action": spec["action"],
                    "url": url}
        except Exception as exc:  # agent down — try CLI, else honest failure
            if self.allow_cli and agent.cli:
                cli = self._cli(agent, spec["action"], payload or {})
                if cli is not None:
                    return {**cli, "agent": agent.slug, "action": spec["action"],
                            "via": "cli"}
            return {"ok": False, "agent": agent.slug, "action": spec["action"],
                    "url": url, "error": f"{type(exc).__name__}: {exc}"}

    def _http(self, method: str, url: str, body: dict) -> dict:
        if method == "GET":
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
        else:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method=method,
                headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return {"ok": 200 <= resp.status < 300, "status": resp.status,
                    "body": parsed}

    def _cli(self, agent: Agent, action: str, payload: dict) -> Optional[dict]:
        cli = agent.cli or {}
        cwd = os.path.join(MODULES_DIR, cli.get("cwd", ""))
        entry = cli.get("entry")
        if not entry or not os.path.isdir(cwd):
            return None
        cmd = [sys.executable, entry, action]
        if payload:
            cmd += ["--json", json.dumps(payload)]
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                  timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"cli {type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "returncode": proc.returncode,
                "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-500:]}


def build_registry(path: str = REGISTRY_PATH) -> AgentRegistry:
    return AgentRegistry(path)


def build_invoker(offline: Optional[bool] = None) -> Invoker:
    if offline is None:
        offline = os.environ.get("EVA_DIRACATRON_OFFLINE") == "1"
    return StubInvoker() if offline else HttpInvoker()


__all__ = [
    "Agent", "AgentRegistry", "Invoker", "StubInvoker", "HttpInvoker",
    "build_registry", "build_invoker", "REGISTRY_PATH",
]
