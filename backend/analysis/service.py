"""Core team-analysis engine (_perform_team_analysis).

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Loads game data, builds the 7 prompts, runs them concurrently through the
Redis-cached LLM layer, classifies errors, and assembles TeamAnalysisOut.
Behavior — including the mid-function db.close() and the partial-failure
handling — is UNCHANGED.
"""
import time
import asyncio
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from backend import models, schemas
from backend.logger import logger
from backend.config import ENABLE_REFERENCE_RESOLUTION, LLM_PROVIDER
from backend import reference_resolver
from backend.cache import redis_cache
from backend.llm_service import generate_analysis_json
from backend.tier_limits import record_llm_failures, reset_llm_failure_counter
from backend.analysis.localization import get_localized_name
from backend.analysis.computations import (
    compute_effective_stats,
    compute_energy_profile,
    resolve_dynamic_move_properties,
    compute_counter_coverage,
    compute_defense_status_move,
    compute_type_coverage,
    compute_magic_item_eval,
    generate_recommendations,
)
from backend.analysis.prompts import build_trait_synergy_prompt, build_team_synergy_prompt
from backend.analysis.cache_keys import (
    generate_monster_cache_key,
    generate_team_cache_key,
    compute_willpower_categories,
)


async def _perform_team_analysis(
    team_data: schemas.TeamCreate,
    language: str,
    db: Session
) -> tuple[schemas.TeamAnalysisOut, bool, int, int]:
    """
    Core team analysis logic shared by both endpoints.
    This function does NOT have rate limiting - that's applied at the endpoint level.

    Returns:
        Tuple of (analysis result, all_succeeded, successful_calls, actual_llm_calls) where:
        - all_succeeded is True only if all 7 LLM calls completed without errors
        - successful_calls is the count of LLM calls that completed successfully
        - actual_llm_calls is the count of calls that invoked the LLM API (not cache hits)
    """
    start_time = time.time()

    # team_data is TeamCreate (with 6 UserMonsterCreate)

    # --- Helper: Call LLM with Caching ---
    _actual_llm_calls = [0]  # mutable counter for real API calls (not cache hits)

    def _on_llm_compute():
        _actual_llm_calls[0] += 1

    async def call_llm(
        prompt: str,
        cache_key: str,
        context: str = None,
        monster_name: str = None,
    ):
        """
        Call LLM with caching support.

        Wrapper for backward compatibility - delegates to generate_analysis_json.
        """
        # Extract team hash from cache key for logging
        team_hash = cache_key[:50] if cache_key else None

        return await generate_analysis_json(
            prompt=prompt,
            cache_key=cache_key,
            llm_cache=redis_cache,  # Use Redis cache with stampede protection
            temperature=None,  # Use default from config
            context=context,
            team_hash=team_hash,
            language=language,
            monster_name=monster_name,
            on_compute=_on_llm_compute,
        )

    # === EFFICIENT DATA LOADING ===
    logger.debug("Start loading data for analysis...")
    monster_ids_to_load = {um.monster_id for um in team_data.user_monsters}
    monster_db_map = {m.id: m for m in db.query(models.Monster).filter(models.Monster.id.in_(monster_ids_to_load)).all()}
    logger.debug(f"Loaded monsters: {len(monster_db_map)}")

    # Validate all monsters were found
    missing_monsters = monster_ids_to_load - set(monster_db_map.keys())
    if missing_monsters:
        raise HTTPException(status_code=400, detail=f"Jingling IDs not found: {sorted(missing_monsters)}")

    logger.debug("Loading moves...")
    move_ids_to_load = set()
    for um in team_data.user_monsters:
        move_ids_to_load.update([um.move1_id, um.move2_id, um.move3_id, um.move4_id])
    move_db_map = {m.id: m for m in db.query(models.Move).filter(models.Move.id.in_(move_ids_to_load)).all()}
    logger.debug(f"Loaded moves: {len(move_db_map)}")

    # Validate all moves were found
    missing_moves = move_ids_to_load - set(move_db_map.keys())
    if missing_moves:
        raise HTTPException(status_code=400, detail=f"Move IDs not found: {sorted(missing_moves)}")

    # "Willpower Impact" is generated at battle time by the Willpower Enhancement
    # magic item; it is not in any jingling's move pool and must not be submitted
    # as a selected move. Its resolved type/category depend on the build
    # (legacy type, personality, talent), which the per-monster cache key does
    # not encode — accepting it would let one build's cached analysis be served
    # for a different build.
    if any(move_db_map[mid].name == "Willpower Impact" for mid in move_ids_to_load):
        raise HTTPException(
            status_code=400,
            detail="Willpower Impact cannot be selected as a move; it is granted in battle by the Willpower Enhancement magic item."
        )

    logger.debug("Loading traits...")
    trait_ids_to_load = {m.trait_id for m in monster_db_map.values()}
    trait_db_map = {t.id: t for t in db.query(models.Trait).filter(models.Trait.id.in_(trait_ids_to_load)).all()}
    logger.debug(f"Loaded traits: {len(trait_db_map)}")

    logger.debug("Loading types...")
    type_db_map = {
        t.id: t
        for t in db.query(models.Type)
        .options(
            joinedload(models.Type.effective_against),
            joinedload(models.Type.weak_against),
            joinedload(models.Type.vulnerable_to),
            joinedload(models.Type.resistant_to),
        )
        .all()
    }
    logger.debug(f"Loaded types: {len(type_db_map)}")

    logger.debug("Loading personalities...")
    personality_ids_to_load = {um.personality_id for um in team_data.user_monsters}
    personality_db_map = {p.id: p for p in db.query(models.Personality).filter(models.Personality.id.in_(personality_ids_to_load)).all()}
    logger.debug(f"Loaded personalities: {len(personality_db_map)}")

    logger.debug("Loading magic item and game terms...")
    if not team_data.magic_item_id:
        raise HTTPException(status_code=400, detail="Magic item is required to analyze a team.")
    magic_item = (db.query(models.MagicItem).filter(models.MagicItem.id == team_data.magic_item_id).first())
    if not magic_item:
        raise HTTPException(status_code=400, detail=f"Magic item with ID {team_data.magic_item_id} not found")

    # Create magic_item_db_map with the selected magic item (may be expanded with referenced magic items later)
    magic_item_db_map = {magic_item.id: magic_item}

    # Load game terms as a map for efficient lookup (used for reference resolution)
    game_term_db_map = {gt.id: gt for gt in db.query(models.GameTerm).all()}
    logger.debug(f"Loaded game terms: {len(game_term_db_map)}")

    logger.debug("Finish loading data for analysis!")

    # === CONCURRENT LLM ANALYSIS ===
    logger.debug("Start creating prompt for LLM analysis...")
    logger.info(f"Language received: {language}")

    llm_tasks = []

    # Per-monster trait synergy analysis
    for um in team_data.user_monsters:
        base_monster = monster_db_map[um.monster_id]
        trait = trait_db_map[base_monster.trait_id]
        selected_moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        preferred_attack_style = getattr(base_monster, "preferred_attack_style", "Both")

        # Get type and personality information
        legacy_type = type_db_map[um.legacy_type_id]
        main_type = type_db_map[base_monster.main_type_id]
        sub_type = type_db_map[base_monster.sub_type_id] if base_monster.sub_type_id else None
        personality = personality_db_map[um.personality_id]

        # Resolve dynamic move properties for LLM prompt
        # Create copies with resolved properties for Willpower Impact
        resolved_moves_for_prompt = []
        for move in selected_moves:
            resolved_props = resolve_dynamic_move_properties(move, um, base_monster, personality, um.talent, type_db_map)
            # Create a shallow copy and update properties if needed
            if resolved_props['type'] != move.move_type or resolved_props['category'] != move.move_category:
                move_copy = type('Move', (), {})()
                move_copy.__dict__.update(move.__dict__)
                move_copy.move_type = resolved_props['type']
                move_copy.move_category = resolved_props['category']
                resolved_moves_for_prompt.append(move_copy)
            else:
                resolved_moves_for_prompt.append(move)

        # Resolve references PER MONSTER
        if ENABLE_REFERENCE_RESOLUTION:
            entities_for_this_monster = [trait] + resolved_moves_for_prompt
            resolved_refs_per_monster = reference_resolver.resolve_references_for_prompt(entities_for_this_monster, language, db)
            game_terms_per_monster = [game_term_db_map[gt_id] for gt_id in sorted(resolved_refs_per_monster.game_terms)]

            # Load any referenced moves that aren't already in move_db_map
            missing_move_ids_per_monster = resolved_refs_per_monster.moves - set(move_db_map.keys())
            if missing_move_ids_per_monster:
                logger.debug(f"Loading {len(missing_move_ids_per_monster)} referenced moves for monster {get_localized_name(base_monster, language)}: {sorted(missing_move_ids_per_monster)}")
                missing_moves = db.query(models.Move).filter(models.Move.id.in_(missing_move_ids_per_monster)).all()
                for move in missing_moves:
                    move_db_map[move.id] = move

            referenced_moves_per_monster = [move_db_map[m_id] for m_id in sorted(resolved_refs_per_monster.moves) if m_id in move_db_map]

            # Load any referenced monsters that aren't already in monster_db_map
            missing_monster_ids_per_monster = resolved_refs_per_monster.monsters - set(monster_db_map.keys())
            if missing_monster_ids_per_monster:
                logger.debug(f"Loading {len(missing_monster_ids_per_monster)} referenced monsters for monster {get_localized_name(base_monster, language)}: {sorted(missing_monster_ids_per_monster)}")
                missing_monsters = db.query(models.Monster).filter(models.Monster.id.in_(missing_monster_ids_per_monster)).all()
                for monster in missing_monsters:
                    monster_db_map[monster.id] = monster

            referenced_monsters_per_monster = [monster_db_map[mon_id] for mon_id in sorted(resolved_refs_per_monster.monsters) if mon_id in monster_db_map]

            # Load traits of referenced monsters that aren't already in trait_db_map
            missing_ref_mon_trait_ids = {m.trait_id for m in referenced_monsters_per_monster} - set(trait_db_map.keys())
            if missing_ref_mon_trait_ids:
                logger.debug(f"Loading {len(missing_ref_mon_trait_ids)} traits for referenced monsters: {sorted(missing_ref_mon_trait_ids)}")
                for trait_obj in db.query(models.Trait).filter(models.Trait.id.in_(missing_ref_mon_trait_ids)).all():
                    trait_db_map[trait_obj.id] = trait_obj

            # Load any referenced traits that aren't already in trait_db_map
            missing_trait_ids_per_monster = resolved_refs_per_monster.traits - set(trait_db_map.keys())
            if missing_trait_ids_per_monster:
                logger.debug(f"Loading {len(missing_trait_ids_per_monster)} referenced traits for monster {get_localized_name(base_monster, language)}: {sorted(missing_trait_ids_per_monster)}")
                missing_traits = db.query(models.Trait).filter(models.Trait.id.in_(missing_trait_ids_per_monster)).all()
                for trait_obj in missing_traits:
                    trait_db_map[trait_obj.id] = trait_obj

            # Load any referenced magic items that aren't already in magic_item_db_map
            missing_magic_item_ids_per_monster = resolved_refs_per_monster.magic_items - set(magic_item_db_map.keys())
            if missing_magic_item_ids_per_monster:
                logger.debug(f"Loading {len(missing_magic_item_ids_per_monster)} referenced magic items for monster {get_localized_name(base_monster, language)}: {sorted(missing_magic_item_ids_per_monster)}")
                missing_magic_items = db.query(models.MagicItem).filter(models.MagicItem.id.in_(missing_magic_item_ids_per_monster)).all()
                for mi in missing_magic_items:
                    magic_item_db_map[mi.id] = mi

            logger.info(f"Monster {get_localized_name(base_monster, language)}: {len(game_terms_per_monster)} game terms, {len(referenced_moves_per_monster)} referenced moves, {len(referenced_monsters_per_monster)} referenced monsters")
        else:
            game_terms_per_monster = list(game_term_db_map.values())
            referenced_moves_per_monster = []
            referenced_monsters_per_monster = []

        # Generate cache key for this monster
        cache_key = generate_monster_cache_key(
            um.monster_id,
            (um.move1_id, um.move2_id, um.move3_id, um.move4_id),
            language
        )

        prompt = build_trait_synergy_prompt(base_monster, trait, resolved_moves_for_prompt, game_terms_per_monster, referenced_moves_per_monster, referenced_monsters_per_monster, main_type, sub_type, type_db_map, trait_db_map, language)

        # Get monster name for logging
        monster_name = get_localized_name(base_monster, language)

        llm_tasks.append(call_llm(
            prompt=prompt,
            cache_key=cache_key,
            context="trait_synergy",
            monster_name=monster_name,
        ))

    # Resolve references for TEAM (all entities combined)
    if ENABLE_REFERENCE_RESOLUTION:
        all_entities_for_team = []
        for um in team_data.user_monsters:
            base_monster = monster_db_map[um.monster_id]
            trait = trait_db_map[base_monster.trait_id]
            selected_moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
            all_entities_for_team.append(trait)
            all_entities_for_team.extend(selected_moves)

        # Include magic item description for reference resolution
        all_entities_for_team.append(magic_item)

        resolved_refs_team = reference_resolver.resolve_references_for_prompt(all_entities_for_team, language, db)
        game_terms_team = [game_term_db_map[gt_id] for gt_id in sorted(resolved_refs_team.game_terms)]

        # Load any referenced moves that aren't already in move_db_map
        missing_move_ids = resolved_refs_team.moves - set(move_db_map.keys())
        if missing_move_ids:
            logger.info(f"Loading {len(missing_move_ids)} referenced moves not in team: {sorted(missing_move_ids)}")
            missing_moves = db.query(models.Move).filter(models.Move.id.in_(missing_move_ids)).all()
            for move in missing_moves:
                move_db_map[move.id] = move

        # Filter out Willpower Impact from referenced moves - it's a magic-item-generated move, not a regular referenced move
        # It will be explained in the Willpower Enhancement section instead
        referenced_moves_team = [
            move_db_map[m_id] for m_id in sorted(resolved_refs_team.moves)
            if m_id in move_db_map and move_db_map[m_id].name != "Willpower Impact"
        ]

        # Load any referenced monsters that aren't already in monster_db_map
        missing_monster_ids_team = resolved_refs_team.monsters - set(monster_db_map.keys())
        if missing_monster_ids_team:
            logger.info(f"Loading {len(missing_monster_ids_team)} referenced monsters not in team: {sorted(missing_monster_ids_team)}")
            missing_monsters = db.query(models.Monster).filter(models.Monster.id.in_(missing_monster_ids_team)).all()
            for monster in missing_monsters:
                monster_db_map[monster.id] = monster

        referenced_monsters_team = [monster_db_map[mon_id] for mon_id in sorted(resolved_refs_team.monsters) if mon_id in monster_db_map]

        # Load traits of referenced monsters that aren't already in trait_db_map
        missing_ref_mon_trait_ids_team = {m.trait_id for m in referenced_monsters_team} - set(trait_db_map.keys())
        if missing_ref_mon_trait_ids_team:
            logger.info(f"Loading {len(missing_ref_mon_trait_ids_team)} traits for referenced monsters (team): {sorted(missing_ref_mon_trait_ids_team)}")
            for trait_obj in db.query(models.Trait).filter(models.Trait.id.in_(missing_ref_mon_trait_ids_team)).all():
                trait_db_map[trait_obj.id] = trait_obj

        # Load any referenced traits that aren't already in trait_db_map
        missing_trait_ids_team = resolved_refs_team.traits - set(trait_db_map.keys())
        if missing_trait_ids_team:
            logger.info(f"Loading {len(missing_trait_ids_team)} referenced traits not in team: {sorted(missing_trait_ids_team)}")
            missing_traits = db.query(models.Trait).filter(models.Trait.id.in_(missing_trait_ids_team)).all()
            for trait_obj in missing_traits:
                trait_db_map[trait_obj.id] = trait_obj

        # Load any referenced magic items that aren't already in magic_item_db_map
        missing_magic_item_ids_team = resolved_refs_team.magic_items - set(magic_item_db_map.keys())
        if missing_magic_item_ids_team:
            logger.info(f"Loading {len(missing_magic_item_ids_team)} referenced magic items not in team: {sorted(missing_magic_item_ids_team)}")
            missing_magic_items = db.query(models.MagicItem).filter(models.MagicItem.id.in_(missing_magic_item_ids_team)).all()
            for mi in missing_magic_items:
                magic_item_db_map[mi.id] = mi

        logger.info(f"Team analysis: {len(game_terms_team)} game terms, {len(referenced_moves_team)} referenced moves, {len(referenced_monsters_team)} referenced monsters")
    else:
        game_terms_team = list(game_term_db_map.values())
        referenced_moves_team = []
        referenced_monsters_team = []

    # Team-wide synergy analysis. For Willpower Enhancement teams the prompt
    # content depends on each monster's resolved Willpower Impact category
    # (personality/talent-dependent), so that signature is part of the key.
    willpower_categories = None
    if magic_item.effect_code == models.MagicEffectCode.ENHANCE_SPELL:
        willpower_categories = compute_willpower_categories(
            team_data.user_monsters, monster_db_map, personality_db_map
        )
    team_cache_key = generate_team_cache_key(team_data, language, willpower_categories)
    team_synergy_prompt = build_team_synergy_prompt(team_data.user_monsters, monster_db_map, move_db_map, type_db_map, trait_db_map, magic_item, game_terms_team, referenced_moves_team, referenced_monsters_team, language, db)
    llm_tasks.append(call_llm(
        prompt=team_synergy_prompt,
        cache_key=team_cache_key,
        context="team_synergy",
        monster_name=None,  # Team-wide analysis, no specific monster
    ))

    # Release the DB connection back to the pool before the LLM call.
    # All required data is already loaded into local dicts (monster_db_map, move_db_map, etc.).
    # ORM column attributes remain accessible on detached objects. All relationships accessed
    # post-LLM (e.g. vulnerable_to, resistant_to, move_type) must be eagerly loaded above.
    # Calling db.close() twice (here + FastAPI generator finally) is a SQLAlchemy no-op.
    db.close()

    # Gather all LLM results, capturing exceptions to handle errors gracefully
    llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)

    # Categorize errors by type for better handling
    quota_errors = []
    rate_limit_errors = []
    server_errors = []
    auth_errors = []
    other_errors = []
    successful_calls = 0

    for i, result in enumerate(llm_results):
        if isinstance(result, Exception):
            error_msg = str(result).lower()

            # Quota exhaustion (Gemini, OpenAI, etc.)
            if any(pattern in error_msg for pattern in ["429", "resource_exhausted", "quota", "insufficient_quota"]):
                quota_errors.append((i, result))
            # Rate limiting (DeepSeek, OpenAI)
            elif any(pattern in error_msg for pattern in ["rate_limit", "too_many_requests", "requests per"]):
                rate_limit_errors.append((i, result))
            # Server errors (500, 502, 503, timeout)
            elif any(pattern in error_msg for pattern in ["500", "502", "503", "504", "timeout", "timed out", "unavailable"]):
                server_errors.append((i, result))
            # Authentication errors (401, 403, invalid API key)
            elif any(pattern in error_msg for pattern in ["401", "403", "unauthorized", "forbidden", "invalid.*key", "api.*key"]):
                auth_errors.append((i, result))
            else:
                other_errors.append((i, result))
        else:
            successful_calls += 1

    # Fail fast only for CRITICAL errors that affect all requests
    # 1. Authentication errors (most critical - prevents all future requests)
    if auth_errors:
        logger.error(f"Authentication failed: {len(auth_errors)} of {len(llm_tasks)} LLM calls failed due to auth issues")
        if language == "zh":
            error_detail = "API 认证失败。请检查 API 密钥配置。"
        else:
            error_detail = "API authentication failed. Please check your API key configuration."
        raise HTTPException(status_code=401, detail=error_detail)

    # 2. Quota exhaustion (common with free tiers) - only fail if ALL calls failed
    if quota_errors and successful_calls == 0:
        logger.error(f"Quota exhausted: {len(quota_errors)} of {len(llm_tasks)} LLM calls failed due to quota limits")
        if language == "zh":
            error_detail = f"API 配额已用尽。当前提供商: {LLM_PROVIDER}。请稍后重试或检查配额限制。"
        else:
            error_detail = f"API quota exhausted for provider: {LLM_PROVIDER}. Please try again later or check your quota limits."
        raise HTTPException(status_code=429, detail=error_detail)

    # For TRANSIENT errors (server issues, rate limits, etc.), allow partial success
    # Replace failed results with error marker dicts so they can be retried later
    total_errors = len(server_errors) + len(rate_limit_errors) + len(other_errors) + len(quota_errors)
    all_succeeded = (total_errors == 0)

    if total_errors > 0:
        # Log warning about partial failure
        logger.warning(
            f"Partial analysis success: {successful_calls}/{len(llm_tasks)} LLM calls succeeded. "
            f"Errors: {len(server_errors)} server, {len(rate_limit_errors)} rate limit, "
            f"{len(quota_errors)} quota, {len(other_errors)} other"
        )

        # Replace exception results with error marker dicts
        for idx, error in server_errors + rate_limit_errors + quota_errors + other_errors:
            error_msg = str(error)
            logger.error(f"LLM call {idx} failed: {error_msg[:200]}")

            # Create error marker dict (will NOT be cached since exception was raised)
            if language == "zh":
                llm_results[idx] = {
                    "synergy_moves": [],
                    "recommendation": [f"⚠️ 分析暂时失败，请重新分析以重试。错误: {error_msg[:100]}"],
                    "_error": True,  # Marker for failed result
                    "_error_type": "transient"
                }
            else:
                llm_results[idx] = {
                    "synergy_moves": [],
                    "recommendation": [f"⚠️ Analysis temporarily failed, please re-analyze to retry. Error: {error_msg[:100]}"],
                    "_error": True,  # Marker for failed result
                    "_error_type": "transient"
                }

        # Log quota tracking info
        logger.info(f"Quota used: {successful_calls} successful LLM calls out of {len(llm_tasks)} total")

    # Circuit breaker: track provider reliability based on real API call outcomes.
    # Quota and auth errors are excluded — those are config/billing issues, not outages.
    # Only act when actual_llm_calls > 0 (cache-only responses don't reflect API health).
    failed_api_calls = len(server_errors) + len(rate_limit_errors) + len(other_errors)
    if failed_api_calls > 0:
        await record_llm_failures(failed_api_calls)
    elif _actual_llm_calls[0] > 0:
        # Real API calls were made and all succeeded — reset failure counter
        await reset_llm_failure_counter()

    logger.debug("Finish creating prompt for LLM analysis!")

    # Build UserMonsterOuts and compute per-monster analysis
    logger.debug("Start per-monster analysis...")
    user_monster_outs = []
    per_monster_analysis = []
    for i, um in enumerate(team_data.user_monsters):
        base_monster = monster_db_map[um.monster_id]
        personality = personality_db_map[um.personality_id]
        legacy_type = type_db_map[um.legacy_type_id]
        trait = trait_db_map[base_monster.trait_id]
        move1 = move_db_map[um.move1_id]
        move2 = move_db_map[um.move2_id]
        move3 = move_db_map[um.move3_id]
        move4 = move_db_map[um.move4_id]
        selected_moves = [move1, move2, move3, move4]
        talent = um.talent
        llm_result = llm_results[i]
        
        # Map move names to ids for schema output (handle both English and localized names)
        move_name_to_id = {m.name: m.id for m in selected_moves}
        # Also add localized names to the mapping
        for m in selected_moves:
            localized_name = get_localized_name(m, language)
            if localized_name != m.name:
                move_name_to_id[localized_name] = m.id
        synergy_moves = [move_name_to_id[name] for name in llm_result.get("synergy_moves", []) if name in move_name_to_id]

        trait_synergy_finding = schemas.TraitSynergyFinding(
            monster_id=base_monster.id,
            trait=schemas.TraitOut.model_validate(trait),
            synergy_moves=synergy_moves,
            recommendation=llm_result.get("recommendation", [])
        )
            
        # Call the top-level helper functions
        effective_stats = compute_effective_stats(base_monster, personality, talent)
        energy_profile = compute_energy_profile(selected_moves)
        counter_coverage = compute_counter_coverage(selected_moves)
        defense_status_move = compute_defense_status_move(selected_moves)

        # Resolve dynamic move properties for display
        move1_props = resolve_dynamic_move_properties(move1, um, base_monster, personality, talent, type_db_map)
        move2_props = resolve_dynamic_move_properties(move2, um, base_monster, personality, talent, type_db_map)
        move3_props = resolve_dynamic_move_properties(move3, um, base_monster, personality, talent, type_db_map)
        move4_props = resolve_dynamic_move_properties(move4, um, base_monster, personality, talent, type_db_map)

        # Build UserMonsterOut
        def to_monster_lite_out(monster, type_db_map):
            return schemas.MonsterLiteOut(
                id=monster.id,
                name=monster.name,
                form=monster.form,
                main_type=schemas.TypeOut(**type_db_map[monster.main_type_id].__dict__),
                sub_type=schemas.TypeOut(**type_db_map[monster.sub_type_id].__dict__) if monster.sub_type_id else None,
                leader_potential=getattr(monster, "leader_potential", False),
                is_leader_form=monster.is_leader_form,
                preferred_attack_style=getattr(monster, "preferred_attack_style", "Both"),
                localized=monster.localized,
                base_hp=monster.base_hp,
                base_phy_atk=monster.base_phy_atk,
                base_mag_atk=monster.base_mag_atk,
                base_phy_def=monster.base_phy_def,
                base_mag_def=monster.base_mag_def,
                base_spd=monster.base_spd,
                evolves_from_id=getattr(monster, "evolves_from_id", None),
            )

        # Helper to create MoveOut with resolved properties
        def to_move_out(move, resolved_props):
            move_dict = move.__dict__.copy()
            move_dict['move_type'] = resolved_props['type']
            move_dict['move_category'] = resolved_props['category']
            # Handle the type_id field
            if resolved_props['type']:
                move_dict['move_type_id'] = resolved_props['type'].id
            return schemas.MoveOut(**move_dict)

        user_monster_out = schemas.UserMonsterOut(
            id=i,
            monster=to_monster_lite_out(base_monster, type_db_map),
            personality=schemas.PersonalityOut(**personality.__dict__),
            legacy_type=schemas.TypeOut(**legacy_type.__dict__),
            move1=to_move_out(move1, move1_props),
            move2=to_move_out(move2, move2_props),
            move3=to_move_out(move3, move3_props),
            move4=to_move_out(move4, move4_props),
            talent=schemas.TalentOut(id=i, **talent.model_dump()),
        )
        
        user_monster_outs.append(user_monster_out)

        # Build MonsterAnalysisOut
        monster_analysis = schemas.MonsterAnalysisOut(
            user_monster=user_monster_out,
            effective_stats=effective_stats,
            energy_profile=energy_profile,
            counter_coverage=counter_coverage,
            defense_status_move=defense_status_move,
            trait_synergies=[trait_synergy_finding]
        )
        per_monster_analysis.append(monster_analysis)

    logger.debug("Finish per-monster analysis!")

    # Call the top-level helper functions
    logger.debug("Start team-level analysis...")
    type_coverage = compute_type_coverage(team_data.user_monsters, move_db_map, monster_db_map, type_db_map, personality_db_map, magic_item)
    magic_item_eval_dict = compute_magic_item_eval(magic_item, user_monster_outs, type_db_map)
    magic_item_out = schemas.MagicItemOut(**magic_item.__dict__)
    magic_item_eval = schemas.MagicItemEvaluation(
        chosen_item=magic_item_out,
        valid_targets=magic_item_eval_dict["valid_targets"],
        best_target_monster_id=magic_item_eval_dict.get("best_target_monster_id"),
        reasoning=magic_item_eval_dict.get("reasoning"),
    )

    recs_struct = generate_recommendations(
        per_monster_analysis,
        type_coverage,
        magic_item_eval,
        move_db_map,
        type_db_map,
        language
    )

    # Extract team synergy from the last LLM result
    team_synergy_result = llm_results[-1]  # Last result is team synergy
    team_synergy = schemas.TeamSynergyRecommendation(
        team_archetype=team_synergy_result.get("team_archetype", []),
        action_priority=team_synergy_result.get("action_priority", []),
        switching_strategy=team_synergy_result.get("switching_strategy", []),
        magic_item_usage=team_synergy_result.get("magic_item_usage", []),
        overall_strategy=team_synergy_result.get("overall_strategy", [])
    )

    team_out = schemas.TeamOut(
        id=0,
        name=team_data.name,
        user_monsters=user_monster_outs,
        magic_item=magic_item_out,
    )
    result = schemas.TeamAnalysisOut(
        team=team_out,
        per_monster=per_monster_analysis,
        type_coverage=type_coverage,
        magic_item_eval=magic_item_eval,
        recommendations=[r.message for r in recs_struct],
        recommendations_structured=recs_struct,
        team_synergy=team_synergy,
        has_partial_errors=not all_succeeded,
    )

    logger.debug("Finish team-level analysis!")
    elapsed = time.time() - start_time
    logger.info(f"Team analysis took {elapsed:.3f} seconds")
    return result, all_succeeded, successful_calls, _actual_llm_calls[0]
