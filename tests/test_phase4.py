from uuid import uuid4

import pytest

from jayai.contracts import JobState
from jayai.engine import Engine, validate_transition


def test_transition_graph_rejects_skips_and_terminal_reentry():
    validate_transition(JobState.RECEIVED, JobState.PLANNING)
    validate_transition(JobState.VERIFYING, JobState.COMPLETED)
    with pytest.raises(ValueError):
        validate_transition(JobState.RECEIVED, JobState.COMPLETED)
    with pytest.raises(ValueError):
        validate_transition(JobState.CANCELLED, JobState.EXECUTING)


def test_engine_rejects_empty_reason_without_store_call():
    class NeverCalled:
        def transition_job(self, *args):
            raise AssertionError("store called")

    with pytest.raises(ValueError):
        Engine(NeverCalled()).transition(uuid4(), uuid4(), JobState.PLANNING, " ")
