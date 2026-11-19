"""대시보드 화면 파일 제공 테스트 (DESIGN.md 3.7 ③, Issue #8).

PR 코멘트의 /dashboard/report.html?id=... 링크(server/github/comment.py)가 열려야 하고,
화면 파일을 붙여도 기존 API·Webhook·세션 인증은 그대로여야 한다.
"""
import os

import pytest
from fastapi.testclient import TestClient

# server.main 은 import 시점에 SESSION_SECRET 을 읽으므로 import 전에 넣어 둔다.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from server.api.dashboard_api import get_store  # noqa: E402
from server.github.comment import DASHBOARD_PATH  # noqa: E402
from server.main import DASHBOARD_DIR, app  # noqa: E402
from server.store.report_store import ReportStore  # noqa: E402

PASSWORD = "test-password"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def store(tmp_path):
    s = ReportStore(tmp_path / "test.db")
    app.dependency_overrides[get_store] = lambda: s
    yield s
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


# --- 화면 파일 제공 ---


def test_report_link_from_pr_comment_serves_html(client):
    """PR 코멘트가 만드는 링크 그대로 요청한다. 로그인 없이도 화면 파일은 내려간다."""
    r = client.get(DASHBOARD_PATH + "rpt_1_abc")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.text == (DASHBOARD_DIR / "report.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["index.html", "login.html", "report.html"])
def test_html_pages_served(client, name):
    r = client.get(f"/dashboard/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize(
    "path, content_type",
    [
        ("/dashboard/style.css?v=5", "text/css"),
        ("/dashboard/app.js?v=5", "javascript"),
        ("/dashboard/sample-data.js", "javascript"),
    ],
)
def test_assets_referenced_by_pages_served(client, path, content_type):
    """HTML이 상대 경로로 부르는 CSS·JS가 /dashboard/ 아래에서 열린다."""
    r = client.get(path)
    assert r.status_code == 200
    assert content_type in r.headers["content-type"]


def test_dashboard_root_serves_index(client):
    r = client.get("/dashboard/")
    assert r.status_code == 200
    assert r.text == (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")


def test_dashboard_without_slash_redirects_to_index(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (301, 307, 308)
    assert r.headers["location"].endswith("/dashboard/")
    assert client.get("/dashboard").status_code == 200


def test_missing_file_404(client):
    assert client.get("/dashboard/nope.html").status_code == 404


@pytest.mark.parametrize("path", ["/dashboard/../server/main.py", "/dashboard/%2e%2e/server/main.py"])
def test_no_access_outside_dashboard_dir(client, path):
    r = client.get(path)
    assert r.status_code == 404


# --- 기존 API·Webhook·인증 영향 없음 ---


def test_health_unchanged(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_api_still_requires_session(client, store):
    """화면 파일을 열었다고 세션이 생기지 않는다. 데이터 API는 여전히 401."""
    client.get(DASHBOARD_PATH + "rpt_1")
    assert client.get("/api/reports").status_code == 401
    assert client.get("/api/reports/rpt_1").status_code == 401
    assert client.post("/api/reports/rpt_1/issues/iss_1/fix", json={"direction": "code"}).status_code == 401


def test_login_flow_still_works(client, store):
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/reports").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/reports").status_code == 401


def test_webhook_still_checks_signature(client):
    assert client.post("/webhook/github", content=b"{}").status_code == 401


def test_routes_not_shadowed_by_mount():
    paths = app.openapi()["paths"]
    for p in ["/health", "/webhook/github", "/api/login", "/api/logout", "/api/reports", "/api/reports/{id}"]:
        assert p in paths
