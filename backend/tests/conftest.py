import os
from collections.abc import Generator

os.environ.setdefault(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://resume_job_matcher:change-me-only-local@localhost:5432/resume_job_matcher_test",
    ),
)
os.environ.setdefault(
    "SESSION_SECRET", "test-session-secret-that-is-at-least-thirty-two-characters"
)
os.environ.setdefault("WEB_ORIGIN", "http://localhost:3000")

import pytest
from fastapi.testclient import TestClient

from resume_job_matcher.api.app import app
from resume_job_matcher.infrastructure.db import engine
from resume_job_matcher.infrastructure.models import Base


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> Generator[None]:
    database_name = engine.url.database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("Tests require a dedicated database whose name ends with '_test'")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
