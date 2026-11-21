"""설계 정합성 분석 (DESIGN.md 3.2, 3.3). Gemini API 호출은 이 모듈과 FixGenerator에서만 한다 (llm_call.py를 거친다)."""
from __future__ import annotations

from pydantic import BaseModel

from server.analyzer.llm_call import LLMCallError, call_structured, load_prompt, make_client


class AnalysisError(Exception):
    """분석 실패. WebhookHandler는 이 예외를 받으면 리포트 status를 failed로 바꾼다 (3.1)."""


# --- Gemini 응답 형식 (JSON 스키마). 3.3의 summary / impact / issues 와 같은 이름을 쓴다. ---


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


SUMMARY_PROMPT = (
    "PR의 diff와 커밋 메시지를 읽고 실제 변경 내용을 요약한다. "
    "commitMessage에는 커밋 메시지를, actualChanges에는 실제 변경을 한 줄씩, "
    "unmentionedChanges에는 커밋 메시지에 없는 변경 수를 넣는다."
)


class ConformanceAnalyzer:
    def __init__(self, client=None):
        # client를 넘기지 않으면 GEMINI_API_KEY 환경 변수로 만든다. 테스트에서는 가짜 client를 넘긴다.
        self.client = client or make_client()
        self.system_prompt = load_prompt("conformance_analysis.md")

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
            # 1단계: 설계 문서 없이 diff와 커밋 메시지만 보내 변경 요약을 먼저 받는다 (요약 정확도 향상).
            pre_summary = call_structured(
                self.client,
                SUMMARY_PROMPT,
                _build_summary_message(diff, commits),
                _Summary,
            )
            # 2단계: 1단계 요약을 함께 넣어 설계 정합성을 분석한다.
            result = call_structured(
                self.client,
                self.system_prompt,
                _build_user_message(diff, design_docs, commits) + _summary_block(pre_summary),
                _AnalysisOutput,
            )
        except LLMCallError as e:
            raise AnalysisError(str(e)) from e

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


def _build_summary_message(diff: str, commits: list[str]) -> str:
    commit_text = "\n".join(f"- {c}" for c in commits) or "(커밋 메시지 없음)"
    return f"<commits>\n{commit_text}\n</commits>\n\n<diff>\n{diff}\n</diff>"


def _summary_block(summary: _Summary) -> str:
    return f"\n\n<pre_summary>\n{summary.model_dump_json()}\n</pre_summary>"
