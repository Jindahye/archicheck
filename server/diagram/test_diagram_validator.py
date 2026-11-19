"""DiagramValidator 단위 테스트.

Node.js와 npm 패키지(server/diagram에서 npm install)가 있어야 실제 검사를 한다.
없으면 실제 검사 테스트는 건너뛰고(skip), '없을 때 건너뛰는 동작'만 확인한다.
"""
import shutil
from pathlib import Path

import pytest

from server.diagram.diagram_validator import DiagramValidator, _strip_fence

READY = bool(shutil.which("node")) and (Path(__file__).parent / "node_modules" / "mermaid").is_dir()
needs_node = pytest.mark.skipif(not READY, reason="Node.js 또는 npm 패키지 없음 (server/diagram에서 npm install)")


@needs_node
@pytest.mark.parametrize("code", [
    "sequenceDiagram\n  User->>AuthController: 로그인\n  AuthController->>SessionDB: 세션 저장\n  AuthController-->>User: 토큰",
    "classDiagram\n  UserService ..> UserRepository : 사용\n  class DiagramValidator {\n    +validate(mermaidCode) str\n  }",
    "flowchart LR\n  Dev[\"개발자\"] --- UC1([\"설계 정합성 검사\"])",
    "```mermaid\nsequenceDiagram\n  A->>B: login\n```",
])
def test_valid_returns_none(code):
    assert DiagramValidator().validate(code) is None


@needs_node
@pytest.mark.parametrize("code", [
    "sequenceDiagram\n  User->>: 로그인",
    "classDiagram\n  UserService --> \n",
    "notADiagram\n  A --> B",
])
def test_invalid_returns_message(code):
    msg = DiagramValidator().validate(code)
    assert isinstance(msg, str) and msg.strip()


@needs_node
def test_error_message_points_to_line():
    msg = DiagramValidator().validate("sequenceDiagram\n  A->>B: ok\n  User->>: 로그인")
    assert "line 3" in msg


def test_empty_code_is_error():
    assert DiagramValidator().validate("   ") == "Mermaid 코드가 비어 있음"


def test_skips_when_node_missing(caplog):
    v = DiagramValidator()
    v.node_bin = None
    assert v.validate("sequenceDiagram\n  User->>: broken") is None
    assert "Node.js" in caplog.text


def test_strip_fence():
    assert _strip_fence("```mermaid\nclassDiagram\n  A --> B\n```") == "classDiagram\n  A --> B"
    assert _strip_fence("classDiagram\n  A --> B") == "classDiagram\n  A --> B"
