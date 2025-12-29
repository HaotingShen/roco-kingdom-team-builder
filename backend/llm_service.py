"""
LLM Service Abstraction Layer

Provides unified interface for multiple LLM providers:
- Google Gemini (testing - free tier)
- DeepSeek Official API (production - for China access)
"""

from typing import Optional, Dict, Any
import json
import logging
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
    ANALYSIS_TEMPERATURE,
    ANALYSIS_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


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
                timeout=60.0,
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
    ) -> Dict[str, Any]:
        """
        Generate JSON response from LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system message
            temperature: Sampling temperature (0.0-2.0), defaults to ANALYSIS_TEMPERATURE
            max_tokens: Maximum tokens to generate, defaults to ANALYSIS_MAX_TOKENS

        Returns:
            Parsed JSON response as dictionary

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
    ) -> Dict[str, Any]:
        """Call Gemini API with thinking mode enabled."""
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

        # Log usage metadata (includes thinking tokens)
        if hasattr(resp, 'usage_metadata'):
            usage = resp.usage_metadata
            prompt_tokens = getattr(usage, 'prompt_token_count', 0)
            output_tokens = getattr(usage, 'candidates_token_count', 0)
            thinking_tokens = getattr(usage, 'thoughts_token_count', 0)
            total_tokens = getattr(usage, 'total_token_count', 0)

            if thinking_tokens > 0:
                # Thinking mode was used
                logger.info(
                    f"Gemini usage (with thinking) - "
                    f"Input: {prompt_tokens}, "
                    f"🧠 Thinking: {thinking_tokens}, "
                    f"Output: {output_tokens}, "
                    f"Total: {total_tokens}"
                )
            else:
                # No thinking tokens
                logger.info(
                    f"Gemini usage - "
                    f"Input: {prompt_tokens}, "
                    f"Output: {output_tokens}, "
                    f"Total: {total_tokens}"
                )

        return json.loads(resp.text)

    async def _generate_openai_compatible(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Call OpenAI-compatible API (DeepSeek).

        Note: DeepSeek does NOT support strict json_schema mode.
        We use json_object mode and rely on prompt engineering.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        # Use DeepSeek model
        model = DEEPSEEK_MODEL

        # Important: DeepSeek-reasoner does NOT support temperature
        # Use chat model for temperature control
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},  # Force JSON output
        }

        # Only add temperature if NOT using reasoner model
        if "reasoner" not in model.lower():
            kwargs["temperature"] = temperature

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

        # Log reasoning if available (DeepSeek R1)
        if hasattr(response.choices[0].message, 'reasoning_content'):
            reasoning = response.choices[0].message.reasoning_content
            if reasoning:
                logger.debug(f"LLM Reasoning (first 200 chars): {reasoning[:200]}...")

        # Log DeepSeek cache metrics if available
        if hasattr(response, 'usage') and hasattr(response.usage, 'prompt_cache_hit_tokens'):
            usage = response.usage
            hit_tokens = getattr(usage, 'prompt_cache_hit_tokens', 0)
            miss_tokens = getattr(usage, 'prompt_cache_miss_tokens', 0)
            total_tokens = usage.prompt_tokens

            if total_tokens > 0:
                hit_rate = (hit_tokens / total_tokens * 100)
                logger.info(
                    f"DeepSeek Cache: {hit_tokens} hits, {miss_tokens} misses "
                    f"({hit_rate:.1f}% hit rate)"
                )

        return json.loads(content)


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
) -> Dict[str, Any]:
    """
    Generate analysis with caching support.

    This is a drop-in replacement for the existing call_llm() function.

    Args:
        prompt: User prompt
        cache_key: Cache key for result storage
        llm_cache: Cache instance
        system_prompt: Optional system message
        temperature: Sampling temperature (uses ANALYSIS_TEMPERATURE if None)

    Returns:
        Analysis result as dictionary
    """
    # Check cache first
    cached_result = llm_cache.get(cache_key)
    if cached_result is not None:
        logger.info(f"Cache HIT for key: {cache_key[:50]}...")
        return cached_result

    # Cache miss - call LLM
    logger.info(f"Cache MISS for key: {cache_key[:50]}...")

    try:
        client = get_llm_client()
        result = await client.generate_json(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        # Cache the result
        llm_cache.set(cache_key, result)
        logger.info(f"Cached result for key: {cache_key[:50]}...")

        return result

    except Exception as e:
        logger.error(f"LLM error: {e}", exc_info=True)
        return {
            "synergy_moves": [],
            "recommendation": [f"Error generating analysis: {str(e)}"]
        }
