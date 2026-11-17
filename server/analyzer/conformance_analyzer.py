"""설계 정합성 분석. Claude API 호출은 이 모듈과 FixGenerator에서만 한다."""


class ConformanceAnalyzer:
    def analyze(self, diff, design_docs, commits) -> dict:
        """diff와 설계 문서를 비교해 3.3 형식의 리포트를 만든다."""
        raise NotImplementedError
