"""대시보드용 API (DESIGN.md 3.4).

POST /api/login, POST /api/logout, GET /api/reports, GET /api/reports/{id}, POST .../fix
"""
from __future__ import annotations

import hmac
import logging
import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.store.report_store import ReportStore

log = logging.getLogger("archicheck.dashboard")

# 세션에 로그인 여부를 저장하는 키
SESSION_KEY = "logged_in"

# 수정안을 만들 수 있는 리포트 상태 (3.3: analyzing·failed는 불일치 목록이 확정되지 않았다)
FIXABLE_STATUSES = {"done", "resolved"}

# 외부 연동(②·① 모듈)이 던지는 실패. 다른 담당자의 모듈을 import하지 않고 클래스 이름으로 구분한다.
# (FixGenerator는 google-genai를, GitHubClient는 httpx를 import하므로, 여기서 예외 클래스를 직접
#  import하면 해당 패키지가 없는 환경에서 서버 전체가 뜨지 않는다.)
# LLMCallError: server/analyzer/llm_call.py의 Gemini 호출 실패 (DESIGN.md v0.4에서 ClaudeCallError 대체)
_EXTERNAL_ERROR_NAMES = {"FixError", "GitHubAPIError", "LLMCallError", "HTTPError"}


class DashboardAPI:
    def __init__(self, store: ReportStore, fix_generator=None, github=None):
        """fix_generator, github은 테스트에서 가짜를 넣을 때만 쓴다. None이면 처음 필요할 때 만든다."""
        self.store = store
        self.fix_generator = fix_generator
        self.github = github

    def login(self, password: str, session: dict) -> bool:
        """비밀번호가 DASHBOARD_PASSWORD와 같으면 세션에 로그인 표시를 남긴다.

        DASHBOARD_PASSWORD가 비어 있으면 아무 비밀번호로도 로그인할 수 없다.
        """
        expected = os.environ.get("DASHBOARD_PASSWORD", "")
        if not expected:
            return False
        # 한글 등 비ASCII 비밀번호도 비교할 수 있도록 bytes로 비교한다.
        if not hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
            return False
        session[SESSION_KEY] = True
        return True

    def logout(self, session: dict) -> None:
        session.clear()

    def list_reports(self) -> list[dict]:
        return self.store.list()

    def get_report(self, id: str) -> dict:
        report = self.store.get(id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    def request_fix(self, report_id: str, issue_id: str, direction: str) -> dict:
        """수정 방향을 정하고 수정안을 만들어 리포트에 저장한다 (3.4).

        direction: "code" 또는 "doc". 반환: {"direction": ..., "fix": ...}

        - 같은 issue에 같은 direction으로 다시 요청하면 저장된 수정안을 그대로 돌려준다.
        - direction이 바뀌면 새로 만들어 기존 값을 덮어쓴다.
        - 수정안 생성이나 검증에 실패하면 아무것도 저장하지 않는다.
        """
        report = self.get_report(report_id)
        issue = _find_issue(report, issue_id)

        if report.get("status") not in FIXABLE_STATUSES:
            raise HTTPException(
                status_code=409, detail=f"Report is {report.get('status')}; fix not available"
            )

        if issue.get("direction") == direction and issue.get("fix"):
            return {"direction": direction, "fix": issue["fix"]}

        design_path = str(issue.get("designRef") or "").split("#", 1)[0].strip()
        if not design_path:
            raise HTTPException(status_code=422, detail="Issue has no designRef")
        code_path = str(issue.get("codeRef") or "").strip()
        if direction == "code" and not code_path:
            raise HTTPException(status_code=422, detail="Issue has no codeRef for code fix")

        github = self._get_github()
        generator = self._get_fix_generator()
        repo, ref = report.get("repo"), report.get("headSha")
        try:
            design_doc = github.get_file(repo, ref, design_path)
            if direction == "code":
                code = github.get_file(repo, ref, code_path)
                raw = generator.code_fix(dict(issue), design_doc, code)
            else:
                raw = generator.doc_revision(dict(issue), design_doc)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"File not found in repository: {e}") from e
        except Exception as e:  # noqa: BLE001 - 아래에서 외부 실패와 내부 오류를 나눈다
            if _is_external_error(e):
                log.warning("수정안 생성 실패 (%s): %s", type(e).__name__, e)
                raise HTTPException(status_code=502, detail="Fix generation failed upstream") from e
            log.exception("수정안 생성 중 예상하지 못한 오류")
            raise

        fix = _validate_fix(direction, raw)  # 형식이 틀리면 저장 전에 502

        # 생성하는 동안 리포트가 바뀌었을 수 있으므로 다시 읽어 이 issue만 갱신한다.
        latest = self.get_report(report_id)
        target = _find_issue(latest, issue_id)
        target["direction"] = direction
        target["fix"] = fix
        if all(i.get("fix") for i in latest.get("issues", [])):
            latest["status"] = "resolved"
        self.store.save(latest)
        return {"direction": direction, "fix": fix}

    def _get_github(self):
        if self.github is not None:
            return self.github
        return _build_or_503(_default_github_client, "GitHub")

    def _get_fix_generator(self):
        if self.fix_generator is not None:
            return self.fix_generator
        return _build_or_503(_default_fix_generator, "FixGenerator")


def _find_issue(report: dict, issue_id: str) -> dict:
    for issue in report.get("issues", []):
        if issue.get("id") == issue_id:
            return issue
    raise HTTPException(status_code=404, detail="Issue not found")


def _is_external_error(exc: BaseException) -> bool:
    return any(cls.__name__ in _EXTERNAL_ERROR_NAMES for cls in type(exc).__mro__)


def _validate_fix(direction: str, raw) -> dict:
    """FixGenerator 반환값을 3.3 issues[].fix 형식으로 확인·정리한다. 틀리면 502."""
    bad = HTTPException(status_code=502, detail="Fix generator returned an invalid result")
    if not isinstance(raw, dict):
        raise bad
    if direction == "code":
        diff = raw.get("diff")
        if not isinstance(diff, str) or not diff.strip():
            raise bad
        return {"diff": diff}
    before, after, mermaid = raw.get("before"), raw.get("after"), raw.get("mermaid")
    if not isinstance(before, str) or not isinstance(after, str) or not (before.strip() or after.strip()):
        raise bad
    if mermaid is not None and not isinstance(mermaid, str):
        raise bad
    return {"before": before, "after": after, "mermaid": mermaid or None}


def _build_or_503(factory, name: str):
    try:
        return factory()
    except Exception:  # noqa: BLE001 - 패키지 미설치, API 키 없음 등. 자세한 내용은 로그에만 남긴다.
        log.exception("%s를 만들 수 없습니다 (패키지·환경 변수 확인)", name)
        raise HTTPException(status_code=503, detail=f"{name} is not available") from None


@lru_cache
def _default_fix_generator():
    # 지연 import: google-genai가 없거나 GEMINI_API_KEY가 없어도 서버는 뜬다.
    from server.analyzer.fix_generator import FixGenerator

    return FixGenerator()


@lru_cache
def _default_github_client():
    from server.github.github_client import GitHubClient

    return GitHubClient()  # GITHUB_TOKEN은 GitHubClient가 환경 변수에서 읽는다


@lru_cache
def get_store() -> ReportStore:
    return ReportStore()


def get_dashboard_api(store: ReportStore = Depends(get_store)) -> DashboardAPI:
    return DashboardAPI(store)


def require_session(request: Request) -> None:
    """3.4 표에서 인증이 "세션"인 API에 붙인다. 세션이 없으면 401."""
    if not request.session.get(SESSION_KEY):
        raise HTTPException(status_code=401, detail="Login required")


class LoginRequest(BaseModel):
    password: str


class FixRequest(BaseModel):
    direction: Literal["code", "doc"]


router = APIRouter(prefix="/api")


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    api: DashboardAPI = Depends(get_dashboard_api),
) -> dict:
    if not api.login(body.password, request.session):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"status": "ok"}


@router.post("/logout", dependencies=[Depends(require_session)])
def logout(request: Request, api: DashboardAPI = Depends(get_dashboard_api)) -> dict:
    api.logout(request.session)
    return {"status": "ok"}


@router.get("/reports", dependencies=[Depends(require_session)])
def list_reports(api: DashboardAPI = Depends(get_dashboard_api)) -> list[dict]:
    return api.list_reports()


@router.get("/reports/{id}", dependencies=[Depends(require_session)])
def get_report(id: str, api: DashboardAPI = Depends(get_dashboard_api)) -> dict:
    return api.get_report(id)


@router.post("/reports/{id}/issues/{issue_id}/fix", dependencies=[Depends(require_session)])
def request_fix(
    id: str,
    issue_id: str,
    body: FixRequest,
    api: DashboardAPI = Depends(get_dashboard_api),
) -> dict:
    # 일부러 async가 아닌 def: Gemini·GitHub 호출이 오래 걸려서 스레드풀에서 돌린다.
    return api.request_fix(id, issue_id, body.direction)
