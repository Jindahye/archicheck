"""ConformanceAnalyzer와 FixGenerator가 함께 쓰는 Claude 호출 도우미."""
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

T = TypeVar("T", bound=BaseModel)


class ClaudeCallError(Exception):
    """Claude 호출 실패 (API 오류, 거절, 잘림, 형식 오류)."""


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def call_structured(client, system: str, user: str, output_format: type[T]) -> T:
    """output_format(pydantic 모델) 형식으로만 답하게 해서 검증된 객체를 돌려준다."""
    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "high"},
            output_format=output_format,
            # 안전 분류기가 요청을 거절하면 서버가 다른 모델로 다시 실행한다.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIError as e:
        raise ClaudeCallError(f"Claude API 호출 실패: {e}") from e

    if response.stop_reason == "refusal":
        raise ClaudeCallError("Claude가 요청을 거절했습니다.")
    if response.stop_reason == "max_tokens":
        raise ClaudeCallError("응답이 너무 길어 중간에 잘렸습니다.")
    if response.parsed_output is None:
        raise ClaudeCallError("응답을 정해진 형식으로 읽지 못했습니다.")
    return response.parsed_output
