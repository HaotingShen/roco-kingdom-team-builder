"""FastAPI routes for team analysis and saved-analysis persistence.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
The @app.* decorators became @router.* on an APIRouter that main.py includes;
paths, response models, tags, dependencies, and bodies are UNCHANGED.
"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, joinedload
from pydantic import ValidationError
from backend import models, schemas
from backend.logger import logger
from backend.database import get_db
from backend.dependencies import get_current_user, get_user_or_anonymous
from backend.tier_limits import end_analysis_inflight
from backend.analysis.service import _perform_team_analysis
from backend.analysis.persistence import save_or_update_analysis
from backend.analysis.quota import (
    _analysis_quota_preflight,
    _analysis_quota_postflight,
    _resolve_analysis_effective_user,
)

router = APIRouter()


@router.post("/team/analyze", response_model=schemas.TeamAnalysisOut)
async def analyze_team(
    req: schemas.TeamAnalyzeInlineRequest,
    request: Request,
    user_or_anon: tuple = Depends(get_user_or_anonymous),
    db: Session = Depends(get_db)
):
    """Analyze a team configuration (inline data from request).

    Three-tier rate limiting:
    - Anonymous: 1/day via device_id + IP tracking
    - Guest: 3/day via user.id tracking
    - Registered: 5/day (free) or more (premium) via user.id tracking
    - IP-based rate limit also applies (prevents rapid requests)
    - Cached analyses bypass ALL rate limits
    - Anonymous users whose device_id maps to an existing account
      use that account's quota (prevents double-dipping on logout)
    """
    user, device_id, client_ip = user_or_anon

    ctx = await _analysis_quota_preflight(
        user, device_id, client_ip, req.team, req.language, db
    )

    try:
        result, all_succeeded, successful_calls, actual_llm_calls = await _perform_team_analysis(
            req.team, req.language, db
        )
    finally:
        if ctx.inflight_started:
            await end_analysis_inflight(ctx.effective_user, device_id, client_ip)

    await _analysis_quota_postflight(ctx, all_succeeded, successful_calls, actual_llm_calls)

    return result


@router.post("/team/analyze_by_id", response_model=schemas.TeamAnalysisOut)
async def analyze_team_by_id(
    req: schemas.TeamAnalyzeByIdRequest,
    request: Request,
    user_or_anon: tuple = Depends(get_user_or_anonymous),
    db: Session = Depends(get_db)
):
    """Analyze a saved team by its ID.

    Three-tier rate limiting (same as /team/analyze):
    - Anonymous: 1/day via device_id + IP tracking
    - Guest: 3/day via user.id tracking
    - Registered: 5/day (free) or more (premium) via user.id tracking
    - Cached analyses bypass ALL rate limits
    - Anonymous users whose device_id maps to an existing account
      use that account's quota (prevents double-dipping on logout)
    """
    user, device_id, client_ip = user_or_anon

    # Load the team with its monsters and talents (single query, no N+1)
    db_team = (
        db.query(models.Team)
        .options(joinedload(models.Team.user_monsters).joinedload(models.UserMonster.talent))
        .filter(models.Team.id == req.team_id)
        .first()
    )
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Only the team's owner may analyze a private team — the response
    # includes the full composition, and team IDs are sequential integers.
    # "Owner" means the authenticated user, or (when the access token has
    # expired mid-session) the account linked to this device. Featured teams
    # are public and analyzable by anyone.
    effective_user = _resolve_analysis_effective_user(user, device_id, db)
    is_owner = effective_user is not None and db_team.owner_id == effective_user.id
    if not (is_owner or db_team.is_featured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to analyze this team"
        )

    # Snapshot before _perform_team_analysis closes the session (detaching db_team)
    team_is_featured = db_team.is_featured

    # Build TeamCreate from DB objects
    user_monsters = []
    for um in db_team.user_monsters:
        talent = um.talent
        user_monsters.append(
            schemas.UserMonsterCreate(
                monster_id=um.monster_id,
                personality_id=um.personality_id,
                legacy_type_id=um.legacy_type_id,
                move1_id=um.move1_id,
                move2_id=um.move2_id,
                move3_id=um.move3_id,
                move4_id=um.move4_id,
                talent=schemas.TalentIn(
                    hp_boost=talent.hp_boost,
                    phy_atk_boost=talent.phy_atk_boost,
                    mag_atk_boost=talent.mag_atk_boost,
                    phy_def_boost=talent.phy_def_boost,
                    mag_def_boost=talent.mag_def_boost,
                    spd_boost=talent.spd_boost
                ),
            )
        )
    try:
        team_data = schemas.TeamCreate(
            name=db_team.name or "Team",
            user_monsters=user_monsters,
            magic_item_id=db_team.magic_item_id
        )
    except ValidationError:
        # Stored team can't be analyzed (e.g. not exactly 6 monsters, from a
        # pre-validation era or partial import) — client error, not a crash.
        raise HTTPException(
            status_code=400,
            detail="This team is incomplete and cannot be analyzed. Edit and re-save it first."
        )

    ctx = await _analysis_quota_preflight(
        user, device_id, client_ip, team_data, req.language, db
    )

    try:
        result, all_succeeded, successful_calls, actual_llm_calls = await _perform_team_analysis(
            team_data, req.language, db
        )
    finally:
        if ctx.inflight_started:
            await end_analysis_inflight(ctx.effective_user, device_id, client_ip)

    await _analysis_quota_postflight(ctx, all_succeeded, successful_calls, actual_llm_calls)

    # Persist the fresh analysis server-side for the owner. This is what makes
    # a saved team's analysis appear on the owner's other devices without the
    # separate manual "Save Analysis" step. Partial results are not persisted —
    # they contain transient error markers and would overwrite a good analysis.
    if is_owner and not team_is_featured and all_succeeded and successful_calls > 0:
        try:
            save_or_update_analysis(
                team_id=req.team_id,
                language=req.language,
                analysis_data=result.model_dump(mode="json"),
                is_from_cache=(actual_llm_calls == 0),
                db=db,
            )
            logger.info(f"Auto-saved analysis for team {req.team_id} ({req.language})")
        except Exception as e:
            # Persistence failure must not fail the analysis response the user paid for.
            logger.error(f"Auto-save of analysis for team {req.team_id} failed: {e}")

    return result


@router.post("/analysis/save", response_model=schemas.SavedAnalysisOut, tags=["Analysis"])
def save_analysis(
    req: schemas.SaveAnalysisRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save an analysis result for a team. Replaces existing if present.

    SECURITY: Only owner can save analysis for their team.
    """
    team = db.query(models.Team).filter(models.Team.id == req.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to save analysis for this team"
        )

    saved = save_or_update_analysis(
        team_id=req.team_id,
        language=req.language,
        # mode="json" keeps the stored JSONB free of Python-only types
        # (enums, datetimes) regardless of how the schema evolves
        analysis_data=req.analysis_data.model_dump(mode="json"),
        is_from_cache=req.is_from_cache,
        db=db
    )

    return saved


@router.get("/teams/{team_id}/analysis", response_model=schemas.FullSavedAnalysisOut, tags=["Analysis"])
def get_saved_analysis(
    team_id: int,
    language: Literal["en", "zh"] = "en",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve saved analysis for a team.

    SECURITY: Only owner can view team's analysis.
    """
    # Check team ownership first
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this team's analysis"
        )

    saved = (
        db.query(models.TeamAnalysis)
        .filter(
            models.TeamAnalysis.team_id == team_id,
            models.TeamAnalysis.language == language
        )
        .first()
    )

    if not saved:
        # Fall back to the analysis saved under the other language: an analysis
        # saved in ZH on one device should still be viewable on an EN-defaulting
        # device instead of looking like it was never saved. The response's
        # `language` field tells the client what it actually got.
        saved = (
            db.query(models.TeamAnalysis)
            .filter(models.TeamAnalysis.team_id == team_id)
            .order_by(models.TeamAnalysis.created_at.desc())
            .first()
        )

    if not saved:
        raise HTTPException(status_code=404, detail="No saved analysis found for this team")

    return saved


@router.delete("/teams/{team_id}/analysis", status_code=status.HTTP_204_NO_CONTENT, tags=["Analysis"])
def delete_saved_analysis(
    team_id: int,
    language: Literal["en", "zh"] = "en",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete saved analysis for a team.

    SECURITY: Only owner can delete team's analysis.
    """
    # Check team ownership first
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this team's analysis"
        )

    saved = (
        db.query(models.TeamAnalysis)
        .filter(
            models.TeamAnalysis.team_id == team_id,
            models.TeamAnalysis.language == language
        )
        .first()
    )

    if not saved:
        raise HTTPException(status_code=404, detail="No saved analysis found")

    db.delete(saved)
    db.commit()
    return
