"""ConformanceAnalyzer와 FixGenerator가 함께 쓰는 Gemini 호출 도우미 (DESIGN.md 3.2)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

# GEMINI_MODEL 환경 변수가 없을 때 쓰는 모델. 무료 등급 한도가 넉넉한(분당 15회, 하루 500회) Flash Lite를 쓴다.
# "gemini-flash-latest" 같은 별칭은 SDK가 쓰는 v1 API에서 404가 나므로 정확한 모델 ID를 적는다.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Gemini 일시 오류(429 한도, 500, 503 수요 과다)는 잠깐 뒤 다시 시도한다 (E2E에서 503이 실제로 났다, DESIGN.md 4.2).
# 최대 3번 시도, 2초 → 4초 간격. 응답이 오지 않는 요청은 90초에서 끊는다.
HTTP_OPTIONS = types.HttpOptions(
    timeout=90_000,  # 밀리초
    retry_options=types.HttpRetryOptions(
        attempts=3, initial_delay=2.0, max_delay=8.0, http_status_codes=[429, 500, 503]
    ),
)

T = TypeVar("T", bound=BaseModel)


class LLMCallError(Exception):
    """Gemini 호출 실패 (API 오류, 차단, 잘림, 형식 오류)."""


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def make_client() -> genai.Client:
    """GEMINI_API_KEY 환경 변수로 클라이언트를 만든다. 키가 없으면 예외가 난다."""
    return genai.Client(http_options=HTTP_OPTIONS)


def call_structured(client, system: str, user: str, output_format: type[T]) -> T:
    """output_format(pydantic 모델) 형식의 JSON으로만 답하게 해서 검증된 객체를 돌려준다."""
    try:
        response = client.models.generate_content(
            model=model_name(),
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=output_format,
            ),
        )
    except Exception as e:  # noqa: BLE001 - API 오류, 네트워크 오류, 한도 초과(429) 등
        raise LLMCallError(f"Gemini API 호출 실패: {e}") from e

    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise LLMCallError(f"Gemini가 요청을 차단했습니다: {feedback.block_reason}")

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise LLMCallError("Gemini 응답이 비어 있습니다.")
    finish = candidates[0].finish_reason
    if finish == types.FinishReason.MAX_TOKENS:
        raise LLMCallError("응답이 너무 길어 중간에 잘렸습니다.")
    if finish not in (None, types.FinishReason.STOP):
        raise LLMCallError(f"Gemini가 응답을 끝내지 못했습니다: {finish}")

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, output_format):
        return parsed
    try:
        return output_format.model_validate_json(response.text or "")
    except ValidationError as e:
        raise LLMCallError("응답을 정해진 형식으로 읽지 못했습니다.") from e
