import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# API Keys
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
# IMPORTANT: Each analysis makes 6 LLM calls (one per monster in team)
# - "3/minute" = 18 LLM calls/min per user (conservative, recommended for cost control)
# - "5/minute" = 30 LLM calls/min per user (moderate)
# - "10/minute" = 60 LLM calls/min per user (generous, higher API costs)
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
ANALYSIS_RATE_LIMIT = os.getenv("ANALYSIS_RATE_LIMIT", "3/minute")