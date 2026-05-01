from services.brain.policy import route_task


def test_regular_question_routes_to_answer() -> None:
    decision = route_task("what is my schedule today")
    assert decision.route == "answer"
    assert decision.requires_approval is False


def test_high_impact_action_requires_approval() -> None:
    decision = route_task("send an email to the supplier")
    assert decision.route == "approval"
    assert decision.requires_approval is True


def test_empty_request_clarifies() -> None:
    decision = route_task("")
    assert decision.route == "clarify"

