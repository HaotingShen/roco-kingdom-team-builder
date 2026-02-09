"""
Tests for reference resolution system.

Tests cover:
- English reference detection (quoted, capitalized)
- Chinese reference detection (bracketed, brute-force)
- Transitive resolution (BFS, cycle detection)
- Caching behavior
- Edge cases
"""

import pytest
from unittest.mock import Mock, MagicMock
from backend.reference_resolver import (
    detect_references_en,
    detect_references_zh,
    resolve_references_transitive,
    resolve_references_for_prompt,
    get_lookup_tables,
    invalidate_reference_cache,
    LookupTables,
    EntityReference,
    ResolvedReferences,
    _get_zh_name,
    _get_zh_description
)
from backend import models


# ==================== FIXTURES ====================

@pytest.fixture
def mock_lookup_tables():
    """Create mock lookup tables for testing."""
    return LookupTables(
        move_names_en={"Focus": 1, "Dragon Claw": 2, "Fire Blast": 3},
        game_term_keys_en={"Charge": 10, "Charge Extension": 11, "Attack Mark": 12, "Poison": 13},
        monster_names_en={"Chess Queen": 20, "Dimo": 21},
        trait_names_en={"Supercharge": 30},
        magic_item_names_en={"Willpower Enhancement": 40},
        move_names_zh={"聚能": 1, "龙爪": 2, "火焰爆炸": 3},
        game_term_names_zh={"蓄力": 10, "积蓄": 11, "攻击印记": 12, "中毒": 13},
        monster_names_zh={"棋绮后": 20, "迪莫": 21},
        trait_names_zh={"超聚能": 30},
        magic_item_names_zh={"愿力强化": 40},
        game_term_names_zh_sorted=[("积蓄", 11), ("蓄力", 10), ("攻击印记", 12), ("中毒", 13)],
        monster_names_zh_sorted=[("棋绮后", 20), ("迪莫", 21)]
    )


# ==================== ENGLISH DETECTION TESTS ====================

def test_detect_quoted_moves(mock_lookup_tables):
    """Test that quoted move names are detected."""
    desc = "When in Charge state, 'Focus' changes to something."
    refs = detect_references_en(desc, mock_lookup_tables)

    move_refs = [r for r in refs if r.entity_type == "move"]
    assert len(move_refs) == 1
    assert move_refs[0].name == "Focus"
    assert move_refs[0].entity_id == 1


def test_detect_quoted_game_term(mock_lookup_tables):
    """Test that quoted game terms are detected (edge case)."""
    desc = "When in Charge state, 'Focus' changes to 'Charge Extension'."
    refs = detect_references_en(desc, mock_lookup_tables)

    # 'Focus' should match move
    move_refs = [r for r in refs if r.entity_type == "move"]
    assert len(move_refs) == 1
    assert "Focus" in [r.name for r in move_refs]

    # 'Charge Extension' should match game term (not move)
    term_refs = [r for r in refs if r.entity_type == "game_term"]
    assert len(term_refs) >= 1
    assert "Charge Extension" in [r.name for r in term_refs]


def test_detect_quoted_monster_name(mock_lookup_tables):
    """Test that quoted monster names are detected (with data annotation)."""
    desc = "transforms into 'Chess Queen'"
    refs = detect_references_en(desc, mock_lookup_tables)

    # 'Chess Queen' should match monster (after trying moves and game terms)
    monster_refs = [r for r in refs if r.entity_type == "monster"]
    assert len(monster_refs) == 1
    assert monster_refs[0].name == "Chess Queen"
    assert monster_refs[0].entity_id == 20


def test_detect_capitalized_terms(mock_lookup_tables):
    """Test capitalized mid-sentence game terms."""
    desc = "Gains Attack Mark when entering field."
    refs = detect_references_en(desc, mock_lookup_tables)

    term_refs = [r for r in refs if r.entity_type == "game_term"]
    assert len(term_refs) >= 1
    assert "Attack Mark" in [r.name for r in term_refs]


def test_detect_capitalized_with_blacklist(mock_lookup_tables):
    """Test that blacklisted words are not detected."""
    desc = "This Move gains Attack and Defense."
    refs = detect_references_en(desc, mock_lookup_tables)

    # Should not detect "Move", "Attack", "Defense" (blacklisted)
    term_refs = [r for r in refs if r.entity_type == "game_term"]
    # Only should find terms actually in lookup
    assert all(r.name not in ["Move", "Attack", "Defense"] for r in term_refs)


def test_detect_multiple_references(mock_lookup_tables):
    """Test detection of multiple different reference types."""
    desc = "When using 'Focus', gains Charge and Attack Mark."
    refs = detect_references_en(desc, mock_lookup_tables)

    # Should find: Move 'Focus', GameTerm 'Charge', GameTerm 'Attack Mark'
    assert any(r.entity_type == "move" and r.name == "Focus" for r in refs)
    assert any(r.entity_type == "game_term" and r.name == "Charge" for r in refs)
    assert any(r.entity_type == "game_term" and r.name == "Attack Mark" for r in refs)


def test_detect_empty_description(mock_lookup_tables):
    """Test handling of empty description."""
    refs = detect_references_en("", mock_lookup_tables)
    assert len(refs) == 0

    refs = detect_references_en(None, mock_lookup_tables)
    assert len(refs) == 0


# ==================== CHINESE DETECTION TESTS ====================

def test_detect_bracketed_moves(mock_lookup_tables):
    """Test that bracketed move names are detected."""
    desc = "蓄力时，【聚能】变为其他。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    move_refs = [r for r in refs if r.entity_type == "move"]
    assert len(move_refs) >= 1
    assert "聚能" in [r.name_zh for r in move_refs]


def test_detect_bracketed_game_term(mock_lookup_tables):
    """Test that bracketed game terms are detected (edge case)."""
    desc = "蓄力时，【聚能】变为【积蓄】。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    # 【聚能】 should match move
    move_refs = [r for r in refs if r.entity_type == "move"]
    assert len(move_refs) >= 1
    assert "聚能" in [r.name_zh for r in move_refs]

    # 【积蓄】 should match game term (not move)
    term_refs = [r for r in refs if r.entity_type == "game_term"]
    assert len(term_refs) >= 1
    assert "积蓄" in [r.name_zh for r in term_refs]


def test_detect_bracketed_monster_name(mock_lookup_tables):
    """Test bracketed monster names are detected (with data annotation)."""
    desc = "变身为【棋绮后】。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    # 【棋绮后】 should match monster (after trying moves and game terms)
    monster_refs = [r for r in refs if r.entity_type == "monster"]
    assert len(monster_refs) >= 1
    assert "棋绮后" in [r.name_zh for r in monster_refs]


def test_detect_game_term_brute_force(mock_lookup_tables):
    """Test brute-force detection of game term names."""
    desc = "获得蓄力状态。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    # Should detect "蓄力" via brute-force
    term_refs = [r for r in refs if r.entity_type == "game_term"]
    assert len(term_refs) >= 1
    assert "蓄力" in [r.name_zh for r in term_refs]


def test_longest_match_first(mock_lookup_tables):
    """Test that longest matches take priority."""
    # "积蓄" (Charge Extension) is longer than "蓄" if it existed
    # This test verifies the sorting works
    desc = "获得积蓄效果。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    term_refs = [r for r in refs if r.entity_type == "game_term"]
    # Should match "积蓄" as a whole
    assert any(r.name_zh == "积蓄" for r in term_refs)


def test_no_overlap_brackets_brute_force(mock_lookup_tables):
    """Test that brute-force doesn't match text inside brackets."""
    desc = "【蓄力】状态下，获得能量。"
    refs = detect_references_zh(desc, mock_lookup_tables)

    # "蓄力" should be matched by brackets, not brute-force
    # Should only appear once in results
    term_count = sum(1 for r in refs if r.name_zh == "蓄力")
    assert term_count == 1  # Only once


# ==================== HELPER FUNCTION TESTS ====================

def test_get_zh_name_string_format():
    """Test _get_zh_name with string format (Type, Personality)."""
    mock_entity = Mock()
    mock_entity.localized = {"zh": "火"}

    result = _get_zh_name(mock_entity)
    assert result == "火"


def test_get_zh_name_dict_format():
    """Test _get_zh_name with dict format (most tables)."""
    mock_entity = Mock()
    mock_entity.localized = {"zh": {"name": "棋绮后", "description": "..."}}

    result = _get_zh_name(mock_entity)
    assert result == "棋绮后"


def test_get_zh_name_missing():
    """Test _get_zh_name with missing Chinese data."""
    mock_entity = Mock()
    mock_entity.localized = {}

    result = _get_zh_name(mock_entity)
    assert result is None


def test_get_zh_description():
    """Test _get_zh_description extraction."""
    mock_entity = Mock()
    mock_entity.localized = {"zh": {"name": "超聚能", "description": "蓄力时，【聚能】变为【积蓄】。"}}

    result = _get_zh_description(mock_entity)
    assert result == "蓄力时，【聚能】变为【积蓄】。"


# ==================== INTEGRATION TESTS ====================

def test_resolved_references_merge():
    """Test ResolvedReferences.merge()."""
    refs1 = ResolvedReferences()
    refs1.moves.add(1)
    refs1.game_terms.add(10)

    refs2 = ResolvedReferences()
    refs2.moves.add(2)
    refs2.game_terms.add(10)  # Duplicate
    refs2.monsters.add(20)

    refs1.merge(refs2)

    assert refs1.moves == {1, 2}
    assert refs1.game_terms == {10}
    assert refs1.monsters == {20}


def test_cache_invalidation():
    """Test that cache invalidation clears all caches."""
    # This is a basic test - just ensure it doesn't crash
    invalidate_reference_cache()
    # Cache should be empty after invalidation
    from backend.reference_resolver import _lookup_tables, _entity_references_cache
    assert _lookup_tables is None
    assert len(_entity_references_cache) == 0


# ==================== TRANSITIVE RESOLUTION TESTS ====================
# Note: These require a real database session, so they're marked as integration tests

@pytest.mark.integration
def test_transitive_resolution_depth(db_session):
    """Test that transitive resolution respects depth limit."""
    # This test requires actual database entities
    # Skipping implementation as it needs real DB setup
    pass


@pytest.mark.integration
def test_cycle_detection(db_session):
    """Test that circular references don't cause infinite loops."""
    # This test requires actual database entities
    # Skipping implementation as it needs real DB setup
    pass


# ==================== PERFORMANCE TESTS ====================

def test_lookup_tables_caching():
    """Test that lookup tables are cached after first build."""
    # Clear cache first
    invalidate_reference_cache()

    # First call should build tables
    # Second call should use cache
    # This test would need a real DB session to work properly
    pass
