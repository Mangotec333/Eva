"""Routing-decision executor.

The router (`services/brain/routing.py`) classifies an utterance into a
``RoutingDecision``; this module is the seam that *acts* on that
decision for routes that escape the local tier. Local tools (reminders,
adapters) continue to be handled inside the orchestrator — keeping that
behaviour untouched is a hard requirement for this module.

Today the only remote route this executor implements is
``PERPLEXITY_COMPUTER``. Other remote routes (``DYNAMIC_BUILD``,
``EXTERNAL_AGENT``) currently degrade to a clarify-shaped result so the
shell never silently drops the request; future modules will replace
those branches with real adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.brain.routing import RouteKind, RoutingDecision
from services.remote.perplexity import (
    NoopPerplexityClient,
    PerplexityClient,
    PerplexityRequest,
    PerplexityStatus,
)


@dataclass(frozen=True)
class ExecutionResult:
    """Audit-friendly outcome of dispatching a routing decision.

    The fields here are exactly what the bridge audit log wants — task
    id, route kind, the original utterance, a status string, a human
    summary, the approval flag, and an error string if applicable.
    """

    task_id: str
    route: RouteKind
    utterance: str
    status: str
    summary: str
    needs_approval: bool = False
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


class RouteExecutor:
    """Dispatch a ``RoutingDecision`` to the appropriate tier.

    Local tools are not handled here — callers should invoke the local
    handler before reaching the executor, and only pass remote routes in.
    The executor accepts any ``RouteKind`` defensively so the audit log
    always gets a well-formed entry.
    """

    def __init__(self, perplexity: PerplexityClient | None = None) -> None:
        self._perplexity = perplexity or NoopPerplexityClient()

    def execute(
        self,
        *,
        task_id: str,
        utterance: str,
        decision: RoutingDecision,
        context: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        if decision.kind is RouteKind.PERPLEXITY_COMPUTER:
            return self._dispatch_perplexity(
                task_id=task_id,
                utterance=utterance,
                context=context or {},
                constraints=constraints or {},
            )

        # Routes the executor doesn't (yet) own. The orchestrator should
        # have handled LOCAL_TOOL/CLARIFY/APPROVAL_REQUIRED before
        # calling us; if they reach here, fall through with a stable
        # audit entry so nothing gets silently dropped.
        return ExecutionResult(
            task_id=task_id,
            route=decision.kind,
            utterance=utterance,
            status="not_implemented",
            summary=f"Route {decision.kind.value} is not yet wired to an executor.",
            error="route_not_implemented",
        )

    def _dispatch_perplexity(
        self,
        *,
        task_id: str,
        utterance: str,
        context: dict[str, Any],
        constraints: dict[str, Any],
    ) -> ExecutionResult:
        request = PerplexityRequest(
            task_id=task_id,
            utterance=utterance,
            context=context,
            constraints=constraints,
        )
        response = self._perplexity.submit(request)
        return ExecutionResult(
            task_id=response.task_id,
            route=RouteKind.PERPLEXITY_COMPUTER,
            utterance=utterance,
            status=response.status.value,
            summary=response.summary,
            needs_approval=response.needs_approval
            or response.status is PerplexityStatus.NEEDS_APPROVAL,
            error=response.error,
            result=response.result,
        )
