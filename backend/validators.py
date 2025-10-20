"""Validation functions for game entities and teams."""

from typing import List
from backend import schemas
from backend.exceptions import TeamValidationError, ValidationError


def validate_team_structure(team: schemas.TeamCreate) -> None:
    """
    Validate team composition before processing.

    Args:
        team: Team data to validate

    Raises:
        TeamValidationError: If team structure is invalid
    """
    # Check team has exactly 6 monsters
    if len(team.user_monsters) != 6:
        raise TeamValidationError(
            f"Team must have exactly 6 monsters, got {len(team.user_monsters)}"
        )

    # Check for duplicate monsters (same monster_id)
    monster_ids = [um.monster_id for um in team.user_monsters]
    if len(monster_ids) != len(set(monster_ids)):
        duplicates = [mid for mid in set(monster_ids) if monster_ids.count(mid) > 1]
        raise TeamValidationError(
            f"Duplicate monsters not allowed in team: monster_id(s) {duplicates}"
        )

    # Validate each user monster
    for idx, um in enumerate(team.user_monsters, 1):
        validate_user_monster(um, position=idx)

    # Validate magic item is set
    if not team.magic_item_id or team.magic_item_id <= 0:
        raise TeamValidationError("Team must have a magic item selected")

    # Validate team name
    if not team.name or not team.name.strip():
        raise TeamValidationError("Team name cannot be empty")

    if len(team.name) > 50:
        raise TeamValidationError("Team name must be 50 characters or less")


def validate_user_monster(um: schemas.UserMonsterCreate, position: int = None) -> None:
    """
    Validate a single user monster configuration.

    Args:
        um: User monster data to validate
        position: Position in team (for error messages)

    Raises:
        ValidationError: If user monster configuration is invalid
    """
    pos_str = f" at position {position}" if position else ""

    # Check monster is selected
    if not um.monster_id or um.monster_id <= 0:
        raise ValidationError(f"Monster not selected{pos_str}")

    # Check personality is selected
    if not um.personality_id or um.personality_id <= 0:
        raise ValidationError(f"Personality not selected{pos_str}")

    # Check legacy type is selected
    if not um.legacy_type_id or um.legacy_type_id <= 0:
        raise ValidationError(f"Legacy type not selected{pos_str}")

    # Check all 4 moves are selected
    move_ids = [um.move1_id, um.move2_id, um.move3_id, um.move4_id]
    if any(mid is None or mid <= 0 for mid in move_ids):
        raise ValidationError(f"All 4 moves must be selected{pos_str}")

    # Check for duplicate moves
    if len(move_ids) != len(set(move_ids)):
        raise ValidationError(f"Duplicate moves not allowed{pos_str}")

    # Validate talent distribution
    validate_talent(um.talent, position)


def validate_talent(talent: schemas.TalentUpsert, position: int = None) -> None:
    """
    Validate talent point distribution.

    Args:
        talent: Talent data to validate
        position: Position in team (for error messages)

    Raises:
        ValidationError: If talent distribution is invalid
    """
    pos_str = f" at position {position}" if position else ""

    # Get all talent values
    talent_values = [
        talent.hp_boost,
        talent.phy_atk_boost,
        talent.mag_atk_boost,
        talent.phy_def_boost,
        talent.mag_def_boost,
        talent.spd_boost,
    ]

    # Check all values are non-negative
    if any(v < 0 for v in talent_values):
        raise ValidationError(f"Talent values must be non-negative{pos_str}")

    # Check at least one stat is boosted
    boosted_count = sum(1 for v in talent_values if v > 0)
    if boosted_count == 0:
        raise ValidationError(f"At least one talent must be set{pos_str}")

    # Check maximum of 3 stats can be boosted
    if boosted_count > 3:
        raise ValidationError(
            f"Maximum of 3 talents can be boosted, got {boosted_count}{pos_str}"
        )

    # Check each talent value doesn't exceed maximum (assuming max is 31)
    MAX_TALENT_VALUE = 31
    for v in talent_values:
        if v > MAX_TALENT_VALUE:
            raise ValidationError(
                f"Talent value cannot exceed {MAX_TALENT_VALUE}{pos_str}"
            )


def validate_team_update(team_update: schemas.TeamUpdate, team_id: int) -> None:
    """
    Validate team update data.

    Args:
        team_update: Team update data to validate
        team_id: ID of team being updated

    Raises:
        TeamValidationError: If update data is invalid
    """
    # Validate team name if provided
    if team_update.name is not None:
        if not team_update.name.strip():
            raise TeamValidationError("Team name cannot be empty")
        if len(team_update.name) > 50:
            raise TeamValidationError("Team name must be 50 characters or less")

    # Validate magic item if provided
    if team_update.magic_item_id is not None and team_update.magic_item_id <= 0:
        raise TeamValidationError("Invalid magic item ID")

    # Validate user monsters if provided
    if team_update.user_monsters is not None:
        if len(team_update.user_monsters) != 6:
            raise TeamValidationError(
                f"Team must have exactly 6 monsters, got {len(team_update.user_monsters)}"
            )

        # Validate each monster update
        for idx, um in enumerate(team_update.user_monsters, 1):
            # For updates, monster_id, personality_id, etc. might be 0 to keep existing
            # Only validate if they're being changed (> 0)
            if um.monster_id and um.monster_id > 0:
                validate_user_monster(um, position=idx)
