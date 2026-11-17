import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.api.dashboard_api import get_store
from server.main import app
from server.store.report_store import ReportStore

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "report.json"


@pytest.fixture
def store(tmp_path):
    s = ReportStore(tmp_path / "test.db")
    app.dependency_overrides[get_store] = lambda: s
    yield s
    app.dependency_overrides.clear()


@pytest.fixture
def client(store):
    return TestClient(app)


@pytest.fixture
def sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_list_empty(client):
    r = client.get("/api/reports")
    assert r.status_code == 200 and r.json() == []


def test_list_and_get(client, store, sample):
    store.save(sample)
    assert client.get("/api/reports").json() == [sample]
    r = client.get(f"/api/reports/{sample['id']}")
    assert r.status_code == 200 and r.json() == sample


def test_get_missing_404(client):
    assert client.get("/api/reports/nope").status_code == 404


def test_docs_available(client):
    assert client.get("/docs").status_code == 200


def test_list_with_odd_created_at_returns_200(client, store, sample):
    store.save({**sample, "id": "aware"})
    store.save({**sample, "id": "naive", "createdAt": "2026-11-18T14:20:00"})
    store.save({**sample, "id": "bad", "createdAt": "garbage"})
    store.save({k: v for k, v in {**sample, "id": "missing"}.items() if k != "createdAt"})
    r = client.get("/api/reports")
    assert r.status_code == 200
    assert {x["id"] for x in r.json()} == {"aware", "naive", "bad", "missing"}
