"""server/github 단위 테스트. 실제 GitHub·Claude 없이 가짜 응답으로 검증한다."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.github.design_doc_locator import DesignDocLocator, parse_design_docs
from server.github.github_client import GitHubAPIError, GitHubClient, PullRequestRef
from server.github.webhook_handler import WebhookHandler, router
import server.github.webhook_handler as wh

SECRET = "test-secret"
PR = PullRequestRef(repo="o/r", number=7, head_sha="abcdef1234", title="t")


def make_client(handler) -> GitHubClient:
    http = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubClient(token="tok", client=http)


# ---------- GitHubClient ----------
def test_get_diff_uses_diff_accept_and_auth():
    seen = {}

    def handler(req):
        seen["accept"] = req.headers["accept"]
        seen["auth"] = req.headers["authorization"]
        seen["path"] = req.url.path
        return httpx.Response(200, text="diff --git a/x b/x")

    assert make_client(handler).get_diff(PR) == "diff --git a/x b/x"
    assert seen == {"accept": "application/vnd.github.diff", "auth": "Bearer tok", "path": "/repos/o/r/pulls/7"}


def test_get_commit_messages():
    client = make_client(lambda r: httpx.Response(200, json=[{"commit": {"message": "a"}}, {"commit": {"message": "b"}}]))
    assert client.get_commit_messages(PR) == ["a", "b"]


def test_get_file_404_raises_filenotfound_and_500_raises_api_error():
    with pytest.raises(FileNotFoundError):
        make_client(lambda r: httpx.Response(404, text="nf")).get_file("o/r", "main", "x.md")
    with pytest.raises(GitHubAPIError) as err:
        make_client(lambda r: httpx.Response(500, text="boom")).get_file("o/r", "main", "x.md")
    assert err.value.status_code == 500


def test_list_files_returns_only_blobs():
    tree = {"tree": [{"path": "docs", "type": "tree"}, {"path": "docs/a.md", "type": "blob"}]}
    assert make_client(lambda r: httpx.Response(200, json=tree)).list_files("o/r", "main") == ["docs/a.md"]


def test_post_comment_sends_body():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["path"] = req.url.path
        return httpx.Response(201, json={"id": 99})

    assert make_client(handler).post_comment(PR, "hi") == 99
    assert seen == {"body": {"body": "hi"}, "path": "/repos/o/r/issues/7/comments"}


# ---------- DesignDocLocator ----------
class FakeGH:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def get_file(self, repo, ref, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def list_files(self, repo, ref):
        return list(self.files)


def test_parse_design_docs():
    text = "name: x\ndesign_docs:\n  - docs/a.md  # 주석\n  - 'docs/설계서.md'\nother: 1\n"
    assert parse_design_docs(text) == ["docs/a.md", "docs/설계서.md"]


def test_locator_prefers_config():
    gh = FakeGH({".archicheck.yml": "design_docs:\n  - docs/x.md\n", "docs/x.md": "X", "docs/architecture.md": "A"})
    assert DesignDocLocator(gh).locate("o/r", "main") == [{"path": "docs/x.md", "content": "X"}]


def test_locator_auto_detects_by_name_and_mermaid_body():
    gh = FakeGH({
        "docs/DESIGN.md": "d",
        "notes/flow.md": "```mermaid\ngraph TD\n```",
        "README.md": "plain",
        "node_modules/x/architecture.md": "skip me",
        "src/a.py": "code",
    })
    paths = [d["path"] for d in DesignDocLocator(gh).locate("o/r", "main")]
    assert paths == ["docs/DESIGN.md", "notes/flow.md"]


def test_locator_returns_empty_when_nothing_found():
    assert DesignDocLocator(FakeGH({"README.md": "x"})).locate("o/r", "main") == []


# ---------- WebhookHandler ----------
class FakeStore:
    def __init__(self):
        self.saved = []

    def save(self, report):
        self.saved.append(json.loads(json.dumps(report)))


class FakeClient:
    def __init__(self):
        self.comments = []

    def get_diff(self, pr): return "diff"
    def get_commit_messages(self, pr): return ["msg"]
    def post_comment(self, pr, body): self.comments.append(body)


class FakeLocator:
    def locate(self, repo, ref): return [{"path": "docs/DESIGN.md", "content": "d"}]


class OkAnalyzer:
    def analyze(self, diff, docs, commits):
        return {"summary": {"actualChanges": ["a"], "unmentionedChanges": 0}, "impact": [],
                "issues": [{"id": "iss_1", "title": "불일치", "direction": None, "fix": None}]}


class BrokenAnalyzer:
    def analyze(self, *a): raise RuntimeError("claude down")


def build(analyzer):
    client, store = FakeClient(), FakeStore()
    handler = WebhookHandler(client=client, locator=FakeLocator(), analyzer=analyzer, store=store,
                             secret=SECRET, base_url="http://1.2.3.4:8000")
    wh._handler = handler
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), client, store


def post(tc, payload, event="pull_request", secret=SECRET, sign=True):
    body = json.dumps(payload).encode()
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if sign:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return tc.post("/webhook/github", content=body, headers=headers)


def pr_payload(action="opened"):
    return {"action": action, "repository": {"full_name": "o/r"},
            "pull_request": {"number": 12, "title": "로그인 버그 수정", "head": {"sha": "a1b2c3dffff"}}}


def test_bad_or_missing_signature_is_401():
    tc, _, store = build(OkAnalyzer())
    assert post(tc, pr_payload(), secret="wrong").status_code == 401
    assert post(tc, pr_payload(), sign=False).status_code == 401
    assert store.saved == []


def test_empty_secret_rejects_everything():
    tc, _, _ = build(OkAnalyzer())
    wh._handler.secret = ""
    assert post(tc, pr_payload(), secret="").status_code == 401


def test_ping_and_ignored_events():
    tc, _, store = build(OkAnalyzer())
    assert post(tc, {"zen": "x"}, event="ping").json() == {"status": "pong"}
    assert post(tc, {}, event="push").json()["status"] == "ignored"
    assert post(tc, pr_payload("closed")).json()["status"] == "ignored"
    assert store.saved == []


def test_pr_opened_runs_full_flow_and_comments():
    tc, client, store = build(OkAnalyzer())
    resp = post(tc, pr_payload())
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted", "reportId": "rpt_12_a1b2c3d"}
    # TestClient는 백그라운드 작업이 끝난 뒤 반환한다: analyzing -> done
    assert [r["status"] for r in store.saved] == ["analyzing", "done"]
    done = store.saved[-1]
    assert done["designDocs"] == ["docs/DESIGN.md"] and done["pr"] == 12 and done["headSha"] == "a1b2c3dffff"
    assert len(client.comments) == 1
    assert "불일치 1건" in client.comments[0] and "http://1.2.3.4:8000" in client.comments[0]


def test_analysis_failure_marks_failed_and_comments():
    tc, client, store = build(BrokenAnalyzer())
    assert post(tc, pr_payload("synchronize")).status_code == 202
    assert [r["status"] for r in store.saved] == ["analyzing", "failed"]
    assert "분석 실패" in client.comments[0]
    assert "claude down" not in client.comments[0]  # 오류 내용은 공개 PR에 쓰지 않는다


# ---------- 수정 사항 검증 ----------
class CommentFailsClient(FakeClient):
    def post_comment(self, pr, body):
        raise GitHubAPIError("POST -> 403: Resource not accessible", 403)


def test_comment_failure_keeps_done_report():
    """코멘트 게시가 실패해도 분석 결과(done)를 failed로 덮어쓰지 않는다."""
    tc, _, store = build(OkAnalyzer())
    wh._handler.client = CommentFailsClient()
    assert post(tc, pr_payload()).status_code == 202
    assert [r["status"] for r in store.saved] == ["analyzing", "done"]
    assert store.saved[-1]["issues"][0]["title"] == "불일치"


def test_comment_tolerates_missing_fields():
    from server.github.comment import format_report_comment
    report = {"id": "rpt_1_x", "pr": 1, "impact": [{"file": "a.py"}, {"reason": "r"}, "junk"],
              "issues": [{"id": "iss_1"}, {"detail": "d"}]}
    body = format_report_comment(report, "http://1.2.3.4:8000")
    assert "불일치 2건" in body and "`a.py`" in body and "- d" in body


def test_comment_omits_link_without_valid_base_url():
    from server.github.comment import format_report_comment
    report = {"id": "rpt_1_x", "pr": 1}
    assert "수정 방향 선택" not in format_report_comment(report, "")
    assert "수정 방향 선택" not in format_report_comment(report, "1.2.3.4:8000")
    assert "http://1.2.3.4:8000/dashboard/report.html?id=rpt_1_x" in format_report_comment(report, "http://1.2.3.4:8000/")
