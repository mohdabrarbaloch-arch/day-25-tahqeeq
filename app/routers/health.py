"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/api/health", response_model=HealthResponse, summary="Health check")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Reports whether the database is actually reachable, not just that the
    process is up. A health check that only proves the process started is
    worse than none."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=VERSION,
        database=database,
        url_fetch_enabled=settings.allow_url_fetch,
    )
