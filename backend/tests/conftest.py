import os
import sys
import tempfile
from pathlib import Path

# isolated DB per test session, set before the app is imported
_tmpdir = tempfile.mkdtemp(prefix="fulcrum-test-")
os.environ["FULCRUM_DB"] = str(Path(_tmpdir) / "test.db")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine, SessionLocal
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()
