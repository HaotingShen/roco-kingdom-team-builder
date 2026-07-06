"""LLM prompt construction for team analysis.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Contains the battle-mechanics system prompts and the per-monster / team-wide
synergy prompt builders. Prompt text is UNCHANGED.
"""
from backend import models, schemas
from backend.analysis.localization import (
    get_localized_name,
    get_localized_description,
    get_localized_move_category,
)
from backend.analysis.computations import (
    compute_effective_stats,
    resolve_dynamic_move_properties,
)


BATTLE_MECHANICS_ZH = """每位玩家携带6只精灵对战，每只精灵有6项属性（生命、物攻、魔攻、物防、魔防、速度）。实战中每只精灵只能携带4个技能。技能描述中的"攻击"或"双攻"同时影响物攻与魔攻；"防御"或"双防"同时影响物防与魔防。

战斗开始时双方各有4点魔力值，场上各只能同时上场1只精灵。精灵力竭（被击败）时失去1点魔力值（部分特性会改变此规则）。魔力值归零则判负。力竭后需手动选择新精灵入场。

每只精灵初始10点能量（部分特性影响初始值）。能量按精灵单独记录，释放技能消耗对应能量。

每回合双方同时选择一个行动：（1）释放技能：从4个技能中选1个并支付能量；（2）聚能：本回合不行动，恢复5点能量（属于状态类技能）；（3）主动更换精灵。血脉魔法不属于行动选项：若本回合可用，可在任意时点额外使用，不消耗行动或能量，并在己方行动前生效。

主动更换精灵先于所有技能结算。精灵主动入场时，若其携带含有"迅捷"效果的技能且能量充足，会立即自动释放首个满足条件的迅捷技能（按技能栏顺序）。迅捷仅在主动换上时触发，被动入场不触发。

所有技能分为三类：攻击类（物攻/魔攻）、防御类、状态类。存在"应对"系统：若敌方技能类别与本技能可应对类别匹配，则应对成功，本技能以最高优先级立即释放，忽略速度顺序。双方不可同时应对成功。未触发应对时按先手值判定顺序，先手值相同则速度高者先行动。主动更换始终优先于技能结算。

应对关系：防御类技能自带应对攻击；部分状态类技能带应对防御；部分攻击类技能带应对状态。这形成克制三角，预测对手技能类别选择应对是PvP关键策略。

增益指提升攻击、防御、速度、技能威力、连击数、吸血或降低技能能耗；减益相反。技能中的"全技能威力/全技能能耗"影响该精灵当前所有技能。精灵离场时清除非永久性增减益和大多数状态效果（印记除外）。

层数定义：当"层数"用于增益/减益时，以10为换算基准。百分比增减：每10% = 1层，如物攻+150% = +15层物攻。数值增减（非百分比且为10的倍数）：每10点 = 1层，如技能威力+20 = +2层技能威力。当"层数"用于状态/印记时，层数按状态本身叠加规则计算，不做上述换算。

冷却定义：技能或血脉魔法在再次使用前必须经过的回合数。除非另有说明，所有防御类技能的冷却为1回合，而其他类别的技能通常没有冷却；血脉魔法中"愿力强化"的冷却为3回合且每场战斗最多使用2次，而其他血脉魔法为每场一次性使用。

在进行队伍与精灵分析时，请默认对战结算遵循以上关于魔力值、力竭、能量、技能类别、应对系统、增减益、迅捷、先手与速度、层数定义、冷却定义及血脉魔法的规则。"""


BATTLE_MECHANICS_EN = """Each player brings 6 jinglings into battle. Each jingling has 6 stats (HP, Physical Attack, Magic Attack, Physical Defense, Magic Defense, Speed). In battle, each jingling can only carry 4 moves. In move descriptions, "Attack" affects both Physical and Magic Attack; "Defense" affects both Physical and Magic Defense.

At battle start, each player has 4 Life Points. Only 1 jingling per side can be on the field at once. When a jingling is defeated, the player loses 1 Life Point (some traits alter this). When Life Points reach 0, that player loses. After defeat, manually select a new jingling to enter.

Each jingling starts with 10 energy (some traits affect initial energy). Energy is tracked per jingling. Using moves consumes their marked energy cost.

Each turn, both players simultaneously choose one action: (1) Use a move: select 1 of 4 moves and pay its energy cost; (2) Focus: skip this turn, restore 5 energy (classified as Status-type move); (3) Actively switch jinglings. Magic Item does not count as an action. If available this turn, it may be used at any time without consuming an action or energy, and it takes effect before your chosen action resolves.

Active switching executes before all move resolutions. When a jingling enters via active switch, if it has any move with "Quick Entry" effect and enough energy to use it, it immediately and automatically uses the first eligible Quick Entry move in moveset slot order. Quick Entry only triggers on active switch-in, not passive entry.

All moves fall into three categories: Attack-type (Physical/Magic Attack), Defense-type, Status-type. A "Counter" system exists: if the opponent's move category matches this move's counterable category, counter succeeds and this move resolves immediately with highest priority, ignoring speed order. Both sides cannot counter simultaneously. Without counter triggers, turn order is determined by priority value; if equal, higher speed acts first. Active switching always executes before move resolution.

Counter relationships: All Defense moves have Counter Attack; some Status moves have Counter Defense; some Attack moves have Counter Status. This forms a counter triangle—predicting opponent's move category to select counters is key PvP strategy.

Buffs increase Attack, Defense, Speed, move power, Combo count, Lifesteal, or decrease move energy cost; Debuffs do the opposite. "All Move Power/Move Energy Cost" affects all moves currently carried by that jingling. When jinglings leave the field, non-permanent buffs/debuffs and most of status effects are removed (except marks).

Stack definition: When "stacks" are used for buffs/debuffs, convert using 10 as the base unit. For percentage changes, every 10% = 1 stack (e.g., Physical Attack +150% = +15 stacks of Physical Attack). For flat value changes (non-percentage and a multiple of 10), every 10 points = 1 stack (e.g., Move Power +20 = +2 stacks of Move Power). When "stacks" refer to status/mark effects, stacks follow their own stacking rules and do not use the above conversion.

Cooldown definition: The number of turns that must pass before a move or magic item can be used again. Unless otherwise specified, all Defense-type moves have a 1-turn cooldown, while moves of other categories have no cooldown. For magic items, "Willpower Enhancement" has a 3-turn cooldown and can be used at most 2 times per battle, while other magic item effects are single-use per battle.

When performing jingling and team analysis, assume battle resolution follows the above rules regarding Life Points, defeated state, energy, move categories, counter system, buffs/debuffs, Quick Entry, priority and speed, stack definitions, cooldown definitions, and Magic Items."""


def build_trait_synergy_prompt(monster, trait, selected_moves, game_terms, referenced_moves, referenced_monsters, main_type, sub_type, type_db_map, trait_db_map, language="en"):
    # Use localized names and descriptions
    monster_name = get_localized_name(monster, language)
    trait_name = get_localized_name(trait, language)
    trait_desc = get_localized_description(trait, language)

    # Build type information
    main_type_name = get_localized_name(main_type, language)
    type_info = main_type_name
    if sub_type:
        sub_type_name = get_localized_name(sub_type, language)
        type_info = f"{main_type_name}/{sub_type_name}"

    # Build complete type effectiveness table for all types
    type_chart_lines = []
    # Get all types and sort them by name for consistency
    all_types = sorted(type_db_map.values(), key=lambda t: get_localized_name(t, language))

    for t in all_types:
        type_name = get_localized_name(t, language)
        # Skip "Leader" or other special types that aren't real battle types
        if type_name in ["Leader", "首领"]:
            continue

        effective = []
        weak = []

        if hasattr(t, 'effective_against') and t.effective_against:
            effective = sorted([get_localized_name(target, language) for target in t.effective_against])
        if hasattr(t, 'weak_against') and t.weak_against:
            weak = sorted([get_localized_name(target, language) for target in t.weak_against])

        if language == "zh":
            eff_str = ', '.join(effective) if effective else '无'
            weak_str = ', '.join(weak) if weak else '无'
            type_chart_lines.append(f"  {type_name} → 克制: {eff_str} | 效果不佳: {weak_str}")
        else:
            eff_str = ', '.join(effective) if effective else 'None'
            weak_str = ', '.join(weak) if weak else 'None'
            type_chart_lines.append(f"  {type_name} → Effective Against: {eff_str} | Weak Against: {weak_str}")

    type_chart = "\n".join(type_chart_lines)

    # Build move information with type, category, energy cost, and power
    move_lines = []
    for m in selected_moves:
        move_name = get_localized_name(m, language)
        move_desc = get_localized_description(m, language)
        move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
        move_category_str = get_localized_move_category(m.move_category, language)
        energy_cost = getattr(m, 'energy_cost', 'N/A')
        power_str = str(m.power) if m.power is not None else "-"

        if language == "zh":
            move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
        else:
            move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
    move_lines_str = "\n".join(move_lines)
    glossary = "\n".join(
        f"- {get_localized_name(gt, language)}: {get_localized_description(gt, language)}" for gt in game_terms
    )

    # Build referenced moves section (moves mentioned in trait/move descriptions)
    referenced_moves_section = ""
    if referenced_moves:
        ref_move_lines = []
        for m in referenced_moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)
            move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
            move_category_str = get_localized_move_category(m.move_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                ref_move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                ref_move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
        referenced_moves_section = "\n".join(ref_move_lines)

    # Build referenced monsters section (monsters mentioned in trait/move descriptions)
    referenced_monsters_section = ""
    if referenced_monsters:
        ref_monster_lines = []
        for mon in referenced_monsters:
            mon_name = get_localized_name(mon, language)
            mon_main_type = type_db_map[mon.main_type_id]
            mon_type_str = get_localized_name(mon_main_type, language)
            if mon.sub_type_id:
                mon_sub_type = type_db_map[mon.sub_type_id]
                mon_type_str = f"{mon_type_str}/{get_localized_name(mon_sub_type, language)}"

            # Get trait information
            mon_trait = trait_db_map[mon.trait_id]
            mon_trait_name = get_localized_name(mon_trait, language)
            mon_trait_desc = get_localized_description(mon_trait, language)

            # Get base stats
            if language == "zh":
                base_stats = f"生命:{mon.base_hp}, 物攻:{mon.base_phy_atk}, 魔攻:{mon.base_mag_atk}, 物防:{mon.base_phy_def}, 魔防:{mon.base_mag_def}, 速度:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  属性: {mon_type_str}\n"
                    f"  特性: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  基础属性: {base_stats}"
                )
            else:
                base_stats = f"HP:{mon.base_hp}, Physical Attack:{mon.base_phy_atk}, Magic Attack:{mon.base_mag_atk}, Physical Defense:{mon.base_phy_def}, Magic Defense:{mon.base_mag_def}, Speed:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  Type: {mon_type_str}\n"
                    f"  Trait: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  Base Stats: {base_stats}"
                )
        referenced_monsters_section = "\n".join(ref_monster_lines)

    # Adjust language in the prompt based on user's language
    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家，精通洛克王国的对战机制、属性克制和精灵配队。

## 对战机制
说明：以下规则适用于PvP单人模式，是分析队伍和精灵配置的基础：
{BATTLE_MECHANICS_ZH}

## 属性克制表（作为攻击方）
{type_chart}
说明：本表仅描述"攻击方属性X攻击防守方属性Y"时的对阵结果：哪些对阵更有利（克制），哪些对阵不利（效果不佳）。
注意：这里的"效果不佳"不等同于"X被这些属性克制"，请不要反向推断。精灵自身属性只允许用于说明技能的本系加成效果，不允许用于防守克制/抗性分析。

## 游戏术语表
注意：在特性/技能/血脉魔法的描述中出现的术语必须按此表解释。
{glossary}
{f'''
## 引用的技能
注意：以下技能在特性或已选技能的描述中被提及，这里提供其完整信息供参考。
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## 引用的精灵
注意：以下精灵在特性或已选技能的描述中被提及，这里提供其类型信息供参考。
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

精灵: {monster_name}
属性: {type_info}
特性: {trait_name} — {trait_desc}

已选技能:
{move_lines_str}

---

指示:
1. 识别哪些技能与特性特别有协同作用。
2. 对于你的建议:
    - 给出**恰好两条建议** (每条最多3-4句话)，**详细解释用户应该如何在不同对局情况下使用所选技能**：
      * 说明各技能的出手时机：哪些技能在大多数对局中都能稳定出手，哪些需要等待特定条件或局势
      * 说明哪些技能使用后可能获得关键收益（如建立优势、扭转战局），并评估其能耗
      * 给出具体的使用场景建议，包括可能的技能协同、防守/进攻应用，以及如何结合特性和能量管理来发挥最大效果
    - 给出**一条额外的建议** (3-4句话)，**分析技能配置的合理性**：
      * 分析攻击类技能的属性克制覆盖（能够有效克制哪些属性）
      * 分析攻击/防御/状态类技能的配比是否适配特性和对局需求
      * 若技能配置存在重大缺陷（如：没有任何与特性协同的技能、能量配比极度不合理导致无法持续输出、缺少必要的防御手段导致无法应对常见威胁），基于以上分析建议改善方向（但请勿建议具体的技能替换）。若配置合理，则说明其优势。
3. 以以下JSON格式输出 (使用中文回复):
{{
"synergy_moves": [协同技能名称列表],
"recommendation": [建议列表（字符串形式）]
}}
"""
    else:
        prompt = f"""You are an expert game strategist specializing in Roco Kingdom battle mechanics, type matchups, and team composition.

## Battle Mechanics
Note: The following rules apply to PvP solo mode and form the foundation for team and monster analysis.
{BATTLE_MECHANICS_EN}

## Type Effectiveness Table (Attacking Perspective)
{type_chart}
Note: This chart only describes the outcome when the attacking type X hits the defending type Y: which matchups are favorable (effective) and which are unfavorable (weak).
Important: "Unfavorable" here does NOT mean "X is countered by these types." Do not infer the reverse direction. You may mention the monster's own types ONLY for STAB/same-type bonuses, not for defensive weaknesses/resistances.

## Game Terms Glossary
Important: Any terms appearing in trait/move/magic item descriptions must be interpreted using this glossary.
{glossary}
{f'''
## Referenced Moves
Note: The following moves are mentioned in trait or selected move descriptions. Their full details are provided here for reference.
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## Referenced Monsters
Note: The following monsters are mentioned in trait or selected move descriptions. Their type information is provided here for reference.
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

Monster: {monster_name}
Type: {type_info}
Trait: {trait_name} — {trait_desc}

Selected moves:
{move_lines_str}

---

Instructions:
1. Identify which moves are especially synergistic with the trait.
2. For your recommendations:
    - Give **exactly two recommendations** (3-4 sentences each) that **explain in detail how to use the selected moves in different battle situations**:
      * Explain when and why to use each move—covering moves that perform reliably across most matchups as well as those reserved for specific situations
      * Identify which moves can provide key benefits after use (e.g., establishing advantage, turning the tide) and assess their energy cost
      * Provide specific usage scenarios including possible move synergies, defensive/offensive applications, and how to maximize effectiveness through trait synergy and energy management
    - Give **one additional recommendation** (3-4 sentences) that **analyzes the moveset's composition**:
      * Analyze the type coverage of attacking moves (which types are effectively countered)
      * Analyze whether the attack/defense/status move ratio fits the trait and battle requirements
      * If the moveset has major flaws (e.g., zero trait-synergy moves, extremely poor energy distribution preventing sustained output, lack of necessary defensive tools against common threats), suggest improvement directions based on the above analysis (but do NOT recommend specific move replacements). If the configuration is sound, highlight its strengths.
3. Output as JSON in the following format:
{{
"synergy_moves": [list of move names],
"recommendation": [list of suggestions as strings]
}}
"""
    return prompt


def build_team_synergy_prompt(user_monsters, monster_db_map, move_db_map, type_db_map, trait_db_map, magic_item, game_terms, referenced_moves, referenced_monsters, language="en", db=None):
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

        # Get legacy type and trait
        legacy_type = type_db_map[um.legacy_type_id]
        legacy_type_name = get_localized_name(legacy_type, language)
        trait = trait_db_map[monster.trait_id]
        trait_name = get_localized_name(trait, language)
        trait_desc = get_localized_description(trait, language)

        # Get base stats with localized labels
        if language == "zh":
            base_stats = f"生命:{monster.base_hp}, 物攻:{monster.base_phy_atk}, 魔攻:{monster.base_mag_atk}, 物防:{monster.base_phy_def}, 魔防:{monster.base_mag_def}, 速度:{monster.base_spd}"
        else:
            base_stats = f"HP:{monster.base_hp}, Physical Attack:{monster.base_phy_atk}, Magic Attack:{monster.base_mag_atk}, Physical Defense:{monster.base_phy_def}, Magic Defense:{monster.base_mag_def}, Speed:{monster.base_spd}"

        # Get moves with full details
        moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        move_details = []

        # Get personality for dynamic move resolution
        personality = db.query(models.Personality).filter(models.Personality.id == um.personality_id).first() if db else None

        for m in moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)

            # Resolve dynamic move properties (for Willpower Impact)
            resolved_props = resolve_dynamic_move_properties(m, um, monster, personality, um.talent, type_db_map)
            resolved_type = resolved_props['type']
            resolved_category = resolved_props['category']

            move_type_name = get_localized_name(resolved_type, language) if resolved_type else "None"
            move_category_str = get_localized_move_category(resolved_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                move_details.append(f"    - {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                move_details.append(f"    - {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")

        if language == "zh":
            team_summary_lines.append(
                f"{i}. {monster_name} | 属性:{type_str} | 血脉:{legacy_type_name} | 特性:{trait_name} — {trait_desc}\n"
                f"   基础属性: {base_stats}\n"
                f"   技能:\n{chr(10).join(move_details)}"
            )
        else:
            team_summary_lines.append(
                f"{i}. {monster_name} | Type:{type_str} | Legacy Type:{legacy_type_name} | Trait:{trait_name} — {trait_desc}\n"
                f"   Base Stats: {base_stats}\n"
                f"   Moves:\n{chr(10).join(move_details)}"
            )

    team_summary = "\n".join(team_summary_lines)
    magic_item_name = get_localized_name(magic_item, language)
    magic_item_desc = get_localized_description(magic_item, language)

    # Build game terms glossary
    glossary = "\n".join(
        f"- {get_localized_name(gt, language)}: {get_localized_description(gt, language)}" for gt in game_terms
    )

    # Build referenced moves section (moves mentioned in trait/move/magic item descriptions)
    referenced_moves_section = ""
    if referenced_moves:
        ref_move_lines = []
        for m in referenced_moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)
            move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
            move_category_str = get_localized_move_category(m.move_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                ref_move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                ref_move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
        referenced_moves_section = "\n".join(ref_move_lines)

    # Build referenced monsters section (monsters mentioned in trait/move/magic item descriptions)
    referenced_monsters_section = ""
    if referenced_monsters:
        ref_monster_lines = []
        for mon in referenced_monsters:
            mon_name = get_localized_name(mon, language)
            mon_main_type = type_db_map[mon.main_type_id]
            mon_type_str = get_localized_name(mon_main_type, language)
            if mon.sub_type_id:
                mon_sub_type = type_db_map[mon.sub_type_id]
                mon_type_str = f"{mon_type_str}/{get_localized_name(mon_sub_type, language)}"

            # Get trait information
            mon_trait = trait_db_map[mon.trait_id]
            mon_trait_name = get_localized_name(mon_trait, language)
            mon_trait_desc = get_localized_description(mon_trait, language)

            # Get base stats
            if language == "zh":
                base_stats = f"生命:{mon.base_hp}, 物攻:{mon.base_phy_atk}, 魔攻:{mon.base_mag_atk}, 物防:{mon.base_phy_def}, 魔防:{mon.base_mag_def}, 速度:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  属性: {mon_type_str}\n"
                    f"  特性: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  基础属性: {base_stats}"
                )
            else:
                base_stats = f"HP:{mon.base_hp}, Physical Attack:{mon.base_phy_atk}, Magic Attack:{mon.base_mag_atk}, Physical Defense:{mon.base_phy_def}, Magic Defense:{mon.base_mag_def}, Speed:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  Type: {mon_type_str}\n"
                    f"  Trait: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  Base Stats: {base_stats}"
                )
        referenced_monsters_section = "\n".join(ref_monster_lines)

    # Build Evolution Power leader forms section
    # If Evolution Power is selected, show the Leader form data for monsters with Leader legacy type
    leader_forms_section = ""
    if db is not None and hasattr(magic_item, 'effect_code') and magic_item.effect_code == models.MagicEffectCode.EVOLUTION_POWER:
        leader_form_lines = []
        for um in user_monsters:
            # Check if this monster has Leader legacy type
            legacy_type = type_db_map[um.legacy_type_id]
            legacy_type_name = get_localized_name(legacy_type, language)

            if legacy_type_name in ["Leader", "首领"]:
                # Get the base monster
                base_monster = monster_db_map[um.monster_id]

                # Query for the leader form of this monster (same species, is_leader_form=True)
                leader_form = db.query(models.Monster).filter(
                    models.Monster.species_id == base_monster.species_id,
                    models.Monster.is_leader_form == True
                ).first()

                if leader_form:
                    # Get leader form details
                    leader_name = get_localized_name(leader_form, language)
                    base_monster_name = get_localized_name(base_monster, language)

                    # Get leader form types
                    leader_main_type = type_db_map[leader_form.main_type_id]
                    leader_type_str = get_localized_name(leader_main_type, language)
                    if leader_form.sub_type_id:
                        leader_sub_type = type_db_map[leader_form.sub_type_id]
                        leader_type_str = f"{leader_type_str}/{get_localized_name(leader_sub_type, language)}"

                    # Get leader form trait (load if not already in map)
                    if leader_form.trait_id not in trait_db_map:
                        leader_trait_obj = db.query(models.Trait).filter(models.Trait.id == leader_form.trait_id).first()
                        if leader_trait_obj:
                            trait_db_map[leader_form.trait_id] = leader_trait_obj

                    leader_trait = trait_db_map.get(leader_form.trait_id)
                    if not leader_trait:
                        # Skip this monster if trait cannot be loaded
                        continue

                    leader_trait_name = get_localized_name(leader_trait, language)
                    leader_trait_desc = get_localized_description(leader_trait, language)

                    # Get leader form base stats
                    if language == "zh":
                        leader_stats = f"生命:{leader_form.base_hp}, 物攻:{leader_form.base_phy_atk}, 魔攻:{leader_form.base_mag_atk}, 物防:{leader_form.base_phy_def}, 魔防:{leader_form.base_mag_def}, 速度:{leader_form.base_spd}"
                        leader_form_lines.append(
                            f"- {base_monster_name} → 进化为 {leader_name}\n"
                            f"  属性: {leader_type_str}\n"
                            f"  特性: {leader_trait_name} — {leader_trait_desc}\n"
                            f"  基础属性: {leader_stats}"
                        )
                    else:
                        leader_stats = f"HP:{leader_form.base_hp}, Physical Attack:{leader_form.base_phy_atk}, Magic Attack:{leader_form.base_mag_atk}, Physical Defense:{leader_form.base_phy_def}, Magic Defense:{leader_form.base_mag_def}, Speed:{leader_form.base_spd}"
                        leader_form_lines.append(
                            f"- {base_monster_name} → Evolves to {leader_name}\n"
                            f"  Type: {leader_type_str}\n"
                            f"  Trait: {leader_trait_name} — {leader_trait_desc}\n"
                            f"  Base Stats: {leader_stats}"
                        )

        if leader_form_lines:
            leader_forms_section = "\n".join(leader_form_lines)

    # Build Willpower Enhancement section
    # If Willpower Enhancement is selected, show which monsters can use it and what type/category they get
    willpower_enhancement_section = ""
    if db is not None and hasattr(magic_item, 'effect_code') and magic_item.effect_code == models.MagicEffectCode.ENHANCE_SPELL:
        willpower_lines = []
        eligible_count = 0

        # Find the Leader type ID
        leader_type_id = next((t.id for t in type_db_map.values() if t.name == "Leader"), None)

        for um in user_monsters:
            # Check if this monster can use Willpower Enhancement (not Leader legacy type)
            legacy_type = type_db_map[um.legacy_type_id]
            legacy_type_name = get_localized_name(legacy_type, language)

            if um.legacy_type_id != leader_type_id:
                eligible_count += 1
                base_monster = monster_db_map[um.monster_id]
                monster_name = get_localized_name(base_monster, language)

                # Get personality for stat comparison
                personality = db.query(models.Personality).filter(models.Personality.id == um.personality_id).first()

                if personality:
                    # Compute effective stats to determine if Willpower Impact will be Physical or Magical
                    effective_stats = compute_effective_stats(base_monster, personality, um.talent)
                    is_physical = effective_stats.phy_atk > effective_stats.mag_atk

                    if language == "zh":
                        attack_type = "物理攻击" if is_physical else "魔法攻击"
                        willpower_lines.append(
                            f"- {monster_name}: 愿力冲击将成为 {legacy_type_name} 系别的 {attack_type} 技能"
                        )
                    else:
                        attack_type = "Physical Attack" if is_physical else "Magic Attack"
                        willpower_lines.append(
                            f"- {monster_name}: Willpower Impact will become a {legacy_type_name}-type {attack_type} move"
                        )

        if willpower_lines:
            if language == "zh":
                willpower_enhancement_section = (
                    f"注意：队伍选择了「愿力强化」血脉魔法。此魔法可以被队内 {eligible_count} 个精灵使用（首领血脉除外）。\n"
                    f"该魔法有3回合冷却时间，每场战斗最多使用2次（可用于不同精灵）。\n\n"
                    f"使用后，该精灵的第1个技能在本回合被替换为「愿力冲击」：\n"
                    f"- 愿力冲击 (系别：根据使用精灵的血脉属性动态变化, 类别：物攻/魔攻, 能量消耗:2, 威力:80): "
                    f"造成物理/魔法伤害（取决于使用精灵的物攻和魔攻哪个更高），应对成功时本次威力提高150%，应对状态。\n\n"
                    f"这是该血脉魔法的核心战术价值：通过血脉属性获得额外的攻击覆盖面和应对覆盖面。以下是各精灵使用该魔法时的愿力冲击效果：\n"
                    + "\n".join(willpower_lines)
                )
            else:
                willpower_enhancement_section = (
                    f"Note: The team has selected \"Willpower Enhancement\" magic item. This item can be used by {eligible_count} jinglings in the team (except those with Leader legacy type). \n"
                    f"The item has a 3-turn cooldown and can be used at most 2 times per battle (can be used on different jinglings).\n\n"
                    f"When used, the jingling's 1st move is replaced with \"Willpower Impact\" for that turn:\n"
                    f"- Willpower Impact (Type: Dynamically matches user's legacy type, Category: Physical/Magic Attack, Energy Cost:2, Power:80): "
                    f"Deals physical or magic damage (based on user's higher attack stat). If this move counters successfully, power +150%. Counter Status.\n\n"
                    f"This is the core tactical value of this magic item: gaining additional offensive coverage and counter coverage through legacy types. Here's what Willpower Impact will be for each eligible jingling:\n"
                    + "\n".join(willpower_lines)
                )

    # Build complete type effectiveness table
    type_chart_lines = []
    all_types = sorted(type_db_map.values(), key=lambda t: get_localized_name(t, language))
    for t in all_types:
        type_name = get_localized_name(t, language)
        if type_name in ["Leader", "首领"]:
            continue

        effective = []
        weak = []
        if hasattr(t, 'effective_against') and t.effective_against:
            effective = sorted([get_localized_name(target, language) for target in t.effective_against])
        if hasattr(t, 'weak_against') and t.weak_against:
            weak = sorted([get_localized_name(target, language) for target in t.weak_against])

        if language == "zh":
            eff_str = ', '.join(effective) if effective else '无'
            weak_str = ', '.join(weak) if weak else '无'
            type_chart_lines.append(f"  {type_name} → 克制: {eff_str} | 效果不佳: {weak_str}")
        else:
            eff_str = ', '.join(effective) if effective else 'None'
            weak_str = ', '.join(weak) if weak else 'None'
            type_chart_lines.append(f"  {type_name} → Effective Against: {eff_str} | Weak Against: {weak_str}")

    type_chart = "\n".join(type_chart_lines)

    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家，精通洛克王国的对战机制、属性克制和精灵配队。

## 对战机制
说明：以下规则适用于PvP单人模式，是分析队伍和精灵配置的基础：
{BATTLE_MECHANICS_ZH}

## 属性克制表（作为攻击方）
{type_chart}
说明：本表仅描述"攻击方属性X攻击防守方属性Y"时的对阵结果：哪些对阵更有利（克制），哪些对阵不利（效果不佳）。
注意：这里的"效果不佳"不等同于"X被这些属性克制"，请不要反向推断。精灵自身属性只允许用于说明技能的本系加成效果，不允许用于防守克制/抗性分析。

## 游戏术语表
注意：在特性/技能/血脉魔法的描述中出现的术语必须按此表解释。
{glossary}
{f'''
## 引用的技能
注意：以下技能在特性或已选技能的描述中被提及，这里提供其完整信息供参考。
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## 引用的精灵
注意：以下精灵在特性或已选技能的描述中被提及，这里提供其信息供参考。
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

队伍组成:
{team_summary}

血脉魔法: {magic_item_name} — {magic_item_desc}
{f'''

## 进化之力效果
注意：队伍选择了"进化之力"血脉魔法。以下精灵仅在玩家主动对其使用该血脉魔法的回合内进化为首领形态（进化时机由玩家选择）。一旦进化，该精灵将在本场战斗的剩余时间内保持首领形态，除非被特定技能或效果强制退化。分析时请考虑进化后的属性、特性和战术定位的变化，以及何时使用该魔法以触发进化的战术价值。
{leader_forms_section}
''' if leader_forms_section else ''}{f'''

## 愿力强化效果
{willpower_enhancement_section}
''' if willpower_enhancement_section else ''}

---

## 队伍整体协同作用分析
> **硬性要求**：所有结论必须**结合队内具体精灵与其「特性 / 技能类别（攻击/防御/状态）/ 能量消耗 / 应对标签 / 迅捷 / 血脉魔法」**来论证，避免泛泛而谈。

### 1) 队伍定位与战术体系
* **战术类型判定（写 2–3 句话）**
判定队伍属于养成/控制/消耗/平衡/反制体系中的哪一种或两种混合，并用队内配置证明：至少点出**核心输出结构（物攻/魔攻/混合）**、**防守与控场资源（防御/状态）**、以及**能量曲线（稳定低能耗循环 vs 依赖"聚能回合"来维持技能释放/关键回合能量）**各自由哪些精灵与技能承担。
* **体系核心与闭环链条（写 3–4 句话）**
指定 **2–4 只"体系核心/关键枢纽"**，逐一说明它们分别负责什么（增益/减益/控制/能量压制/应对触发/收割），并把它们串成一个闭环：
"谁负责铺垫 → 谁负责承伤/控场 → 谁负责触发应对或迅捷 → 谁负责终结"。必须明确引用：相关特性效果、技能类别与能耗、应对标签或迅捷触发条件。
* **节奏拆解（开局→中期→终局）（写 3–4 句话）**
给出清晰的战斗节奏路线：开局如何建立优势（例如先手压制/控场/压低对手能量），中期如何滚雪球（例如叠层、持续压迫对手能量或逼换），终局如何收割（明确由谁收割、靠什么能量/应对/迅捷窗口）。同时指出队伍是否**依赖速度优势**或**依赖应对系统**启动，以及如果启动失败会出现什么代价。

### 2) 行动优先级与应对策略
* **先手/后手角色划分与出手排序（写 3–4 句话）**
基于速度与技能定位，把队内精灵分成：先手压制位、后手反制位、站场/承伤位、机会收割位。说明你的建议出手顺序（谁更适合先动/后动），并用证据支撑：例如技能类别与能耗是否允许频繁出手、是否依赖聚能、是否依赖触发类特性/迅捷。
* **应对三角（防御↔攻击↔状态）的执行人（写 3–4 句话）**
说明队伍如何利用应对三角做反制：
  * 哪些精灵/技能更适合用"防御"应对对手攻击
  * 哪些更适合用"攻击"压制对手状态
  * 哪些更适合用"状态"反制对手防御
必须点名队内**最适合执行应对的精灵**及其依据（应对标签、技能类别、能耗、特性触发条件），并指出可能的失败点（例如能量断档/怕被对手同类反制）。
* **能量经济评估与资源分配（写 3–4 句话）**
评价队伍能量是否健康：是否存在稳定低能耗循环、回复能量/降耗机制、或逼迫对手聚能的手段（例如持续压能/提高对手技能能耗）。若队伍自身经常需要聚能来维持关键技能释放，则必须明确：哪只精灵在聚能时最不容易被击穿/被逼换，以及聚能带来的收益（能量回补后能立刻形成输出/控场/应对优势）与代价（丢回合导致掉节奏、被对手换入压制、或被反向应对）。

### 3) 轮换与进场策略
* **安全换入点/防守支点/节奏转换点（写 3–4 句话）**
找出队内能稳定换入的精灵（能吃伤害、能用防御/状态稳局面、或能逼退对手），并解释每个"换入点"成立的原因：特性带来的抗压/免疫/回血/脱离/进场收益？技能类别与低能耗是否允许立刻稳住？是否具备应对标签可反制对手的常见出手？
* **主动换人的触发场景（写 2–3 句话）**
列出至少 2 种应主动换人的局面：例如当前精灵能量枯竭、关键核心需要保护、需要切入制造关键回合（应对窗口/控场窗口/收割窗口）。每个场景都要说明：换到谁、为什么换他（能耗/应对/速度/特性/技能类别）。
* **迅捷相关的换入收益与风险（写 2–3 句话）**
如果队内存在带"迅捷"效果的技能：说明如何通过主动换入触发迅捷建立优势——谁负责触发、触发后的收益（先手权/抢节奏/应对优先级变化/能量收益）、以及风险（换入吃伤害、被对手预判克制、迅捷窗口被状态/防御应对打断等）。
如果队内不存在迅捷技能：简要说明这意味着队伍缺少迅捷战术选项，并评估这对队伍节奏控制的影响（例如：是否依赖其他方式抢先手、或是否通过应对系统弥补）。

### 4) 血脉魔法的最优化使用
* **最适配对象与轮转思路（写 3–4 句话）**
若血脉魔法一场战斗中只能使用一次：指出最值得给的 1 只精灵，并说明原因（与其特性/技能类别/能耗曲线/应对标签/迅捷或收割能力的契合点）。
若可多次使用或有冷却：给出适配的 2–3 只精灵与轮转逻辑（什么局面给谁、为何能提高全队胜率/稳定性）。
* **具体使用时机（写 2–3 句话）**
提供 1–2 个明确的使用时机：例如配合某关键技能回合、弥补能量断档、丰富应对种类、或提升精灵整体强度。必须讲清楚"使用前提"和"预期收益"。
* **匹配度评估（写 2–3 句话）**
若血脉魔法可以被队内精灵正常使用：用一句话确认匹配度良好，再用1-2句话简述该魔法与队伍战术的契合点或潜在协同。
若血脉魔法无法被任何队伍成员使用：用一句话解释原因，再用两句话给出调整思路（如何修改队内配置以符合使用标准，或根据队伍优势建议魔法替换方向，仅描述功能方向不提供具体名称）。

### 5) 整体战术建议与结构性弱点
* **胜利条件与达成路径（写 3–4 句话）**
用 1–2 条总结队伍主要胜利条件（例如"通过能量压制+应对链条滚雪球后收割"或"靠速度与迅捷抢关键回合打穿"），并写清楚达成路径需要的前置条件：至少包含能量状态、关键精灵存活/进场条件、应对链条是否成立。
* **最容易被针对的节奏点（写 3–4 句话）**
指出队伍最脆弱的 1–2 个结构性问题：如能量断档、缺乏稳定防守回合、过度依赖某核心、或对某类状态/防御体系缺少反制。每个弱点都要落到具体证据（哪个精灵、哪类技能、哪个能耗节点、哪个应对标签缺口）。
* **规避与调整建议（写 3–4 句话）**
从以下方向里选择最关键的 1–2 条给出"可执行"的建议：出手优先级调整 / 应对策略调整 / 轮换触发点设计 / 能量管理方案 / 技能或精灵替换建议。必须明确：改动点是什么、解决哪个弱点、带来的副作用是什么。

以以下JSON格式输出（用中文回复）：
{{
"team_archetype": {{
  "tactical_type": "战术类型判定的内容",
  "core_loop": "体系核心与闭环链条的内容",
  "battle_rhythm": "节奏拆解的内容"
}},
"action_priority": {{
  "role_assignment": "先手/后手角色划分与出手排序的内容",
  "counter_triangle": "应对三角的执行人的内容",
  "energy_economy": "能量经济评估与资源分配的内容"
}},
"switching_strategy": {{
  "pivot_points": "安全换入点/防守支点/节奏转换点的内容",
  "active_switch_scenarios": "主动换人的触发场景的内容",
  "quick_entry_synergy": "迅捷相关的换入收益与风险的内容"
}},
"magic_item_usage": {{
  "best_targets": "最适配对象与轮转思路的内容",
  "timing": "具体使用时机的内容",
  "mismatch_analysis": "匹配度评估的内容"
}},
"overall_strategy": {{
  "win_conditions": "胜利条件与达成路径的内容",
  "vulnerable_points": "最容易被针对的节奏点的内容",
  "adjustments": "规避与调整建议的内容"
}}
}}
"""
    else:
        prompt = f"""You are an expert game strategist specializing in Roco Kingdom battle mechanics, type matchups, and team composition.

## Battle Mechanics
Note: The following rules apply to PvP solo mode and form the foundation for team and monster analysis.
{BATTLE_MECHANICS_EN}

## Type Effectiveness Table (Attacking Perspective)
{type_chart}
Note: This chart only describes the outcome when the attacking type X hits the defending type Y: which matchups are favorable (effective) and which are unfavorable (weak).
Important: "Unfavorable" here does NOT mean "X is countered by these types." Do not infer the reverse direction. You may mention the monster's own types ONLY for STAB/same-type bonuses, not for defensive weaknesses/resistances.

## Game Terms Glossary
Important: Any terms appearing in trait/move/magic item descriptions must be interpreted using this glossary.
{glossary}
{f'''
## Referenced Moves
Note: The following moves are mentioned in trait or selected move descriptions. Their full details are provided here for reference.
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## Referenced Monsters
Note: The following monsters are mentioned in trait or selected move descriptions. Their information is provided here for reference.
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

Team Composition:
{team_summary}

Magic Item: {magic_item_name} — {magic_item_desc}
{f'''

## Evolution Power Effect
Note: The team has selected the "Evolution Power" magic item. The following monsters will evolve into their Leader forms only when the player actively uses this magic item on them during a specific turn (timing chosen by the player). Once evolved, the monster will remain in its Leader form for the rest of the battle, unless forcibly devolved by certain moves or effects. In your analysis, consider the changes in stats, traits, and tactical positioning after evolution, as well as the strategic value of when to use this magic item to trigger the evolution.
{leader_forms_section}
''' if leader_forms_section else ''}{f'''

## Willpower Enhancement Effect
{willpower_enhancement_section}
''' if willpower_enhancement_section else ''}

---

## Team Synergy Analysis
> **Critical Requirement**: All conclusions must be **grounded in specific monsters and their traits/move categories (Attack/Defense/Status)/energy costs/counter tags/Quick Entry/Magic Item**, avoiding generic statements.

### 1) Team Archetype & Tactical System
* **Tactical Type Identification (2-3 sentences)**
Determine whether the team follows a setup/control/attrition/balanced/reactive archetype (or a hybrid), and justify using the team's configuration: at minimum, identify the **core damage structure (Physical/Magical/Hybrid)**, **defensive and control resources (Defense/Status)**, and **energy curve (stable low-cost loops vs reliance on "Focus turns" to maintain move usage/critical turns)**, specifying which monsters and moves handle each role.
* **Core Members & Closed Loop (3-4 sentences)**
Designate **2-4 "core members/key pivots"**, explain what each handles (buffs/debuffs/control/energy pressure/counter triggers/sweeping), and connect them into a closed loop:
"Who sets up → Who tanks/controls → Who triggers counters or Quick Entry → Who finishes". Must explicitly reference: relevant trait effects, move categories and costs, counter tags, or Quick Entry trigger conditions.
* **Battle Rhythm Breakdown (Early → Mid → Late) (3-4 sentences)**
Provide a clear battle rhythm roadmap: how to establish early advantage (e.g., first-strike pressure/control/draining opponent energy), how to snowball mid-game (e.g., stacking layers, continuous energy pressure or forcing switches), how to close out late (specify who finishes, via what energy/counter/Quick Entry window). Also indicate whether the team **relies on speed advantage** or **relies on counter system** to initiate, and what happens if initiation fails.

### 2) Action Priority & Counter Strategy
* **First-Strike/Reactive Role Assignment & Turn Order (3-4 sentences)**
Based on speed and move positioning, categorize team monsters into: first-strike pressure, reactive counter, tank/absorber, opportunistic sweeper. Explain your recommended turn order (who should move first/last), with evidence: e.g., whether move category and cost allow frequent action, whether they depend on Focus, whether they depend on trigger-based traits/Quick Entry.
* **Counter Triangle (Defense↔Attack↔Status) Executors (3-4 sentences)**
Explain how the team leverages the counter triangle for reactive play:
  * Which monsters/moves best use "Defense" to counter opponent Attacks
  * Which best use "Attack" to pressure opponent Status
  * Which best use "Status" to counter opponent Defense
Must name the **best counter executors** in the team with justification (counter tags, move categories, costs, trait trigger conditions), and point out potential failure modes (e.g., energy drought/vulnerable to opponent's same-type counter).
* **Energy Economy Assessment & Resource Allocation (3-4 sentences)**
Evaluate whether the team's energy is healthy: does it have stable low-cost loops, energy refund/cost reduction mechanisms, or ways to force opponent Focus (e.g., continuous pressure/increasing opponent move costs). If the team itself often needs Focus to maintain key move usage, must specify: which monster is least likely to be broken/forced out during Focus, and Focus benefits (immediate damage/control/counter advantage after energy recovery) vs costs (losing tempo, being pressured by opponent switches, or being reverse-countered).

### 3) Switching & Entry Strategy
* **Safe Switch-Ins/Defensive Pivots/Tempo Shifters (3-4 sentences)**
Identify monsters that can safely switch in (can take hits, stabilize with Defense/Status, or force opponent switches), and explain why each "switch-in point" works: does the trait provide durability/immunity/healing/escape/entry benefits? Do move categories and low costs allow immediate stabilization? Do they have counter tags to react to common opponent actions?
* **Active Switch Triggers (2-3 sentences)**
List at least 2 scenarios requiring active switches: e.g., current monster's energy depleted, protecting key sweepers, bringing in a counter for a critical turn (counter window/control window/sweep window). For each scenario, specify: switch to whom, why (cost/counter/speed/trait/move category).
* **Quick Entry Synergy, Benefits & Risks (2-3 sentences)**
If Quick Entry moves exist: explain how to leverage active switch-ins to trigger Quick Entry for advantage—who triggers, post-trigger benefits (priority/tempo steal/counter priority shift/energy gain), and risks (switch-in takes damage, opponent predicts and counters, Quick Entry window interrupted by Status/Defense counters, etc.).
If no Quick Entry moves exist: briefly note that the team lacks Quick Entry tactical options and assess the impact on tempo control (e.g., whether relying on other methods for priority, or compensating via the counter system).

### 4) Magic Item Optimization
* **Best Targets & Rotation Logic (3-4 sentences)**
If magic item is one-time use: identify the 1 monster most worth using it on, with reasoning (synergy with trait/move category/energy curve/counter tags/Quick Entry or sweep potential).
If it is multi-use or has cooldown: provide 2-3 best-fit monsters and rotation logic (what situation for whom, why it improves team win rate/stability).
* **Specific Usage Timing (2-3 sentences)**
Provide 1-2 concrete usage timings: e.g., combo with key move turn, covering energy gaps, enriching counter variety, or boosting monster overall power. Must clarify "prerequisites" and "expected benefits".
* **Compatibility Assessment (2-3 sentences)**
If the magic item can be used by team monsters: confirm good compatibility in one sentence, then briefly describe synergies between the item and team tactics in 1-2 sentences.
If the magic item cannot be used by any team member: explain why in one sentence, then provide adjustment ideas in two sentences (how to modify team configuration to meet usage requirements, or suggest magic item replacement direction based on team strengths—functional direction only, no specific names).

### 5) Overall Strategy & Structural Weaknesses
* **Win Conditions & Achievement Paths (3-4 sentences)**
Summarize the team's 1-2 primary win conditions (e.g., "snowball via energy pressure + counter chains then sweep" or "steal critical turns via speed + Quick Entry to break through"), and clarify the prerequisites for achieving them: at minimum, include energy state, key monster survival/entry conditions, whether counter chains hold.
* **Most Exploitable Tempo Vulnerabilities (3-4 sentences)**
Identify the team's 1-2 most fragile structural issues: e.g., energy drought, lack of stable defensive turns, over-reliance on certain cores, or lack of counter-play against certain Status/Defense archetypes. Each weakness must be backed by concrete evidence (which monster, which move type, which energy node, which counter tag gap).
* **Mitigation & Adjustment Recommendations (3-4 sentences)**
From the following directions, select the most critical 1-2 for "actionable" recommendations: action priority adjustments / counter strategy adjustments / switching trigger design / energy management plans / move or monster swap suggestions. Must specify: what to change, which weakness it addresses, what side effects it brings.

Output as JSON in the following format:
{{
"team_archetype": {{
  "tactical_type": "Content for tactical type identification",
  "core_loop": "Content for core members and closed loop",
  "battle_rhythm": "Content for battle rhythm breakdown"
}},
"action_priority": {{
  "role_assignment": "Content for role assignment and turn order",
  "counter_triangle": "Content for counter triangle executors",
  "energy_economy": "Content for energy economy assessment"
}},
"switching_strategy": {{
  "pivot_points": "Content for safe switch-ins/pivots/tempo shifters",
  "active_switch_scenarios": "Content for active switch triggers",
  "quick_entry_synergy": "Content for Quick Entry synergy, benefits & risks"
}},
"magic_item_usage": {{
  "best_targets": "Content for best targets and rotation logic",
  "timing": "Content for specific usage timing",
  "mismatch_analysis": "Content for compatibility assessment"
}},
"overall_strategy": {{
  "win_conditions": "Content for win conditions and achievement paths",
  "vulnerable_points": "Content for most exploitable vulnerabilities",
  "adjustments": "Content for mitigation and adjustment recommendations"
}}
}}
"""
    return prompt
