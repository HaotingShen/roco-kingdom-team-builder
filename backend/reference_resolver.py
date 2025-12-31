"""
Intelligent reference resolution for LLM prompts.

Detects and resolves references in trait/move/game term descriptions,
supporting both English and Chinese with transitive resolution.

Key Features:
- English: Single quotes for moves/terms/monsters, capitalized mid-sentence for game terms
- Chinese: 【】brackets for moves/terms/monsters, brute-force for game terms
- Transitive resolution with BFS traversal
- Multi-level caching for performance
"""

from dataclasses import dataclass, field
from typing import Set, Dict, List, Tuple, Optional, Union, Any
from collections import deque
import re
import logging
from sqlalchemy.orm import Session
from backend import models

logger = logging.getLogger(__name__)

# Constants
MAX_DEPTH = 3  # Maximum depth for transitive resolution
CACHE_TTL = 3600  # 1 hour in seconds

# Common English words to blacklist (not game terms)
ENGLISH_BLACKLIST = {
    "Attack", "Defense", "Speed", "HP", "Type", "Move", "Moves",
    "Physical", "Magic", "Special", "Normal", "Power", "Energy",
    "Damage", "Turn", "Turns", "Field", "Team", "Enemy", "Opponent",
    "Monster", "Monsters", "When", "After", "Before", "While", "During",
    "If", "Then", "Else", "Can", "Cannot", "All", "Each", "Every",
    "This", "That", "These", "Those", "The", "A", "An", "And", "Or",
    "But", "Not", "Is", "Are", "Was", "Were", "Be", "Been", "Being"
}


@dataclass
class EntityReference:
    """Represents a single entity reference."""
    entity_type: str  # "move", "game_term", "monster", "trait"
    entity_id: int
    name: str  # English name or key
    name_zh: Optional[str] = None  # Chinese name (if available)


@dataclass
class ResolvedReferences:
    """Container for all resolved entity references."""
    moves: Set[int] = field(default_factory=set)  # Set of move IDs
    game_terms: Set[int] = field(default_factory=set)  # Set of game term IDs
    monsters: Set[int] = field(default_factory=set)  # Set of monster IDs
    traits: Set[int] = field(default_factory=set)  # Set of trait IDs

    def merge(self, other: 'ResolvedReferences') -> None:
        """Merge another ResolvedReferences into this one."""
        self.moves.update(other.moves)
        self.game_terms.update(other.game_terms)
        self.monsters.update(other.monsters)
        self.traits.update(other.traits)


@dataclass
class LookupTables:
    """Precomputed lookup tables for efficient reference detection."""
    # English lookups
    move_names_en: Dict[str, int]  # "Focus" -> move_id
    game_term_keys_en: Dict[str, int]  # "Charge" -> game_term_id
    monster_names_en: Dict[str, int]  # "Chess Queen" -> monster_id
    trait_names_en: Dict[str, int]  # "Supercharge" -> trait_id

    # Chinese lookups
    move_names_zh: Dict[str, int]  # "聚能" -> move_id
    game_term_names_zh: Dict[str, int]  # "蓄力" -> game_term_id
    monster_names_zh: Dict[str, int]  # "棋绮后" -> monster_id
    trait_names_zh: Dict[str, int]  # "超聚能" -> trait_id

    # Sorted lists for longest-match-first (Chinese brute-force)
    game_term_names_zh_sorted: List[Tuple[str, int]]  # [(name, id), ...] sorted by length desc
    monster_names_zh_sorted: List[Tuple[str, int]]  # For fallback if needed


# Module-level cache
_lookup_tables: Optional[LookupTables] = None
_entity_references_cache: Dict[str, ResolvedReferences] = {}


# ==================== PUBLIC API ====================

def resolve_references_for_prompt(
    entities: List[Union[models.Trait, models.Move, models.GameTerm]],
    language: str,
    db: Session
) -> ResolvedReferences:
    """
    Resolve all transitive references for a list of entities.

    Main entry point for prompt building. Combines results from all entities.

    Args:
        entities: List of entities (Trait, Move, GameTerm objects) to analyze
        language: "en" or "zh"
        db: SQLAlchemy session

    Returns:
        ResolvedReferences containing all referenced entity IDs
    """
    logger.debug(f"Resolving references for {len(entities)} entities in language={language}")

    # Get or build lookup tables
    lookup = get_lookup_tables(db)

    # Accumulate all resolved references
    combined = ResolvedReferences()

    for entity in entities:
        resolved = resolve_references_transitive(entity, language, db, lookup)
        combined.merge(resolved)

    logger.debug(f"Total resolved: {len(combined.moves)} moves, {len(combined.game_terms)} terms, "
                 f"{len(combined.monsters)} monsters, {len(combined.traits)} traits")

    return combined


def invalidate_reference_cache():
    """Clear all reference caches. Call after data import."""
    global _lookup_tables, _entity_references_cache
    _lookup_tables = None
    _entity_references_cache.clear()
    logger.info("Reference resolver caches cleared")


# ==================== LOOKUP TABLES ====================

def get_lookup_tables(db: Session) -> LookupTables:
    """Build or retrieve cached lookup tables."""
    global _lookup_tables

    if _lookup_tables is not None:
        return _lookup_tables

    logger.info("Building lookup tables for reference resolution...")

    # Load all entities from database
    moves = db.query(models.Move).all()
    game_terms = db.query(models.GameTerm).all()
    monsters = db.query(models.Monster).all()
    traits = db.query(models.Trait).all()

    # Build English lookups
    move_names_en = {}
    for m in moves:
        if m.name:
            move_names_en[m.name] = m.id

    game_term_keys_en = {}
    for gt in game_terms:
        if gt.key:
            game_term_keys_en[gt.key] = gt.id

    monster_names_en = {}
    for mon in monsters:
        if mon.name:
            monster_names_en[mon.name] = mon.id

    trait_names_en = {}
    for tr in traits:
        if tr.name:
            trait_names_en[tr.name] = tr.id

    # Build Chinese lookups
    move_names_zh = {}
    for m in moves:
        zh_name = _get_zh_name(m)
        if zh_name:
            move_names_zh[zh_name] = m.id

    game_term_names_zh = {}
    for gt in game_terms:
        zh_name = _get_zh_name(gt)
        if zh_name:
            game_term_names_zh[zh_name] = gt.id

    monster_names_zh = {}
    for mon in monsters:
        zh_name = _get_zh_name(mon)
        if zh_name:
            monster_names_zh[zh_name] = mon.id

    trait_names_zh = {}
    for tr in traits:
        zh_name = _get_zh_name(tr)
        if zh_name:
            trait_names_zh[zh_name] = tr.id

    # Build sorted lists for longest-match-first
    game_term_names_zh_sorted = sorted(
        game_term_names_zh.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )

    monster_names_zh_sorted = sorted(
        monster_names_zh.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )

    _lookup_tables = LookupTables(
        move_names_en=move_names_en,
        game_term_keys_en=game_term_keys_en,
        monster_names_en=monster_names_en,
        trait_names_en=trait_names_en,
        move_names_zh=move_names_zh,
        game_term_names_zh=game_term_names_zh,
        monster_names_zh=monster_names_zh,
        trait_names_zh=trait_names_zh,
        game_term_names_zh_sorted=game_term_names_zh_sorted,
        monster_names_zh_sorted=monster_names_zh_sorted
    )

    logger.info(f"Lookup tables built: {len(move_names_en)} EN moves, {len(game_term_keys_en)} EN terms, "
                f"{len(move_names_zh)} ZH moves, {len(game_term_names_zh)} ZH terms")

    return _lookup_tables


def _get_zh_name(entity: Any) -> Optional[str]:
    """Extract Chinese name from entity's localized field."""
    if not hasattr(entity, 'localized') or not entity.localized:
        return None

    zh_data = entity.localized.get('zh')
    if not zh_data:
        return None

    # Format 1: Simple string (Type, Personality)
    if isinstance(zh_data, str):
        return zh_data

    # Format 2: Dict with name key (most tables)
    if isinstance(zh_data, dict):
        return zh_data.get('name')

    return None


def _get_zh_description(entity: Any) -> Optional[str]:
    """Extract Chinese description from entity's localized field."""
    if not hasattr(entity, 'localized') or not entity.localized:
        return None

    zh_data = entity.localized.get('zh')
    if not zh_data:
        return None

    if isinstance(zh_data, dict):
        return zh_data.get('description')

    return None


# ==================== REFERENCE DETECTION ====================

def detect_references_en(description: str, lookup: LookupTables) -> List[EntityReference]:
    """
    Detect references in English description.

    Patterns:
    1. Single quotes (e.g., 'Focus') - check moves, game terms, monsters in order
    2. Capitalized mid-sentence (e.g., "Charge state") - check game terms only

    Args:
        description: English text to analyze
        lookup: Precomputed lookup tables

    Returns:
        List of EntityReference objects
    """
    if not description:
        return []

    refs = []

    # Pattern 1: Single quotes (priority cascade: moves -> game terms -> monsters)
    # Use negative lookbehind to avoid matching possessive apostrophes like "opponent's"
    # Pattern: match quotes that are NOT preceded by alphanumeric (possessive/contraction)
    quoted_pattern = r"(?<![a-zA-Z0-9])'([^']+)'(?![a-zA-Z0-9])"
    for match in re.finditer(quoted_pattern, description):
        text = match.group(1)

        # Try move first
        if text in lookup.move_names_en:
            refs.append(EntityReference(
                entity_type="move",
                entity_id=lookup.move_names_en[text],
                name=text
            ))
        # Then game term
        elif text in lookup.game_term_keys_en:
            refs.append(EntityReference(
                entity_type="game_term",
                entity_id=lookup.game_term_keys_en[text],
                name=text
            ))
        # Finally monster
        elif text in lookup.monster_names_en:
            refs.append(EntityReference(
                entity_type="monster",
                entity_id=lookup.monster_names_en[text],
                name=text
            ))
        else:
            logger.warning(f"Quoted text '{text}' not found in any lookup table")

    # Pattern 2: Capitalized mid-sentence (game terms only)
    # Split by sentences and check non-first words
    sentences = description.split('. ')
    matched_positions = set()  # Track which words we've already matched

    for sentence in sentences:
        words = sentence.split()
        for i, word in enumerate(words):
            # Skip first word (sentence start)
            if i == 0:
                continue

            # Skip if this position already matched as part of a multi-word term
            if i in matched_positions:
                continue

            # Check if capitalized
            if not word or not word[0].isupper():
                continue

            # Check for multi-word game terms first (e.g., "Attack Mark")
            # Try 3-word, 2-word, then 1-word phrases
            matched = False
            for phrase_len in [3, 2, 1]:
                if i + phrase_len > len(words):
                    continue

                phrase_words = words[i:i+phrase_len]
                phrase = ' '.join(phrase_words)
                clean_phrase = phrase.strip('.,;:!?()[]{}')

                if clean_phrase in lookup.game_term_keys_en:
                    # Skip if already added
                    if not any(r.name == clean_phrase for r in refs):
                        refs.append(EntityReference(
                            entity_type="game_term",
                            entity_id=lookup.game_term_keys_en[clean_phrase],
                            name=clean_phrase
                        ))
                        # Mark all words in this phrase as matched
                        for j in range(i, i + phrase_len):
                            matched_positions.add(j)
                        matched = True
                    break

            # If no match found and it's a single word, check blacklist
            if not matched and phrase_len == 1:
                clean_word = word.strip('.,;:!?()[]{}')
                if clean_word in ENGLISH_BLACKLIST:
                    continue  # Skip blacklisted single words

    return refs


def detect_references_zh(description: str, lookup: LookupTables) -> List[EntityReference]:
    """
    Detect references in Chinese description.

    Patterns:
    1. Brackets【】(e.g., 【聚能】) - check moves, game terms, monsters in order
    2. Brute-force substring matching - check game terms (sorted longest first)

    Args:
        description: Chinese text to analyze
        lookup: Precomputed lookup tables

    Returns:
        List of EntityReference objects
    """
    if not description:
        return []

    refs = []
    matched_spans = set()  # Track matched positions to avoid duplicates

    # Pattern 1: Brackets【】(priority cascade: moves -> game terms -> monsters)
    bracket_pattern = r"【([^】]+)】"
    for match in re.finditer(bracket_pattern, description):
        text = match.group(1)
        start, end = match.span()
        matched_spans.add((start, end))

        # Try move first
        if text in lookup.move_names_zh:
            refs.append(EntityReference(
                entity_type="move",
                entity_id=lookup.move_names_zh[text],
                name=text,
                name_zh=text
            ))
        # Then game term
        elif text in lookup.game_term_names_zh:
            refs.append(EntityReference(
                entity_type="game_term",
                entity_id=lookup.game_term_names_zh[text],
                name=text,
                name_zh=text
            ))
        # Finally monster
        elif text in lookup.monster_names_zh:
            refs.append(EntityReference(
                entity_type="monster",
                entity_id=lookup.monster_names_zh[text],
                name=text,
                name_zh=text
            ))
        else:
            logger.warning(f"Bracketed text 【{text}】 not found in any lookup table")

    # Pattern 2: Brute-force game term matching (longest first)
    for term_name, term_id in lookup.game_term_names_zh_sorted:
        # Find all occurrences
        start_idx = 0
        while True:
            idx = description.find(term_name, start_idx)
            if idx == -1:
                break

            end_idx = idx + len(term_name)

            # Check if this span overlaps with brackets
            overlaps = any(
                (idx >= s and idx < e) or (end_idx > s and end_idx <= e)
                for s, e in matched_spans
            )

            if not overlaps:
                # Check if already added
                if not any(r.name_zh == term_name for r in refs):
                    refs.append(EntityReference(
                        entity_type="game_term",
                        entity_id=term_id,
                        name=term_name,
                        name_zh=term_name
                    ))
                    matched_spans.add((idx, end_idx))
                    break  # Only match once per term

            start_idx = end_idx

    return refs


# ==================== TRANSITIVE RESOLUTION ====================

def resolve_references_transitive(
    entity: Union[models.Trait, models.Move, models.GameTerm, models.Monster],
    language: str,
    db: Session,
    lookup: LookupTables
) -> ResolvedReferences:
    """
    BFS-based transitive resolution with cycle detection.

    Resolves all references for an entity, following reference chains up to MAX_DEPTH.

    Args:
        entity: Starting entity (Trait, Move, GameTerm, or Monster)
        language: "en" or "zh"
        db: SQLAlchemy session
        lookup: Precomputed lookup tables

    Returns:
        ResolvedReferences containing all transitively referenced entity IDs
    """
    # Check cache first
    cache_key = f"refs:{entity.__class__.__name__}:{entity.id}:{language}"
    if cache_key in _entity_references_cache:
        logger.debug(f"Cache HIT for {cache_key}")
        return _entity_references_cache[cache_key]

    logger.debug(f"Cache MISS for {cache_key}, resolving...")

    # Initialize BFS
    visited = set()  # (entity_type, entity_id)
    queue = deque([(entity.__class__.__name__, entity.id, 0)])  # (type, id, depth)
    result = ResolvedReferences()

    while queue:
        entity_type, entity_id, depth = queue.popleft()

        # Depth limit
        if depth > MAX_DEPTH:
            continue

        # Cycle detection
        if (entity_type, entity_id) in visited:
            continue
        visited.add((entity_type, entity_id))

        # Load entity from database
        entity_obj = _load_entity(entity_type, entity_id, db)
        if not entity_obj:
            logger.warning(f"Entity not found: {entity_type} ID={entity_id}")
            continue

        # Get description
        description = _get_description(entity_obj, language)
        if not description:
            continue

        # Detect direct references
        refs = []
        if language == "zh":
            refs = detect_references_zh(description, lookup)
        else:
            refs = detect_references_en(description, lookup)

        logger.debug(f"{entity_type} ID={entity_id} depth={depth}: found {len(refs)} references")

        # Add to result and queue
        for ref in refs:
            if ref.entity_type == "move":
                result.moves.add(ref.entity_id)
                queue.append(("Move", ref.entity_id, depth + 1))
            elif ref.entity_type == "game_term":
                result.game_terms.add(ref.entity_id)
                queue.append(("GameTerm", ref.entity_id, depth + 1))
            elif ref.entity_type == "monster":
                result.monsters.add(ref.entity_id)
                queue.append(("Monster", ref.entity_id, depth + 1))
            elif ref.entity_type == "trait":
                result.traits.add(ref.entity_id)
                queue.append(("Trait", ref.entity_id, depth + 1))

    # Cache result
    _entity_references_cache[cache_key] = result

    return result


def _load_entity(entity_type: str, entity_id: int, db: Session) -> Optional[Any]:
    """Load entity from database by type and ID."""
    if entity_type == "Move":
        return db.query(models.Move).filter(models.Move.id == entity_id).first()
    elif entity_type == "GameTerm":
        return db.query(models.GameTerm).filter(models.GameTerm.id == entity_id).first()
    elif entity_type == "Monster":
        return db.query(models.Monster).filter(models.Monster.id == entity_id).first()
    elif entity_type == "Trait":
        return db.query(models.Trait).filter(models.Trait.id == entity_id).first()
    else:
        logger.error(f"Unknown entity type: {entity_type}")
        return None


def _get_description(entity: Any, language: str) -> Optional[str]:
    """Extract description from entity based on language."""
    if language == "zh":
        return _get_zh_description(entity)
    else:
        # English description is in the base 'description' field
        return getattr(entity, 'description', None)
