"""GitHub REST API 클라이언트. GitHub API 호출은 이 모듈에서만 한다 (DESIGN.md 3.2)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubAPIError(RuntimeError):
    """GitHub API가 오류 응답을 돌려줬을 때. status_code로 원인을 구분한다."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PullRequestRef:
    """PR 하나를 가리키는 값. Webhook payload에서 만든다."""

    repo: str  # "owner/name"
    number: int
    head_sha: str = ""
    title: str = ""


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = API_BASE,
    ):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self._client = client or httpx.Client(base_url=base_url, timeout=30.0)

    # ---- 내부 공통 ----
    def _headers(self, accept: str = "application/vnd.github+json") -> dict:
        headers = {"Accept": accept, "X-GitHub-Api-Version": API_VERSION}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, *, accept: str | None = None, **kwargs) -> httpx.Response:
        headers = self._headers(accept) if accept else self._headers()
        resp = self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise GitHubAPIError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:200]}", resp.status_code
            )
        return resp

    # ---- DESIGN.md 3.2 인터페이스 ----
    def get_diff(self, pr: PullRequestRef) -> str:
        """PR 전체 diff(unified diff 텍스트)."""
        resp = self._request(
            "GET", f"/repos/{pr.repo}/pulls/{pr.number}", accept="application/vnd.github.diff"
        )
        return resp.text

    def get_commit_messages(self, pr: PullRequestRef) -> list[str]:
        """PR에 포함된 커밋 메시지 목록(오래된 순). 최대 250개(GitHub 상한)."""
        messages: list[str] = []
        for page in (1, 2, 3):
            resp = self._request(
                "GET",
                f"/repos/{pr.repo}/pulls/{pr.number}/commits",
                params={"per_page": 100, "page": page},
            )
            batch = resp.json()
            messages += [c["commit"]["message"] for c in batch]
            if len(batch) < 100:
                break
        return messages

    def get_file(self, repo: str, ref: str, path: str) -> str:
        """ref 시점의 파일 내용(텍스트). 없으면 FileNotFoundError."""
        try:
            resp = self._request(
                "GET",
                f"/repos/{repo}/contents/{path}",
                params={"ref": ref},
                accept="application/vnd.github.raw+json",
            )
        except GitHubAPIError as e:
            if e.status_code == 404:
                raise FileNotFoundError(f"{repo}@{ref}:{path}") from e
            raise
        return resp.text

    def list_files(self, repo: str, ref: str) -> list[str]:
        """ref 시점의 모든 파일 경로(폴더 제외)."""
        resp = self._request(
            "GET", f"/repos/{repo}/git/trees/{ref}", params={"recursive": "1"}
        )
        tree = resp.json().get("tree", [])
        return [item["path"] for item in tree if item.get("type") == "blob"]

    def post_comment(self, pr: PullRequestRef, body: str) -> int:
        """PR 대화창에 코멘트를 단다. 생성된 코멘트 id를 돌려준다."""
        resp = self._request(
            "POST", f"/repos/{pr.repo}/issues/{pr.number}/comments", json={"body": body}
        )
        return resp.json()["id"]
