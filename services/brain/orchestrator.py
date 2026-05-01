from __future__ import annotations

from services.brain.policy import route_task
from services.brain.schema import BrainResponse, TaskRequest, TaskStatus
from services.model.provider import ModelProvider


class BrainOrchestrator:
    def __init__(self, model_provider: ModelProvider) -> None:
        self.model_provider = model_provider

    async def handle(self, request: TaskRequest) -> BrainResponse:
        decision = route_task(request.utterance)

        if decision.route == "clarify":
            return BrainResponse(
                task_id=request.task_id,
                status=TaskStatus.NEEDS_CLARIFICATION,
                spoken_summary="I did not catch the request. Please say that again.",
                text="I did not catch the request. Please say that again.",
            )

        if decision.route == "approval":
            draft = (
                "I can help with that, but this action may have an external side effect. "
                "Please approve the exact action before I execute it."
            )
            return BrainResponse(
                task_id=request.task_id,
                status=TaskStatus.NEEDS_APPROVAL,
                spoken_summary=draft,
                text=draft,
                approval_request={
                    "reason": decision.reason,
                    "utterance": request.utterance,
                },
            )

        answer = await self.model_provider.answer(request.utterance)
        return BrainResponse(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            spoken_summary=answer,
            text=answer,
        )

