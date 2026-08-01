import pytest

from career_job_search.api.context import current_user_id
from career_job_search.recruiters.ollama_client import reset_circuit_breaker


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    current_user_id.set("local-user")
    reset_circuit_breaker()
