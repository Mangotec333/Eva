from __future__ import annotations

from services.brain.policy import route_task
from services.brain.schema import BrainResponse, TaskRequest, TaskStatus
from services.model.provider import ModelProvider
from services.reminders import (
    ParsedReminder,
    ReminderParseError,
    ReminderScheduler,
    parse_reminder,
)


class BrainOrchestrator:
    def __init__(
        self,
        model_provider: ModelProvider,
        reminder_scheduler: ReminderScheduler | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.reminder_scheduler = reminder_scheduler

    async def handle(self, request: TaskRequest) -> BrainResponse:
        decision = route_task(request.utterance)

        if decision.route == "clarify":
            return BrainResponse(
                task_id=request.task_id,
                status=TaskStatus.NEEDS_CLARIFICATION,
                spoken_summary="I did not catch the request. Please say that again.",
                text="I did not catch the request. Please say that again.",
            )

        if decision.route == "reminder":
            return self._handle_reminder(request)

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

    def _handle_reminder(self, request: TaskRequest) -> BrainResponse:
        try:
            parsed = parse_reminder(request.utterance)
        except ReminderParseError as exc:
            text = f"I can set local reminders, but: {exc}"
            return BrainResponse(
                task_id=request.task_id,
                status=TaskStatus.NEEDS_CLARIFICATION,
                spoken_summary=text,
                text=text,
            )

        if self.reminder_scheduler is None:
            text = (
                "Reminders are not available in this run. "
                "Start `eva text` or `eva voice` to schedule local reminders."
            )
            return BrainResponse(
                task_id=request.task_id,
                status=TaskStatus.FAILED_SAFE,
                spoken_summary=text,
                text=text,
            )

        self.reminder_scheduler.schedule(
            delay_seconds=parsed.delay_seconds,
            message=parsed.message,
            job_id=request.task_id,
        )
        confirmation = _confirmation_text(parsed)
        return BrainResponse(
            task_id=request.task_id,
            status=TaskStatus.SCHEDULED,
            spoken_summary=confirmation,
            text=confirmation,
            artifacts=[
                {
                    "kind": "reminder",
                    "delay_seconds": parsed.delay_seconds,
                    "message": parsed.message,
                }
            ],
        )


def _confirmation_text(parsed: ParsedReminder) -> str:
    return f"Okay, in {parsed.describe_delay()} I will remind you to {parsed.message}."
