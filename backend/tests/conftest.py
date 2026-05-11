"""Force test env before any `app` import (pytest loads conftest before test modules)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_fd, _TEST_DB = tempfile.mkstemp(suffix="_ea_control_pytest.db")
os.close(_fd)
_TEST_DB_PATH = Path(_TEST_DB).resolve().as_posix()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

os.environ.setdefault("EA_API_TOKEN", "test_ea_token")
os.environ.setdefault("ADMIN_API_TOKEN", "test_admin_token")
os.environ.setdefault("EA_OFFLINE_SECONDS", "60")
os.environ.setdefault("COMMAND_TIMEOUT_SECONDS", "120")


@pytest.fixture
def client() -> TestClient:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus) -> None:
    try:
        os.remove(_TEST_DB)
    except OSError:
        pass
