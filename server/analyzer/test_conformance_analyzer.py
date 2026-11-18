"""ConformanceAnalyzer 단위 테스트. 실제 Claude API는 호출하지 않는다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.analyzer.conformance_analyzer import (
    AnalysisError,
    ConformanceAnalyzer,
    _AnalysisOutput,
)

SAMPLE = json.loads(
    (Path(__file__).resolve().parents[2] / "samples" / "report.json").read_text(encoding="utf-8")
)
DOCS = [{"path": "docs/architecture.md", "content": "## 인증 흐름\n세션은 메모리에 저장한다."}]


class FakeClient:
    """client.beta.messages.parse(...) 만 흉내 낸다."""

    def __init__(self, parsed=None, stop_reason="end_turn"):
        self.calls = []
        response = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

        def parse(**kwargs):
            self.calls.append(kwargs)
            return response

        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse))


def sample_output():
    issue = {k: SAMPLE["issues"][0][k] for k in ("title", "designRef", "codeRef", "detail")}
    return _AnalysisOutput.model_validate(
        {"summary": SAMPLE["summary"], "impact": SAMPLE["impact"], "issues": [issue]}
    )


def test_result_matches_sample_report_fields():
    analyzer = ConformanceAnalyzer(client=FakeClient(sample_output()))
    result = analyzer.analyze("diff text", DOCS, ["로그인 버그 수정"])

    assert result["designDocs"] == ["docs/architecture.md"]
    assert result["summary"] == SAMPLE["summary"]
    assert result["impact"] == SAMPLE["impact"]
    assert result["issues"] == SAMPLE["issues"]  # id=iss_1, direction/fix=None 포함


def test_issue_ids_are_numbered():
    out = sample_output()
    out.issues = out.issues * 3
    result = ConformanceAnalyzer(client=FakeClient(out)).analyze("d", DOCS, [])
    assert [i["id"] for i in result["issues"]] == ["iss_1", "iss_2", "iss_3"]


def test_request_contains_inputs_without_truncation():
    client = FakeClient(sample_output())
    big_diff = "+line\n" * 50_000
    ConformanceAnalyzer(client=client).analyze(big_diff, DOCS, ["커밋 A", "커밋 B"])

    call = client.calls[0]
    content = call["messages"][0]["content"]
    assert big_diff in content
    assert '<design_doc path="docs/architecture.md">' in content
    assert "- 커밋 A\n- 커밋 B" in content
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is _AnalysisOutput


def test_no_design_docs_fails_without_calling_api():
    client = FakeClient(sample_output())
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=client).analyze("d", [], [])
    assert client.calls == []


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_bad_stop_reason_raises(stop_reason):
    client = FakeClient(sample_output(), stop_reason=stop_reason)
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=client).analyze("d", DOCS, [])


def test_unparsed_output_raises():
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=FakeClient(parsed=None)).analyze("d", DOCS, [])
