"""Local API entrypoint. Project-specific routes can be added here."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AWS hackathon API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health", tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
