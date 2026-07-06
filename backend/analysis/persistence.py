"""Saved-analysis persistence helper.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Upsert of a TeamAnalysis row keyed by (team_id, language), concurrency-safe
against the unique constraint. Behavior UNCHANGED.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend import models


def save_or_update_analysis(
    team_id: int,
    language: str,
    analysis_data: dict,
    is_from_cache: bool,
    db: Session
) -> models.TeamAnalysis:
    """Save or update analysis for a team (replaces if exists).

    Concurrency-safe against the (team_id, language) unique constraint: with
    2 uvicorn workers, two simultaneous saves can both miss the SELECT and
    race on INSERT — the loser retries as an UPDATE instead of returning 500.
    """
    def _find_existing():
        return (
            db.query(models.TeamAnalysis)
            .filter(
                models.TeamAnalysis.team_id == team_id,
                models.TeamAnalysis.language == language
            )
            .first()
        )

    existing = _find_existing()
    if existing is None:
        new_analysis = models.TeamAnalysis(
            team_id=team_id,
            language=language,
            analysis_data=analysis_data,
            is_from_cache=is_from_cache
        )
        db.add(new_analysis)
        try:
            db.commit()
            db.refresh(new_analysis)
            return new_analysis
        except IntegrityError:
            # Concurrent request inserted the row first — fall through to update
            db.rollback()
            existing = _find_existing()
            if existing is None:
                raise

    existing.analysis_data = analysis_data
    existing.is_from_cache = is_from_cache
    existing.created_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(existing)
    return existing
