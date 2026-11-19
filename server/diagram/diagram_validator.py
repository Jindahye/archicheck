"""Mermaid 문법 검증 (DESIGN.md 3.2, NFR-5). 담당 ⑤.

DiagramValidator().validate(mermaid_code)
  - 문법이 맞으면 None
  - 틀리면 오류 메시지 문자열. FixGenerator가 재생성 요청(<mermaid_error>)에 넣는다.

방식: Node.js에서 mermaid.parse()로 문법만 검사한다 (mermaid_validate.mjs).
  - mermaid-cli(mmdc)는 크롬(Chromium)을 띄워야 해서 서버에 추가 설치가 필요하고 무겁다.
  - mermaid.parse는 대시보드의 mermaid.js와 같은 파서라 결과가 같다.

서버 준비: Node.js 18 이상 설치 → `cd server/diagram && npm install` 한 번.
Node.js나 npm 패키지가 없으면 검증을 건너뛰고(None) 경고 로그를 남긴다.
환경 문제 때문에 수정안 생성 전체가 멈추지 않게 하기 위함이다.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_SCRIPT = _HERE / "mermaid_validate.mjs"
_MAX_ERROR_LINES = 6  # 재생성 프롬프트에 넣을 오류 메시지 길이 제한


class DiagramValidator:
    def __init__(self, node_bin: str | None = None, timeout: float = 15.0):
        self.node_bin = node_bin or shutil.which("node")
        self.timeout = timeout

    def validate(self, mermaid_code: str) -> str | None:
        """문법이 맞으면 None, 틀리면 오류 메시지."""
        code = _strip_fence(mermaid_code or "")
        if not code.strip():
            return "Mermaid 코드가 비어 있음"

        if not self.node_bin:
            log.warning("Node.js를 찾을 수 없어 Mermaid 검증을 건너뜁니다 (서버에 Node.js 18 이상 설치 필요).")
            return None
        if not (_HERE / "node_modules" / "mermaid").is_dir():
            log.warning("Mermaid 검증용 npm 패키지가 없어 검증을 건너뜁니다 (server/diagram에서 npm install 필요).")
            return None

        try:
            r = subprocess.run(
                [self.node_bin, str(_SCRIPT)],
                input=code.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout,
                cwd=_HERE,
            )
        except subprocess.TimeoutExpired:
            log.warning("Mermaid 검증 시간 초과(%.0f초), 검증을 건너뜁니다.", self.timeout)
            return None
        except OSError:
            log.exception("Mermaid 검증 스크립트 실행 실패, 검증을 건너뜁니다.")
            return None

        if r.returncode == 0:
            return None
        if r.returncode == 1:  # 문법 오류
            lines = r.stdout.decode("utf-8", "replace").strip().splitlines()[:_MAX_ERROR_LINES]
            return "\n".join(lines) or "Mermaid 문법 오류 (상세 메시지 없음)"

        # 그 밖의 종료 코드는 검사기 자체 문제다. 다이어그램 탓으로 돌리지 않는다.
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        log.warning("Mermaid 검사기 오류(code %s), 검증을 건너뜁니다: %s", r.returncode, err[-1] if err else "")
        return None


def _strip_fence(code: str) -> str:
    """AI가 ```mermaid ... ``` 로 감싸서 준 경우 벗긴다."""
    s = code.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines)
    return s
