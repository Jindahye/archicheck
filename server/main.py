"""ArchiCheck FastAPI 앱 시작점 (DESIGN.md 3.6: 앱 시작점, 세션 미들웨어)."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from server.api.dashboard_api import router as dashboard_router

load_dotenv()

_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    raise RuntimeError("SESSION_SECRET 환경 변수가 필요합니다 (DESIGN.md 2.4). .env에 설정하세요.")

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
