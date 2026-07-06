"""Deterministic (non-LLM) analysis computations.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Effective stats, energy profile, counter/defense coverage, dynamic move
resolution, team type coverage, magic-item evaluation, and the rule-based
recommendation generator. All formulas are UNCHANGED.
"""
import re
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from backend import models, schemas
from backend.analysis.localization import get_localized_name


def compute_effective_stats(monster, personality, talent):
    # Stat formula (corrected — double-rounding, HP final +100):
    #
    #   hp     = round( round( (2·base + 6·talent) · 85/100 + 70 ) · (1 + mod) + 100 )
    #   others = round( round( (2·base + 6·talent) · 55/100 + 10 ) · (1 + mod) + 50  )
    #
    # Two rounding steps: an inner round on the pre-personality value, then
    # an outer round on the final value. HP's final additive is +100; every
    # other stat's is +50.
    #
    # The inner core `170·L + 70` (with `L = (base + 3·talent)/100`) is
    # algebraically identical to `(2·base + 6·talent) · 0.85 + 70` — kept in
    # the old form here so the arithmetic is easy to step through, same for
    # the 110L+10 form below.

    # All arithmetic is done in exact Decimal. Building the half-way values in
    # float first (e.g. 1.1*205+10 = 235.4999...) makes ROUND_HALF_UP round the
    # wrong way at exact .5 boundaries; Decimal(str(...)) on the personality mod
    # recovers the intended exact decimal (0.15, -0.1, ...).
    def exact_stat(base, boost, mod, factor, inner_add, outer_add):
        inner_exact = Decimal(2 * base + 6 * boost) * factor / Decimal(100) + inner_add
        inner = int(inner_exact.to_integral_value(rounding=ROUND_HALF_UP))
        final = inner * (1 + Decimal(str(mod))) + outer_add
        return int(final.to_integral_value(rounding=ROUND_HALF_UP))

    return schemas.EffectiveStats(
        hp=exact_stat(monster.base_hp, talent.hp_boost, personality.hp_mod_pct, 85, 70, 100),
        phy_atk=exact_stat(monster.base_phy_atk, talent.phy_atk_boost, personality.phy_atk_mod_pct, 55, 10, 50),
        mag_atk=exact_stat(monster.base_mag_atk, talent.mag_atk_boost, personality.mag_atk_mod_pct, 55, 10, 50),
        phy_def=exact_stat(monster.base_phy_def, talent.phy_def_boost, personality.phy_def_mod_pct, 55, 10, 50),
        mag_def=exact_stat(monster.base_mag_def, talent.mag_def_boost, personality.mag_def_mod_pct, 55, 10, 50),
        spd=exact_stat(monster.base_spd, talent.spd_boost, personality.spd_mod_pct, 55, 10, 50),
    )


def compute_energy_profile(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .energy_cost
    costs = [getattr(m, "energy_cost", None) for m in moves if m is not None]
    costs = [c for c in costs if c is not None]

    avg_cost = sum(costs) / len(costs) if costs else 0.0
    # dict.fromkeys preserves first-seen order while removing duplicate IDs that
    # arise from traits like Blind Obedience (Borrow/Rewrite/Mind Grab x4 builds).
    zero_cost_moves = list(dict.fromkeys(
        m.id for m in moves if m and getattr(m, "energy_cost", None) == 0
    ))
    has_zero_cost = len(zero_cost_moves) > 0

    # Energy restore pattern
    energy_patterns = [
        r"gain[s]? \w+ energy",
        r"restore[s]? \w+ energy",
        r"steal[s]? \w+ energy",
        r"gain[s]? energy",
        r"restore[s]? energy"
    ]
    combined_pattern = re.compile("|".join(energy_patterns), flags=re.IGNORECASE)

    energy_restore_moves = list(dict.fromkeys(
        m.id for m in moves
        if m and hasattr(m, "description") and m.description and combined_pattern.search(m.description)
    ))
    has_energy_restore = len(energy_restore_moves) > 0

    return schemas.EnergyProfile(
        avg_energy_cost=round(avg_cost, 2),
        has_zero_cost_move=has_zero_cost,
        has_energy_restore_move=has_energy_restore,
        zero_cost_moves=zero_cost_moves,
        energy_restore_moves=energy_restore_moves
    )


def resolve_dynamic_move_properties(move, user_monster, monster, personality, talent, type_db_map):
    """
    Resolve dynamic properties for special moves like Willpower Impact.

    Returns dict with 'type' and 'category' (resolved or original values).
    """
    # Check if this is Willpower Impact (the only dynamic move currently)
    if move.name != "Willpower Impact":
        return {'type': move.move_type, 'category': move.move_category}

    # Resolve type: Use user's legacy type (stored as null)
    resolved_type = type_db_map.get(user_monster.legacy_type_id)

    # Resolve category: Based on effective stats comparison
    effective_stats = compute_effective_stats(monster, personality, talent)
    resolved_category = (models.MoveCategory.PHY_ATTACK
                        if effective_stats.phy_atk > effective_stats.mag_atk
                        else models.MoveCategory.MAG_ATTACK)

    return {'type': resolved_type, 'category': resolved_category}


def compute_counter_coverage(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .move_category and .has_counter
    has_attack_counter_status = False
    has_defense_counter_attack = False
    has_status_counter_defense = False
    # Track per-slot to keep `total_counter_moves` reflecting slot-fill count
    # (used by warning logic). The returned ID list dedupes for clean display
    # when traits like Blind Obedience permit duplicate moves.
    counter_slot_count = 0
    counter_move_ids = []
    seen_ids = set()

    for m in moves:
        if not m or not getattr(m, "has_counter", False):
            continue
        counter_slot_count += 1
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            counter_move_ids.append(m.id)
        cat = getattr(m, "move_category", None)
        if cat in [models.MoveCategory.PHY_ATTACK, models.MoveCategory.MAG_ATTACK]:
            has_attack_counter_status = True
        elif cat == models.MoveCategory.DEFENSE:
            has_defense_counter_attack = True
        elif cat == models.MoveCategory.STATUS:
            has_status_counter_defense = True

    return schemas.CounterCoverage(
        has_attack_counter_status=has_attack_counter_status,
        has_defense_counter_attack=has_defense_counter_attack,
        has_status_counter_defense=has_status_counter_defense,
        total_counter_moves=counter_slot_count,
        counter_move_ids=counter_move_ids
    )


def compute_defense_status_move(moves):
    # Track per-slot for the count (used by the "<2 moves" warning) and
    # dedupe the displayed ID list. Matters when traits like Blind Obedience
    # let the same move occupy multiple slots.
    slot_count = 0
    defense_status_move_ids = []
    seen_ids = set()
    for m in moves:
        if m.move_category in [models.MoveCategory.DEFENSE, models.MoveCategory.STATUS]:
            slot_count += 1
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                defense_status_move_ids.append(m.id)
    return schemas.DefenseStatusMove(
        defense_status_move_count=slot_count,
        defense_status_move=defense_status_move_ids,
    )


def compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map, personality_db_map=None, magic_item=None):
    """
    Compute offensive type coverage for a team.

    If magic_item is Willpower Enhancement (愿力强化), returns both:
    - Base coverage (original moves only)
    - Enhanced coverage (with legacy types added as Willpower Impact)
    """
    IGNORED_TYPE_NAMES = {"Leader"}
    ignored_type_ids = {t.id for t in type_db_map.values() if t.name in IGNORED_TYPE_NAMES}
    all_type_ids = set(type_db_map.keys()) - ignored_type_ids

    # Helper function to compute coverage for a given set of attack types
    def compute_coverage_levels(attack_type_ids_set):
        if not attack_type_ids_set:
            # No attack moves
            return {
                "super_effective_types": [],
                "neutral_types": [],
                "resisted_types": sorted(all_type_ids),
            }

        super_effective_types = []
        neutral_types = []
        resisted_types = []

        for def_type_id in all_type_ids:
            def_type = type_db_map[def_type_id]

            # Check if any attack type is super-effective
            has_super_effective = any(
                def_type in type_db_map[atk_id].effective_against
                for atk_id in attack_type_ids_set
            )

            if has_super_effective:
                super_effective_types.append(def_type_id)
                continue

            # Check if any attack type is at least neutral (not resisted)
            has_non_resisted_option = any(
                def_type not in type_db_map[atk_id].weak_against
                for atk_id in attack_type_ids_set
            )

            if has_non_resisted_option:
                neutral_types.append(def_type_id)
            else:
                resisted_types.append(def_type_id)

        return {
            "super_effective_types": sorted(super_effective_types),
            "neutral_types": sorted(neutral_types),
            "resisted_types": sorted(resisted_types),
        }

    # Gather all ATTACK move types for offense (exclude STATUS/DEFENSE)
    attack_type_ids = set()
    for um in user_monsters:
        base_monster = monster_db_map[um.monster_id]
        personality = personality_db_map.get(um.personality_id) if personality_db_map else None

        for move_id in [um.move1_id, um.move2_id, um.move3_id, um.move4_id]:
            move = move_db_map[move_id]

            # Only count ATTACK category moves (PHY_ATTACK or MAG_ATTACK)
            if move.move_category not in [models.MoveCategory.PHY_ATTACK, models.MoveCategory.MAG_ATTACK]:
                continue  # Skip STATUS/DEFENSE moves

            # Resolve dynamic move properties if needed
            if personality and move.name == "Willpower Impact":
                resolved_props = resolve_dynamic_move_properties(move, um, base_monster, personality, um.talent, type_db_map)
                if resolved_props['type']:
                    attack_type_ids.add(resolved_props['type'].id)
            elif move.move_type_id:
                attack_type_ids.add(move.move_type_id)

    # Compute base coverage (original moves only)
    base_coverage = compute_coverage_levels(attack_type_ids)

    # Check if Willpower Enhancement (愿力强化) is active
    willpower_enhancement_active = (
        magic_item and
        getattr(magic_item, "effect_code", None) == models.MagicEffectCode.ENHANCE_SPELL
    )

    # Compute enhanced coverage if Willpower Enhancement is active
    enhanced_coverage = None
    if willpower_enhancement_active:
        leader_type_id = next((t.id for t in type_db_map.values() if t.name == "Leader"), None)
        enhanced_attack_types = attack_type_ids.copy()

        # Add legacy types as additional attack types (simulating Willpower Impact)
        for um in user_monsters:
            legacy_type_id = um.legacy_type_id
            # Add if legacy type exists and is not Leader (Willpower Enhancement doesn't work on Leader)
            if legacy_type_id and legacy_type_id != leader_type_id:
                enhanced_attack_types.add(legacy_type_id)

        enhanced_coverage = compute_coverage_levels(enhanced_attack_types)

    # Defensive weakness, build weakness count per type across team
    type_weak_count = Counter()
    all_types = list(type_db_map.values())
    for um in user_monsters:
        base_monster = monster_db_map[um.monster_id]
        main_type = type_db_map[base_monster.main_type_id]
        sub_type = type_db_map[base_monster.sub_type_id] if base_monster.sub_type_id else None

        for attacking_type in all_types:
            weak_main = attacking_type in main_type.vulnerable_to
            weak_sub = sub_type and attacking_type in sub_type.vulnerable_to

            resist_main = attacking_type in main_type.resistant_to
            resist_sub = sub_type and attacking_type in sub_type.resistant_to

            # Per-monster weakness logic
            is_weak = False
            if weak_main and weak_sub:
                is_weak = True
            elif (weak_main and not resist_sub and not weak_sub) or (weak_sub and not resist_main and not weak_main):
                is_weak = True

            if is_weak:
                type_weak_count[attacking_type.id] += 1

    # Only include types that appear >= 3 times
    team_weak_to = [type_id for type_id, count in type_weak_count.items() if count >= 3]

    # Build result with base coverage
    result = {
        "super_effective_types": base_coverage["super_effective_types"],
        "neutral_types": base_coverage["neutral_types"],
        "resisted_types": base_coverage["resisted_types"],
        "team_weak_to": sorted(team_weak_to),
        # Backward compatibility (deprecated)
        "effective_against_types": base_coverage["super_effective_types"],
        "weak_against_types": base_coverage["resisted_types"],
    }

    # Add enhanced coverage if Willpower Enhancement is active
    if enhanced_coverage:
        result["enhanced_coverage"] = {
            "super_effective_types": enhanced_coverage["super_effective_types"],
            "neutral_types": enhanced_coverage["neutral_types"],
            "resisted_types": enhanced_coverage["resisted_types"],
        }

    return result


def compute_magic_item_eval(magic_item, user_monster_outs, type_db_map):
    valid_targets = []

    # Dynamic type IDs by name
    TYPE_NAME_TO_ID = {t.name.lower(): t.id for t in type_db_map.values()}
    GRASS_TYPE_ID = TYPE_NAME_TO_ID.get("grass")
    FIRE_TYPE_ID = TYPE_NAME_TO_ID.get("fire")
    WATER_TYPE_ID = TYPE_NAME_TO_ID.get("water")
    LEADER_TYPE_ID = TYPE_NAME_TO_ID.get("leader")

    effect_code = getattr(magic_item, "effect_code", None)

    for user_monster in user_monster_outs:
        m = user_monster.monster  # MonsterLiteOut
        legacy_type_id = getattr(user_monster.legacy_type, "id", None)
        main_type_id = getattr(m.main_type, "id", None)
        sub_type_id = getattr(m.sub_type, "id", None)

        # Willpower Enhancement: any monster except Leader legacy type
        if effect_code == models.MagicEffectCode.ENHANCE_SPELL:
            if legacy_type_id != LEADER_TYPE_ID:
                valid_targets.append(user_monster.id)

        # Sun Healing: grass main/sub/legacy
        elif effect_code == models.MagicEffectCode.SUN_HEALING:
            if ((main_type_id == GRASS_TYPE_ID) or
                (sub_type_id == GRASS_TYPE_ID) or
                (legacy_type_id == GRASS_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Flare Burst: fire main/sub/legacy
        elif effect_code == models.MagicEffectCode.FLARE_BURST:
            if ((main_type_id == FIRE_TYPE_ID) or
                (sub_type_id == FIRE_TYPE_ID) or
                (legacy_type_id == FIRE_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Flow Spell: water main/sub/legacy
        elif effect_code == models.MagicEffectCode.FLOW_SPELL:
            if ((main_type_id == WATER_TYPE_ID) or
                (sub_type_id == WATER_TYPE_ID) or
                (legacy_type_id == WATER_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Evolution Power: only if leader_potential and legacy type is Leader
        elif effect_code == models.MagicEffectCode.EVOLUTION_POWER:
            if getattr(m, "leader_potential", False) and (legacy_type_id == LEADER_TYPE_ID):
                valid_targets.append(user_monster.id)

    # More logic can be added here for other analysis aspects
    return {
        "chosen_item": magic_item,
        "valid_targets": valid_targets,
        "best_target_monster_id": None,
        "reasoning": None,
    }


def generate_recommendations(per_monster_analysis, type_coverage, magic_item_eval, move_db_map, type_db_map, language="en"):
    recs: List[schemas.RecItem] = []

    def add(category, severity, message, *, type_ids=None, monster_ids=None, move_ids=None):
        recs.append(schemas.RecItem(
            category=category,
            severity=severity,
            message=message,
            type_ids=type_ids or [],
            monster_ids=monster_ids or [],
            move_ids=move_ids or []
        ))

    # 1) Type coverage – offense (resisted types only)
    if type_coverage["resisted_types"]:
        names = [get_localized_name(type_db_map[t], language) for t in type_coverage["resisted_types"]]
        if language == "zh":
            add("coverage", "danger",
                f"你的攻击技能被以下属性完全抵抗：{', '.join(names)}。建议增加其他属性的攻击技能以提升覆盖面。",
                type_ids=type_coverage["resisted_types"])
        else:
            add("coverage", "danger",
                f"Your team's attacks are resisted by: {', '.join(names)}. Add different attack types for better coverage.",
                type_ids=type_coverage["resisted_types"])

    # 2) Team defensive weaknesses
    if type_coverage["team_weak_to"]:
        names = [get_localized_name(type_db_map[t], language) for t in type_coverage["team_weak_to"]]
        if language == "zh":
            add("weakness", "danger",
                f"你的队伍特别容易受到这些属性的攻击：{', '.join(names)}。建议考虑防守选项或抗性。",
                type_ids=type_coverage["team_weak_to"])
        else:
            add("weakness", "danger",
                f"Your team is especially vulnerable to: {', '.join(names)}. Consider defensive options or resistances.",
                type_ids=type_coverage["team_weak_to"])

    # 3) Magic item usage
    vt = magic_item_eval.valid_targets
    if not vt:
        if language == "zh":
            add("magic_item", "danger", "当前队伍中没有精灵可以使用所选择的血脉魔法！")
        else:
            add("magic_item", "danger", "Your selected magic item cannot be used by any jingling in your current team!")
    elif len(vt) == 1:
        if language == "zh":
            add("magic_item", "info", "只有一只精灵可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Only one jingling can use the selected magic item.", monster_ids=vt)
    else:
        if language == "zh":
            add("magic_item", "info", "多个精灵可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Multiple jinglings can use the selected magic item.", monster_ids=vt)

    # 4) Redundant typing
    from collections import Counter
    all_types = []
    for analysis in per_monster_analysis:
        m = analysis.user_monster.monster
        all_types.append(m.main_type.id)
        if m.sub_type is not None:
            all_types.append(m.sub_type.id)
    counts = Counter(all_types)
    common_type_ids = [tid for tid, cnt in counts.items() if cnt >= 4]
    if common_type_ids:
        names = [get_localized_name(type_db_map[t], language) for t in common_type_ids]
        if language == "zh":
            add("weakness", "warn",
                f"许多精灵共享这些属性：{', '.join(names)}。这使队伍容易受到特定克制的影响。",
                type_ids=common_type_ids)
        else:
            add("weakness", "warn",
                f"Many jinglings share these types: {', '.join(names)}. This increases vulnerability to specific counters.",
                type_ids=common_type_ids)

    # 5) Per-monster checks
    for analysis in per_monster_analysis:
        mid = analysis.user_monster.id
        mname = get_localized_name(analysis.user_monster.monster, language)

        if analysis.energy_profile.avg_energy_cost > 4:
            if language == "zh":
                add("energy", "warn",
                    f"{mname}的技能平均能量消耗很高。建议使用低能量消耗或恢复能量的技能。",
                    monster_ids=[mid])
            else:
                add("energy", "warn",
                    f"{mname}'s moves have high average energy cost. Consider lower-cost or energy-restoring moves.",
                    monster_ids=[mid])

        if analysis.counter_coverage.total_counter_moves == 0:
            if language == "zh":
                add("counters", "warn",
                    f"{mname}没有选择含有应对效果的技能。",
                    monster_ids=[mid])
            else:
                add("counters", "warn",
                    f"{mname} has no counter-effect moves selected.",
                    monster_ids=[mid])

        if analysis.defense_status_move.defense_status_move_count < 2:
            if language == "zh":
                add("defense_status", "warn",
                    f"{mname}的总防御/状态技能少于2个。建议增加更多相应技能以提升灵活性。",
                    monster_ids=[mid])
            else:
                add("defense_status", "warn",
                    f"{mname} has fewer than 2 Defense/Status moves. Consider adding more for flexibility.",
                    monster_ids=[mid])

        # Trait synergy recommendations removed - already covered in per-monster trait synergy analysis
        # for synergy in analysis.trait_synergies:
        #     if synergy.synergy_moves:
        #         move_names = [get_localized_name(move_db_map[x], language) for x in synergy.synergy_moves]
        #         if language == "zh":
        #             add("trait_synergy", "info",
        #                 f"{mname}的特性与以下技能配合良好：{', '.join(move_names)}。",
        #                 monster_ids=[mid], move_ids=synergy.synergy_moves)
        #         else:
        #             add("trait_synergy", "info",
        #                 f"{mname}'s trait works well with: {', '.join(move_names)}.",
        #                 monster_ids=[mid], move_ids=synergy.synergy_moves)

    # 6) Role diversity
    styles = [getattr(a.user_monster.monster, "preferred_attack_style", None) for a in per_monster_analysis]
    if len(set(styles)) == 1 and styles[0]:
        # ORM attribute access yields the AttackStyle enum member; interpolating
        # it directly renders "AttackStyle.PHYSICAL" instead of "Physical"
        style_value = styles[0].value if hasattr(styles[0], "value") else str(styles[0])
        if language == "zh":
            style_zh = {"Physical": "物攻", "Magic": "魔攻", "Both": "双攻"}.get(style_value, style_value)
            add("general", "warn", f"所有精灵都是{style_zh}风格的攻击者。这可能使队伍变得可预测。")
        else:
            add("general", "warn", f"All jinglings are {style_value}-style attackers. This may make the team predictable.")

    # 7) Stat and role highlights
    stat_roles_en = {
        "hp": "frontline or defensive pivot",
        "phy_atk": "main physical attacker",
        "mag_atk": "main magic attacker",
        "overall_def": "physical or special tank",
        "spd": "pressure role or finisher",
    }

    stat_roles_zh = {
        "hp": "前排或防守核心",
        "phy_atk": "主要物理输出手",
        "mag_atk": "主要魔法输出手",
        "overall_def": "物理或魔法坦克",
        "spd": "压制位或收割手",
    }

    stat_roles = stat_roles_zh if language == "zh" else stat_roles_en

    def best_of(stat, label, role_key=None):
        vals = [(get_localized_name(a.user_monster.monster, language), getattr(a.effective_stats, stat), a.user_monster.id)
                for a in per_monster_analysis]
        if not vals:
            return
        name, value, uid = max(vals, key=lambda x: x[1])
        role_txt = stat_roles.get(role_key or stat)
        if language == "zh":
            role_suffix = f"建议将其作为你的{role_txt}。" if role_txt else ""
            add(
                "stat_highlight",
                "info",
                f"{name}拥有最高的{label}（{value}）。{role_suffix}",
                monster_ids=[uid],
            )
        else:
            role_suffix = f" Consider using it as your {role_txt}." if role_txt else ""
            add(
                "stat_highlight",
                "info",
                f"{name} has the highest {label} ({value}).{role_suffix}",
                monster_ids=[uid],
            )

    best_of("hp", "生命值" if language == "zh" else "HP")
    best_of("phy_atk", "物理攻击" if language == "zh" else "Physical Attack")
    best_of("mag_atk", "魔法攻击" if language == "zh" else "Magic Attack")
    # overall defense = phy_def + mag_def
    vals_def = [
        (get_localized_name(a.user_monster.monster, language),
         a.effective_stats.phy_def + a.effective_stats.mag_def,
         a.user_monster.id)
        for a in per_monster_analysis
    ]
    if vals_def:
        name, value, uid = max(vals_def, key=lambda x: x[1])
        role_txt = stat_roles['overall_def']
        if language == "zh":
            add(
                "stat_highlight",
                "info",
                f"{name}拥有最高的总防御（{value}）。建议将其作为你的{role_txt}。",
                monster_ids=[uid],
            )
        else:
            add(
                "stat_highlight",
                "info",
                f"{name} has the highest Total Defense ({value}). Consider using it as your {role_txt}.",
                monster_ids=[uid],
            )
    best_of("spd", "速度" if language == "zh" else "Speed")

    return recs
