import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# server.main 은 import 시점에 SESSION_SECRET 을 읽으므로 import 전에 넣어 둔다.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from server.api import dashboard_api  # noqa: E402
from server.api.dashboard_api import DashboardAPI, get_dashboard_api, get_store  # noqa: E402
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


# --- 수정안 생성 (DESIGN.md 3.4 fix API, 3.3 issues[].fix) ---
# FixGenerator·GitHubClient는 가짜로 바꾼다. 실제 클래스와의 연결은 통합 테스트(임시 worktree)에서 따로 확인한다.


class FixError(Exception):  # 이름으로 외부 실패를 구분하므로 실제 예외와 같은 이름을 쓴다
    pass


class GitHubAPIError(Exception):
    pass


class LLMCallError(Exception):  # server/analyzer/llm_call.py의 Gemini 호출 실패와 같은 이름
    pass


CODE_FIX = {"diff": "--- a/src/auth/SessionStore.java\n+++ b/src/auth/SessionStore.java\n@@\n-old\n+new\n"}
DOC_FIX = {"before": "old text", "after": "new text", "mermaid": "sequenceDiagram\n  A->>B: hi"}


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.files = {
            "docs/architecture.md": "# 설계 문서 전문",
            "src/auth/SessionStore.java": "class SessionStore {}",
        }
        self.error = None

    def get_file(self, repo, ref, path):
        self.calls.append((repo, ref, path))
        if self.error:
            raise self.error
        if path not in self.files:
            raise FileNotFoundError(f"{repo}@{ref}:{path}")
        return self.files[path]


class FakeFixGenerator:
    def __init__(self):
        self.calls = []
        self.code_result = dict(CODE_FIX)
        self.doc_result = dict(DOC_FIX)
        self.error = None

    def code_fix(self, issue, design_doc, code):
        self.calls.append(("code", issue, design_doc, code))
        if self.error:
            raise self.error
        return self.code_result

    def doc_revision(self, issue, design_doc):
        self.calls.append(("doc", issue, design_doc))
        if self.error:
            raise self.error
        return self.doc_result


@pytest.fixture
def github():
    return FakeGitHub()


@pytest.fixture
def generator():
    return FakeFixGenerator()


@pytest.fixture
def fix_client(client, store, github, generator):
    """로그인한 클라이언트. DashboardAPI에 가짜 GitHubClient·FixGenerator를 넣는다."""
    app.dependency_overrides[get_dashboard_api] = lambda: DashboardAPI(
        store, fix_generator=generator, github=github
    )
    return client


def fix_url(report_id="rpt_12_a1b2c3", issue_id="iss_1"):
    return f"/api/reports/{report_id}/issues/{issue_id}/fix"


def two_issue_report(sample):
    second = {**sample["issues"][0], "id": "iss_2", "title": "두 번째"}
    return {**sample, "issues": [dict(sample["issues"][0]), second]}


def test_fix_requires_session(anon):
    assert anon.post(fix_url(), json={"direction": "code"}).status_code == 401


def test_fix_unauthenticated_does_not_reveal_missing_report(anon):
    assert anon.post(fix_url("nope", "nope"), json={"direction": "code"}).status_code == 401


def test_fix_code_success(fix_client, store, sample, github, generator):
    store.save(sample)
    r = fix_client.post(fix_url(), json={"direction": "code"})
    assert r.status_code == 200
    assert r.json() == {"direction": "code", "fix": CODE_FIX}

    # 설계 문서(designRef의 '#' 앞)와 코드 전문을 headSha 시점으로 조회한다
    assert github.calls == [
        ("owner/target-repo", "a1b2c3d", "docs/architecture.md"),
        ("owner/target-repo", "a1b2c3d", "src/auth/SessionStore.java"),
    ]
    kind, issue, design_doc, code = generator.calls[0]
    assert (kind, design_doc, code) == ("code", "# 설계 문서 전문", "class SessionStore {}")
    assert issue["id"] == "iss_1" and issue["designRef"] == "docs/architecture.md#인증 흐름"

    saved = store.get(sample["id"])["issues"][0]
    assert saved["direction"] == "code" and saved["fix"] == CODE_FIX


def test_fix_doc_success_does_not_fetch_code(fix_client, store, sample, github, generator):
    store.save(sample)
    r = fix_client.post(fix_url(), json={"direction": "doc"})
    assert r.status_code == 200
    assert r.json() == {"direction": "doc", "fix": DOC_FIX}
    assert github.calls == [("owner/target-repo", "a1b2c3d", "docs/architecture.md")]
    assert generator.calls[0][0] == "doc" and generator.calls[0][2] == "# 설계 문서 전문"
    saved = store.get(sample["id"])["issues"][0]
    assert saved["direction"] == "doc" and saved["fix"] == DOC_FIX


def test_fix_doc_without_diagram_keeps_mermaid_null(fix_client, store, sample, generator):
    store.save(sample)
    generator.doc_result = {"before": "a", "after": "b", "mermaid": None}
    r = fix_client.post(fix_url(), json={"direction": "doc"})
    assert r.json()["fix"] == {"before": "a", "after": "b", "mermaid": None}


def test_fix_result_is_limited_to_report_format(fix_client, store, sample, generator):
    """FixGenerator가 필드를 더 돌려줘도 3.3 형식의 필드만 저장한다."""
    store.save(sample)
    generator.code_result = {**CODE_FIX, "extra": "x"}
    r = fix_client.post(fix_url(), json={"direction": "code"})
    assert r.json()["fix"] == CODE_FIX
    assert store.get(sample["id"])["issues"][0]["fix"] == CODE_FIX


def test_fix_keeps_other_report_fields_unchanged(fix_client, store, sample):
    store.save(two_issue_report(sample))
    fix_client.post(fix_url(), json={"direction": "code"})
    saved = store.get(sample["id"])
    expected = two_issue_report(sample)
    expected["issues"][0]["direction"] = "code"
    expected["issues"][0]["fix"] = CODE_FIX
    assert saved == expected  # 다른 issue와 다른 필드, 상태(done)가 그대로다


def test_fix_same_direction_returns_stored_without_calling_again(fix_client, store, sample, github, generator):
    store.save(sample)
    first = fix_client.post(fix_url(), json={"direction": "code"}).json()
    github.calls.clear()
    generator.calls.clear()
    generator.code_result = {"diff": "다른 결과"}  # 다시 만들었다면 이 값이 나온다

    again = fix_client.post(fix_url(), json={"direction": "code"})
    assert again.status_code == 200 and again.json() == first
    assert github.calls == [] and generator.calls == []


def test_fix_direction_change_regenerates_and_overwrites(fix_client, store, sample, generator):
    store.save(sample)
    fix_client.post(fix_url(), json={"direction": "code"})
    r = fix_client.post(fix_url(), json={"direction": "doc"})
    assert r.json() == {"direction": "doc", "fix": DOC_FIX}
    assert [c[0] for c in generator.calls] == ["code", "doc"]
    saved = store.get(sample["id"])["issues"][0]
    assert saved["direction"] == "doc" and saved["fix"] == DOC_FIX


def test_fix_status_becomes_resolved_when_all_issues_have_fix(fix_client, store, sample):
    store.save(two_issue_report(sample))
    fix_client.post(fix_url(issue_id="iss_1"), json={"direction": "code"})
    assert store.get(sample["id"])["status"] == "done"  # 아직 iss_2가 남았다
    fix_client.post(fix_url(issue_id="iss_2"), json={"direction": "doc"})
    assert store.get(sample["id"])["status"] == "resolved"


def test_fix_invalid_direction_422(fix_client, store, sample, github):
    store.save(sample)
    assert fix_client.post(fix_url(), json={"direction": "both"}).status_code == 422
    assert fix_client.post(fix_url(), json={}).status_code == 422
    assert github.calls == []


def test_fix_missing_report_404(fix_client):
    assert fix_client.post(fix_url("nope"), json={"direction": "code"}).status_code == 404


def test_fix_missing_issue_404(fix_client, store, sample, github):
    store.save(sample)
    assert fix_client.post(fix_url(issue_id="iss_99"), json={"direction": "code"}).status_code == 404
    assert github.calls == []


@pytest.mark.parametrize("status", ["analyzing", "failed"])
def test_fix_report_not_ready_409(fix_client, store, sample, github, status):
    store.save({**sample, "status": status})
    assert fix_client.post(fix_url(), json={"direction": "code"}).status_code == 409
    assert github.calls == []


def test_fix_code_without_code_ref_422(fix_client, store, sample, github):
    issue = {**sample["issues"][0], "codeRef": None}
    store.save({**sample, "issues": [issue]})
    assert fix_client.post(fix_url(), json={"direction": "code"}).status_code == 422
    assert github.calls == []
    # 문서 개정은 코드 위치가 없어도 만들 수 있다
    assert fix_client.post(fix_url(), json={"direction": "doc"}).status_code == 200


def test_fix_without_design_ref_422(fix_client, store, sample):
    issue = {**sample["issues"][0], "designRef": ""}
    store.save({**sample, "issues": [issue]})
    assert fix_client.post(fix_url(), json={"direction": "doc"}).status_code == 422


def test_fix_design_ref_without_section(fix_client, store, sample, github):
    issue = {**sample["issues"][0], "designRef": "docs/architecture.md"}
    store.save({**sample, "issues": [issue]})
    assert fix_client.post(fix_url(), json={"direction": "doc"}).status_code == 200
    assert github.calls[0][2] == "docs/architecture.md"


def test_fix_file_not_in_repo_404(fix_client, store, sample, github):
    github.files.pop("src/auth/SessionStore.java")
    store.save(sample)
    r = fix_client.post(fix_url(), json={"direction": "code"})
    assert r.status_code == 404
    assert store.get(sample["id"]) == sample


@pytest.mark.parametrize("where", ["github", "generator"])
@pytest.mark.parametrize(
    "error",
    [
        GitHubAPIError("GET -> 500 secret-token"),
        FixError("secret-key 실패"),
        LLMCallError("Gemini API 호출 실패: secret-key"),
    ],
)
def test_fix_upstream_failure_502_and_nothing_saved(fix_client, store, sample, github, generator, where, error):
    store.save(sample)
    {"github": github, "generator": generator}[where].error = error
    r = fix_client.post(fix_url(), json={"direction": "code"})
    assert r.status_code == 502
    assert "secret" not in r.text  # 외부 오류 메시지를 응답에 그대로 싣지 않는다
    assert store.get(sample["id"]) == sample  # 불완전한 수정안이 저장되지 않는다


def test_external_error_names_match_real_classes():
    """이름으로 구분하는 외부 실패 목록이 실제 예외 클래스 이름과 맞는지 확인한다.

    다른 담당자 모듈에서 예외 이름이 바뀌면(예: ClaudeCallError → LLMCallError) 여기서 바로 드러난다.
    """
    pytest.importorskip("google.genai")
    from server.analyzer.fix_generator import FixError as RealFixError
    from server.analyzer.llm_call import LLMCallError as RealLLMCallError

    assert dashboard_api._is_external_error(RealFixError("x"))
    assert dashboard_api._is_external_error(RealLLMCallError("x"))


def test_fix_network_error_is_502(fix_client, store, sample, github):
    class HTTPError(Exception):  # httpx.HTTPError와 같은 이름
        pass

    store.save(sample)
    github.error = HTTPError("timeout")
    assert fix_client.post(fix_url(), json={"direction": "doc"}).status_code == 502


@pytest.mark.parametrize(
    "direction, bad",
    [
        ("code", None),
        ("code", {}),
        ("code", {"diff": ""}),
        ("code", {"diff": 123}),
        ("doc", {"before": "a"}),
        ("doc", {"before": "a", "after": "b", "mermaid": 5}),
        ("doc", "text"),
    ],
)
def test_fix_invalid_generator_result_502_and_nothing_saved(fix_client, store, sample, generator, direction, bad):
    store.save(sample)
    generator.code_result = bad
    generator.doc_result = bad
    assert fix_client.post(fix_url(), json={"direction": direction}).status_code == 502
    assert store.get(sample["id"]) == sample


def test_fix_failed_direction_change_keeps_previous_fix(fix_client, store, sample, generator):
    store.save(sample)
    fix_client.post(fix_url(), json={"direction": "code"})
    before = store.get(sample["id"])
    generator.error = FixError("boom")
    assert fix_client.post(fix_url(), json={"direction": "doc"}).status_code == 502
    assert store.get(sample["id"]) == before  # 기존 수정안이 그대로 남는다


def test_fix_unexpected_error_is_not_swallowed(store, sample, github, generator):
    """FixError 같은 외부 실패가 아닌 버그는 502로 숨기지 않는다 (저장도 하지 않는다)."""
    store.save(sample)
    generator.error = KeyError("bug")
    app.dependency_overrides[get_dashboard_api] = lambda: DashboardAPI(
        store, fix_generator=generator, github=github
    )
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert c.post(fix_url(), json={"direction": "code"}).status_code == 500
    assert store.get(sample["id"]) == sample


def test_fix_unavailable_generator_503(client, store, sample, github, monkeypatch):
    """google-genai 미설치·API 키 없음처럼 FixGenerator를 만들 수 없으면 503이다 (서버는 정상 기동)."""

    def broken():
        raise ImportError("No module named 'google.genai'")

    monkeypatch.setattr(dashboard_api, "_default_fix_generator", broken)
    app.dependency_overrides[get_dashboard_api] = lambda: DashboardAPI(store, github=github)
    store.save(sample)
    r = client.post(fix_url(), json={"direction": "doc"})
    assert r.status_code == 503
    assert store.get(sample["id"]) == sample


def test_fix_does_not_break_existing_endpoints(fix_client, store, sample):
    store.save(sample)
    fix_client.post(fix_url(), json={"direction": "code"})
    assert fix_client.get("/api/reports").status_code == 200
    assert fix_client.get(f"/api/reports/{sample['id']}").json()["issues"][0]["fix"] == CODE_FIX
    assert fix_client.post("/api/logout").status_code == 200
    assert fix_client.post(fix_url(), json={"direction": "code"}).status_code == 401
