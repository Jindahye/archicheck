import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# server.main 은 import 시점에 SESSION_SECRET 을 읽으므로 import 전에 넣어 둔다.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from server.api.dashboard_api import get_store  # noqa: E402
from server.main import app  # noqa: E402
from server.store.report_store import ReportStore  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "report.json"
PASSWORD = "test-password"


@pytest.fixture(autouse=True)
def dashboard_password(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)


@pytest.fixture
def store(tmp_path):
    s = ReportStore(tmp_path / "test.db")
    app.dependency_overrides[get_store] = lambda: s
    yield s
    app.dependency_overrides.clear()


@pytest.fixture
def anon(store):
    """로그인하지 않은 클라이언트."""
    return TestClient(app)


@pytest.fixture
def client(store):
    """로그인한 클라이언트."""
    c = TestClient(app)
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 200
    return c


@pytest.fixture
def sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


# --- 조회 API ---


def test_health(anon):
    r = anon.get("/health")
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


def test_docs_available(anon):
    assert anon.get("/docs").status_code == 200


def test_list_with_odd_created_at_returns_200(client, store, sample):
    store.save({**sample, "id": "aware"})
    store.save({**sample, "id": "naive", "createdAt": "2026-11-18T14:20:00"})
    store.save({**sample, "id": "bad", "createdAt": "garbage"})
    store.save({k: v for k, v in {**sample, "id": "missing"}.items() if k != "createdAt"})
    r = client.get("/api/reports")
    assert r.status_code == 200
    assert {x["id"] for x in r.json()} == {"aware", "naive", "bad", "missing"}


# --- 로그인·세션 (DESIGN.md 3.4 대시보드 인증) ---


def test_login_success_sets_session_cookie(anon):
    r = anon.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_login_wrong_password_401(anon):
    r = anon.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_login_rejected_when_password_not_configured(anon, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    assert anon.post("/api/login", json={"password": ""}).status_code == 401


def test_login_non_ascii_password(anon, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "비밀번호")
    assert anon.post("/api/login", json={"password": "비밀번호"}).status_code == 200
    assert anon.post("/api/login", json={"password": "비밀"}).status_code == 401


def test_login_missing_body_422(anon):
    assert anon.post("/api/login", json={}).status_code == 422


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/reports"),
        ("get", "/api/reports/rpt_12_a1b2c3"),
        ("post", "/api/logout"),
    ],
)
def test_session_required_401(anon, method, path):
    assert getattr(anon, method)(path).status_code == 401


def test_missing_report_without_login_is_401_not_404(anon):
    assert anon.get("/api/reports/nope").status_code == 401


def test_logout_ends_session(client):
    assert client.get("/api/reports").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/reports").status_code == 401


def test_forged_cookie_rejected(anon):
    anon.cookies.set("session", "forged-value")
    assert anon.get("/api/reports").status_code == 401
