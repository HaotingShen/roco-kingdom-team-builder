"""Test Gemini thinking mode functionality."""

import asyncio
import sys
import os
import json
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_service import get_llm_client
from backend.config import LLM_PROVIDER, GEMINI_THINKING_BUDGET

# Configure logging to see INFO messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_thinking_mode():
    """Test Gemini with thinking mode enabled."""
    print(f"\n{'='*60}")
    print(f"Testing Gemini Thinking Mode")
    print(f"{'='*60}\n")
    print(f"Provider: {LLM_PROVIDER}")
    print(f"Thinking Budget: {GEMINI_THINKING_BUDGET} tokens (max capacity)")
    print()

    client = get_llm_client()

    # Complex prompt that should trigger thinking
    prompt = """Analyze this complex team synergy scenario:

Monster: Flame Dragon (Fire/Dragon type)
Trait: Pressure - Opponent's moves cost 2x PP
Personality: Adamant (+Attack, -Sp.Attack)
Selected Moves:
1. Flare Blitz (Fire, Physical, 120 power, 1/3 recoil, contact)
2. Dragon Claw (Dragon, Physical, 80 power, contact)
3. Earthquake (Ground, Physical, 100 power)
4. Will-O-Wisp (Fire, Status, burns target)

Consider:
- How does Pressure interact with PP-draining strategies?
- Should this monster prioritize contact moves given Flare Blitz's recoil?
- How does Adamant personality affect move selection?
- What's the optimal strategy against Water/Fairy types?
- Should Will-O-Wisp be used to reduce physical attackers' damage?

Return JSON with this exact structure:
{
  "synergy_moves": ["move1", "move2"],
  "recommendation": ["strategy1", "strategy2", "general_tip"]
}
"""

    try:
        import time
        start_time = time.time()

        print("⏱️  Sending complex analysis request...")
        print("🧠 Thinking mode enabled with max budget (24576 tokens)")
        print()

        result = await client.generate_json(
            prompt=prompt,
            temperature=0.7,
            max_tokens=4096
        )

        elapsed = time.time() - start_time

        print(f"\n✅ SUCCESS! Response received in {elapsed:.1f} seconds")
        print(f"\n{'='*60}")
        print("Analysis Result:")
        print(f"{'='*60}\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n{'='*60}")
        print(f"✅ Thinking mode test PASSED")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"\n{'='*60}")
        print("❌ Thinking mode test FAILED")
        print(f"{'='*60}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 Starting Gemini Thinking Mode Test...\n")
    success = asyncio.run(test_thinking_mode())
    sys.exit(0 if success else 1)
