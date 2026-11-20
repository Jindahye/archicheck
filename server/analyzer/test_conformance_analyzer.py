"""ConformanceAnalyzer 단위 테스트. 실제 Gemini API는 호출하지 않는다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

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
    """client.models.generate_content(...) 만 흉내 낸다."""

    def __init__(self, parsed=None, finish_reason=types.FinishReason.STOP, block_reason=None, text=None):
        self.calls = []
        response = SimpleNamespace(
            parsed=parsed,
            text=text if text is not None else (parsed.model_dump_json() if parsed else ""),
            candidates=[SimpleNamespace(finish_reason=finish_reason)],
            prompt_feedback=SimpleNamespace(block_reason=block_reason) if block_reason else None,
        )

        def generate_content(**kwargs):
            self.calls.append(kwargs)
            return response

        self.models = SimpleNamespace(generate_content=generate_content)


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


def test_request_contains_inputs_without_truncation(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    client = FakeClient(sample_output())
    big_diff = "+line\n" * 50_000
    ConformanceAnalyzer(client=client).analyze(big_diff, DOCS, ["커밋 A", "커밋 B"])

    call = client.calls[0]
    content = call["contents"]
    assert big_diff in content
    assert '<design_doc path="docs/architecture.md">' in content
    assert "- 커밋 A\n- 커밋 B" in content
    assert call["model"] == "gemini-3.5-flash-lite"
    assert call["config"].response_schema is _AnalysisOutput
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].system_instruction  # 프롬프트 파일 내용


def test_model_can_be_changed_by_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    client = FakeClient(sample_output())
    ConformanceAnalyzer(client=client).analyze("d", DOCS, [])
    assert client.calls[0]["model"] == "gemini-test-model"


def test_falls_back_to_text_when_parsed_missing():
    out = sample_output()
    client = FakeClient(parsed=None, text=out.model_dump_json())
    result = ConformanceAnalyzer(client=client).analyze("d", DOCS, [])
    assert result["summary"] == SAMPLE["summary"]


def test_no_design_docs_fails_without_calling_api():
    client = FakeClient(sample_output())
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=client).analyze("d", [], [])
    assert client.calls == []


@pytest.mark.parametrize("finish_reason", [types.FinishReason.MAX_TOKENS, types.FinishReason.SAFETY])
def test_bad_finish_reason_raises(finish_reason):
    client = FakeClient(sample_output(), finish_reason=finish_reason)
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=client).analyze("d", DOCS, [])


def test_blocked_prompt_raises():
    client = FakeClient(sample_output(), block_reason="SAFETY")
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=client).analyze("d", DOCS, [])


def test_api_exception_raises():
    class BrokenClient:
        models = SimpleNamespace(generate_content=lambda **kw: (_ for _ in ()).throw(RuntimeError("429")))

    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=BrokenClient()).analyze("d", DOCS, [])


def test_unparsed_output_raises():
    with pytest.raises(AnalysisError):
        ConformanceAnalyzer(client=FakeClient(parsed=None)).analyze("d", DOCS, [])


def test_client_retries_temporary_gemini_errors(monkeypatch):
    """make_client는 503(수요 과다)·429(한도) 같은 일시 오류를 재시도하도록 설정한다."""
    from server.analyzer import llm_call

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = llm_call.make_client()
    retry = llm_call.HTTP_OPTIONS.retry_options
    assert retry.attempts >= 2
    assert {429, 503} <= set(retry.http_status_codes)
    assert client._api_client._http_options.retry_options == retry
