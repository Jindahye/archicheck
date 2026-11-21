"""빠른 리포트: 분석 결과를 바로 DB에 넣고 PR에 짧은 코멘트를 단다."""
from __future__ import annotations

import json
import os
import sqlite3

import httpx
from google import genai

DB_PATH = "data/archicheck.db"


def quick_summary(diff: str) -> str:
    """diff를 한 문장으로 요약한다."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"다음 diff를 한 문장으로 요약해:\n{diff}",
    )
    return resp.text


def save_report(report: dict) -> None:
    """리포트를 SQLite에 바로 저장한다."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO reports (id, data) VALUES (?, ?)",
        (report["id"], json.dumps(report, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def post_quick_comment(repo: str, pr: int, text: str) -> None:
    """PR에 짧은 코멘트를 단다."""
    httpx.post(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
        json={"body": text},
        timeout=10,
    )


def run(report: dict, diff: str) -> None:
    summary = quick_summary(diff)
    report["quickSummary"] = summary
    save_report(report)
    post_quick_comment(report["repo"], report["pr"], f"빠른 요약: {summary}")
