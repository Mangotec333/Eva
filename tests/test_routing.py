from services.brain.routing import (
    RouteKind,
    RoutingDecision,
    RoutingInput,
    RoutingPolicy,
    RoutingSignals,
    decide_route,
)


def _inp(utterance: str, **kwargs) -> RoutingInput:
    signals = kwargs.pop("signals", RoutingSignals())
    policy = kwargs.pop("policy", RoutingPolicy())
    return RoutingInput(utterance=utterance, signals=signals, policy=policy)


def test_empty_utterance_is_clarify() -> None:
    decision = decide_route(_inp("   "))
    assert decision.kind is RouteKind.CLARIFY
    assert decision.requires_approval is False


def test_reminder_is_local_tool() -> None:
    decision = decide_route(_inp("remind me in 10 seconds to stand up"))
    assert decision.kind is RouteKind.LOCAL_TOOL


def test_high_impact_verb_requires_approval() -> None:
    decision = decide_route(_inp("delete the old logs"))
    assert decision.kind is RouteKind.APPROVAL_REQUIRED
    assert decision.requires_approval is True


def test_high_impact_verb_with_explicit_approval_skips_gate() -> None:
    decision = decide_route(
        _inp(
            "delete the old logs",
            signals=RoutingSignals(
                matches_known_adapter=True,
                user_explicit_approval=True,
            ),
        )
    )
    assert decision.kind is RouteKind.API_ADAPTER


def test_high_impact_verb_beats_reminder_when_unapproved() -> None:
    # An utterance like "remind me to send the email" still mentions
    # "send" — but reminders parser only matches the explicit
    # "remind me in N <unit> to ..." shape, so this falls through to the
    # high-impact gate. We keep that ordering deliberate.
    decision = decide_route(_inp("send the email"))
    assert decision.kind is RouteKind.APPROVAL_REQUIRED


def test_known_adapter_routes_to_api_adapter() -> None:
    decision = decide_route(
        _inp("look up the price of milk", signals=RoutingSignals(matches_known_adapter=True))
    )
    assert decision.kind is RouteKind.API_ADAPTER


def test_fresh_world_knowledge_routes_to_perplexity() -> None:
    decision = decide_route(
        _inp(
            "what happened in the news today",
            signals=RoutingSignals(requires_fresh_world_knowledge=True),
        )
    )
    assert decision.kind is RouteKind.PERPLEXITY_COMPUTER


def test_remote_disabled_falls_back_to_clarify() -> None:
    decision = decide_route(
        _inp(
            "what happened in the news today",
            signals=RoutingSignals(requires_fresh_world_knowledge=True),
            policy=RoutingPolicy(allow_remote=False),
        )
    )
    assert decision.kind is RouteKind.CLARIFY


def test_zero_budget_blocks_remote() -> None:
    decision = decide_route(
        _inp(
            "what happened in the news today",
            signals=RoutingSignals(requires_fresh_world_knowledge=True),
            policy=RoutingPolicy(credit_budget_remaining=0),
        )
    )
    assert decision.kind is RouteKind.CLARIFY


def test_novel_workflow_routes_to_dynamic_build() -> None:
    decision = decide_route(
        _inp(
            "stitch together a script that downloads X and posts a summary",
            signals=RoutingSignals(novel_workflow=True, user_explicit_approval=True),
        )
    )
    assert decision.kind is RouteKind.DYNAMIC_BUILD


def test_dynamic_build_disabled_falls_back_to_clarify() -> None:
    decision = decide_route(
        _inp(
            "do something novel",
            signals=RoutingSignals(novel_workflow=True),
            policy=RoutingPolicy(allow_dynamic_build=False),
        )
    )
    assert decision.kind is RouteKind.CLARIFY


def test_low_budget_blocks_dynamic_build_but_allows_remote() -> None:
    # Budget of 1 covers a remote call but not a dynamic build.
    decision = decide_route(
        _inp(
            "explain quantum tunneling",
            signals=RoutingSignals(
                requires_fresh_world_knowledge=True,
                novel_workflow=True,
            ),
            policy=RoutingPolicy(credit_budget_remaining=1),
        )
    )
    assert decision.kind is RouteKind.PERPLEXITY_COMPUTER


def test_unmatched_safe_request_is_clarify() -> None:
    decision = decide_route(_inp("hello eva"))
    assert decision.kind is RouteKind.CLARIFY


def test_decision_is_immutable_dataclass() -> None:
    decision = decide_route(_inp("hello eva"))
    assert isinstance(decision, RoutingDecision)
    try:
        decision.kind = RouteKind.LOCAL_TOOL  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RoutingDecision should be frozen")
