import pytest

from services.brain.orchestrator import BrainOrchestrator
from services.brain.schema import TaskRequest, TaskStatus
from services.model.provider import HeuristicModelProvider


@pytest.mark.asyncio
async def test_orchestrator_answers_safe_request() -> None:
    brain = BrainOrchestrator(HeuristicModelProvider())
    response = await brain.handle(TaskRequest(utterance="hello eva"))
    assert response.status == TaskStatus.COMPLETED
    assert "EVA Phase 1" in response.text


@pytest.mark.asyncio
async def test_orchestrator_requests_approval_for_side_effect() -> None:
    brain = BrainOrchestrator(HeuristicModelProvider())
    response = await brain.handle(TaskRequest(utterance="delete the old files"))
    assert response.status == TaskStatus.NEEDS_APPROVAL
    assert response.approval_request is not None

