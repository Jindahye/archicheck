"""GitHub Webhook 라우터 연결 테스트 (DESIGN.md 3.4 POST /webhook/github).

라우터는 ②의 server/github/webhook_handler.py가 만든다. 그 구현(PR #5)이 main에 들어오기 전과
후 모두에서 통과하도록, 실제 라우터가 필요한 테스트는 router가 있을 때만 실행한다.
"""
import hashlib
import hmac
import importlib
import json
import logging
import os

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

# server.main 은 import 시점에 SESSION_SECRET 을 읽으므로 import 전에 넣어 둔다.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import server.main as main  # noqa: E402
from server.api.dashboard_api import get_store  # noqa: E402
from server.main import app, include_webhook_router  # noqa: E402
from server.store.report_store import ReportStore  # noqa: E402

PASSWORD = "test-password"
SECRET = "test-webhook-secret"

webhook_module = importlib.import_module("server.github.webhook_handler")
HAS_REAL_ROUTER = getattr(webhook_module, "router", None) is not None
needs_real_router = pytest.mark.skipif(
    not HAS_REAL_ROUTER, reason="server.github.webhook_handler에 router가 아직 없음 (PR #5 병합 후 실행)"
)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    # 실제 핸들러는 처음 쓸 때 만들어 secret을 읽는다. 테스트마다 새로 만들게 비워 둔다.
    if hasattr(webhook_module, "_handler"):
        monkeypatch.setattr(webhook_module, "_handler", None)


@pytest.fixture
def store(tmp_path):
    s = ReportStore(tmp_path / "test.db")
    app.dependency_overrides[get_store] = lambda: s
    yield s
    app.dependency_overrides.clear()


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def fake_router() -> APIRouter:
    r = APIRouter()

    @r.post("/webhook/github", status_code=202)
    def receive() -> dict:
        return {"status": "accepted"}

    return r


# --- include_webhook_router: 연결 방식 (실제 라우터 없이 검증) ---


def test_include_registers_route_when_router_exists(monkeypatch):
    monkeypatch.setattr(webhook_module, "router", fake_router(), raising=False)
    target = FastAPI()
    assert include_webhook_router(target) is True
    assert "post" in target.openapi()["paths"]["/webhook/github"]
    assert TestClient(target).post("/webhook/github").status_code == 202


def test_include_skips_with_warning_when_router_missing(monkeypatch, caplog):
    monkeypatch.delattr(webhook_module, "router", raising=False)
    target = FastAPI()
    with caplog.at_level(logging.WARNING, logger="archicheck.main"):
        assert include_webhook_router(target) is False
    assert "/webhook/github" not in target.openapi()["paths"]
    assert any("연결하지 못했습니다" in rec.getMessage() for rec in caplog.records)


def test_include_does_not_hide_real_import_errors(monkeypatch):
    """router가 없어서 건너뛰는 것과 달리, 모듈을 불러오다 난 오류는 그대로 올려 보낸다."""

    def broken(name):
        raise ImportError("No module named 'httpx'")

    monkeypatch.setattr(main.importlib, "import_module", broken)
    with pytest.raises(ImportError):
        include_webhook_router(FastAPI())


# --- 기존 API 영향 없음 (PR #5 병합 전후 모두) ---


def test_health_and_login_still_work(store):
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert c.get("/api/reports").status_code == 200
    assert c.post("/api/logout").status_code == 200
    assert c.get("/api/reports").status_code == 401


def test_session_protected_api_still_401_without_login(store):
    c = TestClient(app)
    assert c.get("/api/reports").status_code == 401
    assert c.get("/api/reports/rpt_1").status_code == 401


# --- 실제 라우터 연결 (PR #5 병합 후 실행) ---


@needs_real_router
def test_webhook_route_registered_in_app():
    assert "post" in app.openapi()["paths"]["/webhook/github"]


@needs_real_router
@pytest.mark.parametrize("headers", [{}, {"X-Hub-Signature-256": "sha256=" + "0" * 64}, {"X-Hub-Signature-256": "garbage"}])
def test_webhook_without_valid_signature_401(headers):
    r = TestClient(app).post("/webhook/github", content=b"{}", headers=headers)
    assert r.status_code == 401


@needs_real_router
def test_webhook_rejects_everything_when_secret_not_configured(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    body = b"{}"
    r = TestClient(app).post("/webhook/github", content=body, headers={"X-Hub-Signature-256": sign(body, "")})
    assert r.status_code == 401


@needs_real_router
def test_webhook_signature_is_checked_before_parsing_body():
    r = TestClient(app).post("/webhook/github", content=b"not json", headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 401  # 잘못된 본문이어도 500이 아니라 서명 오류로 거절한다


@needs_real_router
def test_webhook_valid_ping_needs_no_session():
    body = json.dumps({"zen": "hi"}).encode()
    r = TestClient(app).post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"},
    )
    # 라우트가 status_code=202로 선언돼 있어 본문만 다르고 상태 코드는 202다. 로그인 없이 서명만으로 접근한다.
    assert r.status_code == 202 and r.json() == {"status": "pong"}


@needs_real_router
def test_webhook_ignores_other_events_without_touching_store(store):
    body = b"{}"
    r = TestClient(app).post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "push"},
    )
    assert r.status_code == 202 and r.json()["status"] == "ignored"
    assert store.list() == []


@needs_real_router
def test_webhook_does_not_open_session_protected_api(store):
    """Webhook 라우터를 붙여도 대시보드 API의 세션 인증은 그대로다."""
    body = b"{}"
    c = TestClient(app)
    c.post("/webhook/github", content=body, headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"})
    assert c.get("/api/reports").status_code == 401
