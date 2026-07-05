"""
Regression tests for the 2026-07 analysis-system review fixes.

Covers:
- /team/analyze_by_id ownership enforcement (was an IDOR: any caller could
  read any team's full composition by numeric ID)
- TeamUpdate/TalentUpsert validation parity with the create path
- compute_effective_stats exact half-up rounding at .5 boundaries
- Willpower-aware team cache keys
- Strict 401 on optional-auth endpoints when a bad token is presented
"""

import pytest
from pydantic import ValidationError

from backend import models, schemas
from backend.auth import create_access_token
from backend.main import (
    compute_effective_stats,
    generate_team_cache_key,
)
from backend.tests.conftest import TestingSessionLocal


class Dummy:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# Build users and teams directly in the DB and mint tokens, rather than hitting
# /auth/guest. The guest-creation endpoint is rate-limited per IP (2/day) via
# Redis, which is live in CI — creating several guests on the shared test IP
# 429s. The ownership checks under test run BEFORE any Redis rate-limit code,
# so DB-direct setup makes them deterministic regardless of Redis state.
_uid = [1000]


def _create_user(is_guest: bool = True) -> tuple[int, dict]:
    """Insert a User row and return (id, auth_headers). CSRF isn't required in
    tests (COOKIE_SAMESITE defaults to 'lax')."""
    db = TestingSessionLocal()
    try:
        _uid[0] += 1
        uname = f"owner_{_uid[0]}"
        user = models.User(
            username=uname,
            canonical_username=uname,
            is_guest=is_guest,
            is_active=True,
            token_version=0,
            subscription_tier="guest" if is_guest else "free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(user.id, user.username, is_guest, user.token_version)
        return user.id, {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def _create_team_row(owner_id: int, name: str = "Victim Team", is_featured: bool = False) -> int:
    """Insert a bare Team row directly (SQLite doesn't enforce the FKs we skip)."""
    db = TestingSessionLocal()
    try:
        team = models.Team(name=name, owner_id=owner_id, is_featured=is_featured)
        db.add(team)
        db.commit()
        db.refresh(team)
        return team.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# /team/analyze_by_id ownership
# ---------------------------------------------------------------------------

class TestAnalyzeByIdOwnership:
    def test_anonymous_cannot_analyze_private_team(self, client):
        owner_id, _ = _create_user()
        team_id = _create_team_row(owner_id=owner_id)

        # No auth header and no device cookie → truly anonymous, so
        # find_device_owner can't map back to the owner.
        client.cookies.clear()
        resp = client.post("/team/analyze_by_id", json={"team_id": team_id, "language": "en"})
        assert resp.status_code == 403

    def test_other_user_cannot_analyze_private_team(self, client):
        owner_id, _ = _create_user()
        team_id = _create_team_row(owner_id=owner_id)

        _, other_headers = _create_user()
        client.cookies.clear()
        resp = client.post(
            "/team/analyze_by_id",
            json={"team_id": team_id, "language": "en"},
            headers=other_headers,
        )
        assert resp.status_code == 403

    def test_unknown_team_is_404(self, client):
        _, headers = _create_user()
        client.cookies.clear()
        resp = client.post(
            "/team/analyze_by_id",
            json={"team_id": 999999, "language": "en"},
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update-path validation parity
# ---------------------------------------------------------------------------

def _upsert_monster(i: int = 1) -> dict:
    return {
        "monster_id": i,
        "personality_id": 1,
        "legacy_type_id": 1,
        "move1_id": 1, "move2_id": 2, "move3_id": 3, "move4_id": 4,
        "talent": {"hp_boost": 10, "phy_atk_boost": 0, "mag_atk_boost": 0,
                   "phy_def_boost": 0, "mag_def_boost": 0, "spd_boost": 0},
    }


class TestTeamUpdateValidation:
    def test_rejects_fewer_than_six_monsters(self):
        with pytest.raises(ValidationError):
            schemas.TeamUpdate(name="x", user_monsters=[_upsert_monster(i) for i in range(3)])

    def test_rejects_more_than_six_monsters(self):
        with pytest.raises(ValidationError):
            schemas.TeamUpdate(name="x", user_monsters=[_upsert_monster(i) for i in range(9)])

    def test_accepts_exactly_six_monsters(self):
        team = schemas.TeamUpdate(name="x", user_monsters=[_upsert_monster(i) for i in range(6)])
        assert len(team.user_monsters) == 6

    def test_talent_upsert_rejects_illegal_boost_value(self):
        with pytest.raises(ValidationError):
            schemas.TalentUpsert(hp_boost=5)  # only {0,7,8,9,10} allowed

    def test_talent_upsert_rejects_zero_boosted_stats(self):
        with pytest.raises(ValidationError):
            schemas.TalentUpsert()  # at least 1 stat must be boosted

    def test_talent_upsert_rejects_four_boosted_stats(self):
        with pytest.raises(ValidationError):
            schemas.TalentUpsert(hp_boost=10, phy_atk_boost=10, mag_atk_boost=10, spd_boost=10)


# ---------------------------------------------------------------------------
# Exact half-up rounding at .5 boundaries
# ---------------------------------------------------------------------------

class TestEffectiveStatsRoundingBoundary:
    """The old float pipeline built 235.4999... for exact 235.5 boundaries and
    rounded DOWN; the game rounds half up. These bases sit exactly on .5."""

    def test_non_hp_stat_half_up_at_boundary(self):
        # (2*205)*0.55 + 10 = 235.5 -> 236 (float math gave 235)
        monster = Dummy(base_hp=100, base_phy_atk=205, base_mag_atk=100,
                        base_phy_def=100, base_mag_def=100, base_spd=100)
        talent = Dummy(hp_boost=0, phy_atk_boost=0, mag_atk_boost=0,
                       phy_def_boost=0, mag_def_boost=0, spd_boost=0)
        personality = Dummy(hp_mod_pct=0, phy_atk_mod_pct=0, mag_atk_mod_pct=0,
                            phy_def_mod_pct=0, mag_def_mod_pct=0, spd_mod_pct=0)
        stats = compute_effective_stats(monster, personality, talent)
        assert stats.phy_atk == 236 + 50  # inner 236, +50 final

    def test_hp_half_up_at_boundary(self):
        # (2*105)*0.85 + 70 = 248.5 -> 249 (float math gave 248)
        monster = Dummy(base_hp=105, base_phy_atk=100, base_mag_atk=100,
                        base_phy_def=100, base_mag_def=100, base_spd=100)
        talent = Dummy(hp_boost=0, phy_atk_boost=0, mag_atk_boost=0,
                       phy_def_boost=0, mag_def_boost=0, spd_boost=0)
        personality = Dummy(hp_mod_pct=0, phy_atk_mod_pct=0, mag_atk_mod_pct=0,
                            phy_def_mod_pct=0, mag_def_mod_pct=0, spd_mod_pct=0)
        stats = compute_effective_stats(monster, personality, talent)
        assert stats.hp == 249 + 100

    def test_personality_mod_applied_exactly(self):
        # inner 236 * 1.15 + 50 = 321.4 -> 321; exercises Decimal(str(mod))
        monster = Dummy(base_hp=100, base_phy_atk=205, base_mag_atk=100,
                        base_phy_def=100, base_mag_def=100, base_spd=100)
        talent = Dummy(hp_boost=0, phy_atk_boost=0, mag_atk_boost=0,
                       phy_def_boost=0, mag_def_boost=0, spd_boost=0)
        personality = Dummy(hp_mod_pct=0, phy_atk_mod_pct=0.15, mag_atk_mod_pct=0,
                            phy_def_mod_pct=0, mag_def_mod_pct=0, spd_mod_pct=0)
        stats = compute_effective_stats(monster, personality, talent)
        assert stats.phy_atk == 321


# ---------------------------------------------------------------------------
# Willpower-aware team cache keys
# ---------------------------------------------------------------------------

def _team_create(monster_order=None) -> schemas.TeamCreate:
    order = monster_order or [1, 2, 3, 4, 5, 6]
    return schemas.TeamCreate(
        name="Key Test",
        magic_item_id=1,
        user_monsters=[
            schemas.UserMonsterCreate(
                monster_id=mid,
                personality_id=1,
                legacy_type_id=mid,  # distinct legacies keep sort alignment honest
                move1_id=1, move2_id=2, move3_id=3, move4_id=4,
                talent=schemas.TalentIn(hp_boost=10),
            )
            for mid in order
        ],
    )


class TestWillpowerCacheKey:
    def test_willpower_signature_changes_key(self):
        team = _team_create()
        base_key = generate_team_cache_key(team, "en")
        wp_key = generate_team_cache_key(team, "en", ["P"] * 6)
        assert base_key != wp_key

    def test_different_categories_produce_different_keys(self):
        team = _team_create()
        assert generate_team_cache_key(team, "en", ["P"] * 6) != \
               generate_team_cache_key(team, "en", ["M"] * 6)

    def test_key_stable_under_monster_reordering(self):
        cats = ["P", "M", "P", "M", "P", "M"]
        team_a = _team_create([1, 2, 3, 4, 5, 6])
        # Reverse the monsters AND their aligned categories — same team, same key
        team_b = _team_create([6, 5, 4, 3, 2, 1])
        assert generate_team_cache_key(team_a, "en", cats) == \
               generate_team_cache_key(team_b, "en", list(reversed(cats)))


# ---------------------------------------------------------------------------
# Strict 401 when a bad token is presented on optional-auth endpoints
# ---------------------------------------------------------------------------

class TestOptionalAuthStrictness:
    def test_quota_with_garbage_token_is_401(self, client):
        resp = client.get("/auth/quota", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_quota_without_token_is_anonymous_200(self, client):
        client.cookies.clear()
        resp = client.get("/auth/quota")
        assert resp.status_code == 200
        assert resp.json()["is_anonymous"] is True
