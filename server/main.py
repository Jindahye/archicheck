"""ArchiCheck FastAPI 앱 시작점."""
from fastapi import FastAPI

app = FastAPI(title="ArchiCheck")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
