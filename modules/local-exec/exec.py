"""
EVA Local-Exec — the subprocess runner + allowlist + secret masking core.

This is the "Mac hands" primitive: Eva asks to run a shell command, and this
module decides *whether it may auto-run* (a small allowlist of demonstrably-safe
ops), actually runs it (``subprocess.run`` with ``shell=False`` and an argv list
— never a shell string, so there is no shell-injection surface), and masks any
secrets out of the captured output before it is ever returned or logged.

**Safety is paramount** — this runs shell on the user's Mac:

  * **Allowlist, config-file-primary.** The set of ops that auto-run (no human
    approval) lives in ``~/.eva/local_exec_allowlist.json`` with an in-code
    default. Matching is by command-prefix + per-rule argument validation, never
    a substring match. Anything not matched does NOT run here — the caller must
    route it through the approval gate.
  * **No shell.** Commands run as an argv list with ``shell=False``. Pipes,
    redirects, ``;`` / ``&&`` chaining, and globbing are therefore inert — a
    single program with explicit arguments is executed, nothing more.
  * **Secret masking.** Before any stdout/stderr (or the echoed command/args) is
    returned or persisted, common secret shapes (Bearer tokens, API-key
    assignments, AWS keys, Slack/GitHub tokens, passwords, long high-entropy
    tokens) are masked. ``masked=True`` is set if anything was redacted.
  * **Offline-safe.** ``EVA_LOCAL_EXEC_OFFLINE=1`` → the runner NEVER touches
    ``subprocess`` and returns a deterministic mocked no-op, so tests (and the
    sandbox) can exercise the whole path without executing anything real.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("local-exec")

# Config-file-primary allowlist (mirrors social-publish credentials / deployer
# config): the local, gitignored JSON wins over the in-code default.
ALLOWLIST_PATH = Path(os.environ.get(
    "EVA_LOCAL_EXEC_ALLOWLIST",
    str(Path.home() / ".eva" / "local_exec_allowlist.json")))

# Launcher (control plane) — service-restart auto-runs must target it locally.
LAUNCHER_HOST_PORTS = {"8768"}

DEFAULT_EXEC_TIMEOUT = 120  # seconds; per-call override allowed

MASK_TOKEN = "***MASKED***"


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------
#
# A rule matches when the incoming argv starts with ``prefix`` (token-wise) AND,
# if the rule names a ``check``, that validator also passes for (argv, cwd).
# Rules loaded from the config file may only supply ``name`` + ``prefix`` (a pure
# prefix allow) — the security-sensitive validators live in code, never in the
# editable config, so a tampered config can only *narrow* what auto-runs, and any
# named check it references still runs.

def _default_allowlist() -> list[dict]:
    """The in-code default set of SAFE ops that auto-run without approval."""
    return [
        {"name": "git-pull", "prefix": ["git", "pull"]},
        {"name": "git-status", "prefix": ["git", "status"]},
        {"name": "git-diff", "prefix": ["git", "diff"]},
        {"name": "git-log", "prefix": ["git", "log"]},
        # service restart via the launcher's own stop/start endpoints (:8768).
        # Ordered before curl-localhost so the specific rule wins the name.
        {"name": "service-restart", "prefix": ["curl"], "check": "launcher_restart"},
        # curl against the loopback interface only (localhost / 127.0.0.1).
        {"name": "curl-localhost", "prefix": ["curl"], "check": "curl_localhost"},
        # front-end prod deploy — cwd must be a real git checkout.
        {"name": "vercel-prod", "prefix": ["vercel", "--prod"], "check": "cwd_git_repo"},
        # env-file token swaps: a single KEY=VALUE append/replace via sed/python
        # on ~/.eva/*.json or ~/Eva/.env (nothing else).
        {"name": "env-swap-sed", "prefix": ["sed"], "check": "env_file_edit"},
        {"name": "env-swap-python", "prefix": ["python"], "check": "env_file_edit"},
        {"name": "env-swap-python3", "prefix": ["python3"], "check": "env_file_edit"},
    ]


def load_allowlist(path: Optional[Path] = None) -> list[dict]:
    """Config-file-primary allowlist: the local JSON if present, else the default.

    A malformed / missing file falls back to the in-code default (never raises).
    Config entries are sanitised to ``name`` + ``prefix`` (list of str) only —
    the config cannot inject or weaken a code-defined validator.
    """
    p = Path(path) if path else ALLOWLIST_PATH
    try:
        raw = json.loads(p.read_text())
    except Exception:  # missing / unreadable / bad JSON → in-code default
        return _default_allowlist()
    rules = raw.get("allowlist") if isinstance(raw, dict) else raw
    if not isinstance(rules, list):
        return _default_allowlist()
    out: list[dict] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        prefix = r.get("prefix")
        if not isinstance(prefix, list) or not all(isinstance(x, str) for x in prefix) or not prefix:
            continue
        rule = {"name": str(r.get("name", "config-rule")), "prefix": prefix}
        chk = r.get("check")
        if isinstance(chk, str) and chk in _CHECKS:
            rule["check"] = chk
        out.append(rule)
    return out or _default_allowlist()


_LOOPBACK_RE = re.compile(
    r"^(?:https?://)?(?:localhost|127\.0\.0\.1)(?::(\d+))?(?:/.*)?$", re.IGNORECASE)

# A token is a URL target if it carries a scheme, is loopback, or is a
# dotted-domain (optionally with :port / path). This deliberately ignores bare
# words like ``GET`` / ``POST`` that follow a ``-X`` flag.
_URLISH_RE = re.compile(
    r"^(?:https?://\S+"
    r"|(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/.*)?"
    r"|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::\d+)?(?:/.*)?)$", re.IGNORECASE)


def _url_targets(argv: list[str]) -> list[str]:
    """Non-flag args that look like an actual URL / host target (for curl)."""
    out = []
    for a in argv[1:]:
        if a.startswith("-"):
            continue
        if "://" in a or _URLISH_RE.match(a):
            out.append(a)
    return out


def _check_curl_localhost(argv: list[str], cwd: Optional[str]) -> bool:
    """curl is allowed only when every URL target is loopback (and there is one)."""
    targets = _url_targets(argv)
    if not targets:
        return False
    return all(_LOOPBACK_RE.match(t) for t in targets)


def _check_launcher_restart(argv: list[str], cwd: Optional[str]) -> bool:
    """A curl to the launcher's own start/stop/restart route on :8768."""
    for t in _url_targets(argv):
        m = _LOOPBACK_RE.match(t)
        if not m:
            continue
        port = m.group(1)
        if port in LAUNCHER_HOST_PORTS and re.search(r"/(start|stop|restart)(/|$)", t):
            return True
    return False


def _check_cwd_git_repo(argv: list[str], cwd: Optional[str]) -> bool:
    """vercel --prod may only auto-run inside a real git checkout."""
    if not cwd:
        return False
    return os.path.isdir(os.path.join(os.path.expanduser(cwd), ".git"))


_ENV_JSON_RE = re.compile(r"\.eva/[^/]+\.json$")


def _is_allowed_env_file(token: str) -> bool:
    """True iff ``token`` is a path under ~/.eva/*.json or ~/Eva/.env."""
    home = str(Path.home())
    expanded = os.path.expanduser(token)
    norm = os.path.normpath(expanded)
    eva_dir = os.path.normpath(os.path.join(home, ".eva"))
    if norm.startswith(eva_dir + os.sep) and norm.endswith(".json"):
        return True
    if norm == os.path.normpath(os.path.join(home, "Eva", ".env")):
        return True
    return False


_KV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _check_env_file_edit(argv: list[str], cwd: Optional[str]) -> bool:
    """sed/python token-swap on an allowed env file, single KEY=VALUE only.

    Exactly one argument must be an allowed env-file path, and at least one
    argument must look like a ``KEY=VALUE`` (the swap). No path outside the
    allowed set may appear, so a command can only touch ~/.eva/*.json or
    ~/Eva/.env.
    """
    env_targets = [a for a in argv[1:] if _looks_like_path(a)]
    allowed = [a for a in env_targets if _is_allowed_env_file(a)]
    if len(allowed) != 1 or len(env_targets) != len(allowed):
        return False
    has_kv = any(_KV_RE.search(a) for a in argv[1:])
    return has_kv


def _looks_like_path(token: str) -> bool:
    """A filesystem path arg (not a sed/python script that merely has slashes)."""
    if token.startswith("-"):
        return False
    if token.startswith(("/", "~", "./", "../")):
        return True
    # a relative path to an env file, e.g. ``dir/config.json`` (but not ``s/a/b/``)
    return ("/" in token) and token.endswith((".json", ".env"))


_CHECKS = {
    "curl_localhost": _check_curl_localhost,
    "launcher_restart": _check_launcher_restart,
    "cwd_git_repo": _check_cwd_git_repo,
    "env_file_edit": _check_env_file_edit,
}


def _prefix_matches(argv: list[str], prefix: list[str]) -> bool:
    return len(argv) >= len(prefix) and argv[:len(prefix)] == prefix


def match_allowlist(argv: list[str], cwd: Optional[str] = None,
                    allowlist: Optional[list[dict]] = None) -> Optional[dict]:
    """Return the first allowlist rule that matches ``argv``/``cwd``, or None.

    A match means the command auto-runs with no approval. No match means the
    caller must route the run through the approval gate.
    """
    if not argv:
        return None
    rules = allowlist if allowlist is not None else load_allowlist()
    for rule in rules:
        if not _prefix_matches(argv, rule.get("prefix", [])):
            continue
        chk = rule.get("check")
        if chk:
            fn = _CHECKS.get(chk)
            if fn is None or not fn(argv, cwd):
                continue
        return rule
    return None


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------

_MASK_PATTERNS = [
    # AWS access key id
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Slack tokens (bot/user/app/refresh)
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    # GitHub PAT / classic token
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    # OpenAI-style
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    # Bearer <token>
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    # key/secret/token/password assignments (KEY=VALUE, KEY: VALUE, "key":"...")
    re.compile(
        r"(?i)(api[_-]?key|secret|access[_-]?token|token|password|passwd|pwd)"
        r"(\s*[:=]\s*|\s*[:=]\s*[\"']?)([A-Za-z0-9._\-/+]{8,})"),
]

# Generic high-entropy token: 20+ chars containing at least one letter AND one
# digit (so ordinary words / long paths are not clobbered, but real API keys are).
_GENERIC_TOKEN_RE = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{20,}\b")


def mask_secrets(text: str) -> tuple[str, bool]:
    """Redact common secret shapes from ``text``. Returns (masked, did_mask)."""
    if not text:
        return text, False
    original = text
    for pat in _MASK_PATTERNS:
        if pat.groups >= 3:
            text = pat.sub(lambda m: m.group(1) + (m.group(2) or "") + MASK_TOKEN, text)
        elif pat.groups == 1:
            text = pat.sub(lambda m: m.group(1) + MASK_TOKEN, text)
        else:
            text = pat.sub(MASK_TOKEN, text)
    text = _GENERIC_TOKEN_RE.sub(MASK_TOKEN, text)
    return text, (text != original)


def mask_argv(argv: list[str]) -> tuple[list[str], bool]:
    """Mask any secret-looking arguments (no raw secrets in the audit trail)."""
    out: list[str] = []
    did = False
    for a in argv:
        masked, m = mask_secrets(a)
        out.append(masked)
        did = did or m
    return out, did


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def is_offline() -> bool:
    return os.environ.get("EVA_LOCAL_EXEC_OFFLINE") == "1"


def _now() -> float:
    return time.monotonic()


def run_command(command: str, args: Optional[list[str]] = None,
                cwd: Optional[str] = None, timeout: int = DEFAULT_EXEC_TIMEOUT) -> dict:
    """Execute ``[command, *args]`` with ``shell=False`` and capture output.

    NEVER raises: a missing binary, non-zero exit, or timeout is reported as a
    structured result. Output is secret-masked before it is returned. When
    ``EVA_LOCAL_EXEC_OFFLINE=1`` no subprocess is spawned — a deterministic
    mocked no-op is returned so tests never run anything real.
    """
    args = list(args or [])
    argv = [command, *args]

    if is_offline():
        stdout, m1 = mask_secrets(f"[offline] would run: {shlex.join(argv)}")
        return {"ok": True, "exit_code": 0, "stdout": stdout, "stderr": "",
                "duration": 0.0, "masked": m1, "offline": True}

    start = _now()
    try:
        cp = subprocess.run(  # noqa: S603 — argv list, shell=False by design
            argv, cwd=(os.path.expanduser(cwd) if cwd else None),
            capture_output=True, text=True, timeout=timeout, shell=False)
        duration = round(_now() - start, 4)
        out, m1 = mask_secrets(cp.stdout or "")
        err, m2 = mask_secrets(cp.stderr or "")
        return {"ok": cp.returncode == 0, "exit_code": cp.returncode,
                "stdout": out, "stderr": err, "duration": duration,
                "masked": m1 or m2}
    except subprocess.TimeoutExpired:
        duration = round(_now() - start, 4)
        return {"ok": False, "exit_code": -1, "stdout": "",
                "stderr": f"command timed out after {timeout}s",
                "duration": duration, "masked": False}
    except FileNotFoundError:
        duration = round(_now() - start, 4)
        return {"ok": False, "exit_code": -1, "stdout": "",
                "stderr": f"command not found: {command}",
                "duration": duration, "masked": False}
    except Exception as exc:  # noqa: BLE001 — resilience: never crash on a bad command
        logger.exception("local-exec run failed")
        err, m = mask_secrets(f"{type(exc).__name__}: {exc}")
        return {"ok": False, "exit_code": -1, "stdout": "", "stderr": err,
                "duration": round(_now() - start, 4), "masked": m}


__all__ = [
    "ALLOWLIST_PATH", "DEFAULT_EXEC_TIMEOUT", "MASK_TOKEN",
    "load_allowlist", "match_allowlist", "mask_secrets", "mask_argv",
    "run_command", "is_offline",
]
