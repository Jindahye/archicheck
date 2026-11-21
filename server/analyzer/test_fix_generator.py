"""FixGenerator 단위 테스트. 실제 Gemini API는 호출하지 않는다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

from server.analyzer.fix_generator import (
    MAX_MERMAID_RETRIES,
    FixError,
    FixGenerator,
    _CodeFixOutput,
    _DocRevisionOutput,
)

ISSUE = json.loads(
    (Path(__file__).resolve().parents[2] / "samples" / "report.json").read_text(encoding="utf-8")
)["issues"][0]
DOC = "## 인증 흐름\n세션은 메모리에 저장한다.\n```mermaid\nsequenceDiagram\n  A->>B: login\n```"
CODE = "class SessionStore:\n    def save(self, s): db.insert(s)\n"


class FakeClient:
    """client.models.generate_content(...) 를 흉내 낸다. 호출마다 outputs를 차례로 돌려준다."""

    def __init__(self, *outputs, finish_reason=types.FinishReason.STOP):
        self.calls = []
        outputs = list(outputs)

        def generate_content(**kwargs):
            self.calls.append(kwargs)
            out = outputs.pop(0)
            return SimpleNamespace(
                parsed=out,
                text=out.model_dump_json(),
                candidates=[SimpleNamespace(finish_reason=finish_reason)],
                prompt_feedback=None,
            )

        self.models = SimpleNamespace(generate_content=generate_content)


class FakeValidator:
    """errors를 차례로 돌려준다 (None = 통과)."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.seen = []

    def validate(self, code):
        self.seen.append(code)
        return self.errors.pop(0)


class NotReadyValidator:
    def validate(self, code):
        raise NotImplementedError


def rev(mermaid="sequenceDiagram\n  A->>B: login\n  B->>DB: save"):
    return _DocRevisionOutput(before="세션은 메모리에 저장한다.", after="세션은 DB에 저장한다.", mermaid=mermaid)


# --- 코드 수정안 ---


def test_code_fix_returns_diff_and_sends_inputs():
    client = FakeClient(_CodeFixOutput(diff="--- a/x\n+++ b/x\n"))
    result = FixGenerator(client=client, validator=FakeValidator()).code_fix(ISSUE, DOC, CODE)

    assert result == {"diff": "--- a/x\n+++ b/x\n"}
    content = client.calls[0]["contents"]
    assert '<design_doc path="docs/architecture.md">' in content  # "#섹션" 은 경로에서 뗀다
    assert f'<code path="{ISSUE["codeRef"]}">\n{CODE}' in content
    assert ISSUE["detail"] in content


def test_code_fix_blocked_response_raises():
    client = FakeClient(_CodeFixOutput(diff=""), finish_reason=types.FinishReason.SAFETY)
    with pytest.raises(FixError):
        FixGenerator(client=client, validator=FakeValidator()).code_fix(ISSUE, DOC, CODE)


# --- 문서 개정안 ---


def test_doc_revision_valid_mermaid_first_try():
    client = FakeClient(rev())
    result = FixGenerator(client=client, validator=FakeValidator(None)).doc_revision(ISSUE, DOC)

    assert set(result) == {"before", "after", "mermaid"}
    assert len(client.calls) == 1


def test_doc_revision_without_diagram_skips_validation():
    validator = FakeValidator()
    result = FixGenerator(client=FakeClient(rev(mermaid=None)), validator=validator).doc_revision(ISSUE, DOC)

    assert result["mermaid"] is None
    assert validator.seen == []


def test_doc_revision_retries_with_error_message():
    client = FakeClient(rev("bad"), rev())
    validator = FakeValidator("Parse error on line 2", None)
    result = FixGenerator(client=client, validator=validator).doc_revision(ISSUE, DOC)

    assert result["mermaid"].startswith("sequenceDiagram")
    assert len(client.calls) == 2
    retry = client.calls[1]["contents"]
    assert "<previous_mermaid>\nbad\n</previous_mermaid>" in retry
    assert "Parse error on line 2" in retry


def test_doc_revision_gives_up_after_max_retries():
    attempts = MAX_MERMAID_RETRIES + 1
    client = FakeClient(*[rev("bad")] * attempts)
    validator = FakeValidator(*["error"] * attempts)
    with pytest.raises(FixError):
        FixGenerator(client=client, validator=validator).doc_revision(ISSUE, DOC)
    assert len(client.calls) == attempts  # 처음 1회 + 재생성 2회


def test_doc_revision_passes_when_validator_not_ready():
    client = FakeClient(rev())
    result = FixGenerator(client=client, validator=NotReadyValidator()).doc_revision(ISSUE, DOC)
    assert result["mermaid"] is not None


# --- 재분석 요청 문구 (feedback) ---


def test_code_fix_includes_feedback_when_given():
    client = FakeClient(_CodeFixOutput(diff="d"))
    FixGenerator(client=client, validator=FakeValidator()).code_fix(ISSUE, DOC, CODE, feedback="  새 클래스를 만들지 말 것 ")
    assert "<user_feedback>\n새 클래스를 만들지 말 것\n</user_feedback>" in client.calls[0]["contents"]


def test_no_feedback_block_when_empty():
    client = FakeClient(_CodeFixOutput(diff="d"), _CodeFixOutput(diff="d"))
    gen = FixGenerator(client=client, validator=FakeValidator())
    gen.code_fix(ISSUE, DOC, CODE)
    gen.code_fix(ISSUE, DOC, CODE, feedback="   ")
    assert all("<user_feedback>" not in c["contents"] for c in client.calls)


def test_doc_revision_keeps_feedback_on_mermaid_retry():
    client = FakeClient(rev(), rev())
    FixGenerator(client=client, validator=FakeValidator("Parse error", None)).doc_revision(
        ISSUE, DOC, feedback="실제 메서드 이름을 쓸 것"
    )
    assert len(client.calls) == 2
    assert all("<user_feedback>\n실제 메서드 이름을 쓸 것\n</user_feedback>" in c["contents"] for c in client.calls)
