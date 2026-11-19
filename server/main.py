"""ArchiCheck FastAPI 앱 시작점 (DESIGN.md 3.6: 앱 시작점, 세션 미들웨어)."""
import importlib
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from server.api.dashboard_api import router as dashboard_router

load_dotenv()

log = logging.getLogger("archicheck.main")

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


def include_webhook_router(target: FastAPI) -> bool:
    """GitHub Webhook 라우터(POST /webhook/github, DESIGN.md 3.4)를 연결한다.

    라우터는 ②의 server/github/webhook_handler.py가 만든다. 그 모듈에 router가 아직 없는
    (스텁 상태인) 동안에는 연결을 건너뛰고 경고를 남긴다. 그래야 ②의 구현이 main에 들어오기
    전에도 서버가 뜨고, 들어온 뒤에는 이 코드를 고치지 않아도 자동으로 연결된다.

    모듈을 불러오다 실패하는 진짜 오류(패키지 미설치 등)는 숨기지 않고 그대로 올려 보낸다.
    연결했으면 True, 건너뛰었으면 False.
    """
    module = importlib.import_module("server.github.webhook_handler")
    router = getattr(module, "router", None)
    if router is None:
        log.warning(
            "server.github.webhook_handler에 router가 없어 POST /webhook/github을 연결하지 못했습니다. "
            "GitHub Webhook을 받을 수 없습니다."
        )
        return False
    target.include_router(router)
    return True


include_webhook_router(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
