"""분석 결과 캐시. 같은 diff와 같은 설계 문서로 다시 분석하면 Gemini를 부르지 않고 저장된 결과를 돌려준다."""
from __future__ import annotations

import hashlib
import json


class AnalysisCache:
    """메모리 캐시. 키는 diff·설계 문서·커밋 메시지의 해시다."""

    def __init__(self, max_items: int = 100):
        self.max_items = max_items
        self._items: dict[str, dict] = {}

    @staticmethod
    def key(diff: str, design_docs: list[dict], commits: list[str]) -> str:
        raw = json.dumps({"diff": diff, "docs": design_docs, "commits": commits}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        return self._items.get(key)

    def put(self, key: str, result: dict) -> None:
        if len(self._items) >= self.max_items:
            self._items.pop(next(iter(self._items)))
        self._items[key] = result
