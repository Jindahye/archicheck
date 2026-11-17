"""수정안 생성 (코드 수정 / 문서 개정)."""


class FixGenerator:
    def code_fix(self, issue) -> dict:
        """코드 수정안을 만든다. 반환: {"diff": "..."}"""
        raise NotImplementedError

    def doc_revision(self, issue) -> dict:
        """문서 개정안을 만든다. 반환: {"before": "...", "after": "...", "mermaid": "..." | None}"""
        raise NotImplementedError
