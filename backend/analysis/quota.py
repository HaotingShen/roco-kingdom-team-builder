"""Quota / rate-limit / grace orchestration for the analyze endpoints.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Pre-flight and post-flight logic shared by both analyze endpoints. Every
quota rule, cap, grace interaction, and the CloudFront-retry contract is
UNCHANGED.
"""
from dataclasses import dataclass
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend import models, schemas
from backend.logger import logger
from backend.rate_limiter import (
    check_analysis_rate_limit_async,
    record_analysis_async,
    clear_analysis_rate_limit_async,
    get_rate_limit_message,
)
from backend.tier_limits import (
    check_analysis_limit,
    check_anonymous_analysis_limit,
    check_device_daily_cap,
    check_ip_daily_cap,
    find_device_owner,
    set_retry_grace,
    check_retry_grace,
    consume_retry_grace,
    clear_retry_grace,
    has_user_analyzed_team,
    try_claim_user_analysis_slot,
    mark_user_team_analyzed,
    record_analysis_usage,
    record_anonymous_analysis,
    record_device_and_ip_usage,
    is_circuit_open,
    try_begin_analysis_inflight,
)
from backend.analysis.cache_keys import check_if_all_cached, generate_team_composition_hash


@dataclass
class _AnalysisQuotaContext:
    """State threaded from pre-flight quota checks to post-flight charging."""
    effective_user: Optional[models.User]
    device_id: str
    client_ip: str
    team_hash: str
    language: str
    is_fully_cached: bool = False
    has_grace: bool = False
    # True when this request atomically claimed the paying slot for a cached
    # result. Only meaningful when is_fully_cached=True.
    is_paying_cached_request: bool = False
    # True when an in-flight concurrency slot was reserved and must be released.
    inflight_started: bool = False


def _resolve_analysis_effective_user(
    user: Optional[models.User], device_id: str, db: Session
) -> Optional[models.User]:
    """Anonymous requests whose device maps to an existing account use that
    account's quota. This prevents users from logging out to get fresh
    anonymous quota."""
    if user is not None:
        return user
    return find_device_owner(device_id, db)


async def _analysis_quota_preflight(
    user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_data: schemas.TeamCreate,
    language: str,
    db: Session,
) -> _AnalysisQuotaContext:
    """Run every pre-analysis quota / rate-limit / grace check.

    Raises HTTPException (429/503) when the request must be rejected.
    On success returns the context needed by _analysis_quota_postflight.
    """
    effective_user = _resolve_analysis_effective_user(user, device_id, db)
    team_hash = generate_team_composition_hash(team_data)
    ctx = _AnalysisQuotaContext(
        effective_user=effective_user,
        device_id=device_id,
        client_ip=client_ip,
        team_hash=team_hash,
        language=language,
    )

    ctx.is_fully_cached = await check_if_all_cached(team_data, language, db)

    if ctx.is_fully_cached:
        # Check grace first — a grace token means the user already paid for a
        # partial failure; this cached result is their free retry, so skip
        # quota entirely.
        ctx.has_grace = await check_retry_grace(effective_user, device_id, client_ip, team_hash, language)
        if not ctx.has_grace:
            # Check if this user already paid for this team within the cache
            # TTL. Must happen BEFORE quota checks so a user at their daily
            # limit can still retrieve their own cached result without a 429.
            already_paid = await has_user_analyzed_team(
                effective_user, device_id, client_ip, team_hash, language
            )
            if not already_paid:
                # New user hitting this cached result — quota applies.
                if effective_user is None:
                    await check_anonymous_analysis_limit(device_id, client_ip, language)
                else:
                    await check_analysis_limit(effective_user, db, language)

                # Note: device/IP daily caps are intentionally skipped for
                # cached results. Those caps guard LLM compute costs; since
                # there's no LLM call here, they must not block a new identity
                # whose device accumulated usage under a different account.

                # Atomically claim the slot (SET NX EX). Only the first of any
                # concurrent same-user requests claims it and pays; others are free.
                ctx.is_paying_cached_request = await try_claim_user_analysis_slot(
                    effective_user, device_id, client_ip, team_hash, language
                )
            # else: same user within TTL — no quota check, request is free.

        # IP/per-team throughput rate limits are skipped — they protect LLM
        # API cost, and cached results have no LLM cost.
        return ctx

    # Not cached — check circuit breaker first, before any rate limit or grace
    # consumption. If the LLM provider is in an outage, return 503 immediately
    # so no quota is charged, no rate limit key is set, and no grace is consumed.
    if await is_circuit_open():
        if language == "zh":
            circuit_detail = "AI 分析服务暂时不可用，您的次数未被扣除，请几分钟后重试。"
        else:
            circuit_detail = "AI analysis service is temporarily unavailable. Your quota has NOT been consumed. Please try again in a few minutes."
        raise HTTPException(status_code=503, detail=circuit_detail)

    # Check retry grace before quota checks
    ctx.has_grace = await check_retry_grace(effective_user, device_id, client_ip, team_hash, language)

    if not ctx.has_grace:
        # Normal flow: apply all quota checks

        # 1. Per-user quota check based on user type
        if effective_user is None:
            # Truly anonymous user (no account on device)
            await check_anonymous_analysis_limit(device_id, client_ip, language)
        else:
            # Authenticated user OR anonymous with device-linked account
            await check_analysis_limit(effective_user, db, language)

        # 2. Cross-account device daily cap (prevents multi-account abuse)
        # Premium/unlimited users are exempt
        await check_device_daily_cap(device_id, effective_user)

        # 3. IP daily cap (fallback when device_id missing).
        # Intentionally NOT applied when a device_id exists: CGNAT'd mobile
        # networks share IPs across many legitimate users.
        if device_id == "unknown-device":
            await check_ip_daily_cap(client_ip, effective_user)

        # 4. Per-team rate limit (prevents same-team concurrent duplicate
        # submissions). Grace users bypass this check — the 60s cooldown must
        # not block free retries.
        if not await check_analysis_rate_limit_async(client_ip, team_hash):
            logger.warning(
                f"Per-team rate limit exceeded for {client_ip} analyzing team {team_hash} in {language}"
            )
            raise HTTPException(
                status_code=429,
                detail=get_rate_limit_message(language)
            )

    else:
        logger.info(
            f"Retry grace active for {client_ip}:{team_hash}:{language} — "
            f"bypassing quota checks"
        )

    # 5. In-flight concurrency cap: the per-user quota check above is
    # check-then-increment (charged only after the LLM run), so a parallel
    # burst of DIFFERENT-team analyses could all pass it. Cap concurrent
    # non-cached analyses per identity; the limit (2) keeps the CloudFront
    # timeout retry working. Reserved slot is released in the endpoint's
    # finally block via ctx.inflight_started.
    if not await try_begin_analysis_inflight(effective_user, device_id, client_ip):
        raise HTTPException(status_code=429, detail=get_rate_limit_message(language))
    ctx.inflight_started = True

    # Record rate limit BEFORE analysis (always, even for grace users).
    # Grace users skipped the check above but still set the key here so that
    # concurrent non-grace users on the same IP are blocked while grace runs.
    # TTL=60s (1 min) is intentionally less than CloudFront's 120s origin timeout.
    # When CF times out and TanStack retries, the retry arrives at ~t=120s after the
    # rate limit keys have already expired. The retry then passes rate limit checks,
    # waits for the original request's distributed lock (up to 60s), and returns the
    # cached result with actual_llm_calls=0 — no duplicate quota charge.
    logger.info(f"Recording analysis for {client_ip}:{team_hash}")
    await record_analysis_async(client_ip, team_hash, limit_per_minutes=1)

    # Consume grace AFTER all pre-flight checks pass, BEFORE analysis starts.
    # This is the "point of no return" — rate limits didn't reject us, so we're
    # committed to running the analysis. Consuming here means:
    # - Rate-limited 429s don't waste grace retries
    # - Concurrent requests can't both bypass quota then both run LLM calls
    # - Crashes mid-analysis don't leak infinite free retries
    if ctx.has_grace:
        await consume_retry_grace(effective_user, device_id, client_ip, team_hash, language)

    return ctx


async def _analysis_quota_postflight(
    ctx: _AnalysisQuotaContext,
    all_succeeded: bool,
    successful_calls: int,
    actual_llm_calls: int,
) -> None:
    """Post-analysis quota recording and grace management (shared by both endpoints)."""
    effective_user = ctx.effective_user
    device_id = ctx.device_id
    client_ip = ctx.client_ip
    team_hash = ctx.team_hash
    language = ctx.language

    # If the analysis completely failed (LLM was called but nothing succeeded),
    # clear the rate limit key so the user can retry immediately without waiting
    # for the 60s cooldown. No quota was charged and no cache entry was written,
    # so there is nothing to protect. The distributed lock in get_or_compute
    # still prevents concurrent duplicate LLM calls.
    if not ctx.is_fully_cached and actual_llm_calls > 0 and successful_calls == 0:
        await clear_analysis_rate_limit_async(client_ip, team_hash)

    if ctx.is_fully_cached:
        if ctx.has_grace:
            # Grace retry resolved by a fully-cached result (full success) — clear
            # grace, no quota charge (the original partial failure already charged).
            await clear_retry_grace(effective_user, device_id, client_ip, team_hash, language)
        elif ctx.is_paying_cached_request:
            # This request atomically claimed the slot in pre-flight — charge quota.
            # The marker is already set in Redis (from try_claim_user_analysis_slot),
            # so future cached requests from the same user within TTL will be free.
            # NOTE: record_device_and_ip_usage is intentionally NOT called here.
            # The device/IP cross-account cap tracks real LLM usage only. Counting
            # cached hits would inflate the cap without any LLM cost, causing false
            # 429s on non-cached analyses and incorrect quota seeding for new accounts.
            if effective_user is None:
                await record_anonymous_analysis(device_id, client_ip)
            else:
                await record_analysis_usage(effective_user)
        # else: slot was already claimed (same user within TTL or concurrent duplicate) — free
        return

    if ctx.has_grace:
        # This was a retry under grace — don't charge quota again
        if all_succeeded:
            await clear_retry_grace(effective_user, device_id, client_ip, team_hash, language)
        # If retry also partially failed, grace counter was already decremented.
        # If counter hit 0, key is deleted — next attempt will be a fresh one.
        return

    # Charge quota only if actual LLM API calls were made and at least one succeeded.
    # actual_llm_calls == 0 means all results came from cache (including via lock-wait),
    # which prevents double-charging when a concurrent retry arrives while the first
    # request is still computing (CloudFront 120s timeout → frontend retry scenario).
    if actual_llm_calls > 0 and successful_calls > 0:
        if effective_user is None:
            await record_anonymous_analysis(device_id, client_ip)
        else:
            await record_analysis_usage(effective_user)
        # Record device/IP usage for cross-account caps
        await record_device_and_ip_usage(device_id, client_ip)
        # Mark so this user gets free repeats within the cache TTL window
        await mark_user_team_analyzed(effective_user, device_id, client_ip, team_hash, language)

        if not all_succeeded:
            # Partial success: grant grace for free retry
            await set_retry_grace(effective_user, device_id, client_ip, team_hash, language)
