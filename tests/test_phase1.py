import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jayai.contracts import Limits
from jayai.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": 1}


def test_limits_reject_unbounded_jobs() -> None:
    with pytest.raises(ValidationError):
        Limits(max_steps=0)
