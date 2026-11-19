"""수정안 생성 (DESIGN.md 3.2, 3.3 issues[].fix, NFR-5)."""
from __future__ import annotations

import logging

from pydantic import BaseModel

from server.analyzer.llm_call import LLMCallError, call_structured, load_prompt, make_client
from server.diagram.diagram_validator import DiagramValidator

log = logging.getLogger(__name__)

# NFR-5: Mermaid 문법 오류가 나면 오류 메시지를 넣어 다시 만든다 (최대 2회).
MAX_MERMAID_RETRIES = 2


class FixError(Exception):
    """수정안 생성 실패."""


class _CodeFixOutput(BaseModel):
    diff: str


class _DocRevisionOutput(BaseModel):
    before: str
    after: str
    mermaid: str | None


class FixGenerator:
    def __init__(self, client=None, validator: DiagramValidator | None = None):
        self.client = client or make_client()
        self.validator = validator or DiagramValidator()
        self.code_prompt = load_prompt("code_fix.md")
        self.doc_prompt = load_prompt("doc_revision.md")

    def code_fix(self, issue: dict, design_doc: str, code: str) -> dict:
        """코드 수정안을 만든다.

        입력: issue(3.3 issues[] 항목), design_doc(designRef 문서 전문), code(codeRef 파일 전문)
        반환: {"diff": "..."}
        """
        user = (
            f"{_issue_block(issue)}\n\n"
            f"{_design_doc_block(issue, design_doc)}\n\n"
            f'<code path="{issue["codeRef"]}">\n{code}\n</code>'
        )
        try:
            result = call_structured(self.client, self.code_prompt, user, _CodeFixOutput)
        except LLMCallError as e:
            raise FixError(str(e)) from e
        return {"diff": result.diff}

    def doc_revision(self, issue: dict, design_doc: str) -> dict:
        """문서 개정안을 만든다.

        입력: issue(3.3 issues[] 항목), design_doc(designRef 문서 전문)
        반환: {"before": "...", "after": "...", "mermaid": "..." | None}
        Mermaid 문법 오류가 최대 횟수만큼 다시 만들어도 남으면 FixError.
        """
        base = f"{_issue_block(issue)}\n\n{_design_doc_block(issue, design_doc)}"
        user = base
        for attempt in range(MAX_MERMAID_RETRIES + 1):
            try:
                result = call_structured(self.client, self.doc_prompt, user, _DocRevisionOutput)
            except LLMCallError as e:
                raise FixError(str(e)) from e

            error = self._check_mermaid(result.mermaid)
            if error is None:
                return result.model_dump()

            log.info("Mermaid 문법 오류 (시도 %d): %s", attempt + 1, error)
            user = (
                f"{base}\n\n<previous_mermaid>\n{result.mermaid}\n</previous_mermaid>\n\n"
                f"<mermaid_error>\n{error}\n</mermaid_error>"
            )

        raise FixError(f"Mermaid 다이어그램을 {MAX_MERMAID_RETRIES}회 다시 만들어도 문법 오류가 남았습니다: {error}")

    def _check_mermaid(self, mermaid: str | None) -> str | None:
        """문제가 없으면 None, 문법 오류면 오류 메시지."""
        if mermaid is None:
            return None
        try:
            return self.validator.validate(mermaid)
        except NotImplementedError:
            # ⑤의 DiagramValidator가 완성되기 전에는 검증 없이 통과시킨다.
            log.warning("DiagramValidator가 아직 구현되지 않아 Mermaid 검증을 건너뜁니다.")
            return None


def _issue_block(issue: dict) -> str:
    return (
        "<issue>\n"
        f"제목: {issue['title']}\n"
        f"설계 문서 위치: {issue['designRef']}\n"
        f"코드 위치: {issue['codeRef']}\n"
        f"내용: {issue['detail']}\n"
        "</issue>"
    )


def _design_doc_block(issue: dict, design_doc: str) -> str:
    path = issue["designRef"].split("#", 1)[0]
    return f'<design_doc path="{path}">\n{design_doc}\n</design_doc>'
