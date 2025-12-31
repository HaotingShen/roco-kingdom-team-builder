"""
Tests for offensive type coverage calculation.

These tests verify that compute_type_coverage() correctly calculates:
- Base coverage from attack moves
- Enhanced coverage when Willpower Enhancement magic item is selected
- Edge cases (no attack moves, single type, etc.)
"""

import pytest
from unittest.mock import Mock
from backend.main import compute_type_coverage
from backend import models


# Mock data builders
def mock_type(type_id, name, effective_against_ids=None, weak_against_ids=None,
              vulnerable_to_ids=None, resistant_to_ids=None):
    """Create a mock Type object with relationships"""
    typ = Mock(spec=models.Type)
    typ.id = type_id
    typ.name = name
    typ.effective_against = []
    typ.weak_against = []
    typ.vulnerable_to = []
    typ.resistant_to = []

    # Store IDs for later resolution
    typ._eff_ids = effective_against_ids or []
    typ._weak_ids = weak_against_ids or []
    typ._vuln_ids = vulnerable_to_ids or []
    typ._resist_ids = resistant_to_ids or []

    return typ


def resolve_type_relationships(type_db_map):
    """Resolve type relationships after all types are created"""
    for typ in type_db_map.values():
        typ.effective_against = [type_db_map[tid] for tid in typ._eff_ids if tid in type_db_map]
        typ.weak_against = [type_db_map[tid] for tid in typ._weak_ids if tid in type_db_map]
        typ.vulnerable_to = [type_db_map[tid] for tid in typ._vuln_ids if tid in type_db_map]
        typ.resistant_to = [type_db_map[tid] for tid in typ._resist_ids if tid in type_db_map]


def mock_move(move_id, name, move_type_id, category):
    """Create a mock Move object"""
    move = Mock(spec=models.Move)
    move.id = move_id
    move.name = name
    move.move_type_id = move_type_id
    move.move_category = category
    return move


def mock_user_monster(monster_id, move_ids, legacy_type_id=None):
    """Create a mock UserMonster object"""
    um = Mock()
    um.monster_id = monster_id
    um.move1_id, um.move2_id, um.move3_id, um.move4_id = move_ids
    um.legacy_type_id = legacy_type_id
    um.talent = Mock()
    return um


def mock_monster(monster_id):
    """Create a mock Monster object"""
    monster = Mock(spec=models.Monster)
    monster.id = monster_id
    monster.main_type_id = 1  # Fire
    monster.sub_type_id = None
    return monster


def mock_magic_item(effect_code):
    """Create a mock MagicItem object"""
    item = Mock(spec=models.MagicItem)
    item.effect_code = effect_code
    return item


class TestBasicCoverage:
    """Test basic offensive coverage calculation without magic items"""

    def test_fire_type_coverage(self):
        """Fire attacks should be SE against Grass/Ice/Bug/Mechanical, resisted by Water/Ground/Dragon"""
        # Setup types (using real type chart data)
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2, 3, 4], weak_against_ids=[5, 6, 7]),  # Fire
            2: mock_type(2, "Grass"),
            3: mock_type(3, "Ice"),
            4: mock_type(4, "Bug"),
            5: mock_type(5, "Water"),
            6: mock_type(6, "Ground"),
            7: mock_type(7, "Dragon"),
            8: mock_type(8, "Normal"),
        }
        resolve_type_relationships(type_db_map)

        # Fire attack moves
        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
            2: mock_move(2, "Fire Punch", 1, models.MoveCategory.PHY_ATTACK),
        }

        # Team with Fire moves
        user_monsters = [
            mock_user_monster(1, [1, 2, 1, 2]),
        ]

        monster_db_map = {1: mock_monster(1)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # Verify super-effective types
        assert set(result["super_effective_types"]) == {2, 3, 4}  # Grass, Ice, Bug

        # Verify resisted types
        assert set(result["resisted_types"]) == {5, 6, 7}  # Water, Ground, Dragon

        # Verify neutral types (everything else)
        assert 8 in result["neutral_types"]  # Normal

    def test_balanced_team_coverage(self):
        """Fire + Water + Grass should have excellent coverage"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2, 3], weak_against_ids=[4]),
            2: mock_type(2, "Grass", effective_against_ids=[4], weak_against_ids=[1]),
            3: mock_type(3, "Ice"),
            4: mock_type(4, "Water", effective_against_ids=[1], weak_against_ids=[2]),
            5: mock_type(5, "Dragon", weak_against_ids=[]),  # No types resist Dragon
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
            2: mock_move(2, "Hydro Pump", 4, models.MoveCategory.MAG_ATTACK),
            3: mock_move(3, "Solar Beam", 2, models.MoveCategory.MAG_ATTACK),
        }

        user_monsters = [
            mock_user_monster(1, [1, 1, 1, 1]),  # Fire moves
            mock_user_monster(2, [2, 2, 2, 2]),  # Water moves
            mock_user_monster(3, [3, 3, 3, 3]),  # Grass moves
        ]

        monster_db_map = {1: mock_monster(1), 2: mock_monster(2), 3: mock_monster(3)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # Fire resists Water, Water resists Grass, Grass resists Fire
        # So no type should be resisted by ALL attacks
        assert len(result["resisted_types"]) == 0  # Perfect coverage!

    def test_no_attack_moves(self):
        """Team with only STATUS/DEFENSE moves should have all types as resisted"""
        type_db_map = {
            1: mock_type(1, "Fire"),
            2: mock_type(2, "Water"),
            3: mock_type(3, "Grass"),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Focus", None, models.MoveCategory.STATUS),
            2: mock_move(2, "Protect", 1, models.MoveCategory.DEFENSE),
        }

        user_monsters = [
            mock_user_monster(1, [1, 2, 1, 2]),
        ]

        monster_db_map = {1: mock_monster(1)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # No attack moves → all types are "resisted"
        assert set(result["resisted_types"]) == {1, 2, 3}
        assert len(result["super_effective_types"]) == 0
        assert len(result["neutral_types"]) == 0

    def test_mixed_attack_and_status_moves(self):
        """STATUS/DEFENSE moves should be ignored in coverage calculation"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2]),
            2: mock_type(2, "Grass"),
            3: mock_type(3, "Water", weak_against_ids=[]),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
            2: mock_move(2, "Focus", None, models.MoveCategory.STATUS),
            3: mock_move(3, "Protect", 3, models.MoveCategory.DEFENSE),  # Water-type defense move
        }

        user_monsters = [
            mock_user_monster(1, [1, 2, 3, 2]),  # Fire attack + STATUS + DEFENSE
        ]

        monster_db_map = {1: mock_monster(1)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # Only Fire attack should count (Water DEFENSE move ignored)
        assert set(result["super_effective_types"]) == {2}  # Grass


class TestWillpowerEnhancement:
    """Test dual coverage when Willpower Enhancement magic item is selected"""

    def test_willpower_enhancement_adds_legacy_types(self):
        """Willpower Enhancement should add legacy types to coverage"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2], weak_against_ids=[3]),
            2: mock_type(2, "Grass"),
            3: mock_type(3, "Water", effective_against_ids=[1], weak_against_ids=[2]),
            4: mock_type(4, "Dragon"),
            5: mock_type(5, "Leader"),  # Leader type (invalid for Willpower Enhancement)
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
        }

        # Team: Fire moves, but Water legacy types
        user_monsters = [
            mock_user_monster(1, [1, 1, 1, 1], legacy_type_id=3),  # Water legacy
            mock_user_monster(2, [1, 1, 1, 1], legacy_type_id=3),  # Water legacy
        ]

        monster_db_map = {1: mock_monster(1), 2: mock_monster(2)}

        magic_item = mock_magic_item(models.MagicEffectCode.ENHANCE_SPELL)

        result = compute_type_coverage(
            user_monsters, move_db_map, monster_db_map, type_db_map,
            personality_db_map=None, magic_item=magic_item
        )

        # Base coverage: Fire only
        assert set(result["super_effective_types"]) == {2}  # Grass
        assert 3 in result["resisted_types"]  # Water resists Fire

        # Enhanced coverage: Fire + Water
        assert result["enhanced_coverage"] is not None
        enhanced = result["enhanced_coverage"]

        # Water is SE against Fire, Fire is SE against Grass
        assert 1 in enhanced["super_effective_types"]  # Fire (from Water)
        assert 2 in enhanced["super_effective_types"]  # Grass (from Fire)

        # Water is resisted by Grass, Fire is resisted by Water
        # But since we have both, neither should be resisted
        # (Fire covers Water's weakness, Water covers Fire's weakness)
        assert 2 not in enhanced["resisted_types"]
        assert 3 not in enhanced["resisted_types"]

    def test_willpower_enhancement_ignores_leader_legacy(self):
        """Willpower Enhancement should ignore Leader legacy type"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2]),
            2: mock_type(2, "Grass"),
            3: mock_type(3, "Leader"),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
        }

        user_monsters = [
            mock_user_monster(1, [1, 1, 1, 1], legacy_type_id=3),  # Leader legacy (should be ignored)
        ]

        monster_db_map = {1: mock_monster(1)}

        magic_item = mock_magic_item(models.MagicEffectCode.ENHANCE_SPELL)

        result = compute_type_coverage(
            user_monsters, move_db_map, monster_db_map, type_db_map,
            personality_db_map=None, magic_item=magic_item
        )

        # Enhanced coverage should be same as base (Leader legacy ignored)
        assert result["enhanced_coverage"]["super_effective_types"] == result["super_effective_types"]
        assert result["enhanced_coverage"]["resisted_types"] == result["resisted_types"]

    def test_no_enhanced_coverage_without_willpower_enhancement(self):
        """Other magic items should not trigger enhanced coverage"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2]),
            2: mock_type(2, "Grass"),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
        }

        user_monsters = [
            mock_user_monster(1, [1, 1, 1, 1], legacy_type_id=2),
        ]

        monster_db_map = {1: mock_monster(1)}

        # Different magic item (not Willpower Enhancement)
        magic_item = mock_magic_item(models.MagicEffectCode.SUN_HEALING)

        result = compute_type_coverage(
            user_monsters, move_db_map, monster_db_map, type_db_map,
            personality_db_map=None, magic_item=magic_item
        )

        # Should not have enhanced coverage (key might not exist or be None)
        assert result.get("enhanced_coverage") is None


class TestEdgeCases:
    """Test edge cases and special scenarios"""

    def test_single_type_coverage(self):
        """Team with all same-type moves"""
        type_db_map = {
            1: mock_type(1, "Electric", effective_against_ids=[2, 3], weak_against_ids=[4]),
            2: mock_type(2, "Water"),
            3: mock_type(3, "Flying"),
            4: mock_type(4, "Ground"),
            5: mock_type(5, "Dragon"),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Thunderbolt", 1, models.MoveCategory.MAG_ATTACK),
        }

        user_monsters = [
            mock_user_monster(i, [1, 1, 1, 1]) for i in range(1, 7)
        ]

        monster_db_map = {i: mock_monster(i) for i in range(1, 7)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # Electric is SE against Water/Flying, resisted by Ground
        assert set(result["super_effective_types"]) == {2, 3}
        assert 4 in result["resisted_types"]
        assert 5 in result["neutral_types"]  # Dragon is neutral

    def test_backward_compatibility_fields(self):
        """Verify deprecated fields are populated for backward compatibility"""
        type_db_map = {
            1: mock_type(1, "Fire", effective_against_ids=[2], weak_against_ids=[3]),
            2: mock_type(2, "Grass"),
            3: mock_type(3, "Water"),
        }
        resolve_type_relationships(type_db_map)

        move_db_map = {
            1: mock_move(1, "Flamethrower", 1, models.MoveCategory.MAG_ATTACK),
        }

        user_monsters = [mock_user_monster(1, [1, 1, 1, 1])]
        monster_db_map = {1: mock_monster(1)}

        result = compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map)

        # Deprecated fields should match new fields
        assert result["effective_against_types"] == result["super_effective_types"]
        assert result["weak_against_types"] == result["resisted_types"]
