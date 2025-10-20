from fastapi import FastAPI, Depends, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker, joinedload
from sqlalchemy import create_engine, or_, cast, String, func
from backend.config import DATABASE_URL, OPENAI_API_KEY, GEMINI_API_KEY
from typing import Optional, List
from decimal import Decimal, ROUND_HALF_UP
from backend import models, schemas
from collections import Counter
import re
from google import genai
from google.genai import types
import asyncio
import json
import time
import logging

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for development, restrict for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === TOP-LEVEL HELPER FUNCTIONS ===
# Compute effective stats with base, talent, and personality multipliers
def round_half_up(n):
    return int(Decimal(n).to_integral_value(rounding=ROUND_HALF_UP))

def compute_effective_stats(monster, personality, talent):
    # HP formula: hp = [1.7 × (base_stats + hp_talent × 6) + 70 − 2.55 × hp_talent] × (1 + hp_personality_modifier) + 100
    base_hp = monster.base_hp
    hp_talent = talent.hp_boost
    hp = (1.7 * (base_hp + hp_talent * 6) + 70 - 2.55 * hp_talent)
    hp = hp * (1 + personality.hp_mod_pct)
    hp = int(round_half_up(hp + 100))  # int() for safety

    # other stats = round_half_up(1.1 × (base_stats + talent × 6) + 10) × (1 + personality_modifier) + 50
    def other_stat(attr, personality_attr, talent_attr):
        base = getattr(monster, attr)
        pers = getattr(personality, personality_attr)
        tal = getattr(talent, talent_attr)
        val = 1.1 * (base + tal * 6) + 10
        val = round_half_up(val) * (1 + pers)
        val = int(round_half_up(val + 50))
        return val

    return schemas.EffectiveStats(
        hp=hp,
        phy_atk=other_stat("base_phy_atk", "phy_atk_mod_pct", "phy_atk_boost"),
        mag_atk=other_stat("base_mag_atk", "mag_atk_mod_pct", "mag_atk_boost"),
        phy_def=other_stat("base_phy_def", "phy_def_mod_pct", "phy_def_boost"),
        mag_def=other_stat("base_mag_def", "mag_def_mod_pct", "mag_def_boost"),
        spd=other_stat("base_spd", "spd_mod_pct", "spd_boost"),
    )
    
# Compute energy profile for moves, including average cost, zero-cost moves, and energy restore moves
def compute_energy_profile(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .energy_cost
    costs = [getattr(m, "energy_cost", None) for m in moves if m is not None]
    costs = [c for c in costs if c is not None]

    avg_cost = sum(costs) / len(costs) if costs else 0.0
    zero_cost_moves = [m.id for m in moves if m and getattr(m, "energy_cost", None) == 0]
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

    energy_restore_moves = [
        m.id for m in moves
        if m and hasattr(m, "description") and m.description and combined_pattern.search(m.description)
    ]
    has_energy_restore = len(energy_restore_moves) > 0

    return schemas.EnergyProfile(
        avg_energy_cost=round(avg_cost, 2),
        has_zero_cost_move=has_zero_cost,
        has_energy_restore_move=has_energy_restore,
        zero_cost_moves=zero_cost_moves,
        energy_restore_moves=energy_restore_moves
    )

# Compute counter coverage for moves with attack/defense/status counters
def compute_counter_coverage(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .move_category and .has_counter
    has_attack_counter_status = False
    has_defense_counter_attack = False
    has_status_counter_defense = False
    counter_move_ids = []

    for m in moves:
        if not m or not getattr(m, "has_counter", False):
            continue
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
        total_counter_moves=len(counter_move_ids),
        counter_move_ids=counter_move_ids
    )
    
# Count and record defense/status moves
def compute_defense_status_move(moves):
    defense_status_move_ids = []
    for m in moves:
        if m.move_category in [models.MoveCategory.DEFENSE, models.MoveCategory.STATUS]:
            defense_status_move_ids.append(m.id)
    return schemas.DefenseStatusMove(
        defense_status_move_count=len(defense_status_move_ids),
        defense_status_move=defense_status_move_ids,
    )
    
# Trait Synergy LLM Analysis
def get_localized_name(entity, language="en"):
    """Extract localized name from entity's localized field, falling back to English name."""
    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("name", entity.name)
                # If zh_data is a string, it might be the name itself
                elif isinstance(zh_data, str):
                    return zh_data
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("name", entity.name)
                elif isinstance(en_data, str):
                    return en_data
        except (KeyError, TypeError, AttributeError):
            pass
    return getattr(entity, "name", str(entity))

def get_localized_description(entity, language="en"):
    """Extract localized description from entity's localized field, falling back to English description."""
    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("description", getattr(entity, "description", ""))
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("description", getattr(entity, "description", ""))
        except (KeyError, TypeError, AttributeError):
            pass
    return getattr(entity, "description", "")

def build_trait_synergy_prompt(monster, trait, selected_moves, preferred_attack_style, game_terms, legacy_type, main_type, sub_type, language="en"):
    # Use localized names and descriptions
    monster_name = get_localized_name(monster, language)
    trait_name = get_localized_name(trait, language)
    trait_desc = get_localized_description(trait, language)

    # Build type information
    legacy_type_name = get_localized_name(legacy_type, language)
    main_type_name = get_localized_name(main_type, language)
    type_info = main_type_name
    if sub_type:
        sub_type_name = get_localized_name(sub_type, language)
        type_info = f"{main_type_name}/{sub_type_name}"

    move_lines = "\n".join(
        f"- {get_localized_name(m, language)}: {get_localized_description(m, language)}" for m in selected_moves
    )
    glossary = "\n".join(
        f"- {gt.key}: {get_localized_description(gt, language)}" for gt in game_terms
    )

    # Adjust language in the prompt based on user's language
    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家。
宠物: {monster_name}
属性: {type_info}
血脉类型: {legacy_type_name}
特性: {trait_name} — {trait_desc}
偏好攻击风格: {preferred_attack_style}
已选技能:
{move_lines}

游戏术语表:
{glossary}

指示:
1. 识别哪些技能与特性特别有协同作用。
2. 对于你的建议:
    - 给出**恰好两条建议** (最多3-4句话)，**详细解释用户应该如何组合使用所选技能**，包括可能的连招、回合顺序、防守或进攻应用，以及如何利用当前技能集与特性的配合。
    - 给出**一条额外的建议** (1-2句话) 说明如何改善整体技能选择 (例如偏好某些类型、效果或实用性，但请勿建议具体的技能替换)。
3. 以以下JSON格式输出 (使用中文回复):
{{
"synergy_moves": [协同技能名称列表],
"recommendation": [建议列表（字符串形式）]
}}
"""
    else:
        prompt = f"""You are an expert game strategist.
Monster: {monster_name}
Type: {type_info}
Legacy Type: {legacy_type_name}
Trait: {trait_name} — {trait_desc}
Preferred attack style: {preferred_attack_style}
Selected moves:
{move_lines}

Game Terms Glossary:
{glossary}

Instructions:
1. Identify which moves are especially synergistic with the trait.
2. For your recommendations:
    - Give **exactly two recommendations** (3-4 sentences max) that **explain in detail how the user should use the selected moves together**, including possible combos, turn order, defensive or offensive applications, and how to leverage the trait with the current moveset.
    - Give **one additional recommendation** (1-2 sentences) for how to improve move selection in general (such as favoring certain types, effects, or utility, but do NOT suggest specific move swaps).
3. Output as JSON in the following format:
{{
"synergy_moves": [list of move names],
"recommendation": [list of suggestions as strings]
}}
"""
    return prompt

def build_team_synergy_prompt(user_monsters, monster_db_map, move_db_map, type_db_map, magic_item, language="en"):
    """Build a prompt for team-wide synergy analysis."""
    # Build a summary of each monster in the team
    team_summary_lines = []
    for i, um in enumerate(user_monsters, 1):
        monster = monster_db_map[um.monster_id]
        monster_name = get_localized_name(monster, language)

        # Get types
        main_type = type_db_map[monster.main_type_id]
        main_type_name = get_localized_name(main_type, language)
        type_str = main_type_name
        if monster.sub_type_id:
            sub_type = type_db_map[monster.sub_type_id]
            sub_type_name = get_localized_name(sub_type, language)
            type_str = f"{main_type_name}/{sub_type_name}"

        # Get moves
        moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        move_names = [get_localized_name(m, language) for m in moves]

        team_summary_lines.append(f"{i}. {monster_name} ({type_str}) - Moves: {', '.join(move_names)}")

    team_summary = "\n".join(team_summary_lines)
    magic_item_name = get_localized_name(magic_item, language)
    magic_item_desc = get_localized_description(magic_item, language)

    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家。请分析以下队伍的整体协同作用和战术建议。

队伍组成:
{team_summary}

魔法道具: {magic_item_name} — {magic_item_desc}

请从以下几个方面分析队伍的整体协同作用:
1. **关键连招组合** (key_combos): 识别2-3个跨宠物的强力连招或协同组合，说明为什么它们有效。
2. **回合顺序策略** (turn_order_strategy): 提供2-3个关于出手顺序和节奏控制的建议。
3. **魔法道具使用** (magic_item_usage): 给出1-2个关于如何在关键时刻使用魔法道具的建议。
4. **整体策略** (general_strategy): 提供2-3个整体战术建议，包括如何应对不同对手类型。

以以下JSON格式输出 (每个建议应该是完整的、独立的字符串，用中文回复):
{{
"key_combos": ["建议1", "建议2", ...],
"turn_order_strategy": ["建议1", "建议2", ...],
"magic_item_usage": ["建议1", ...],
"general_strategy": ["建议1", "建议2", ...]
}}
"""
    else:
        prompt = f"""You are an expert game strategist. Please analyze the overall team synergy and tactical recommendations for the following team.

Team Composition:
{team_summary}

Magic Item: {magic_item_name} — {magic_item_desc}

Please analyze the team's overall synergy from the following perspectives:
1. **Key Combos** (key_combos): Identify 2-3 powerful cross-monster combos or synergy combinations and explain why they work.
2. **Turn Order Strategy** (turn_order_strategy): Provide 2-3 recommendations about move order and tempo control.
3. **Magic Item Usage** (magic_item_usage): Give 1-2 suggestions on how to use the magic item at critical moments.
4. **General Strategy** (general_strategy): Provide 2-3 overall tactical recommendations, including how to handle different opponent types.

Output as JSON in the following format (each recommendation should be a complete, standalone string):
{{
"key_combos": ["recommendation1", "recommendation2", ...],
"turn_order_strategy": ["recommendation1", "recommendation2", ...],
"magic_item_usage": ["recommendation1", ...],
"general_strategy": ["recommendation1", "recommendation2", ...]
}}
"""
    return prompt

# Compute team-level analysis
def compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map):
    IGNORED_TYPE_NAMES = {"Leader"}
    ignored_type_ids = {t.id for t in type_db_map.values() if t.name in IGNORED_TYPE_NAMES}
    all_type_ids = set(type_db_map.keys()) - ignored_type_ids

    # Gather all move types for offense
    team_move_types = set()
    for um in user_monsters:
        for move_id in [um.move1_id, um.move2_id, um.move3_id, um.move4_id]:
            move = move_db_map[move_id]
            if move.move_type_id:
                team_move_types.add(move.move_type_id)

    # Offensive coverage
    effective_against_types = set()
    for move_type_id in team_move_types:
        move_type = type_db_map[move_type_id]
        effective_against_types.update([t.id for t in move_type.effective_against])

    weak_against_types = list(all_type_ids - effective_against_types)

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

    return {
        "effective_against_types": sorted(effective_against_types),
        "weak_against_types": sorted(weak_against_types),
        "team_weak_to": sorted(team_weak_to),
    }
    
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

        # Enhancement Spell: any monster
        if effect_code == models.MagicEffectCode.ENHANCE_SPELL:
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

    # 1) Type coverage – offense
    if type_coverage["weak_against_types"]:
        names = [get_localized_name(type_db_map[t], language) for t in type_coverage["weak_against_types"]]
        if language == "zh":
            add("coverage", "warn",
                f"你的队伍无法对这些属性造成克制伤害：{', '.join(names)}。建议增加相应属性的技能来覆盖。",
                type_ids=type_coverage["weak_against_types"])
        else:
            add("coverage", "warn",
                f"Your team cannot hit these types super-effectively: {', '.join(names)}. Consider adding moves for coverage.",
                type_ids=type_coverage["weak_against_types"])

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
            add("magic_item", "warn", "当前队伍中没有宠物可以使用所选择的血脉魔法！")
        else:
            add("magic_item", "warn", "Your selected magic item cannot be used by any monster in your current team!")
    elif len(vt) == 1:
        if language == "zh":
            add("magic_item", "info", "只有一个宠物可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Only one monster can use the selected magic item.", monster_ids=vt)
    else:
        if language == "zh":
            add("magic_item", "info", "多个宠物可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Multiple monsters can use the selected magic item.", monster_ids=vt)

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
                f"许多宠物共享这些属性：{', '.join(names)}。这会增加对特定克制的脆弱性。",
                type_ids=common_type_ids)
        else:
            add("weakness", "warn",
                f"Many monsters share these types: {', '.join(names)}. This increases vulnerability to specific counters.",
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
                    f"{mname}没有选择反制技能。",
                    monster_ids=[mid])
            else:
                add("counters", "warn",
                    f"{mname} has no counter-effect moves selected.",
                    monster_ids=[mid])

        if analysis.defense_status_move.defense_status_move_count < 2:
            if language == "zh":
                add("defense_status", "info",
                    f"{mname}的防守/状态技能少于2个。建议增加更多技能以提高生存能力。",
                    monster_ids=[mid])
            else:
                add("defense_status", "info",
                    f"{mname} has fewer than 2 Defense/Status moves. Consider adding more for survivability.",
                    monster_ids=[mid])

        for synergy in analysis.trait_synergies:
            if synergy.synergy_moves:
                move_names = [get_localized_name(move_db_map[x], language) for x in synergy.synergy_moves]
                if language == "zh":
                    add("trait_synergy", "info",
                        f"{mname}的特性与以下技能配合良好：{', '.join(move_names)}。",
                        monster_ids=[mid], move_ids=synergy.synergy_moves)
                else:
                    add("trait_synergy", "info",
                        f"{mname}'s trait works well with: {', '.join(move_names)}.",
                        monster_ids=[mid], move_ids=synergy.synergy_moves)

    # 6) Role diversity
    styles = [getattr(a.user_monster.monster, "preferred_attack_style", None) for a in per_monster_analysis]
    if len(set(styles)) == 1 and styles[0]:
        if language == "zh":
            add("general", "warn", f"所有宠物都是{styles[0]}风格的攻击者。这可能使队伍变得可预测。")
        else:
            add("general", "warn", f"All monsters are {styles[0]}-style attackers. This may make the team predictable.")

    # 7) Stat and role highlights
    stat_roles_en = {
        "hp": "frontline or defensive pivot",
        "phy_atk": "main physical attacker",
        "mag_atk": "main magic attacker",
        "overall_def": "physical or special tank",
        "spd": "lead, scout, or revenge killer",
    }

    stat_roles_zh = {
        "hp": "前排或防守核心",
        "phy_atk": "主要物理攻击手",
        "mag_atk": "主要魔法攻击手",
        "overall_def": "物理或魔法坦克",
        "spd": "先手、侦察或收割手",
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


# === GET Endpoints ===

@app.get("/")
def read_root():
    return {"message": "Welcome to Roco Team Builder!"}

@app.get("/monsters", response_model=List[schemas.MonsterLiteOut])
def get_monsters(
    db: Session = Depends(get_db),
    name: Optional[str] = Query(None),
    type_id: Optional[int] = Query(None),
    trait_id: Optional[int] = Query(None),
    is_leader_form: Optional[bool] = Query(None),
    limit: int = Query(117, ge=1, le=117),
    offset: int = Query(0, ge=0),
):
    query = db.query(models.Monster).options(
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
        joinedload(models.Monster.default_legacy_type),
    )

    if name:
        term = f"%{name}%"

        # Dialect-aware JSON -> text extraction for localized.zh.name / localized.zh.form
        dialect = db.bind.dialect.name

        if dialect == "postgresql":
            zh_name_expr = cast(models.Monster.localized['zh']['name'].astext, String)
            zh_form_expr = cast(models.Monster.localized['zh']['form'].astext, String)
        elif dialect == "sqlite":
            zh_name_expr = func.json_extract(models.Monster.localized, '$.zh.name')
            zh_form_expr = func.json_extract(models.Monster.localized, '$.zh.form')
        else:
            zh_name_expr = None
            zh_form_expr = None

        # Allow searching both English name and form column
        filters = [models.Monster.name.ilike(term)]
        filters.append(models.Monster.form.ilike(term))

        if zh_name_expr is not None:
            filters.append(cast(zh_name_expr, String).ilike(term))
        if zh_form_expr is not None:
            filters.append(cast(zh_form_expr, String).ilike(term))

        query = query.filter(or_(*filters))

    if type_id:
        query = query.filter(or_(
            models.Monster.main_type_id == type_id,
            models.Monster.sub_type_id == type_id,
            models.Monster.default_legacy_type_id == type_id,
        ))

    if trait_id:
        query = query.filter(models.Monster.trait_id == trait_id)

    if is_leader_form is not None:
        query = query.filter(models.Monster.is_leader_form == is_leader_form)
        
    # Enforce deterministic order
    query = query.order_by(models.Monster.id.asc())
    
    return query.offset(offset).limit(limit).all()

@app.get("/monsters/{monster_id}", response_model=schemas.MonsterOut)
def get_monster_detail(monster_id: int, db: Session = Depends(get_db)):
    monster = db.query(models.Monster).options(
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
        joinedload(models.Monster.default_legacy_type),
        joinedload(models.Monster.trait),
        joinedload(models.Monster.species),
        joinedload(models.Monster.move_pool).joinedload(models.Move.move_type),
        joinedload(models.Monster.legacy_moves)
    ).filter(models.Monster.id == monster_id).first()
    if not monster:
        raise HTTPException(status_code=404, detail="Monster not found")
    return monster


@app.get("/moves", response_model=List[schemas.MoveOut])
def get_moves(
    db: Session = Depends(get_db),
    ids: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    move_type_id: Optional[int] = Query(None),
    move_category: Optional[schemas.MoveCategory] = Query(None),
    has_counter: Optional[bool] = Query(None),
    is_move_stone: Optional[bool] = Query(None),
    limit: int = Query(468, ge=1, le=468),
    offset: int = Query(0, ge=0),
):
    query = db.query(models.Move).options(
        joinedload(models.Move.move_type)
    )
    # allow fetching by a specific set of ids (comma-separated)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(models.Move.id.in_(id_list))
            return query.all()
    if name:
        query = query.filter(models.Move.name.ilike(f"%{name}%"))
    if move_type_id:
        query = query.filter(models.Move.move_type_id == move_type_id)
    if move_category:
        query = query.filter(models.Move.move_category == models.MoveCategory(move_category.value))
    if has_counter is not None:
        query = query.filter(models.Move.has_counter == has_counter)
    if is_move_stone is not None:
        query = query.filter(models.Move.is_move_stone == is_move_stone)
    return query.offset(offset).limit(limit).all()

@app.get("/moves/{move_id}", response_model=schemas.MoveOut)
def get_move_detail(move_id: int, db: Session = Depends(get_db)):
    move = db.query(models.Move).options(
        joinedload(models.Move.move_type)
    ).filter(models.Move.id == move_id).first()
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")
    return move


@app.get("/traits", response_model=List[schemas.TraitOut])
def get_traits(db: Session = Depends(get_db)):
    return db.query(models.Trait).all()


@app.get("/types", response_model=List[schemas.TypeOut])
def get_types(db: Session = Depends(get_db)):
    return db.query(models.Type).all()


@app.get("/personalities", response_model=List[schemas.PersonalityOut])
def get_personalities(db: Session = Depends(get_db)):
    return db.query(models.Personality).all()


@app.get("/magic_items", response_model=List[schemas.MagicItemOut])
def get_magic_items(db: Session = Depends(get_db)):
    return db.query(models.MagicItem).all()


@app.get("/game_terms", response_model=List[schemas.GameTermOut])
def get_game_terms(db: Session = Depends(get_db)):
    return db.query(models.GameTerm).all()


@app.get("/species", response_model=List[schemas.MonsterSpeciesOut])
def get_species(db: Session = Depends(get_db)):
    return db.query(models.MonsterSpecies).all()


@app.get("/teams", response_model=List[schemas.TeamOut])
def list_teams(db: Session = Depends(get_db)):
    return (
        db.query(models.Team)
        .options(
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.main_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.sub_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.default_legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.personality),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move1),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move2),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move3),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move4),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.talent),
            joinedload(models.Team.magic_item),
        )
        .order_by(models.Team.id.desc())
        .all()
    )

@app.get("/teams/{team_id}", response_model=schemas.TeamOut)
def get_team(team_id: int, db: Session = Depends(get_db)):
    db_team = (
        db.query(models.Team)
        .options(
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.main_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.sub_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.default_legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.personality),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move1),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move2),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move3),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move4),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.talent),
            joinedload(models.Team.magic_item),
        )
        .filter(models.Team.id == team_id)
        .first()
    )
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")
    return db_team


# -------- POST Endpoints --------

@app.post("/teams", response_model=schemas.TeamOut)
def create_team(team: schemas.TeamCreate, db: Session = Depends(get_db)):
    # Persist the team and its monsters to DB
    db_team = models.Team(name=team.name, magic_item_id=team.magic_item_id)
    db.add(db_team)
    db.flush()

    user_monsters_out = []   # For future expand reference
    for um in team.user_monsters:
        db_um = models.UserMonster(
            monster_id=um.monster_id,
            personality_id=um.personality_id,
            legacy_type_id=um.legacy_type_id,
            move1_id=um.move1_id,
            move2_id=um.move2_id,
            move3_id=um.move3_id,
            move4_id=um.move4_id,
            team_id=db_team.id
        )
        db.add(db_um)
        db.flush()
        db_talent = models.Talent(
            monster_instance_id=db_um.id,
            hp_boost=um.talent.hp_boost,
            phy_atk_boost=um.talent.phy_atk_boost,
            mag_atk_boost=um.talent.mag_atk_boost,
            phy_def_boost=um.talent.phy_def_boost,
            mag_def_boost=um.talent.mag_def_boost,
            spd_boost=um.talent.spd_boost
        )
        db.add(db_talent)
        db_um.talent = db_talent
        user_monsters_out.append(db_um)  # For future expand reference
    db.commit()

    # Re-fetch with relationships for output schema
    db.refresh(db_team)
    return db_team

# -------- Analyze Team (Inline) --------

@app.post("/team/analyze", response_model=schemas.TeamAnalysisOut)
async def analyze_team(req: schemas.TeamAnalyzeInlineRequest, db: Session = Depends(get_db)):
    start_time = time.time()
    
    team_data = req.team  # This is TeamCreate (with 6 UserMonsterCreate)
    
    # --- Helper: Call LLM and Parse Result ---
    async def call_llm(prompt: str):
        try:
            resp = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            return json.loads(resp.text)
        except Exception as e:
            logger.error(f"LLM error: {e}", exc_info=True)
            return {"synergy_moves": [], "recommendation": ["Error generating analysis."]}

    # === EFFICIENT DATA LOADING ===
    logger.debug("Start loading data for analysis...")
    monster_ids_to_load = {um.monster_id for um in team_data.user_monsters}
    monster_db_map = {m.id: m for m in db.query(models.Monster).filter(models.Monster.id.in_(monster_ids_to_load)).all()}
    logger.debug(f"Loaded monsters: {len(monster_db_map)}")

    # Validate all monsters were found
    missing_monsters = monster_ids_to_load - set(monster_db_map.keys())
    if missing_monsters:
        raise HTTPException(status_code=400, detail=f"Monster IDs not found: {sorted(missing_monsters)}")

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
    game_terms = db.query(models.GameTerm).all()
    logger.debug(f"Loaded game terms: {len(game_terms)}")

    logger.debug("Finish loading data for analysis!")

    # === CONCURRENT LLM ANALYSIS ===
    logger.debug("Start creating prompt for LLM analysis...")
    language = req.language  # Get language from request
    logger.info(f"Language received: {language}")
    llm_tasks = []

    # Per-monster trait synergy analysis
    for um in team_data.user_monsters:
        base_monster = monster_db_map[um.monster_id]
        trait = trait_db_map[base_monster.trait_id]
        selected_moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        preferred_attack_style = getattr(base_monster, "preferred_attack_style", "Both")

        # Get type information
        legacy_type = type_db_map[um.legacy_type_id]
        main_type = type_db_map[base_monster.main_type_id]
        sub_type = type_db_map[base_monster.sub_type_id] if base_monster.sub_type_id else None

        prompt = build_trait_synergy_prompt(base_monster, trait, selected_moves, preferred_attack_style, game_terms, legacy_type, main_type, sub_type, language)
        llm_tasks.append(call_llm(prompt))

    # Team-wide synergy analysis
    team_synergy_prompt = build_team_synergy_prompt(team_data.user_monsters, monster_db_map, move_db_map, type_db_map, magic_item, language)
    llm_tasks.append(call_llm(team_synergy_prompt))

    llm_results = await asyncio.gather(*llm_tasks)

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
                preferred_attack_style = getattr(monster, "preferred_attack_style", "Both"),
                localized=monster.localized
            )

        user_monster_out = schemas.UserMonsterOut(
            id=i,
            monster=to_monster_lite_out(base_monster, type_db_map),
            personality=schemas.PersonalityOut(**personality.__dict__),
            legacy_type=schemas.TypeOut(**legacy_type.__dict__),
            move1=schemas.MoveOut(**move1.__dict__),
            move2=schemas.MoveOut(**move2.__dict__),
            move3=schemas.MoveOut(**move3.__dict__),
            move4=schemas.MoveOut(**move4.__dict__),
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
    type_coverage = compute_type_coverage(team_data.user_monsters, move_db_map, monster_db_map, type_db_map)
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
        key_combos=team_synergy_result.get("key_combos", []),
        turn_order_strategy=team_synergy_result.get("turn_order_strategy", []),
        magic_item_usage=team_synergy_result.get("magic_item_usage", []),
        general_strategy=team_synergy_result.get("general_strategy", [])
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
    )

    logger.debug("Finish team-level analysis!")
    elapsed = time.time() - start_time
    logger.info(f"POST /team/analyze took {elapsed:.3f} seconds")
    return result

# -------- Analyze Team by ID --------

@app.post("/team/analyze_by_id", response_model=schemas.TeamAnalysisOut)
async def analyze_team_by_id(req: schemas.TeamAnalyzeByIdRequest, db: Session = Depends(get_db)):
    # Load the Team, its UserMonsters, Talents, etc. from the DB
    db_team = db.query(models.Team).filter(models.Team.id == req.team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Build TeamCreate-like dict from DB objects
    user_monsters = []
    for um in db_team.user_monsters:
        talent = db.query(models.Talent).filter(models.Talent.monster_instance_id == um.id).first()
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
    team_data = schemas.TeamCreate(
        name=db_team.name,
        user_monsters=user_monsters,
        magic_item_id=db_team.magic_item_id
    )
    # Wrap as a TeamAnalyzeInlineRequest and call analysis logic
    inline_req = schemas.TeamAnalyzeInlineRequest(team=team_data)
    return await analyze_team(inline_req, db)

# -------- PUT Team (Update) --------

@app.put("/teams/{team_id}", response_model=schemas.TeamOut)
def update_team(
    team_id: int,
    team_update: schemas.TeamUpdate,
    db: Session = Depends(get_db)
):
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Update team fields if provided
    if team_update.name is not None:
        db_team.name = team_update.name
    if team_update.magic_item_id is not None:
        db_team.magic_item_id = team_update.magic_item_id

    # --- UserMonsters sync logic ---
    # Build a mapping of incoming user_monsters by id (if present)
    incoming_by_id = {um.id: um for um in team_update.user_monsters if um.id is not None}

    # Build a set of incoming user_monster ids (for those to keep/update)
    incoming_ids = set(incoming_by_id.keys())

    # Remove any user_monsters not in the new request
    for db_um in list(db_team.user_monsters):
        if db_um.id not in incoming_ids:
            db.delete(db_um)

    db.flush()

    # Update existing and add new user_monsters
    existing_ums = {um.id: um for um in db_team.user_monsters}

    for um_data in team_update.user_monsters:
        if um_data.id is not None and um_data.id in existing_ums:
            # Update existing user_monster
            um = existing_ums[um_data.id]
            um.monster_id = um_data.monster_id
            um.personality_id = um_data.personality_id
            um.legacy_type_id = um_data.legacy_type_id
            um.move1_id = um_data.move1_id
            um.move2_id = um_data.move2_id
            um.move3_id = um_data.move3_id
            um.move4_id = um_data.move4_id
            # Update nested talent
            if um.talent:
                t = um_data.talent
                um.talent.hp_boost = t.hp_boost
                um.talent.phy_atk_boost = t.phy_atk_boost
                um.talent.mag_atk_boost = t.mag_atk_boost
                um.talent.phy_def_boost = t.phy_def_boost
                um.talent.mag_def_boost = t.mag_def_boost
                um.talent.spd_boost = t.spd_boost
        else:
            # Add new user_monster
            um = models.UserMonster(
                monster_id=um_data.monster_id,
                personality_id=um_data.personality_id,
                legacy_type_id=um_data.legacy_type_id,
                move1_id=um_data.move1_id,
                move2_id=um_data.move2_id,
                move3_id=um_data.move3_id,
                move4_id=um_data.move4_id,
                team=db_team
            )
            db.add(um)
            db.flush()
            t = um_data.talent
            talent = models.Talent(
                monster_instance_id=um.id,
                hp_boost=t.hp_boost,
                phy_atk_boost=t.phy_atk_boost,
                mag_atk_boost=t.mag_atk_boost,
                phy_def_boost=t.phy_def_boost,
                mag_def_boost=t.mag_def_boost,
                spd_boost=t.spd_boost,
            )
            db.add(talent)
            um.talent = talent

    db_team.updated_at = func.now()
    db.commit()
    db.refresh(db_team)
    return db_team

# -------- DELETE Team --------

@app.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: int, db: Session = Depends(get_db)):
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(db_team)
    db.commit()
    return