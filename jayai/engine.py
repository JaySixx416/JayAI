"""Bounded state transitions; this phase intentionally executes no tools."""

from uuid import UUID

from jayai.contracts import JobState
from jayai.db import Repository

NEXT: dict[JobState, frozenset[JobState]] = {
    JobState.RECEIVED: frozenset({JobState.PLANNING, JobState.FAILED, JobState.CANCELLED}),
    JobState.PLANNING: frozenset({JobState.WAITING_FOR_APPROVAL, JobState.EXECUTING, JobState.FAILED, JobState.CANCELLED}),
    JobState.WAITING_FOR_APPROVAL: frozenset({JobState.EXECUTING, JobState.CANCELLED}),
    JobState.EXECUTING: frozenset({JobState.OBSERVING, JobState.FAILED, JobState.CANCELLED}),
    JobState.OBSERVING: frozenset({JobState.VERIFYING, JobState.REPLANNING, JobState.FAILED, JobState.CANCELLED}),
    JobState.REPLANNING: frozenset({JobState.WAITING_FOR_APPROVAL, JobState.EXECUTING, JobState.FAILED, JobState.CANCELLED}),
    JobState.VERIFYING: frozenset({JobState.COMPLETED, JobState.REPLANNING, JobState.FAILED, JobState.CANCELLED}),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def validate_transition(current: JobState, target: JobState) -> None:
    if target not in NEXT[current]:
        raise ValueError(f"Invalid transition: {current.value} -> {target.value}")


class Engine:
    def __init__(self, repository: Repository):
        self.repository = repository

    def transition(self, user_id: UUID, job_id: UUID, target: JobState, reason: str) -> JobState:
        if not reason.strip() or len(reason) > 1000:
            raise ValueError("Transition reason must be 1–1000 characters")
        return self.repository.transition_job(user_id, job_id, target, reason)
