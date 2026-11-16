"""Analysis endpoints: create, fetch from URL, list, read, delete, preview."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Analysis, User, get_db
from app.deps import get_current_user, rate_limit
from app.engine import analyse
from app.engine.fetcher import FetchError, fetch_page
from app.schemas import (
    AnalyseRequest,
    AnalyseUrlRequest,
    AnalysisListResponse,
    AnalysisResponse,
    AnalysisResult,
    AnalysisSummary,
    PreviewRequest,
)

router = APIRouter(prefix="/api/analyses", tags=["analyses"], dependencies=[Depends(rate_limit)])


def _to_response(record: Analysis) -> AnalysisResponse:
    """Rebuild the full response from the stored row, without re-running the engine."""
    stored = json.loads(record.signals_json)
    return AnalysisResponse(
        id=record.id,
        title=record.title,
        source_url=record.source_url,
        word_count=record.word_count,
        score=record.score,
        band=record.band,
        confidence=record.confidence,
        created_at=record.created_at,
        result=AnalysisResult.model_validate(stored),
    )


def _persist(
    db: Session,
    user: User,
    *,
    text: str,
    headline: str,
    source_url: str | None,
    title: str,
) -> Analysis:
    result = analyse(text, headline=headline, source_url=source_url)
    payload = result.as_dict()

    record = Analysis(
        user_id=user.id,
        title=title or (headline.strip() or "Untitled analysis")[:500],
        source_url=source_url,
        text=text,
        word_count=result.document.word_count,
        score=result.score,
        band=result.band.id,
        confidence=result.confidence.level,
        signals_json=json.dumps(payload),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyse pasted text",
)
def create_analysis(
    payload: AnalyseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    record = _persist(
        db,
        user,
        text=payload.text,
        headline=payload.headline,
        source_url=payload.source_url,
        title=payload.headline,
    )
    return _to_response(record)


@router.post(
    "/from-url",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Fetch a URL and analyse it",
)
def create_from_url(
    payload: AnalyseUrlRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    try:
        page = fetch_page(payload.url)
    except FetchError as exc:
        # 422: the URL was well-formed but could not be turned into text.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record = _persist(
        db,
        user,
        text=page.text,
        headline=page.title,
        source_url=page.final_url,
        title=page.title or page.final_url,
    )
    return _to_response(record)


@router.post(
    "/preview",
    response_model=AnalysisResult,
    summary="Score text without saving it",
)
def preview_analysis(payload: PreviewRequest) -> AnalysisResult:
    """No auth, no storage — this is what the live preview in the UI calls.

    It is rate limited like everything else, and it never touches the database,
    so an anonymous visitor can try the tool before signing up.
    """
    result = analyse(payload.text, headline=payload.headline, source_url=payload.source_url)
    return AnalysisResult.model_validate(result.as_dict())


@router.post(
    "/preview-url",
    response_model=AnalysisResult,
    summary="Fetch a URL and score it without saving",
)
def preview_from_url(payload: AnalyseUrlRequest) -> AnalysisResult:
    """The anonymous counterpart to /from-url.

    Same fetch and same engine, but nothing is written. This is what lets a
    visitor paste a link before they have an account.
    """
    try:
        page = fetch_page(payload.url)
    except FetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    result = analyse(page.text, headline=page.title, source_url=page.final_url)
    return AnalysisResult.model_validate(result.as_dict())


@router.get("", response_model=AnalysisListResponse, summary="List your analyses")
def list_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisListResponse:
    total = db.scalar(select(func.count()).select_from(Analysis).where(Analysis.user_id == user.id))
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return AnalysisListResponse(
        items=[AnalysisSummary.model_validate(row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{analysis_id}", response_model=AnalysisResponse, summary="Read one analysis")
def get_analysis(
    analysis_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    record = db.get(Analysis, analysis_id)
    # 404, not 403: the API must never confirm that someone else's analysis
    # exists. This is the single most important line in the file.
    if record is None or record.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found.",
        )
    return _to_response(record)


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one analysis",
)
def delete_analysis(
    analysis_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    record = db.get(Analysis, analysis_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found.",
        )
    db.delete(record)
    db.commit()
