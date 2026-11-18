"""설계 문서 탐색 (DESIGN.md 3.5).

반환 형식: [{"path": "docs/architecture.md", "content": "..."}]
"""
from __future__ import annotations

import re

from server.github.github_client import GitHubClient

CONFIG_PATH = ".archicheck.yml"
NAME_KEYWORDS = ("design", "architecture", "arch", "설계", "아키텍처")
SKIP_DIRS = ("node_modules/", ".git/", "vendor/", "dist/", "build/")
MAX_BODY_SCANS = 30  # 이름이 안 맞는 .md를 본문까지 읽어 볼 최대 개수
MAX_DOCS = 5  # 분석에 넘길 설계 문서 최대 개수


class DesignDocLocator:
    def __init__(self, client: GitHubClient | None = None):
        self.client = client or GitHubClient()

    def locate(self, repo: str, ref: str) -> list[dict]:
        """.archicheck.yml을 우선 사용하고, 없으면 자동 탐색한다. 못 찾으면 빈 리스트."""
        paths = self._read_config(repo, ref)
        if paths:
            return self._load(repo, ref, paths)
        return self._auto_detect(repo, ref)

    def _read_config(self, repo: str, ref: str) -> list[str]:
        try:
            text = self.client.get_file(repo, ref, CONFIG_PATH)
        except FileNotFoundError:
            return []
        return parse_design_docs(text)

    def _auto_detect(self, repo: str, ref: str) -> list[dict]:
        md_files = [
            p for p in self.client.list_files(repo, ref)
            if p.lower().endswith(".md") and not p.startswith(SKIP_DIRS) and not any(d in p for d in SKIP_DIRS)
        ]
        by_name = [p for p in md_files if _name_matches(p)]
        found = self._load(repo, ref, by_name[:MAX_DOCS])
        if len(found) >= MAX_DOCS:
            return found

        # 이름이 안 맞는 파일은 본문에 Mermaid 블록이 있는지 확인한다.
        docs = list(found)
        rest = [p for p in md_files if p not in by_name][:MAX_BODY_SCANS]
        for path in rest:
            if len(docs) >= MAX_DOCS:
                break
            try:
                content = self.client.get_file(repo, ref, path)
            except FileNotFoundError:
                continue
            if "```mermaid" in content:
                docs.append({"path": path, "content": content})
        return docs

    def _load(self, repo: str, ref: str, paths: list[str]) -> list[dict]:
        docs = []
        for path in paths:
            try:
                docs.append({"path": path, "content": self.client.get_file(repo, ref, path)})
            except FileNotFoundError:
                continue  # 설정에 적힌 파일이 없으면 건너뛴다
        return docs


def _name_matches(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return any(k in name for k in NAME_KEYWORDS)


def parse_design_docs(text: str) -> list[str]:
    """.archicheck.yml의 `design_docs:` 목록만 읽는 최소 파서 (PyYAML 의존 회피)."""
    paths: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^design_docs\s*:\s*$", line):
            in_block = True
            continue
        if in_block:
            m = re.match(r"^\s*-\s*(.+)$", line)
            if m:
                paths.append(m.group(1).strip().strip("'\""))
            elif not line.startswith((" ", "\t")):
                break  # 다른 최상위 키가 시작됨
    return paths
