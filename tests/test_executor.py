from services.brain.executor import ExecutionResult, RouteExecutor
from services.brain.routing import RouteKind, RoutingDecision
from services.remote.perplexity import (
    MockPerplexityClient,
    NoopPerplexityClient,
    PerplexityResponse,
    PerplexityStatus,
)


def _decision(kind: RouteKind) -> RoutingDecision:
    return RoutingDecision(kind=kind, reason="test")


def test_dispatches_perplexity_route_to_client() -> None:
    client = MockPerplexityClient()
    executor = RouteExecutor(perplexity=client)

    result = executor.execute(
        task_id="t1",
        utterance="what's the weather in Berlin",
        decision=_decision(RouteKind.PERPLEXITY_COMPUTER),
        context={"locale": "en"},
    )

    assert isinstance(result, ExecutionResult)
    assert result.task_id == "t1"
    assert result.route is RouteKind.PERPLEXITY_COMPUTER
    assert result.status == "completed"
    assert result.utterance == "what's the weather in Berlin"
    assert result.needs_approval is False
    assert result.error is None
    assert client.submitted[0].context == {"locale": "en"}


def test_perplexity_failure_propagates_error() -> None:
    executor = RouteExecutor(perplexity=MockPerplexityClient(fail=True))
    result = executor.execute(
        task_id="t2",
        utterance="x",
        decision=_decision(RouteKind.PERPLEXITY_COMPUTER),
    )
    assert result.status == "failed"
    assert result.error == "mock_failure"


def test_perplexity_needs_approval_surfaces_flag() -> None:
    executor = RouteExecutor(perplexity=MockPerplexityClient(needs_approval=True))
    result = executor.execute(
        task_id="t3",
        utterance="x",
        decision=_decision(RouteKind.PERPLEXITY_COMPUTER),
    )
    assert result.needs_approval is True
    assert result.status == "needs_approval"


def test_default_executor_uses_noop_client() -> None:
    executor = RouteExecutor()
    result = executor.execute(
        task_id="t4",
        utterance="x",
        decision=_decision(RouteKind.PERPLEXITY_COMPUTER),
    )
    assert result.status == "failed"
    assert result.error == "no_transport_configured"


def test_unimplemented_route_returns_audit_entry() -> None:
    executor = RouteExecutor(perplexity=NoopPerplexityClient())
    result = executor.execute(
        task_id="t5",
        utterance="build me a workflow",
        decision=_decision(RouteKind.DYNAMIC_BUILD),
    )
    assert result.route is RouteKind.DYNAMIC_BUILD
    assert result.status == "not_implemented"
    assert result.error == "route_not_implemented"


def test_executor_passes_canned_summary_through() -> None:
    canned = PerplexityResponse(
        task_id="ignored",
        status=PerplexityStatus.COMPLETED,
        summary="Berlin is 12C and overcast.",
        result={"temp_c": 12},
    )
    executor = RouteExecutor(perplexity=MockPerplexityClient(responder=canned))
    result = executor.execute(
        task_id="t6",
        utterance="weather",
        decision=_decision(RouteKind.PERPLEXITY_COMPUTER),
    )
    assert result.summary == "Berlin is 12C and overcast."
    assert result.result == {"temp_c": 12}
