"""설계 정합성 분석 (DESIGN.md 3.2, 3.3). Claude API 호출은 이 모듈과 FixGenerator에서만 한다."""
from __future__ import annotations

from pathlib import Path

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "conformance_analysis.md"


class AnalysisError(Exception):
    """분석 실패. WebhookHandler는 이 예외를 받으면 리포트 status를 failed로 바꾼다 (3.1)."""


# --- Claude 응답 형식 (structured outputs). 3.3의 summary / impact / issues 와 같은 이름을 쓴다. ---


class _Summary(BaseModel):
    commitMessage: str
    actualChanges: list[str]
    unmentionedChanges: int


class _Impact(BaseModel):
    file: str
    symbol: str
    reason: str


class _Issue(BaseModel):
    title: str
    designRef: str
    codeRef: str
    detail: str


class _AnalysisOutput(BaseModel):
    summary: _Summary
    impact: list[_Impact]
    issues: list[_Issue]


class ConformanceAnalyzer:
    def __init__(self, client: anthropic.Anthropic | None = None):
        # client를 넘기지 않으면 ANTHROPIC_API_KEY 등 환경 변수로 만든다. 테스트에서는 가짜 client를 넘긴다.
        self.client = client or anthropic.Anthropic()
        self.system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def analyze(self, diff: str, design_docs: list[dict], commits: list[str]) -> dict:
        """diff와 설계 문서를 비교해 3.3 리포트의 분석 필드를 만든다.

        입력:
          diff: PR의 unified diff 텍스트
          design_docs: [{"path": "docs/architecture.md", "content": "..."}] (DesignDocLocator 결과)
          commits: 커밋 메시지 목록

        반환: {"designDocs", "summary", "impact", "issues"}
          id, repo, pr, headSha, title, createdAt, status 는 WebhookHandler가 채운다.
          issues[].id 는 iss_1, iss_2 ... 로 붙이고 direction, fix 는 null 로 둔다.

        실패하면 AnalysisError.
        """
        if not design_docs:
            raise AnalysisError("설계 문서가 없습니다. .archicheck.yml로 경로를 지정하세요.")

        try:
            response = self.client.beta.messages.parse(
                model=MODEL,
                max_tokens=16000,
                system=self.system_prompt,
                messages=[{"role": "user", "content": _build_user_message(diff, design_docs, commits)}],
                output_config={"effort": "high"},
                output_format=_AnalysisOutput,
                # 안전 분류기가 요청을 거절하면 서버가 다른 모델로 다시 실행한다.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as e:
            raise AnalysisError(f"Claude API 호출 실패: {e}") from e

        if response.stop_reason == "refusal":
            raise AnalysisError("Claude가 분석 요청을 거절했습니다.")
        if response.stop_reason == "max_tokens":
            raise AnalysisError("분석 결과가 너무 길어 중간에 잘렸습니다.")
        result = response.parsed_output
        if result is None:
            raise AnalysisError("분석 결과를 3.3 형식으로 읽지 못했습니다.")

        return {
            "designDocs": [d["path"] for d in design_docs],
            "summary": result.summary.model_dump(),
            "impact": [i.model_dump() for i in result.impact],
            "issues": [
                {"id": f"iss_{n}", **issue.model_dump(), "direction": None, "fix": None}
                for n, issue in enumerate(result.issues, start=1)
            ],
        }


def _build_user_message(diff: str, design_docs: list[dict], commits: list[str]) -> str:
    # 설계 문서를 앞에 두고 diff를 마지막에 둔다. 잘라내지 않고 전부 보낸다.
    docs = "\n\n".join(
        f'<design_doc path="{d["path"]}">\n{d["content"]}\n</design_doc>' for d in design_docs
    )
    commit_text = "\n".join(f"- {c}" for c in commits) or "(커밋 메시지 없음)"
    return f"{docs}\n\n<commits>\n{commit_text}\n</commits>\n\n<diff>\n{diff}\n</diff>"
