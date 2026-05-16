"""Hand-traced fixtures for backend.damage.compute_move_damage.

These tests are the SHARED SOURCE OF TRUTH for the damage formula.
The frontend mirror in frontend/src/lib/damageCalc.ts MUST produce
the same numbers for the same inputs — same discipline as
test_stat_calculation.py.

Each fixture's expected value is hand-traced step-by-step in a
comment next to its assertions, so the arithmetic is auditable
without re-deriving the formula from scratch.

Stat values (attacker_atk, defender_def) are passed in directly
rather than computed via compute_effective_stats — this decouples
the damage tests from whichever version of the stat formula is
on main, and lets the fixtures stay readable with round numbers.
"""

from backend.damage import (
    boost_multiplier,
    combine_attacker_statuses,
    combine_defender_statuses,
    compute_move_damage,
    type_effectiveness,
)


# ---------------------------------------------------------------------
# Helpers — minimal duck-typed stand-in for backend.models.Status
# ---------------------------------------------------------------------
class Status:
    """Minimal Status stand-in for tests. All fields default to 0.

    Mirrors backend.models.Status field names so the same combiner
    functions work on both real ORM rows and test dummies.
    """

    def __init__(self, **kwargs):
        defaults = dict(
            hp_boost=0,
            phy_atk_boost=0,
            mag_atk_boost=0,
            phy_def_boost=0,
            mag_def_boost=0,
            spd_boost=0,
            flat_power_boost=0,
            pct_power_boost=0,
            combo_bonus=0,
            dmg_reduction_pct=0.0,
            dmg_bonus_pct=0.0,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------
def test_boost_multiplier_positive_and_negative_are_inverses():
    # +20 ↔ ×1.20, -20 ↔ ×(1/1.20) — symmetric multiplicative inverses
    assert boost_multiplier(0) == 1.0
    assert boost_multiplier(20) == 1.2
    assert boost_multiplier(-20) == 1 / 1.2
    # Stacking +X and -X should return to ~1.0 (within fp tolerance)
    assert abs(boost_multiplier(20) * boost_multiplier(-20) - 1.0) < 1e-12
    assert abs(boost_multiplier(50) * boost_multiplier(-50) - 1.0) < 1e-12
    assert abs(boost_multiplier(100) * boost_multiplier(-100) - 1.0) < 1e-12


def test_type_effectiveness_single_type_defender():
    # Single-type defender → only {2.0, 1.0, 0.5} possible
    assert type_effectiveness("Fire", main_vuln=["Fire"], main_resist=[]) == 2.0
    assert type_effectiveness("Water", main_vuln=["Fire"], main_resist=["Water"]) == 0.5
    assert type_effectiveness("Bug", main_vuln=["Fire"], main_resist=["Water"]) == 1.0


def test_type_effectiveness_dual_type_defender():
    # Defender Grass / Bug, attacker Fire — vuln-vs both → 3.0
    assert type_effectiveness(
        "Fire",
        main_vuln=["Fire", "Bug"], main_resist=["Water", "Grass"],
        sub_vuln=["Fire", "Flying"], sub_resist=["Fighting"],
    ) == 3.0
    # Defender resist on one half, neutral on other → 0.5
    assert type_effectiveness(
        "Water",
        main_vuln=["Fire"], main_resist=["Water"],
        sub_vuln=["Ice"], sub_resist=[],
    ) == 0.5
    # Vuln on one half, resist on the other → cancelled to 1.0
    assert type_effectiveness(
        "Fire",
        main_vuln=["Fire"], main_resist=[],
        sub_vuln=[], sub_resist=["Fire"],
    ) == 1.0
    # Both halves resist → 0.25
    assert type_effectiveness(
        "Water",
        main_vuln=[], main_resist=["Water"],
        sub_vuln=[], sub_resist=["Water"],
    ) == 0.25
    # Neither half cares → neutral 1.0
    assert type_effectiveness(
        "Normal",
        main_vuln=["Fire"], main_resist=["Water"],
        sub_vuln=["Ice"], sub_resist=["Fighting"],
    ) == 1.0


def test_combine_attacker_statuses_additive_stats_multiplicative_dmg():
    s1 = Status(phy_atk_boost=20, dmg_bonus_pct=10)
    s2 = Status(phy_atk_boost=30, dmg_bonus_pct=20)
    deltas = combine_attacker_statuses([s1, s2], is_magic=False)
    # Stats add: 20 + 30 = 50
    assert deltas.atk_boost_total == 50
    # Damage modifiers MULTIPLY: (1.10)(1.20) = 1.32, NOT 1.30
    assert abs(deltas.dmg_factor - 1.32) < 1e-12


def test_combine_defender_statuses_additive_def_multiplicative_reduction():
    s1 = Status(mag_def_boost=20, dmg_reduction_pct=10)
    s2 = Status(mag_def_boost=30, dmg_reduction_pct=20)
    deltas = combine_defender_statuses([s1, s2], is_magic=True)
    assert deltas.def_boost_total == 50
    # (1 - 0.10)(1 - 0.20) = 0.72, NOT 0.70
    assert abs(deltas.dmg_factor - 0.72) < 1e-12


def test_defend_status_reduces_damage_by_70_percent():
    baseline = compute_move_damage(
        move_power=100,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    defended = compute_move_damage(
        move_power=100,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
        defender_statuses=[Status(dmg_reduction_pct=70)],
    )

    # Baseline: round(0.9 * 100 * 200 / 100 * 1.25) = 225.
    # Defend:   round(225 * 0.30) = round(67.5) = 68.
    assert baseline == 225
    assert defended == 68


# ---------------------------------------------------------------------
# Fixture 1 — single-type defender, single attacker status, STAB on, vuln 2×
# ---------------------------------------------------------------------
def test_damage_fixture_1_single_type_vuln_with_stab():
    # Attacker: Fire-type (single), mag_atk = 200, one active status:
    #   pct_power_boost = +20  → power_multiplier = 1.20
    #   mag_atk_boost   = +30  → atk_multiplier   = 1.30
    #   dmg_bonus_pct   = +10  → atk_dmg_factor   = 1.10
    # Defender: Grass (single-type), mag_def = 150, one active status:
    #   mag_def_boost     = +20  → def_multiplier = 1.20
    #   dmg_reduction_pct = +10  → def_dmg_factor = 0.90
    # Move: Fire / MAG_ATTACK / power 80
    #
    # power_term = round((80 + 0) × 1.20)  = round(96)  = 96
    # atk_term   = round(200 × 1.30)       = round(260) = 260
    # def_term   = round(150 × 1.20)       = round(180) = 180
    # STAB       = 1.25 (attacker is Fire, move is Fire)
    # type_eff   = 2.0  (Grass single-type vulnerable to Fire)
    # inner      = 0.9 × 96 × 260 × (1/180) × 1.25 × 2.0 × 0.90 × 1.10
    #            = 0.9 × 96 = 86.4
    #            × 260      = 22464
    #            ÷ 180      = 124.8
    #            × 1.25     = 156.0
    #            × 2.0      = 312.0
    #            × 0.90     = 280.8
    #            × 1.10     = 308.88
    # damage     = round(308.88) = 309
    damage = compute_move_damage(
        move_power=80,
        move_type_name="Fire",
        is_magic=True,
        attacker_atk=200,
        attacker_main_type="Fire",
        attacker_sub_type=None,
        defender_def=150,
        defender_main_vuln=["Fire"],
        defender_main_resist=[],
        defender_sub_vuln=None,
        defender_sub_resist=None,
        attacker_statuses=[Status(pct_power_boost=20, mag_atk_boost=30, dmg_bonus_pct=10)],
        defender_statuses=[Status(mag_def_boost=20, dmg_reduction_pct=10)],
    )
    assert damage == 309


# ---------------------------------------------------------------------
# Fixture 2 — dual-type defender, both vuln (×3.0), no STAB, no statuses
# ---------------------------------------------------------------------
def test_damage_fixture_2_dual_type_triple_weak_no_stab_no_statuses():
    # Attacker: Normal-type, phy_atk = 180, no active statuses
    # Defender: Grass / Bug, phy_def = 120, no active statuses
    # Move: Fighting / PHY_ATTACK / power 100
    #
    # No statuses → all boost_multipliers = bm(0) = 1.0
    # power_term = round((100 + 0) × 1.0) = 100
    # atk_term   = round(180 × 1.0)       = 180
    # def_term   = round(120 × 1.0)       = 120
    # STAB       = 1.0 (attacker Normal, move Fighting)
    # type_eff   = 3.0 (Fighting vulnerable on Grass AND Bug — both halves)
    # inner      = 0.9 × 100 × 180 × (1/120) × 1.0 × 3.0 × 1.0 × 1.0
    #            = 0.9 × 100 = 90
    #            × 180      = 16200
    #            ÷ 120      = 135
    #            × 3.0      = 405
    # damage     = round(405) = 405
    damage = compute_move_damage(
        move_power=100,
        move_type_name="Fighting",
        is_magic=False,
        attacker_atk=180,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=120,
        defender_main_vuln=["Fighting"],
        defender_main_resist=[],
        defender_sub_vuln=["Fighting"],
        defender_sub_resist=[],
        attacker_statuses=[],
        defender_statuses=[],
    )
    assert damage == 405


# ---------------------------------------------------------------------
# Fixture 3 — multiple stacked statuses on each side (additive vs multiplicative)
# ---------------------------------------------------------------------
def test_damage_fixture_3_stacked_statuses():
    # Attacker: Water-type (sub: Ice), mag_atk = 220, TWO active statuses:
    #   s1: pct_power_boost = +20, mag_atk_boost = +20, dmg_bonus_pct = +10
    #   s2: pct_power_boost = +30, mag_atk_boost = +30, dmg_bonus_pct = +20
    # Combined: pct_power = +50 (additive), mag_atk = +50 (additive),
    #           atk_dmg_factor = (1.10)(1.20) = 1.32 (multiplicative — NOT 1.30)
    # Defender: Fire (single-type), mag_def = 130, TWO active statuses:
    #   d1: mag_def_boost = +10, dmg_reduction_pct = +10
    #   d2: mag_def_boost = +10, dmg_reduction_pct = +20
    # Combined: mag_def = +20 (additive),
    #           def_dmg_factor = (0.90)(0.80) = 0.72 (multiplicative — NOT 0.70)
    # Move: Water / MAG_ATTACK / power 70
    #
    # power_term = round((70 + 0) × bm(+50)) = round(70 × 1.50) = round(105) = 105
    # atk_term   = round(220 × bm(+50))      = round(220 × 1.50) = round(330) = 330
    # def_term   = round(130 × bm(+20))      = round(130 × 1.20) = round(156) = 156
    # STAB       = 1.25 (attacker main is Water, move is Water)
    # type_eff   = 2.0  (Fire single-type vulnerable to Water)
    # inner      = 0.9 × 105 × 330 × (1/156) × 1.25 × 2.0 × 0.72 × 1.32
    #            = 0.9 × 105 = 94.5
    #            × 330      = 31185
    #            ÷ 156      = 199.903846...
    #            × 1.25     = 249.879807...
    #            × 2.0      = 499.759615...
    #            × 0.72     = 359.826923...
    #            × 1.32     = 474.971538...
    # damage     = round(474.97...) = 475
    damage = compute_move_damage(
        move_power=70,
        move_type_name="Water",
        is_magic=True,
        attacker_atk=220,
        attacker_main_type="Water",
        attacker_sub_type="Ice",
        defender_def=130,
        defender_main_vuln=["Water"],
        defender_main_resist=[],
        defender_sub_vuln=None,
        defender_sub_resist=None,
        attacker_statuses=[
            Status(pct_power_boost=20, mag_atk_boost=20, dmg_bonus_pct=10),
            Status(pct_power_boost=30, mag_atk_boost=30, dmg_bonus_pct=20),
        ],
        defender_statuses=[
            Status(mag_def_boost=10, dmg_reduction_pct=10),
            Status(mag_def_boost=10, dmg_reduction_pct=20),
        ],
    )
    assert damage == 475


# ---------------------------------------------------------------------
# Fixture 4 — dual-type cancellation (×1.0), negative atk debuff,
# flat power boost, sub-type STAB
# ---------------------------------------------------------------------
def test_damage_fixture_4_cancelled_type_negative_boost_flat_power():
    # Attacker: dual-type (Dragon main / Fire sub), phy_atk = 250, status:
    #   flat_power_boost = +30 (added to move.power before mul)
    #   phy_atk_boost    = -20 (debuff — bm(-20) = 100/120 ≈ 0.8333)
    # Defender: Water main / Fire sub, phy_def = 200, no statuses
    # Move: Fire / PHY_ATTACK / power 60
    #
    # Status combine: flat_power=+30, pct_power=0, atk_boost=-20, dmg_factor=1.0
    # power_term = round((60 + 30) × bm(0)) = round(90 × 1.0) = 90
    # atk_term   = round(250 × bm(-20))     = round(250 × 100/120) = round(208.333…) = 208
    # def_term   = round(200 × bm(0))       = 200
    # STAB       = 1.25 (attacker SUB type Fire matches move Fire — sub_type counts!)
    # type_eff   = Fire vs Water (resist) + Fire (vuln) → cancelled → 1.0
    # inner      = 0.9 × 90 × 208 × (1/200) × 1.25 × 1.0 × 1.0 × 1.0
    #            = 0.9 × 90 = 81
    #            × 208      = 16848
    #            ÷ 200      = 84.24
    #            × 1.25     = 105.30
    # damage     = round(105.30) = 105
    damage = compute_move_damage(
        move_power=60,
        move_type_name="Fire",
        is_magic=False,
        attacker_atk=250,
        attacker_main_type="Dragon",
        attacker_sub_type="Fire",
        defender_def=200,
        defender_main_vuln=[],
        defender_main_resist=["Fire"],
        defender_sub_vuln=["Fire"],
        defender_sub_resist=[],
        attacker_statuses=[Status(flat_power_boost=30, phy_atk_boost=-20)],
        defender_statuses=[],
    )
    assert damage == 105


# ---------------------------------------------------------------------
# Fixture 5 — counter_power_multiplier: orchestrator passes total power
# ---------------------------------------------------------------------
def test_counter_power_multiplier_flow():
    # Multi-Claw Strike: power=30, base_combo=2, counter_power_multiplier=2.
    # Orchestrator computes: move_power = 30 × 2 × 2 = 120 (counter alt row).
    # Attacker: Normal (single), phy_atk=200, def=100, no statuses.
    #
    # Base row (move_power = 30 × 2 = 60):
    #   power_term = 60, atk_term = 200, def_term = 100
    #   STAB = 1.25 (Normal attacker, Normal move)
    #   inner = 0.9 × 60 × 200 / 100 × 1.25 = 54 × 200 / 100 × 1.25 = 135
    #
    # Counter alt row (move_power = 120):
    #   power_term = 120
    #   inner = 0.9 × 120 × 200 / 100 × 1.25 = 108 × 200 / 100 × 1.25 = 270
    base = compute_move_damage(
        move_power=60,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    counter = compute_move_damage(
        move_power=120,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    assert base == 135
    assert counter == 270
    assert counter == base * 2


# ---------------------------------------------------------------------
# Fixture 6 — alt_power_total: pre-computed conditional power
# ---------------------------------------------------------------------
def test_alt_power_total_flow():
    # Extreme Cold Zone: power=105, alt_power_total=165 (if opponent has Freeze).
    # Attacker: Ice (single), mag_atk=180, def=150, dual-type defender (both vuln Ice).
    #
    # Base (move_power=105):
    #   power_term = 105, atk_term = 180, def_term = 150
    #   STAB = 1.25 (Ice attacker, Ice move), type_eff = 3.0
    #   inner = 0.9 × 105 × 180 / 150 × 1.25 × 3.0
    #         = 94.5 × 180 = 17010 / 150 = 113.4 × 1.25 = 141.75 × 3.0 = 425.25 → 425
    #
    # Alt (move_power=165):
    #   power_term = 165
    #   inner = 0.9 × 165 × 180 / 150 × 1.25 × 3.0
    #         = 148.5 × 180 = 26730 / 150 = 178.2 × 1.25 = 222.75 × 3.0 = 668.25 → 668
    base = compute_move_damage(
        move_power=105,
        move_type_name="Ice",
        is_magic=True,
        attacker_atk=180,
        attacker_main_type="Ice",
        attacker_sub_type=None,
        defender_def=150,
        defender_main_vuln=["Ice"],
        defender_main_resist=[],
        defender_sub_vuln=["Ice"],
        defender_sub_resist=[],
    )
    alt = compute_move_damage(
        move_power=165,
        move_type_name="Ice",
        is_magic=True,
        attacker_atk=180,
        attacker_main_type="Ice",
        attacker_sub_type=None,
        defender_def=150,
        defender_main_vuln=["Ice"],
        defender_main_resist=[],
        defender_sub_vuln=["Ice"],
        defender_sub_resist=[],
    )
    assert base == 425
    assert alt == 668


# ---------------------------------------------------------------------
# Fixture 7 — move_specific power_bonus: conditional power = base + bonus
# ---------------------------------------------------------------------
def test_move_specific_power_bonus_flow():
    # All or Nothing: power=80, power_bonus=60 → conditional move_power=140.
    # Attacker: Cute (single), mag_atk=160, def=100, STAB.
    #
    # Base (move_power=80):
    #   power_term = 80, atk_term = 160, def_term = 100
    #   STAB = 1.25, type_eff = 1.0
    #   inner = 0.9 × 80 × 160 / 100 × 1.25 = 72 × 160 / 100 × 1.25 = 144
    #
    # Alt (move_power=140):
    #   power_term = 140
    #   inner = 0.9 × 140 × 160 / 100 × 1.25 = 126 × 160 / 100 × 1.25 = 252
    base = compute_move_damage(
        move_power=80,
        move_type_name="Cute",
        is_magic=True,
        attacker_atk=160,
        attacker_main_type="Cute",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    alt = compute_move_damage(
        move_power=140,
        move_type_name="Cute",
        is_magic=True,
        attacker_atk=160,
        attacker_main_type="Cute",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    assert base == 144
    assert alt == 252


# ---------------------------------------------------------------------
# Fixture 8 — opponent debuff (affect=opponent, negative def_boost)
# ---------------------------------------------------------------------
def test_opponent_debuff_negative_def_boost_raises_damage():
    # Sharp Eyes: affect=opponent, phy_def_boost=-120.
    # Passed as a defender_status — lowers the effective def_term.
    # Attacker: Normal (single), phy_atk=200, move power=100, def=200.
    #
    # Baseline (no debuff):
    #   def_term = round(200 × bm(0)) = 200
    #   inner = 0.9 × 100 × 200 / 200 × 1.25 = 90 × 1.25 = 112.5 → 113
    #
    # With Sharp Eyes (phy_def_boost=-120):
    #   bm(-120) = 100 / (100 + 120) = 100/220 = 0.4545…
    #   def_term = round(200 × 0.4545…) = round(90.909…) = 91
    #   inner = 0.9 × 100 × 200 / 91 × 1.25
    #         = 90 × 200 / 91 × 1.25 = 18000 / 91 × 1.25 = 197.802… × 1.25 = 247.25… → 247
    baseline = compute_move_damage(
        move_power=100,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=200,
        defender_main_vuln=[],
        defender_main_resist=[],
    )
    debuffed = compute_move_damage(
        move_power=100,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=200,
        defender_main_vuln=[],
        defender_main_resist=[],
        defender_statuses=[Status(phy_def_boost=-120)],
    )
    assert baseline == 113
    assert debuffed == 247
    assert debuffed > baseline


# ---------------------------------------------------------------------
# Fixture 9 — flat + pct power: flat added first, then pct multiplied
# ---------------------------------------------------------------------
def test_flat_and_pct_power_order_of_operations():
    # move.power=60, flat_power_boost=40, pct_power_boost=50.
    # Correct:   power_term = round((60 + 40) × bm(+50)) = round(100 × 1.50) = 150
    # Wrong ord: power_term = round(60 × 1.50) + 40 = 90 + 40 = 130
    #
    # Correct path:
    #   power_term = 150, atk_term = 200, def_term = 100
    #   STAB = 1.25 (Normal / Normal), type_eff = 1.0
    #   inner = 0.9 × 150 × 200 / 100 × 1.25 = 135 × 2.0 × 1.25 = 337.5 → 338
    damage = compute_move_damage(
        move_power=60,
        move_type_name="Normal",
        is_magic=False,
        attacker_atk=200,
        attacker_main_type="Normal",
        attacker_sub_type=None,
        defender_def=100,
        defender_main_vuln=[],
        defender_main_resist=[],
        attacker_statuses=[Status(flat_power_boost=40, pct_power_boost=50)],
    )
    assert damage == 338
    assert damage != 293  # guard against wrong order (130 power_term path)
