"""대시보드용 API (DESIGN.md 3.4).

POST /api/login, POST /api/logout, GET /api/reports, GET /api/reports/{id}, POST .../fix
"""
from __future__ import annotations

import hmac
import os
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.store.report_store import ReportStore

# 세션에 로그인 여부를 저장하는 키
SESSION_KEY = "logged_in"


class DashboardAPI:
    def __init__(self, store: ReportStore):
        self.store = store

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

    def request_fix(self, issue_id, direction):
        """direction: "code" 또는 "doc". (2차 개발)"""
        raise NotImplementedError


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
