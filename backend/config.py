import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# API Keys
# Note: OPENAI_API_KEY is reserved for future use (potential alternative LLM provider)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

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
# Gemini 2.5 Flash FREE TIER: 10 requests per minute (RPM)
#
# Recommended settings:
# - "1/2minutes" = 3.5 LLM calls/min per user (FREE TIER - extra safe, well under 10 RPM)
# - "1/minute" = 7 LLM calls/min per user (FREE TIER - stays under 10 RPM limit)
# - "1/90seconds" = ~0.67/min (FREE TIER - safe buffer)
# - "2/minute" = 14 LLM calls/min per user (PAID - requires higher limits)
#
# With caching enabled, repeated analyses are instant (bypasses rate limit)
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
ANALYSIS_RATE_LIMIT = os.getenv("ANALYSIS_RATE_LIMIT", "1/2minutes")