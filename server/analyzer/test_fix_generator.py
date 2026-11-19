"""FixGenerator 단위 테스트. 실제 Claude API는 호출하지 않는다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    """client.beta.messages.parse(...) 를 흉내 낸다. 호출마다 outputs를 차례로 돌려준다."""

    def __init__(self, *outputs, stop_reason="end_turn"):
        self.calls = []
        outputs = list(outputs)

        def parse(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(parsed_output=outputs.pop(0), stop_reason=stop_reason)

        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse))


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
    content = client.calls[0]["messages"][0]["content"]
    assert '<design_doc path="docs/architecture.md">' in content  # "#섹션" 은 경로에서 뗀다
    assert f'<code path="{ISSUE["codeRef"]}">\n{CODE}' in content
    assert ISSUE["detail"] in content


def test_code_fix_refusal_raises():
    client = FakeClient(_CodeFixOutput(diff=""), stop_reason="refusal")
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
    retry = client.calls[1]["messages"][0]["content"]
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
