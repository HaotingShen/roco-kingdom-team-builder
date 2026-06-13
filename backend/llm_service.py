"""
LLM Service Abstraction Layer

Provides unified interface for multiple LLM providers:
- Google Gemini (testing - free tier)
- DeepSeek Official API (production - for China access)
"""

from typing import Optional, Dict, Any, Callable
import json
import logging
import time
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI
from backend.config import (
    LLM_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_THINKING_BUDGET,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT,
    DEEPSEEK_THINKING_ENABLED,
    DEEPSEEK_REASONING_EFFORT,
    ANALYSIS_TEMPERATURE,
    ANALYSIS_MAX_TOKENS,
)
from backend.prompt_logger import save_prompt

logger = logging.getLogger(__name__)


def build_deepseek_request_kwargs(
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    thinking_enabled: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the kwargs for a DeepSeek chat.completions.create call.

    Pure function (no network) so the request-shaping logic is unit-testable.

    Thinking mode:
      - DeepSeek-V4 (deepseek-v4-flash / deepseek-v4-pro): thinking is a request
        parameter passed via extra_body; reasoning_effort goes in extra_body too
        (kept out of the top-level kwarg to avoid coupling to the OpenAI SDK's
        ReasoningEffort Literal, which does not include "max").
      - Legacy deepseek-reasoner: thinks implicitly; rejects temperature.
      - Legacy deepseek-chat: non-thinking; accepts temperature.

    Temperature is honored ONLY when thinking is not active (thinking mode ignores
    it; legacy reasoner errors on it), preserving the prior behavior for legacy names.
    """
    if thinking_enabled is None:
        thinking_enabled = DEEPSEEK_THINKING_ENABLED
    if reasoning_effort is None:
        reasoning_effort = DEEPSEEK_REASONING_EFFORT

    is_v4 = model.startswith("deepseek-v4")

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},  # Force JSON output
    }

    if is_v4:
        extra_body: Dict[str, Any] = {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
        }
        if thinking_enabled:
            extra_body["reasoning_effort"] = reasoning_effort
        kwargs["extra_body"] = extra_body

    thinking_active = thinking_enabled if is_v4 else ("reasoner" in model.lower())
    if not thinking_active:
        kwargs["temperature"] = temperature

    return kwargs


class LLMClient:
    """Unified LLM client supporting multiple providers."""

    def __init__(self, provider: Optional[str] = None):
        """
        Initialize LLM client.

        Args:
            provider: Override default provider (gemini, deepseek)
        """
        self.provider = provider or LLM_PROVIDER
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the appropriate client based on provider."""
        if self.provider == "gemini":
            self._client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info(f"Initialized Gemini client (model: {GEMINI_MODEL})")

        elif self.provider == "deepseek":
            self._client = AsyncOpenAI(
                base_url="https://api.deepseek.com",
                api_key=DEEPSEEK_API_KEY,
                timeout=DEEPSEEK_TIMEOUT,
            )
            logger.info(f"Initialized DeepSeek client (model: {DEEPSEEK_MODEL})")

        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Generate JSON response from LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system message
            temperature: Sampling temperature (0.0-2.0), defaults to ANALYSIS_TEMPERATURE
            max_tokens: Maximum tokens to generate, defaults to ANALYSIS_MAX_TOKENS

        Returns:
            Tuple of (parsed JSON response, metadata dictionary)

        Raises:
            Exception: If LLM call fails
        """
        # Use default values if not specified
        if temperature is None:
            temperature = ANALYSIS_TEMPERATURE
        if max_tokens is None:
            max_tokens = ANALYSIS_MAX_TOKENS

        if self.provider == "gemini":
            return await self._generate_gemini(prompt, system_prompt)
        else:
            return await self._generate_openai_compatible(
                prompt, system_prompt, temperature, max_tokens
            )

    async def _generate_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Call Gemini API with thinking mode enabled. Returns (result, metadata)."""
        # Gemini uses single prompt with system context prepended
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        # Enable thinking mode with configurable budget
        resp = await self._client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(
                    thinking_budget=GEMINI_THINKING_BUDGET
                )
            ),
        )

        # Extract usage metadata
        metadata = {
            'provider': 'gemini',
            'model': GEMINI_MODEL,
            'prompt_tokens': 0,
            'output_tokens': 0,
            'thinking_tokens': 0,
            'total_tokens': 0,
        }

        if hasattr(resp, 'usage_metadata'):
            usage = resp.usage_metadata
            metadata['prompt_tokens'] = getattr(usage, 'prompt_token_count', 0)
            metadata['output_tokens'] = getattr(usage, 'candidates_token_count', 0)
            metadata['thinking_tokens'] = getattr(usage, 'thoughts_token_count', 0)
            metadata['total_tokens'] = getattr(usage, 'total_token_count', 0)

            # Log usage
            if metadata['thinking_tokens'] > 0:
                logger.info(
                    f"Gemini usage (with thinking) - "
                    f"Input: {metadata['prompt_tokens']}, "
                    f"🧠 Thinking: {metadata['thinking_tokens']}, "
                    f"Output: {metadata['output_tokens']}, "
                    f"Total: {metadata['total_tokens']}"
                )
            else:
                logger.info(
                    f"Gemini usage - "
                    f"Input: {metadata['prompt_tokens']}, "
                    f"Output: {metadata['output_tokens']}, "
                    f"Total: {metadata['total_tokens']}"
                )

        return json.loads(resp.text), metadata

    async def _generate_openai_compatible(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Call OpenAI-compatible API (DeepSeek). Returns (result, metadata).

        Note: DeepSeek does NOT support strict json_schema mode.
        We use json_object mode and rely on prompt engineering.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        # Use DeepSeek model
        model = DEEPSEEK_MODEL

        # Build request kwargs (thinking-mode handling lives in the pure helper)
        kwargs = build_deepseek_request_kwargs(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as api_error:
            logger.error(f"API call failed: {api_error}")
            raise

        # Parse JSON from response
        if not response.choices or len(response.choices) == 0:
            logger.error(f"No choices in response: {response}")
            raise ValueError("API returned no choices")

        content = response.choices[0].message.content

        # Log raw response for debugging
        logger.debug(f"Raw LLM response content: {content[:500] if content else 'EMPTY'}")

        if not content or content.strip() == "":
            logger.error(f"Empty content from API. Full response: {response}")
            raise ValueError("API returned empty content")

        # Extract reasoning content if available (DeepSeek V3.2 thinking mode)
        reasoning_content = None
        if hasattr(response.choices[0].message, 'reasoning_content'):
            reasoning_content = response.choices[0].message.reasoning_content
            if reasoning_content:
                logger.debug(f"LLM Reasoning (first 200 chars): {reasoning_content[:200]}...")

        # Extract usage metadata
        metadata = {
            'provider': 'deepseek',
            'model': model,
            'prompt_tokens': 0,
            'output_tokens': 0,
            'thinking_tokens': 0,  # For thinking mode
            'total_tokens': 0,
            'cache_hit_tokens': 0,
            'cache_miss_tokens': 0,
            'reasoning_content': reasoning_content,  # Store reasoning for logging
        }

        if hasattr(response, 'usage'):
            usage = response.usage
            metadata['prompt_tokens'] = getattr(usage, 'prompt_tokens', 0)
            metadata['output_tokens'] = getattr(usage, 'completion_tokens', 0)
            metadata['total_tokens'] = getattr(usage, 'total_tokens', 0)

            # Check for thinking/reasoning tokens (if DeepSeek returns them separately)
            # Similar to Gemini's thoughts_token_count
            if hasattr(usage, 'reasoning_tokens') or hasattr(usage, 'thinking_tokens'):
                metadata['thinking_tokens'] = getattr(usage, 'reasoning_tokens', 0) or getattr(usage, 'thinking_tokens', 0)

            # DeepSeek cache metrics
            if hasattr(usage, 'prompt_cache_hit_tokens'):
                metadata['cache_hit_tokens'] = getattr(usage, 'prompt_cache_hit_tokens', 0)
                metadata['cache_miss_tokens'] = getattr(usage, 'prompt_cache_miss_tokens', 0)

                # Log cache metrics
                if metadata['prompt_tokens'] > 0:
                    hit_rate = (metadata['cache_hit_tokens'] / metadata['prompt_tokens'] * 100)
                    logger.info(
                        f"DeepSeek Cache: {metadata['cache_hit_tokens']} hits, "
                        f"{metadata['cache_miss_tokens']} misses ({hit_rate:.1f}% hit rate)"
                    )

            # Log thinking mode usage if available
            if metadata['thinking_tokens'] > 0:
                logger.info(
                    f"DeepSeek thinking mode - "
                    f"Input: {metadata['prompt_tokens']}, "
                    f"🧠 Thinking: {metadata['thinking_tokens']}, "
                    f"Output: {metadata['output_tokens']}, "
                    f"Total: {metadata['total_tokens']}"
                )

        return json.loads(content), metadata


# Global client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def generate_analysis_json(
    prompt: str,
    cache_key: str,
    llm_cache,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    # Optional metadata for prompt logging
    context: Optional[str] = None,
    team_hash: Optional[str] = None,
    language: Optional[str] = None,
    monster_name: Optional[str] = None,
    on_compute: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """
    Generate analysis with caching support.

    This is a drop-in replacement for the existing call_llm() function.

    Args:
        prompt: User prompt
        cache_key: Cache key for result storage
        llm_cache: Cache instance (RedisCache or TimedCache)
        system_prompt: Optional system message
        temperature: Sampling temperature (uses ANALYSIS_TEMPERATURE if None)
        context: Optional context for logging (e.g., "trait_synergy", "team_synergy")
        team_hash: Optional team hash for logging
        language: Optional language code for logging
        monster_name: Optional monster name for logging

    Returns:
        Analysis result as dictionary
    """
    # Check if cache supports get_or_compute (RedisCache with stampede protection)
    if hasattr(llm_cache, 'get_or_compute'):
        # Use Redis cache with stampede protection
        async def compute_fn():
            """
            Compute function for cache miss.

            NOTE: This function does NOT catch exceptions - they bubble up to the caller.
            This ensures failed LLM calls are NOT cached, allowing retry on subsequent requests.
            Error handling is done at the endpoint level (main.py).
            """
            start_time = time.time()
            client = get_llm_client()

            result, metadata = await client.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )

            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)

            # Log prompt with full metadata after API call
            save_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                team_hash=team_hash,
                language=language,
                monster_name=monster_name,
                cache_status="MISS",
                prompt_tokens=metadata.get('prompt_tokens'),
                output_tokens=metadata.get('output_tokens'),
                thinking_tokens=metadata.get('thinking_tokens'),
                total_tokens=metadata.get('total_tokens'),
                cache_hit_tokens=metadata.get('cache_hit_tokens'),
                cache_miss_tokens=metadata.get('cache_miss_tokens'),
                response_time_ms=response_time_ms,
                provider=metadata.get('provider'),
                model=metadata.get('model'),
                reasoning_content=metadata.get('reasoning_content'),
                save_reasoning=False,
            )

            return result

        # Use get_or_compute with stampede protection
        return await llm_cache.get_or_compute(cache_key, compute_fn, on_compute=on_compute)

    else:
        # Fallback to simple get/set pattern (TimedCache - no stampede protection)
        cached_result = llm_cache.get(cache_key)

        if cached_result is not None:
            logger.info(f"Cache HIT for key: {cache_key[:50]}...")
            save_prompt(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                team_hash=team_hash,
                language=language,
                monster_name=monster_name,
                cache_status="HIT",
            )
            return cached_result

        # Cache miss - call LLM (exceptions bubble up to caller - NOT cached)
        logger.info(f"Cache MISS for key: {cache_key[:50]}...")

        start_time = time.time()
        client = get_llm_client()

        result, metadata = await client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        save_prompt(
            prompt=prompt,
            system_prompt=system_prompt,
            context=context,
            team_hash=team_hash,
            language=language,
            monster_name=monster_name,
            cache_status="MISS",
            prompt_tokens=metadata.get('prompt_tokens'),
            output_tokens=metadata.get('output_tokens'),
            thinking_tokens=metadata.get('thinking_tokens'),
            total_tokens=metadata.get('total_tokens'),
            cache_hit_tokens=metadata.get('cache_hit_tokens'),
            cache_miss_tokens=metadata.get('cache_miss_tokens'),
            response_time_ms=response_time_ms,
            provider=metadata.get('provider'),
            model=metadata.get('model'),
            reasoning_content=metadata.get('reasoning_content'),
            save_reasoning=False,
        )

        llm_cache.set(cache_key, result)
        logger.info(f"Cached result for key: {cache_key[:50]}...")

        return result
