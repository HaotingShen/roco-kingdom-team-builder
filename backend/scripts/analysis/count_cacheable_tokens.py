#!/usr/bin/env python3
"""
DeepSeek Token Counter for Cacheable Prompt Prefixes

This script uses the official DeepSeek V3 tokenizer to count exact tokens
in the cacheable portions of LLM prompts for both Chinese and English versions.

Usage:
    From project root: python3 backend/scripts/analysis/count_cacheable_tokens.py
    From backend dir:  python3 scripts/analysis/count_cacheable_tokens.py

Requirements:
    pip install transformers
"""

import sys
import os

# Get script directory
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add backend to path (script is in backend/scripts/analysis/)
backend_dir = os.path.join(script_dir, '..', '..')
sys.path.insert(0, backend_dir)

# Path to tokenizer (backend/deepseek_v3_tokenizer/deepseek_v3_tokenizer/)
tokenizer_dir = os.path.join(backend_dir, 'deepseek_v3_tokenizer', 'deepseek_v3_tokenizer')
sys.path.insert(0, tokenizer_dir)

try:
    import transformers
except ImportError:
    print("❌ Error: transformers library not installed")
    print("   Install with: pip install transformers")
    sys.exit(1)

# Load DeepSeek tokenizer
print("Loading DeepSeek V3 tokenizer...")
try:
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        tokenizer_dir,
        trust_remote_code=True
    )
    print("✓ Tokenizer loaded\n")
except Exception as e:
    print(f"❌ Error loading tokenizer: {e}")
    sys.exit(1)

# Extract battle mechanics constants from main.py (avoiding module import issues)
import re

try:
    # Path to main.py (script is in backend/scripts/analysis/, main.py is in backend/)
    main_py_path = os.path.join(backend_dir, 'main.py')
    with open(main_py_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract BATTLE_MECHANICS_ZH
    zh_match = re.search(r'BATTLE_MECHANICS_ZH = """(.+?)"""', content, re.DOTALL)
    if not zh_match:
        raise ValueError("Could not find BATTLE_MECHANICS_ZH in main.py")
    BATTLE_MECHANICS_ZH = zh_match.group(1)

    # Extract BATTLE_MECHANICS_EN
    en_match = re.search(r'BATTLE_MECHANICS_EN = """(.+?)"""', content, re.DOTALL)
    if not en_match:
        raise ValueError("Could not find BATTLE_MECHANICS_EN in main.py")
    BATTLE_MECHANICS_EN = en_match.group(1)

    print(f"✓ Loaded battle mechanics constants from {os.path.relpath(main_py_path)}\n")

except FileNotFoundError:
    print(f"❌ Error: Could not find backend/main.py")
    print("   Make sure the backend directory structure is correct")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error loading constants: {e}")
    sys.exit(1)

# Sample type chart for estimation (actual one varies by database content)
SAMPLE_TYPE_CHART_ZH = """  火 → 克制: 草, 冰 | 被克制: 水, 地
  水 → 克制: 火, 地 | 被克制: 草, 电
  草 → 克制: 水, 地 | 被克制: 火, 冰, 飞
  电 → 克制: 水, 飞 | 被克制: 地
  冰 → 克制: 草, 飞, 龙 | 被克制: 火, 格斗
  格斗 → 克制: 普通, 冰 | 被克制: 飞, 超能
  毒 → 克制: 草 | 被克制: 地, 超能
  地 → 克制: 火, 电, 毒 | 被克制: 水, 草, 冰
  飞 → 克制: 草, 格斗 | 被克制: 电, 冰
  超能 → 克制: 格斗, 毒 | 被克制: 恶, 幽灵
  虫 → 克制: 草, 超能, 恶 | 被克制: 火, 飞
  岩石 → 克制: 火, 冰, 飞 | 被克制: 水, 草, 格斗, 地
  幽灵 → 克制: 超能, 幽灵 | 被克制: 恶, 幽灵
  龙 → 克制: 龙 | 被克制: 冰, 龙
  恶 → 克制: 超能, 幽灵 | 被克制: 格斗
  钢 → 克制: 冰, 岩石 | 被克制: 火, 格斗, 地
  普通 → 克制: 无 | 被克制: 格斗"""

SAMPLE_TYPE_CHART_EN = """  Fire → Strong vs: Grass, Ice | Weak vs: Water, Ground
  Water → Strong vs: Fire, Ground | Weak vs: Grass, Electric
  Grass → Strong vs: Water, Ground | Weak vs: Fire, Ice, Flying
  Electric → Strong vs: Water, Flying | Weak vs: Ground
  Ice → Strong vs: Grass, Flying, Dragon | Weak vs: Fire, Fighting
  Fighting → Strong vs: Normal, Ice | Weak vs: Flying, Psychic
  Poison → Strong vs: Grass | Weak vs: Ground, Psychic
  Ground → Strong vs: Fire, Electric, Poison | Weak vs: Water, Grass, Ice
  Flying → Strong vs: Grass, Fighting | Weak vs: Electric, Ice
  Psychic → Strong vs: Fighting, Poison | Weak vs: Dark, Ghost
  Bug → Strong vs: Grass, Psychic, Dark | Weak vs: Fire, Flying
  Rock → Strong vs: Fire, Ice, Flying | Weak vs: Water, Grass, Fighting, Ground
  Ghost → Strong vs: Psychic, Ghost | Weak vs: Dark, Ghost
  Dragon → Strong vs: Dragon | Weak vs: Ice, Dragon
  Dark → Strong vs: Psychic, Ghost | Weak vs: Fighting
  Steel → Strong vs: Ice, Rock | Weak vs: Fire, Fighting, Ground
  Normal → Strong vs: None | Weak vs: Fighting"""

def count_tokens(text):
    """Count tokens in a text string."""
    return len(tokenizer.encode(text))

def analyze_version(language):
    """Analyze token counts for a specific language version."""
    if language == "zh":
        role = "你是一位专业的游戏策略专家，精通洛克王国的对战机制、属性克制和精灵配队。"
        header = "\n\n【核心对战规则】\n以下规则适用于所有PvP对战，是分析队伍和精灵配置的基础：\n\n## 对战机制\n"
        mechanics = BATTLE_MECHANICS_ZH
        type_header = "\n\n## 属性克制表\n"
        type_chart = SAMPLE_TYPE_CHART_ZH
        lang_name = "Chinese (中文)"
    else:
        role = "You are an expert game strategist specializing in Roco Kingdom battle mechanics, type matchups, and team composition."
        header = "\n\n【Core Battle Rules】\nThe following rules apply to all PvP battles and form the foundation for team and monster analysis:\n\n## Battle Mechanics\n"
        mechanics = BATTLE_MECHANICS_EN
        type_header = "\n\n## Type Effectiveness Table\n"
        type_chart = SAMPLE_TYPE_CHART_EN
        lang_name = "English"

    # Count individual components
    role_tokens = count_tokens(role)
    header_tokens = count_tokens(header)
    mechanics_tokens = count_tokens(mechanics)
    type_chart_tokens = count_tokens(type_header + type_chart)

    # Total cacheable prefix
    cacheable = role + header + mechanics + type_header + type_chart
    total_tokens = count_tokens(cacheable)

    return {
        'language': lang_name,
        'role_tokens': role_tokens,
        'header_tokens': header_tokens,
        'mechanics_chars': len(mechanics),
        'mechanics_tokens': mechanics_tokens,
        'type_chart_tokens': type_chart_tokens,
        'total_tokens': total_tokens,
        'minimum': 64,  # DeepSeek cache minimum (64 tokens per storage unit)
        'buffer': total_tokens - 64,
        'savings_per_request': int(total_tokens * 0.9),
        'savings_per_analysis': int(total_tokens * 0.9 * 7),
    }

def print_report():
    """Print detailed token count report."""
    print("=" * 80)
    print("DeepSeek V3 Cacheable Token Analysis")
    print("=" * 80)
    print()

    # Analyze both versions
    zh = analyze_version('zh')
    en = analyze_version('en')

    # Print Chinese version
    print(f"📊 {zh['language']}")
    print("─" * 80)
    print(f"  Role statement:        {zh['role_tokens']:>4d} tokens")
    print(f"  Section header:        {zh['header_tokens']:>4d} tokens")
    print(f"  Battle mechanics:      {zh['mechanics_tokens']:>4d} tokens ({zh['mechanics_chars']} chars)")
    print(f"  Type effectiveness:    {zh['type_chart_tokens']:>4d} tokens (sample)")
    print("  " + "─" * 76)
    print(f"  TOTAL CACHEABLE:       {zh['total_tokens']:>4d} tokens")
    print(f"  DeepSeek minimum:      {zh['minimum']:>4d} tokens (64-token storage unit)")

    if zh['buffer'] >= 0:
        print(f"  Buffer:                {'+' + str(zh['buffer']):>4s} tokens ✅")
        print()
        print(f"  ✅ CACHING ENABLED")
        print(f"  💰 Savings per request:  ~{zh['savings_per_request']} tokens (90% discount)")
        print(f"  💰 Savings per analysis: ~{zh['savings_per_analysis']} tokens (7 LLM calls)")
    else:
        print(f"  Buffer:                {zh['buffer']:>4d} tokens ❌")
        print()
        print(f"  ❌ BELOW MINIMUM - Need {abs(zh['buffer'])} more tokens")

    print()

    # Print English version
    print(f"📊 {en['language']}")
    print("─" * 80)
    print(f"  Role statement:        {en['role_tokens']:>4d} tokens")
    print(f"  Section header:        {en['header_tokens']:>4d} tokens")
    print(f"  Battle mechanics:      {en['mechanics_tokens']:>4d} tokens ({en['mechanics_chars']} chars)")
    print(f"  Type effectiveness:    {en['type_chart_tokens']:>4d} tokens (sample)")
    print("  " + "─" * 76)
    print(f"  TOTAL CACHEABLE:       {en['total_tokens']:>4d} tokens")
    print(f"  DeepSeek minimum:      {en['minimum']:>4d} tokens (64-token storage unit)")

    if en['buffer'] >= 0:
        print(f"  Buffer:                {'+' + str(en['buffer']):>4s} tokens ✅")
        print()
        print(f"  ✅ CACHING ENABLED")
        print(f"  💰 Savings per request:  ~{en['savings_per_request']} tokens (90% discount)")
        print(f"  💰 Savings per analysis: ~{en['savings_per_analysis']} tokens (7 LLM calls)")
    else:
        print(f"  Buffer:                {en['buffer']:>4d} tokens ❌")
        print()
        print(f"  ❌ BELOW MINIMUM - Need {abs(en['buffer'])} more tokens")

    print()

    # Comparison table
    print("=" * 80)
    print("📈 Comparison")
    print("=" * 80)
    print()
    print(f"  {'Component':<25s} {'Chinese':>12s} {'English':>12s}")
    print(f"  {'-' * 53}")
    print(f"  {'Role + Header':<25s} {zh['role_tokens'] + zh['header_tokens']:>12d} {en['role_tokens'] + en['header_tokens']:>12d}")
    print(f"  {'Battle Mechanics':<25s} {zh['mechanics_tokens']:>12d} {en['mechanics_tokens']:>12d}")
    print(f"  {'Type Chart (sample)':<25s} {zh['type_chart_tokens']:>12d} {en['type_chart_tokens']:>12d}")
    print(f"  {'-' * 53}")
    print(f"  {'TOTAL CACHEABLE':<25s} {zh['total_tokens']:>12d} {en['total_tokens']:>12d}")

    zh_buffer_str = f"+{zh['buffer']}" if zh['buffer'] >= 0 else str(zh['buffer'])
    en_buffer_str = f"+{en['buffer']}" if en['buffer'] >= 0 else str(en['buffer'])
    print(f"  {'vs. Minimum (64)':<25s} {zh_buffer_str:>12s} {en_buffer_str:>12s}")
    print()

    # Final status
    if zh['buffer'] >= 0 and en['buffer'] >= 0:
        print("  ✅ Both versions ready for DeepSeek prompt caching!")
        print(f"  📊 Estimated total savings: ~{(zh['savings_per_analysis'] + en['savings_per_analysis']) // 2} tokens per analysis (average)")
    elif zh['buffer'] >= 0 or en['buffer'] >= 0:
        ready = "Chinese" if zh['buffer'] >= 0 else "English"
        needs_work = "English" if zh['buffer'] < 0 else "Chinese"
        shortfall = abs(en['buffer'] if en['buffer'] < 0 else zh['buffer'])
        print(f"  ⚠️  Only {ready} version ready for caching")
        print(f"  {needs_work} needs {shortfall} more tokens to reach minimum")
    else:
        print(f"  ❌ Both versions below minimum threshold")
        print(f"  Chinese needs: {abs(zh['buffer'])} more tokens")
        print(f"  English needs: {abs(en['buffer'])} more tokens")

    print()
    print("=" * 80)
    print()
    print("ℹ️  Note: Type chart size is estimated. Actual size depends on database content.")
    print("ℹ️  Glossary (game terms) is dynamic when reference resolution is enabled.")
    print()

if __name__ == "__main__":
    print_report()
