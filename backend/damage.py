"""
Move damage calculation for the per-slot vs-defender matchup feature.

Pure functions only — no SQLAlchemy session, no FastAPI, no I/O. The
caller is responsible for resolving the attacker's and defender's stats
(via compute_effective_stats), choosing the active subset of statuses,
and looking up the relevant Type vulnerable_to / resistant_to lists.

The formula is mirrored 1:1 in frontend/src/lib/damageCalc.ts. Both
ports MUST stay in sync — the test fixtures in
backend/tests/test_damage_calculation.py are the shared source of
truth and the frontend hand-verifies against them via a Node check.

Formula (from the game's damage rule, double-rounded):

    boost_multiplier(b):
        +b → (100 + b) / 100               # +20 → ×1.20
        -b → 100 / (100 - b)               # -20 → ×(1/1.20) ≈ ×0.833 (symmetric)

    For each attack-category move:

        atk = mag_atk if move is MAG_ATTACK else phy_atk
        def = mag_def if move is MAG_ATTACK else phy_def

        # Combine active attacker statuses (additive within each kind)
        flat_power_total = Σ s.flat_power_boost
        pct_power_total  = Σ s.pct_power_boost           → boost_multiplier
        atk_boost_total  = Σ s.<phy|mag>_atk_boost       → boost_multiplier

        # Combine active defender statuses (additive for stat boost,
        # MULTIPLICATIVE for damage modifiers)
        def_boost_total  = Σ s.<phy|mag>_def_boost       → boost_multiplier
        atk_dmg_factor   = ∏ (1 + s.dmg_bonus_pct/100)     for s in attacker_statuses
        def_dmg_factor   = ∏ (1 - s.dmg_reduction_pct/100) for s in defender_statuses

        power_term = round_half_up( (move.power + flat_power_total) × bm(pct_power_total) )
        atk_term   = round_half_up( atk × bm(atk_boost_total) )
        def_term   = round_half_up( def × bm(def_boost_total) )

        STAB     = 1.25 if move.type ∈ {attacker.main_type, attacker.sub_type} else 1
        type_eff = 3 / 2 / 1 / 0.5 / 0.25 lookup against defender's main + sub type

        damage = round_half_up(
            0.9
            × power_term
            × atk_term
            / def_term
            × STAB
            × type_eff
            × def_dmg_factor
            × atk_dmg_factor
        )

The status fields hp_boost, spd_boost, and combo_bonus are columns on
the Status model for symmetry / future expansion but are NOT consumed
by this formula yet. See backend/models.py:Status for column docs.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence


# ---------------------------------------------------------------------
# Rounding (mirrors compute_effective_stats — round half away from zero)
# ---------------------------------------------------------------------
def round_half_up(n: float) -> int:
    """Python's int(Decimal(...).to_integral_value(ROUND_HALF_UP)).

    Mirrors the rounding rule used by compute_effective_stats so the
    damage formula and the stat formula round consistently. For positive
    half-values, rounds AWAY from zero (214.5 → 215). All damage outputs
    are non-negative in practice; this matches frontend Math.round for
    non-negative inputs.
    """
    return int(Decimal(str(n)).to_integral_value(rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------
# Boost multiplier — symmetric percentage scaling
# ---------------------------------------------------------------------
def boost_multiplier(boost: int) -> float:
    """Convert a percentage boost to a stat multiplier.

    Positive: +20 → ×1.20  (a 20% increase)
    Negative: -20 → ×(1/1.20) ≈ ×0.833  (the multiplicative inverse)

    The asymmetry is intentional and standard for stat-stage systems:
    stacking +20 then -20 returns the original value (1.20 × 0.833 = 1.00).
    """
    if boost >= 0:
        return (100 + boost) / 100
    return 100 / (100 - boost)


# ---------------------------------------------------------------------
# Type effectiveness — game-specific 5-step scale
# ---------------------------------------------------------------------
def type_effectiveness(
    move_type_name: str,
    main_vuln: Iterable[str],
    main_resist: Iterable[str],
    sub_vuln: Optional[Iterable[str]] = None,
    sub_resist: Optional[Iterable[str]] = None,
) -> float:
    """Multiplier for an attacker's move type against a defender's types.

    Returns one of: 3.0, 2.0, 1.0, 0.5, 0.25.

    For a single-type defender (sub_* is None), the result is in
    {2.0, 1.0, 0.5}. For dual-type defenders, the wider scale applies.

    Cancellation: vuln on one type + resist on the other → 1.0 (neutral).
    This matches the in-game rule and the frontend TypeDefensePanel buckets
    (triple/double/half/quarter).

    Inputs are iterables of type-name strings (anything iterable converts
    cleanly to a set in the function body). Pass `defender_main_type.vulnerable_to`
    and friends straight from the SQLAlchemy Type relationships, or plain
    string lists for tests.
    """
    main_v = set(main_vuln)
    main_r = set(main_resist)

    main_is_vuln = move_type_name in main_v
    main_is_resist = move_type_name in main_r

    if sub_vuln is None and sub_resist is None:
        # Single-type defender
        if main_is_vuln:
            return 2.0
        if main_is_resist:
            return 0.5
        return 1.0

    sub_v = set(sub_vuln or [])
    sub_r = set(sub_resist or [])

    sub_is_vuln = move_type_name in sub_v
    sub_is_resist = move_type_name in sub_r

    # Both vulnerable → triple (super-effective on both halves)
    if main_is_vuln and sub_is_vuln:
        return 3.0
    # Both resistant → quarter
    if main_is_resist and sub_is_resist:
        return 0.25
    # One vuln, one resist → cancelled to neutral
    if (main_is_vuln and sub_is_resist) or (main_is_resist and sub_is_vuln):
        return 1.0
    # Exactly one half is vulnerable, the other is neutral → double
    if main_is_vuln or sub_is_vuln:
        return 2.0
    # Exactly one half resists, the other is neutral → half
    if main_is_resist or sub_is_resist:
        return 0.5
    # Both neutral → 1
    return 1.0


# ---------------------------------------------------------------------
# Status combiners
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class AttackerDeltas:
    flat_power_total: int      # additive sum of flat_power_boost
    pct_power_total: int       # additive sum of pct_power_boost
    atk_boost_total: int       # additive sum of (phy|mag)_atk_boost
    dmg_factor: float          # multiplicative ∏(1 + dmg_bonus_pct/100)


@dataclass(frozen=True)
class DefenderDeltas:
    def_boost_total: int       # additive sum of (phy|mag)_def_boost
    dmg_factor: float          # multiplicative ∏(1 - dmg_reduction_pct/100)


def combine_attacker_statuses(statuses: Sequence, *, is_magic: bool) -> AttackerDeltas:
    """Fold a list of active attacker statuses into a single deltas object.

    Stat / power boosts are SUMMED. Damage modifiers are MULTIPLIED — each
    status contributes a factor of (1 + dmg_bonus_pct/100), and they
    combine multiplicatively, not additively.

    Statuses are duck-typed: anything with the relevant attribute names
    works (SQLAlchemy Status rows, dataclass dummies in tests, etc.).
    """
    flat_power = 0
    pct_power = 0
    atk_boost = 0
    dmg_factor = 1.0
    for s in statuses:
        flat_power += s.flat_power_boost
        pct_power += s.pct_power_boost
        atk_boost += (s.mag_atk_boost if is_magic else s.phy_atk_boost)
        if s.dmg_bonus_pct:
            dmg_factor *= 1.0 + s.dmg_bonus_pct / 100
    return AttackerDeltas(flat_power, pct_power, atk_boost, dmg_factor)


def combine_defender_statuses(statuses: Sequence, *, is_magic: bool) -> DefenderDeltas:
    """Fold a list of active defender statuses into a single deltas object.

    Defense boost is SUMMED across statuses. Damage reductions are
    MULTIPLIED — each contributes a factor of (1 - dmg_reduction_pct/100).
    """
    def_boost = 0
    dmg_factor = 1.0
    for s in statuses:
        def_boost += (s.mag_def_boost if is_magic else s.phy_def_boost)
        if s.dmg_reduction_pct:
            dmg_factor *= 1.0 - s.dmg_reduction_pct / 100
    return DefenderDeltas(def_boost, dmg_factor)


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------
def compute_move_damage(
    *,
    move_power: int,
    move_type_name: str,
    is_magic: bool,
    attacker_atk: int,
    attacker_main_type: str,
    attacker_sub_type: Optional[str],
    defender_def: int,
    defender_main_vuln: Iterable[str],
    defender_main_resist: Iterable[str],
    defender_sub_vuln: Optional[Iterable[str]] = None,
    defender_sub_resist: Optional[Iterable[str]] = None,
    attacker_statuses: Sequence = (),
    defender_statuses: Sequence = (),
) -> int:
    """Compute the damage one attack-category move deals to a defender.

    Inputs are flat / primitive on purpose so this function can be unit-
    tested without any ORM. The caller (matchup orchestrator) is
    responsible for picking the right atk/def stat for the move category,
    looking up the type vulnerability lists, and passing only ACTIVE
    statuses (the user's toggle selection).

    Returns a non-negative integer. Per the formula, very negative-modifier
    cases could in principle drive the inner expression below zero —
    clamped to 0 here defensively (the game spec doesn't define negative
    damage).
    """
    a = combine_attacker_statuses(attacker_statuses, is_magic=is_magic)
    d = combine_defender_statuses(defender_statuses, is_magic=is_magic)

    power_term = round_half_up(
        (move_power + a.flat_power_total) * boost_multiplier(a.pct_power_total)
    )
    atk_term = round_half_up(attacker_atk * boost_multiplier(a.atk_boost_total))
    def_term = round_half_up(defender_def * boost_multiplier(d.def_boost_total))

    # Defensive: stat formula keeps def > 0 in practice; guard against
    # divide-by-zero on hand-crafted edge cases.
    if def_term <= 0:
        return 0

    stab = (
        1.25
        if move_type_name == attacker_main_type
        or (attacker_sub_type is not None and move_type_name == attacker_sub_type)
        else 1.0
    )

    type_eff = type_effectiveness(
        move_type_name,
        defender_main_vuln,
        defender_main_resist,
        defender_sub_vuln,
        defender_sub_resist,
    )

    inner = (
        0.9
        * power_term
        * atk_term
        / def_term
        * stab
        * type_eff
        * d.dmg_factor
        * a.dmg_factor
    )

    if inner <= 0:
        return 0
    return round_half_up(inner)
