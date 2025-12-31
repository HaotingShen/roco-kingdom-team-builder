"""
Prompt Logger - Records all LLM prompts for review and debugging

Saves prompts to: backend/logs/prompts/YYYY-MM-DD/HH-MM-SS-{context}.txt
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Base directory for prompt logs
PROMPT_LOG_DIR = Path(__file__).parent / "logs" / "prompts"


def save_prompt(
    prompt: str,
    system_prompt: Optional[str] = None,
    context: str = "",
    team_hash: Optional[str] = None,
    language: Optional[str] = None,
    monster_name: Optional[str] = None,
    cache_status: Optional[str] = None,
    # Token usage metadata
    prompt_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    thinking_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    cache_hit_tokens: Optional[int] = None,
    cache_miss_tokens: Optional[int] = None,
    # Performance metadata
    response_time_ms: Optional[int] = None,
    # Provider metadata
    provider: Optional[str] = None,
    model: Optional[str] = None,
    # Reasoning content (DeepSeek thinking mode)
    reasoning_content: Optional[str] = None,
    save_reasoning: bool = False,  # Set to True to save reasoning content (can be very long)
) -> Path:
    """
    Save an LLM prompt to a log file for review.

    Args:
        prompt: The user prompt content
        system_prompt: The system prompt (if separate)
        context: Short context description (e.g., "trait_synergy", "team_synergy")
        team_hash: Team hash for identification
        language: Language code (en/zh)
        monster_name: Monster name (for trait synergy prompts)
        cache_status: "HIT" or "MISS" if known
        prompt_tokens: Number of input tokens
        output_tokens: Number of output tokens
        thinking_tokens: Number of thinking tokens (Gemini extended thinking)
        total_tokens: Total tokens used
        cache_hit_tokens: Tokens retrieved from cache (DeepSeek)
        cache_miss_tokens: Tokens not in cache (DeepSeek)
        response_time_ms: API response time in milliseconds
        provider: LLM provider (gemini/deepseek)
        model: Model name used
        reasoning_content: Chain-of-thought reasoning (DeepSeek thinking mode)
        save_reasoning: Whether to save reasoning content to log file (default False)

    Returns:
        Path to the saved log file
    """
    # Create dated directory
    now = datetime.now()
    date_dir = PROMPT_LOG_DIR / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    # Build filename with metadata
    timestamp = now.strftime("%H-%M-%S")
    filename_parts = [timestamp]

    if context:
        filename_parts.append(context)
    if monster_name:
        # Sanitize monster name for filename
        safe_name = "".join(c for c in monster_name if c.isalnum() or c in ("-", "_"))
        filename_parts.append(safe_name[:30])  # Limit length
    if language:
        filename_parts.append(language)
    if cache_status:
        filename_parts.append(cache_status.lower())

    filename = "_".join(filename_parts) + ".txt"
    filepath = date_dir / filename

    # Write prompt to file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("LLM PROMPT LOG\n")
        f.write("=" * 80 + "\n\n")

        # Metadata section
        f.write("📋 METADATA\n")
        f.write("-" * 80 + "\n")
        f.write(f"Timestamp:    {now.isoformat()}\n")
        if context:
            f.write(f"Context:      {context}\n")
        if team_hash:
            f.write(f"Team Hash:    {team_hash}\n")
        if language:
            f.write(f"Language:     {language}\n")
        if monster_name:
            f.write(f"Monster:      {monster_name}\n")
        if cache_status:
            f.write(f"Cache Status: {cache_status}\n")
        if provider:
            f.write(f"Provider:     {provider}\n")
        if model:
            f.write(f"Model:        {model}\n")
        f.write("\n")

        # Token usage section
        if any([prompt_tokens, output_tokens, thinking_tokens, total_tokens, cache_hit_tokens, cache_miss_tokens]):
            f.write("💰 TOKEN USAGE\n")
            f.write("-" * 80 + "\n")
            if prompt_tokens is not None:
                f.write(f"Input Tokens:     {prompt_tokens:,}\n")
            if thinking_tokens is not None and thinking_tokens > 0:
                f.write(f"🧠 Thinking:      {thinking_tokens:,}\n")
            if output_tokens is not None:
                f.write(f"Output Tokens:    {output_tokens:,}\n")
            if total_tokens is not None:
                f.write(f"Total Tokens:     {total_tokens:,}\n")

            # DeepSeek cache breakdown
            if cache_hit_tokens is not None or cache_miss_tokens is not None:
                f.write("\nCache Breakdown:\n")
                if cache_hit_tokens is not None:
                    f.write(f"  Cache Hits:     {cache_hit_tokens:,}\n")
                if cache_miss_tokens is not None:
                    f.write(f"  Cache Misses:   {cache_miss_tokens:,}\n")
                if prompt_tokens is not None and prompt_tokens > 0:
                    hit_rate = (cache_hit_tokens / prompt_tokens * 100) if cache_hit_tokens else 0
                    f.write(f"  Hit Rate:       {hit_rate:.1f}%\n")
            f.write("\n")

        # Performance section
        if response_time_ms is not None:
            f.write("⚡ PERFORMANCE\n")
            f.write("-" * 80 + "\n")
            f.write(f"Response Time:    {response_time_ms:,} ms ({response_time_ms/1000:.2f}s)\n")
            f.write("\n")

        # Reasoning content section (DeepSeek thinking mode)
        if save_reasoning and reasoning_content:
            f.write("🧠 REASONING PROCESS (思考过程)\n")
            f.write("-" * 80 + "\n")
            f.write(reasoning_content)
            f.write("\n\n")

        # System prompt section (if provided)
        if system_prompt:
            f.write("🤖 SYSTEM PROMPT\n")
            f.write("-" * 80 + "\n")
            f.write(system_prompt)
            f.write("\n\n")

        # User prompt section
        f.write("👤 USER PROMPT\n")
        f.write("-" * 80 + "\n")
        f.write(prompt)
        f.write("\n\n")

        # Footer
        f.write("=" * 80 + "\n")
        f.write("END OF LOG\n")
        f.write("=" * 80 + "\n")

    logger.debug(f"Saved prompt log to: {filepath}")
    return filepath


def get_latest_prompts(limit: int = 10) -> list[Path]:
    """
    Get the most recent prompt log files.

    Args:
        limit: Maximum number of files to return

    Returns:
        List of file paths, sorted by modification time (newest first)
    """
    if not PROMPT_LOG_DIR.exists():
        return []

    # Get all txt files recursively
    all_files = list(PROMPT_LOG_DIR.rglob("*.txt"))

    # Sort by modification time (newest first)
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return all_files[:limit]


def clear_old_logs(days: int = 7) -> int:
    """
    Delete prompt logs older than specified days.

    Args:
        days: Delete logs older than this many days

    Returns:
        Number of files deleted
    """
    if not PROMPT_LOG_DIR.exists():
        return 0

    cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
    deleted_count = 0

    for file in PROMPT_LOG_DIR.rglob("*.txt"):
        if file.stat().st_mtime < cutoff_time:
            file.unlink()
            deleted_count += 1

    # Remove empty directories
    for directory in sorted(PROMPT_LOG_DIR.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()

    logger.info(f"Deleted {deleted_count} prompt logs older than {days} days")
    return deleted_count
