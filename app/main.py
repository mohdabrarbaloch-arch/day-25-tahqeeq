"""Tahqeeq — credibility analysis for news text.

The app factory is deliberately explicit: every middleware, every router and
every header is visible in one place, so there is no hidden behaviour to
discover later.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import analyses, auth, health

logger = logging.getLogger("tahqeeq")

STATIC_DIR = Path(__file__).parent / "static"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.validate_for_runtime()
    init_db()
    logger.info(
        "Tahqeeq starting — env=%s docs=%s url_fetch=%s",
        settings.app_env,
        settings.docs_enabled,
        settings.allow_url_fetch,
    )
    yield
    logger.info("Tahqeeq shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tahqeeq",
        description=(
            "Credibility analysis for news text. Scores how a piece is written "
            "and shows the evidence behind every signal. It does not tell you "
            "whether a claim is true."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Turn Pydantic's nested error list into one readable sentence.

        The default 422 body is a wall of JSON that a user cannot act on. This
        keeps the field name and the reason, and drops the rest.
        """
        problems: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"] if part != "body")
            message = error.get("msg", "is invalid")
            problems.append(f"{location}: {message}" if location else message)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "; ".join(problems) or "The request was invalid.",
                "code": "validation_error",
            },
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(analyses.router)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/app", include_in_schema=False)
        def app_page() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
