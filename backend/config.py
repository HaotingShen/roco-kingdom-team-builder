import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# === LLM Provider Configuration ===

# Provider selection: gemini, deepseek
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Gemini Configuration (testing - free tier)
# Current free tier limits (Dec 2025): 10 RPM, 20 RPD
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Gemini Thinking Mode Configuration
# thinking_budget range: 512-24576 tokens (higher = more reasoning depth)
# Default: 24576 (maximum capacity for best quality analysis)
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "24576"))

# DeepSeek Official API Configuration (production - for China access)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# Models: deepseek-chat (非思考模式), deepseek-reasoner (思考模式)
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")

# LLM Response Configuration
ANALYSIS_TEMPERATURE = float(os.getenv("ANALYSIS_TEMPERATURE", "0.7"))
ANALYSIS_MAX_TOKENS = int(os.getenv("ANALYSIS_MAX_TOKENS", "4096"))

# Validate API keys based on selected provider
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY required when LLM_PROVIDER=gemini")
elif LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY required when LLM_PROVIDER=deepseek")

# CORS configuration
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",")]

# Application settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Database pool settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

# Rate limiting
# IMPORTANT: Each analysis makes 7 LLM calls (6 per-monster + 1 team-wide)
#
# Gemini 2.5 Flash Lite FREE TIER (Dec 2025): 10 RPM, 20 RPD
# - 10 requests per minute (RPM)
# - 20 requests per day (RPD)
# - Very restrictive! Effectively ~2-3 full team analyses per day max
#
# DeepSeek Official API (production): No hard rate limits (queuing system)
#
# Recommended settings:
# - "1/2minutes" = 3.5 LLM calls/min per user (works with Gemini free tier)
# - "1/minute" = 7 LLM calls/min per user (works with Gemini, stays under 10 RPM)
# - "2/minute" = 14 LLM calls/min per user (requires DeepSeek or paid tier)
#
# With caching enabled, repeated analyses are instant (bypasses rate limit)
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
ANALYSIS_RATE_LIMIT = os.getenv("ANALYSIS_RATE_LIMIT", "1/2minutes")

# Reference Resolution
# When enabled, LLM prompts include only referenced game terms instead of all 50+ terms
# Improves signal-to-noise ratio for better analysis quality
# Default: false (safe rollout - enable after validation)
ENABLE_REFERENCE_RESOLUTION = os.getenv("ENABLE_REFERENCE_RESOLUTION", "false").lower() == "true"