"""
EVA GHL Agent — GoHighLevel API client (behind a Protocol)
==========================================================

The single place Eva talks to GoHighLevel. Everything routes through the
``GHLClient`` Protocol so the service and tests never depend on the network.

Two implementations:

- ``HttpGHLClient`` — the real client. Uses the LeadConnector v2 REST API
  (base ``https://services.leadconnectorhq.com``). The **primary** auth path is the
  static ``GHL_ACCESS_TOKEN`` env var — a GHL **Location API Key** (``pit-*``/``pi-*``),
  which is long-lived and needs no hourly refresh. In this mode a ``401`` does
  **not** trigger any OAuth refresh (there is nothing to refresh); the client
  emits ``ghl_api_failed`` to the state ledger and fails the call cleanly — no
  retry loop, no refresh storm. OAuth is **optional**: when a
  ``GHL_OAUTH_REFRESH_TOKEN`` (``ghl.oauth``) is configured, a self-refreshing
  ``GHLTokenProvider`` is used instead and a ``401`` forces one refresh + retry,
  emitting ``ghl_oauth_failed`` on a persistent ``401``. Uses ``httpx`` if
  available, else falls back to stdlib ``urllib``. Every method is honest: on a
  limited/unsupported endpoint it returns
  ``{"ok": False, "manual_required": True, ...}`` rather than faking success.

- ``StubGHLClient`` — the offline client used by tests and by the sandbox. Keeps
  all state in memory, is fully idempotent (create-if-absent), and never touches
  the network.

## Base URL

GHL has two API generations:

- **v2 / LeadConnector** — ``https://services.leadconnectorhq.com`` (OAuth 2.0
  Bearer tokens, ``Version`` header). This is the current, supported base and the
  one this client targets.
- **v1 (legacy)** — ``https://rest.gohighlevel.com/v1`` (API-key auth). Being
  deprecated; not used here.

The primary auth is a v2 Location API Key, so v2 is the correct base.

See the README "Known GHL API Limitations" section for endpoints that are
UI-only (notably workflow creation and, on many plans, email/SMS template
creation) and how this client degrades gracefully for them.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from oauth import GHLOAuthError, GHLTokenProvider, build_token_provider

logger = logging.getLogger("eva.ghl.client")

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class GHLClient(Protocol):
    """The GoHighLevel surface Eva needs. All methods return plain dicts."""

    # -- one-time build (Part 1) --------------------------------------------
    def list_pipelines(self) -> list[dict]: ...
    def create_pipeline(self, name: str, stages: list[str]) -> dict: ...
    def list_calendars(self) -> list[dict]: ...
    def create_calendar(self, name: str) -> dict: ...
    def list_custom_fields(self) -> list[dict]: ...
    def create_custom_field(self, name: str, field_key: str,
                            default_value: str = "") -> dict: ...
    def list_templates(self) -> list[dict]: ...
    def create_template(self, name: str, channel: str, subject: str,
                        body: str) -> dict: ...
    def list_workflows(self) -> list[dict]: ...
    def create_workflow(self, name: str, trigger_tag: str,
                        template_ids: list[str]) -> dict: ...

    # -- ongoing capture loop (Part 2) --------------------------------------
    def upsert_contact(self, *, email: str = "", name: str = "", phone: str = "",
                       tags: Optional[list[str]] = None,
                       source: str = "") -> dict: ...
    def add_contact_tag(self, contact_id: str, tag: str) -> dict: ...
    def add_contact_to_pipeline(self, contact_id: str, pipeline_id: str,
                                stage_id: str) -> dict: ...
    def add_contact_to_workflow(self, contact_id: str, workflow_id: str) -> dict: ...

    # -- reporting ----------------------------------------------------------
    def count_contacts_by_tag(self, tag: str) -> dict: ...


# ---------------------------------------------------------------------------
# Offline stub (tests + sandbox)
# ---------------------------------------------------------------------------

class StubGHLClient:
    """In-memory, network-free GHL. Idempotent create-if-absent everywhere."""

    def __init__(self, *, workflow_supported: bool = True,
                 template_supported: bool = True) -> None:
        self.pipelines: list[dict] = []
        self.calendars: list[dict] = []
        self.custom_fields: list[dict] = []
        self.templates: list[dict] = []
        self.workflows: list[dict] = []
        self.contacts: dict[str, dict] = {}
        self.opportunities: list[dict] = []
        self.workflow_enrollments: list[dict] = []
        # Toggle to simulate GHL plans where these endpoints are UI-only.
        self.workflow_supported = workflow_supported
        self.template_supported = template_supported

    # -- build --------------------------------------------------------------
    def list_pipelines(self) -> list[dict]:
        return list(self.pipelines)

    def create_pipeline(self, name: str, stages: list[str]) -> dict:
        for p in self.pipelines:
            if p["name"] == name:
                return {**p, "action": "skipped"}
        pid = f"pipe_{uuid.uuid4().hex[:8]}"
        stage_objs = [{"id": f"stage_{uuid.uuid4().hex[:6]}", "name": s}
                      for s in stages]
        p = {"id": pid, "name": name, "stages": stage_objs, "action": "created"}
        self.pipelines.append({k: v for k, v in p.items() if k != "action"})
        return p

    def list_calendars(self) -> list[dict]:
        return list(self.calendars)

    def create_calendar(self, name: str) -> dict:
        for c in self.calendars:
            if c["name"] == name:
                return {**c, "action": "skipped"}
        cid = f"cal_{uuid.uuid4().hex[:8]}"
        link = f"https://api.leadconnectorhq.com/widget/booking/{cid}"
        c = {"id": cid, "name": name, "booking_link": link}
        self.calendars.append(c)
        return {**c, "action": "created"}

    def list_custom_fields(self) -> list[dict]:
        return list(self.custom_fields)

    def create_custom_field(self, name: str, field_key: str,
                            default_value: str = "") -> dict:
        for f in self.custom_fields:
            if f["field_key"] == field_key:
                return {**f, "action": "skipped"}
        fid = f"cf_{uuid.uuid4().hex[:8]}"
        f = {"id": fid, "name": name, "field_key": field_key,
             "default_value": default_value}
        self.custom_fields.append(f)
        return {**f, "action": "created"}

    def list_templates(self) -> list[dict]:
        return list(self.templates)

    def create_template(self, name: str, channel: str, subject: str,
                        body: str) -> dict:
        if not self.template_supported:
            return {"ok": False, "manual_required": True, "name": name,
                    "channel": channel,
                    "reason": "template creation is UI-only on this GHL plan"}
        for t in self.templates:
            if t["name"] == name:
                return {**t, "action": "skipped"}
        tid = f"tmpl_{uuid.uuid4().hex[:8]}"
        t = {"id": tid, "name": name, "channel": channel, "subject": subject,
             "body": body}
        self.templates.append(t)
        return {**t, "action": "created"}

    def list_workflows(self) -> list[dict]:
        return list(self.workflows)

    def create_workflow(self, name: str, trigger_tag: str,
                        template_ids: list[str]) -> dict:
        if not self.workflow_supported:
            return {"ok": False, "manual_required": True, "name": name,
                    "trigger_tag": trigger_tag,
                    "reason": "workflow creation is UI-only in the GHL API"}
        for w in self.workflows:
            if w["name"] == name:
                return {**w, "action": "skipped"}
        wid = f"wf_{uuid.uuid4().hex[:8]}"
        w = {"id": wid, "name": name, "trigger_tag": trigger_tag,
             "template_ids": list(template_ids)}
        self.workflows.append(w)
        return {**w, "action": "created"}

    # -- capture ------------------------------------------------------------
    def upsert_contact(self, *, email: str = "", name: str = "", phone: str = "",
                       tags: Optional[list[str]] = None,
                       source: str = "") -> dict:
        if not email and not phone:
            raise ValueError("GHL requires email or phone to upsert a contact")
        key = (email or phone).lower()
        existing = self.contacts.get(key)
        if existing:
            merged = set(existing.get("tags", [])) | set(tags or [])
            existing["tags"] = sorted(merged)
            if name:
                existing["name"] = name
            return {**existing, "action": "updated"}
        cid = f"contact_{uuid.uuid4().hex[:8]}"
        c = {"id": cid, "email": email, "name": name, "phone": phone,
             "tags": sorted(set(tags or [])), "source": source}
        self.contacts[key] = c
        return {**c, "action": "created"}

    def add_contact_tag(self, contact_id: str, tag: str) -> dict:
        for c in self.contacts.values():
            if c["id"] == contact_id:
                if tag not in c["tags"]:
                    c["tags"] = sorted(set(c["tags"]) | {tag})
                return {"ok": True, "contact_id": contact_id, "tags": c["tags"]}
        return {"ok": False, "error": f"unknown contact {contact_id}"}

    def add_contact_to_pipeline(self, contact_id: str, pipeline_id: str,
                                stage_id: str) -> dict:
        for o in self.opportunities:
            if o["contact_id"] == contact_id and o["pipeline_id"] == pipeline_id:
                return {**o, "action": "skipped"}
        oid = f"opp_{uuid.uuid4().hex[:8]}"
        o = {"id": oid, "contact_id": contact_id, "pipeline_id": pipeline_id,
             "stage_id": stage_id}
        self.opportunities.append(o)
        return {**o, "action": "created"}

    def add_contact_to_workflow(self, contact_id: str, workflow_id: str) -> dict:
        for e in self.workflow_enrollments:
            if e["contact_id"] == contact_id and e["workflow_id"] == workflow_id:
                return {**e, "action": "skipped"}
        e = {"contact_id": contact_id, "workflow_id": workflow_id}
        self.workflow_enrollments.append(e)
        return {**e, "action": "created"}

    def count_contacts_by_tag(self, tag: str) -> dict:
        count = sum(1 for c in self.contacts.values() if tag in c.get("tags", []))
        return {"ok": True, "tag": tag, "count": count}


# ---------------------------------------------------------------------------
# Real HTTP client
# ---------------------------------------------------------------------------

class GHLAuthError(RuntimeError):
    pass


class HttpGHLClient:
    """Live LeadConnector v2 client. Bearer token from a Location API Key.

    **Primary auth** is the static ``GHL_ACCESS_TOKEN`` (a GHL Location API Key,
    ``pit-*``/``pi-*``) — long-lived, so no hourly refresh is needed. In this mode
    a ``401`` does **not** attempt any OAuth refresh (there is no refresh token);
    it emits ``ghl_api_failed`` to the state ledger and fails the call cleanly —
    no loop, no retry storm.

    **Optional OAuth:** when a ``GHLTokenProvider`` is supplied (i.e. an
    ``ghl.oauth`` refresh token is configured) the Authorization token is a
    self-refreshing OAuth access token; a ``401`` then forces one refresh and
    retries once, emitting ``ghl_oauth_failed`` on a persistent ``401`` rather
    than crashing.

    Uses ``httpx`` when installed, else stdlib ``urllib.request``. Endpoints that
    GHL exposes only in the UI (workflow creation; template creation on some
    plans) return an honest ``manual_required`` dict instead of raising.
    """

    def __init__(self, *, access_token: Optional[str] = None,
                 location_id: Optional[str] = None,
                 token_provider: Optional[GHLTokenProvider] = None,
                 state: Optional[Any] = None,
                 base_url: str = GHL_API_BASE, timeout: float = 30.0) -> None:
        self.token_provider = token_provider
        self.state = state
        self.access_token = access_token or os.environ.get("GHL_ACCESS_TOKEN", "")
        self.location_id = location_id or os.environ.get("GHL_LOCATION_ID", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if self.token_provider is None:
            if not self.access_token:
                raise GHLAuthError(
                    "no GHL Location API Key and GHL_ACCESS_TOKEN is unset — "
                    "the live client needs a static Location API Key "
                    "(GHL_ACCESS_TOKEN) or an OAuth refresh_token")
            logger.info(
                "GHL: using static GHL_ACCESS_TOKEN (Location API Key) as the "
                "primary auth — long-lived, no hourly refresh needed")

    # -- transport ----------------------------------------------------------
    def _current_token(self) -> str:
        if self.token_provider is not None:
            try:
                return self.token_provider.get_access_token()
            except GHLOAuthError as exc:
                logger.warning("GHL: could not obtain OAuth access token: %s", exc)
                return ""
        return self.access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._current_token()}",
            "Version": GHL_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, *,
                 params: Optional[dict] = None,
                 body: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        result = self._send(method, url, params=params, body=body)
        if result.get("status") == 401:
            if self.token_provider is not None:
                # OAuth is configured: force a single refresh and retry once.
                logger.info("GHL: 401 on %s — forcing OAuth refresh + retry", path)
                try:
                    self.token_provider.force_refresh()
                except GHLOAuthError as exc:
                    logger.warning("GHL: forced refresh failed: %s", exc)
                result = self._send(method, url, params=params, body=body)
                if result.get("status") == 401:
                    self._emit_oauth_failed(path, result)
            else:
                # Static Location API Key only: there is nothing to refresh, so we
                # must NOT loop. Emit ghl_api_failed and fail the call cleanly.
                self._emit_api_failed(path, result)
        return result

    def _send(self, method: str, url: str, *,
              params: Optional[dict] = None,
              body: Optional[dict] = None) -> dict:
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=self._headers(),
                                      params=params, json=body)
                return self._parse(resp.status_code, resp.text)
        except ImportError:
            return self._request_urllib(method, url, params=params, body=body)

    def _emit_oauth_failed(self, path: str, result: dict) -> None:
        logger.error("GHL: persistent 401 on %s after OAuth refresh", path)
        if self.state is None:
            return
        try:
            self.state.emit(
                event_type="ghl_oauth_failed",
                summary=f"GHL OAuth failed: still 401 on {path} after refresh",
                payload={"path": path, "status": result.get("status")})
        except Exception as exc:  # emitting must never crash the call
            logger.warning("GHL: could not emit ghl_oauth_failed: %s", exc)

    def _emit_api_failed(self, path: str, result: dict) -> None:
        # Static Location API Key path: a 401 means the key is bad/revoked. There
        # is no refresh token, so we log + emit and stop — no retry loop.
        logger.error("GHL: 401 on %s with a static Location API Key — the key is "
                     "invalid or revoked; not retrying", path)
        if self.state is None:
            return
        try:
            self.state.emit(
                event_type="ghl_api_failed",
                summary=f"GHL API failed: 401 on {path} (static Location API Key)",
                payload={"path": path, "status": result.get("status"),
                         "auth": "static_location_api_key"})
        except Exception as exc:  # emitting must never crash the call
            logger.warning("GHL: could not emit ghl_api_failed: %s", exc)

    def _request_urllib(self, method: str, url: str, *,
                        params: Optional[dict] = None,
                        body: Optional[dict] = None) -> dict:
        import urllib.error
        import urllib.parse
        import urllib.request

        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return self._parse(resp.status, resp.read().decode())
        except urllib.error.HTTPError as exc:
            return self._parse(exc.code, exc.read().decode())
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"network error: {exc}"}

    @staticmethod
    def _parse(status: int, text: str) -> dict:
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"raw": text}
        ok = 200 <= status < 300
        if isinstance(payload, list):
            payload = {"items": payload}
        return {"ok": ok, "status": status, **payload}

    # -- build --------------------------------------------------------------
    def list_pipelines(self) -> list[dict]:
        r = self._request("GET", "/opportunities/pipelines",
                          params={"locationId": self.location_id})
        return r.get("pipelines") or r.get("items") or []

    def create_pipeline(self, name: str, stages: list[str]) -> dict:
        # Pipeline creation is not exposed on the public v2 API on most plans.
        body = {
            "locationId": self.location_id,
            "name": name,
            "stages": [{"name": s, "position": i} for i, s in enumerate(stages)],
        }
        r = self._request("POST", "/opportunities/pipelines", body=body)
        if not r.get("ok"):
            return {"ok": False, "manual_required": True, "name": name,
                    "reason": "pipeline creation may be UI-only on this GHL plan",
                    "detail": r}
        pipe = r.get("pipeline", r)
        return {**pipe, "action": "created"}

    def list_calendars(self) -> list[dict]:
        r = self._request("GET", "/calendars/",
                          params={"locationId": self.location_id})
        return r.get("calendars") or r.get("items") or []

    def create_calendar(self, name: str) -> dict:
        body = {"locationId": self.location_id, "name": name,
                "slug": name.lower().replace(" ", "-")}
        r = self._request("POST", "/calendars/", body=body)
        if not r.get("ok"):
            return {"ok": False, "manual_required": True, "name": name,
                    "reason": "calendar creation failed or is restricted",
                    "detail": r}
        cal = r.get("calendar", r)
        cid = cal.get("id", "")
        cal.setdefault("booking_link",
                       f"https://api.leadconnectorhq.com/widget/booking/{cid}")
        return {**cal, "action": "created"}

    def list_custom_fields(self) -> list[dict]:
        r = self._request("GET", f"/locations/{self.location_id}/customFields")
        return r.get("customFields") or r.get("items") or []

    def create_custom_field(self, name: str, field_key: str,
                            default_value: str = "") -> dict:
        body = {"name": name, "dataType": "TEXT", "fieldKey": field_key}
        r = self._request("POST",
                          f"/locations/{self.location_id}/customFields", body=body)
        if not r.get("ok"):
            return {"ok": False, "manual_required": True, "name": name,
                    "field_key": field_key, "detail": r}
        cf = r.get("customField", r)
        return {**cf, "action": "created"}

    def list_templates(self) -> list[dict]:
        r = self._request("GET", "/emails/builder",
                          params={"locationId": self.location_id})
        return r.get("templates") or r.get("items") or []

    def create_template(self, name: str, channel: str, subject: str,
                        body: str) -> dict:
        # Template/campaign creation is largely UI-only in the public v2 API.
        return {"ok": False, "manual_required": True, "name": name,
                "channel": channel,
                "reason": "email/SMS template creation is UI-only in the GHL API; "
                          "copy is generated by campaign.py and must be pasted in"}

    def list_workflows(self) -> list[dict]:
        r = self._request("GET", "/workflows/",
                          params={"locationId": self.location_id})
        return r.get("workflows") or r.get("items") or []

    def create_workflow(self, name: str, trigger_tag: str,
                        template_ids: list[str]) -> dict:
        # Workflow creation is UI-only — the API is read-only for workflows.
        return {"ok": False, "manual_required": True, "name": name,
                "trigger_tag": trigger_tag,
                "reason": "workflow creation is UI-only in the GHL API; build the "
                          f"tag-triggered ({trigger_tag}) workflow in the UI"}

    # -- capture ------------------------------------------------------------
    def upsert_contact(self, *, email: str = "", name: str = "", phone: str = "",
                       tags: Optional[list[str]] = None,
                       source: str = "") -> dict:
        if not email and not phone:
            raise ValueError("GHL requires email or phone to upsert a contact")
        body: dict[str, Any] = {"locationId": self.location_id}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if name:
            body["name"] = name
        if tags:
            body["tags"] = tags
        if source:
            body["source"] = source
        r = self._request("POST", "/contacts/upsert", body=body)
        contact = r.get("contact", r)
        return {**contact, "action": "upserted" if r.get("ok") else "failed",
                "ok": r.get("ok", False)}

    def add_contact_tag(self, contact_id: str, tag: str) -> dict:
        r = self._request("POST", f"/contacts/{contact_id}/tags",
                          body={"tags": [tag]})
        return {"ok": r.get("ok", False), "contact_id": contact_id, "detail": r}

    def add_contact_to_pipeline(self, contact_id: str, pipeline_id: str,
                                stage_id: str) -> dict:
        body = {
            "locationId": self.location_id,
            "contactId": contact_id,
            "pipelineId": pipeline_id,
            "pipelineStageId": stage_id,
            "status": "open",
            "name": "Eva Acquisition lead",
        }
        r = self._request("POST", "/opportunities/", body=body)
        opp = r.get("opportunity", r)
        return {**opp, "ok": r.get("ok", False),
                "action": "created" if r.get("ok") else "failed"}

    def add_contact_to_workflow(self, contact_id: str, workflow_id: str) -> dict:
        r = self._request("POST",
                          f"/contacts/{contact_id}/workflow/{workflow_id}",
                          body={})
        return {"ok": r.get("ok", False), "contact_id": contact_id,
                "workflow_id": workflow_id, "detail": r}

    def count_contacts_by_tag(self, tag: str) -> dict:
        # POST /contacts/search returns a `total` for the given filter, so we can
        # count without paging through every contact. `pageLimit: 1` keeps the
        # payload tiny — only the count matters.
        body = {
            "locationId": self.location_id,
            "page": 1,
            "pageLimit": 1,
            "filters": [{"field": "tags", "operator": "contains", "value": tag}],
        }
        r = self._request("POST", "/contacts/search", body=body)
        total = r.get("total")
        if total is None:
            total = (r.get("meta") or {}).get("total")
        if r.get("ok") and total is not None:
            return {"ok": True, "tag": tag, "count": int(total)}
        return {"ok": False, "tag": tag, "count": None,
                "reason": "contacts/search did not return a total for this tag",
                "detail": r}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def is_offline() -> bool:
    """Offline when forced, or when neither OAuth creds nor a static token exist."""
    if os.environ.get("EVA_GHL_OFFLINE") == "1":
        return True
    from oauth import has_oauth_config

    if has_oauth_config():
        return False
    return not os.environ.get("GHL_ACCESS_TOKEN")


def build_client(offline: Optional[bool] = None,
                 state: Optional[Any] = None,
                 db_path: Optional[str] = None) -> GHLClient:
    """Return the live client when credentials exist, else the offline stub.

    Live mode uses the static ``GHL_ACCESS_TOKEN`` (a GHL Location API Key) as the
    primary auth. OAuth is optional: only when an ``ghl.oauth`` refresh token is
    configured is a self-refreshing ``GHLTokenProvider`` built and used instead.
    """
    use_stub = is_offline() if offline is None else offline
    if use_stub:
        return StubGHLClient()
    kwargs: dict[str, Any] = {}
    if db_path is not None:
        kwargs["db_path"] = db_path
    provider = build_token_provider(offline=False, **kwargs)
    location_id = provider.config.get("location_id", "") if provider else ""
    return HttpGHLClient(token_provider=provider, state=state,
                         location_id=location_id or None)


__all__ = [
    "GHLClient",
    "StubGHLClient",
    "HttpGHLClient",
    "GHLAuthError",
    "build_client",
    "is_offline",
    "GHL_API_BASE",
    "GHL_API_VERSION",
]
