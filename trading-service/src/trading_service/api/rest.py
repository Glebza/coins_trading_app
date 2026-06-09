"""REST API endpoints."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
async def ping() -> dict:
    return {"status": "ok"}
