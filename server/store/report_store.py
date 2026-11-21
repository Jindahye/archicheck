"""SQLite 기반 리포트 저장소 (DESIGN.md 3.2, 3.3).

리포트(3.3 형식의 dict)를 JSON 문자열 그대로 한 행에 저장한다.
필드를 풀어서 컬럼으로 나누지 않으므로 중첩 구조(summary, impact, issues)가 보존된다.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트(= server/ 의 부모) 기준 고정 경로. 실행 위치(cwd)와 무관하다.
# data/ 아래 *.db 는 .gitignore 의 `*.db` 규칙으로 커밋되지 않는다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archicheck.db"


def default_db_path() -> Path:
    """환경 변수 ARCHICHECK_DB_PATH 가 있으면 그 경로, 없으면 data/archicheck.db."""
    env = os.environ.get("ARCHICHECK_DB_PATH")
    return Path(env) if env else DEFAULT_DB_PATH


class ReportStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS reports ("
                " id TEXT PRIMARY KEY,"
                " data TEXT NOT NULL)"
            )

    def _connect(self):
        """커밋/롤백 후 연결을 닫는 컨텍스트 매니저."""
        return _Connection(self.db_path)

    def save(self, report: dict) -> None:
        """리포트 저장. 같은 id 가 이미 있으면 덮어쓴다(upsert).

        report["id"] 가 없으면 KeyError.
        """
        report_id = report["id"]
        data = json.dumps(report, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reports (id, data) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (report_id, data),
            )

    def get(self, report_id: str) -> dict | None:
        """id 로 리포트 조회. 없으면 None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    @contextmanager
    def edit(self, report_id: str):
        """리포트를 읽고 저장할 때까지 다른 쓰기 작업을 기다리게 합니다."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM reports WHERE id = ?", (report_id,)).fetchone()
            report = json.loads(row[0]) if row else None
            yield report
            if report is not None:
                conn.execute(
                    "UPDATE reports SET data = ? WHERE id = ?",
                    (json.dumps(report, ensure_ascii=False), report_id),
                )

    def list(self) -> list[dict]:
        """모든 리포트를 createdAt 최신순으로 반환. 없으면 빈 리스트."""
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM reports").fetchall()
        reports = [json.loads(r[0]) for r in rows]
        reports.sort(key=_created_at_key, reverse=True)
        return reports


class _Connection:
    """with 블록: 정상 종료 시 commit, 예외 시 rollback, 항상 close."""

    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path)

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        with closing(self._conn):
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        return False


def _created_at_key(report: dict) -> datetime:
    """정렬 전용 키. 리포트의 createdAt 값 자체는 바꾸지 않는다.

    내부 정렬 정책:
    - timezone 정보가 있는 값은 UTC 로 변환해 비교한다.
    - timezone 정보가 없는(naive) 값은 UTC 로 간주한다.
    - 필드가 없거나 문자열이 아니거나 형식이 틀린 값은 가장 오래된 값으로 취급한다.
    """
    try:
        dt = datetime.fromisoformat(report["createdAt"])
    except (KeyError, TypeError, ValueError):
        return _OLDEST
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_OLDEST = datetime.min.replace(tzinfo=timezone.utc)
