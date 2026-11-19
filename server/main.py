"""ArchiCheck FastAPI 앱 시작점 (DESIGN.md 3.6: 앱 시작점, 세션 미들웨어)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from server.api.dashboard_api import router as dashboard_router
from server.github.webhook_handler import router as webhook_router

load_dotenv()

_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    raise RuntimeError("SESSION_SECRET 환경 변수가 필요합니다 (DESIGN.md 2.4). .env에 설정하세요.")

# 대시보드 화면 파일 폴더 (DESIGN.md 3.6 dashboard/). 실행 위치와 상관없이 레포 루트 기준으로 찾는다.
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

app = FastAPI(title="ArchiCheck")

# 대시보드 로그인 세션 (DESIGN.md 3.4 대시보드 인증).
# 쿠키는 SESSION_SECRET으로 서명되고, Starlette가 항상 HttpOnly로 설정한다.
# https_only=False: 시연 서버에 HTTPS가 없어서다 (DESIGN.md 5장 한계).
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="lax",
    https_only=False,
)

app.include_router(dashboard_router)
# GitHub Webhook 수신 (POST /webhook/github, DESIGN.md 3.4). 라우터는 ②의 webhook_handler가 만든다.
app.include_router(webhook_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# 대시보드 화면 파일 제공 (DESIGN.md 3.7 ③). PR 코멘트의 /dashboard/report.html?id=... 링크가 여기로 온다.
# 화면 파일 자체는 인증 없이 내려주고, 데이터는 세션이 필요한 /api/* 가 401로 막는다 (DESIGN.md 3.4).
# html=True: /dashboard/ 로 들어오면 index.html을 보여 준다.
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
