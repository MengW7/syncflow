from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_job_service
from app.core.config import settings
from app.db.session import create_mysql_engine
from app.main import app
from app.repositories.job_repo import JobRepository
from app.services.job_service import JobService
from app.services.queue import queue_service

TEST_QUEUE_KEY = "syncflow:jobs:test"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if settings.mysql_test_database == settings.mysql_database:
        pytest.fail("测试库不能和开发库同名")

    test_engine = create_mysql_engine(settings.mysql_test_database)
    with test_engine.connect() as conn:
        database = conn.execute(text("SELECT DATABASE()")).scalar()
    if database != settings.mysql_test_database:
        test_engine.dispose()
        pytest.fail(f"连接的数据库是 {database}，不是测试库")

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "job_queue_key", TEST_QUEUE_KEY)
    queue_service.client.delete(TEST_QUEUE_KEY)

    def _service() -> JobService:
        return JobService(JobRepository(test_engine))

    app.dependency_overrides[get_job_service] = _service
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, test_engine, upload_dir

    app.dependency_overrides.clear()
    queue_service.client.delete(TEST_QUEUE_KEY)
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_jobs WHERE name LIKE 'pytest-%'"))
    test_engine.dispose()
