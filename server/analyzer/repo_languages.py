"""분석 프롬프트에 대상 레포의 사용 언어 정보를 넣기 위한 도우미."""
from __future__ import annotations

import os

import httpx


def fetch_repo_languages(repo: str) -> dict[str, int]:
    """GitHub API에서 레포의 언어별 코드 크기를 직접 가져온다."""
    r = httpx.get(
        f"https://api.github.com/repos/{repo}/languages",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
