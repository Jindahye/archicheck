"""ArchiCheck FastAPI 앱 시작점."""
from fastapi import FastAPI

from server.api.dashboard_api import router as dashboard_router

app = FastAPI(title="ArchiCheck")
app.include_router(dashboard_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
