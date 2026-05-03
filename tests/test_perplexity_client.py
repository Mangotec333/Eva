import pytest
from pydantic import ValidationError

from services.remote.perplexity import (
    MockPerplexityClient,
    NoopPerplexityClient,
    PerplexityClient,
    PerplexityRequest,
    PerplexityResponse,
    PerplexityStatus,
)


def test_request_round_trip() -> None:
    req = PerplexityRequest(task_id="t1", utterance="hello", context={"a": 1})
    assert req.task_id == "t1"
    assert req.utterance == "hello"
    assert req.context == {"a": 1}
    assert req.constraints == {}


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PerplexityRequest(task_id="t1", utterance="hello", surprise=True)  # type: ignore[call-arg]


def test_response_defaults() -> None:
    resp = PerplexityResponse(task_id="t1", status=PerplexityStatus.COMPLETED)
    assert resp.summary == ""
    assert resp.result == {}
    assert resp.needs_approval is False
    assert resp.error is None


def test_mock_default_completed() -> None:
    client = MockPerplexityClient()
    resp = client.submit(PerplexityRequest(task_id="t1", utterance="ping"))
    assert resp.status is PerplexityStatus.COMPLETED
    assert "ping" in resp.summary
    assert resp.result == {"echo": "ping"}
    assert client.submitted[0].utterance == "ping"


def test_mock_failure_mode() -> None:
    client = MockPerplexityClient(fail=True)
    resp = client.submit(PerplexityRequest(task_id="t2", utterance="boom"))
    assert resp.status is PerplexityStatus.FAILED
    assert resp.error == "mock_failure"


def test_mock_needs_approval_mode() -> None:
    client = MockPerplexityClient(needs_approval=True)
    resp = client.submit(PerplexityRequest(task_id="t3", utterance="rm /"))
    assert resp.status is PerplexityStatus.NEEDS_APPROVAL
    assert resp.needs_approval is True


def test_mock_canned_response_overrides_task_id() -> None:
    canned = PerplexityResponse(
        task_id="ignored",
        status=PerplexityStatus.RUNNING,
        summary="working on it",
        progress=0.5,
    )
    client = MockPerplexityClient(responder=canned)
    resp = client.submit(PerplexityRequest(task_id="real-id", utterance="x"))
    assert resp.task_id == "real-id"
    assert resp.status is PerplexityStatus.RUNNING
    assert resp.progress == 0.5


def test_mock_status_returns_unknown_for_unseen_id() -> None:
    client = MockPerplexityClient()
    resp = client.status("never-submitted")
    assert resp.status is PerplexityStatus.FAILED
    assert resp.error == "unknown_task"


def test_noop_client_always_fails_safely() -> None:
    client = NoopPerplexityClient()
    resp = client.submit(PerplexityRequest(task_id="t9", utterance="anything"))
    assert resp.status is PerplexityStatus.FAILED
    assert resp.error == "no_transport_configured"
    status = client.status("t9")
    assert status.status is PerplexityStatus.FAILED


def test_clients_satisfy_protocol() -> None:
    assert isinstance(MockPerplexityClient(), PerplexityClient)
    assert isinstance(NoopPerplexityClient(), PerplexityClient)
