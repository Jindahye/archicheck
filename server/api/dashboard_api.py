"""대시보드용 API (GET /api/reports, GET /api/reports/{id}, POST .../fix)."""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from server.store.report_store import ReportStore


class DashboardAPI:
    def __init__(self, store: ReportStore):
        self.store = store

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


router = APIRouter(prefix="/api")


@router.get("/reports")
def list_reports(api: DashboardAPI = Depends(get_dashboard_api)) -> list[dict]:
    return api.list_reports()


@router.get("/reports/{id}")
def get_report(id: str, api: DashboardAPI = Depends(get_dashboard_api)) -> dict:
    return api.get_report(id)
