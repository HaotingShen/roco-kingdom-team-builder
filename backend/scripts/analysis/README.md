# Analysis Scripts

## Token Counting Script

### `count_cacheable_tokens.py`

Counts the exact number of tokens in the cacheable prompt prefixes using the official DeepSeek V3 tokenizer.

#### Quick Usage:

```bash
# From project root
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/analysis/count_cacheable_tokens.py

# Or from backend directory
cd backend
python3 scripts/analysis/count_cacheable_tokens.py
```

#### Requirements:

- Python 3.10+
- transformers library: `pip install transformers`
- DeepSeek tokenizer files in `backend/deepseek_v3_tokenizer/` directory

#### What It Does:

1. Loads the DeepSeek V3 tokenizer
2. Reads `BATTLE_MECHANICS_ZH` and `BATTLE_MECHANICS_EN` from `backend/main.py`
3. Counts tokens for cacheable components:
   - Role statement
   - Section header
   - Battle mechanics
   - Type effectiveness table (sample)
4. Compares against DeepSeek's 64 token minimum for caching (storage unit size)
5. Calculates estimated cost savings

#### Output Example:

```
================================================================================
DeepSeek V3 Cacheable Token Analysis
================================================================================

📊 Chinese (中文)
────────────────────────────────────────────────────────────────────────────────
  Role statement:          21 tokens
  Section header:          28 tokens
  Battle mechanics:       673 tokens (1027 chars)
  Type effectiveness:     403 tokens (sample)
  ────────────────────────────────────────────────────────────────────────────
  TOTAL CACHEABLE:       1123 tokens
  DeepSeek minimum:        64 tokens (64-token storage unit)
  Buffer:               +1059 tokens ✅

  ✅ CACHING ENABLED
  💰 Savings per request:  ~1010 tokens (90% discount)
  💰 Savings per analysis: ~7074 tokens (7 LLM calls)
```

#### Notes:

- Type chart size is estimated using a sample (actual varies by database)
- Glossary (game terms) is dynamic when reference resolution is enabled
- Run this script after editing battle mechanics to verify token counts

## Directory Structure:

```
backend/
├── deepseek_v3_tokenizer/          # DeepSeek V3 tokenizer files
│   └── deepseek_v3_tokenizer/
│       ├── deepseek_tokenizer.py
│       ├── tokenizer.json
│       └── tokenizer_config.json
└── scripts/
    └── analysis/                    # Analysis tools
        ├── count_cacheable_tokens.py
        └── README.md (this file)
```
