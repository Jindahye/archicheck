"""GitHub Webhook 수신 (POST /webhook/github) 과 분석 처리 순서 연결 (DESIGN.md 3.1)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from server.github.comment import format_failure_comment, format_report_comment
from server.github.design_doc_locator import DesignDocLocator
from server.github.github_client import GitHubClient, PullRequestRef

log = logging.getLogger("archicheck.webhook")

HANDLED_ACTIONS = {"opened", "reopened", "synchronize"}
KST = timezone(timedelta(hours=9))


class WebhookHandler:
    def __init__(self, client=None, locator=None, analyzer=None, store=None,
                 secret: str | None = None, base_url: str | None = None):
        self.client = client or GitHubClient()
        self.locator = locator or DesignDocLocator(self.client)
        self._analyzer = analyzer
        self._store = store
        self.secret = secret if secret is not None else os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        self.base_url = base_url if base_url is not None else os.environ.get("PUBLIC_BASE_URL", "")
        self._warn_missing_config()

    def _warn_missing_config(self) -> None:
        if not self.secret:
            log.warning("GITHUB_WEBHOOK_SECRET이 비어 있습니다. 모든 Webhook을 거부합니다.")
        if not getattr(self.client, "token", "x"):
            log.warning("GITHUB_TOKEN이 비어 있습니다. 코멘트 게시가 실패하고 조회 한도가 낮습니다.")
        if not self.base_url.startswith(("http://", "https://")):
            log.warning("PUBLIC_BASE_URL이 없거나 형식이 틀립니다 (예: http://1.2.3.4:8000). "
                        "PR 코멘트에서 대시보드 링크를 뺍니다.")

    # 분석기·저장소는 처음 쓸 때 만든다 (다른 담당자 모듈의 생성자 변경에 덜 민감하게).
    @property
    def analyzer(self):
        if self._analyzer is None:
            from server.analyzer.conformance_analyzer import ConformanceAnalyzer
            self._analyzer = ConformanceAnalyzer()
        return self._analyzer

    @property
    def store(self):
        if self._store is None:
            from server.store.report_store import ReportStore
            self._store = ReportStore()
        return self._store

    # ---- 수신 ----
    async def receive(self, request: Request, background_tasks: BackgroundTasks) -> dict:
        raw = await request.body()  # 서명은 파싱 전 원본 바이트로 계산해야 한다
        if not self._verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
            raise HTTPException(status_code=401, detail="invalid signature")

        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return {"status": "pong"}
        if event != "pull_request":
            return {"status": "ignored", "reason": f"event {event}"}

        payload = json.loads(raw)
        if payload.get("action") not in HANDLED_ACTIONS:
            return {"status": "ignored", "reason": f"action {payload.get('action')}"}

        pr = self._pr_from_payload(payload)
        report = self._new_report(pr)
        self.store.save(report)  # status: analyzing
        background_tasks.add_task(self._run_analysis, pr, report)
        return {"status": "accepted", "reportId": report["id"]}

    def _verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """X-Hub-Signature-256 검증. secret이 없으면 모든 요청을 거부한다."""
        if not self.secret:
            log.error("GITHUB_WEBHOOK_SECRET이 설정되지 않아 모든 Webhook을 거부합니다")
            return False
        expected = "sha256=" + hmac.new(self.secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    # ---- 백그라운드 분석 (3.1) ----
    def _run_analysis(self, pr: PullRequestRef, report: dict) -> None:
        # 1) 분석·저장: 여기서 실패하면 리포트를 failed로 둔다.
        try:
            diff = self.client.get_diff(pr)
            commits = self.client.get_commit_messages(pr)
            docs = self.locator.locate(pr.repo, pr.head_sha)
            result = self.analyzer.analyze(diff, docs, commits) or {}

            final = {**report, **result}
            # 식별 필드는 우리가 아는 값이 기준이다 (분석기 출력이 덮어쓰지 못하게).
            final.update(id=report["id"], repo=pr.repo, pr=pr.number, headSha=pr.head_sha,
                         title=pr.title, createdAt=report["createdAt"], status="done",
                         designDocs=[d["path"] for d in docs])
            self.store.save(final)
        except Exception:  # noqa: BLE001 - 어떤 실패든 failed 처리가 우선
            log.exception("분석 실패: %s#%s (%s)", pr.repo, pr.number, report["id"])
            try:
                self.store.save({**report, "status": "failed"})
            except Exception:  # noqa: BLE001
                log.exception("failed 상태 저장도 실패: %s", report["id"])
            self._post_comment_safely(pr, format_failure_comment(report["id"]))
            return

        # 2) 코멘트 게시: 실패해도 저장된 분석 결과(done)는 그대로 둔다.
        try:
            body = format_report_comment(final, self.base_url)
        except Exception:  # noqa: BLE001
            log.exception("코멘트 본문 생성 실패: %s", report["id"])
            return
        self._post_comment_safely(pr, body)

    def _post_comment_safely(self, pr: PullRequestRef, body: str) -> None:
        """코멘트 게시 실패는 로그만 남긴다 (토큰 권한 부족 등)."""
        try:
            self.client.post_comment(pr, body)
        except Exception:  # noqa: BLE001
            log.exception("PR 코멘트 게시 실패: %s#%s (GITHUB_TOKEN 권한 확인)", pr.repo, pr.number)

    # ---- 보조 ----
    @staticmethod
    def _pr_from_payload(payload: dict) -> PullRequestRef:
        pr = payload["pull_request"]
        return PullRequestRef(
            repo=payload["repository"]["full_name"],
            number=pr["number"],
            head_sha=pr["head"]["sha"],
            title=pr.get("title", ""),
        )

    @staticmethod
    def _new_report(pr: PullRequestRef) -> dict:
        return {
            "id": f"rpt_{pr.number}_{pr.head_sha[:7]}",
            "repo": pr.repo,
            "pr": pr.number,
            "headSha": pr.head_sha,
            "title": pr.title,
            "createdAt": datetime.now(KST).isoformat(timespec="seconds"),
            "status": "analyzing",
            "designDocs": [],
            "summary": {},
            "impact": [],
            "issues": [],
        }


# ---- FastAPI 라우터: server/main.py에서 include_router 한다 ----
router = APIRouter()
_handler: WebhookHandler | None = None


def get_handler() -> WebhookHandler:
    global _handler
    if _handler is None:
        _handler = WebhookHandler()
    return _handler


@router.post("/webhook/github", status_code=202)
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    return await get_handler().receive(request, background_tasks)
