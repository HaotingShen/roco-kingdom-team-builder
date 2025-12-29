"""Quick test script for LLM migration."""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_service import get_llm_client
from backend.config import LLM_PROVIDER
import json


async def test_llm():
    """Test LLM provider integration."""
    print(f"\n{'='*60}")
    print(f"Testing LLM Provider: {LLM_PROVIDER}")
    print(f"{'='*60}\n")

    client = get_llm_client()

    # Simple test prompt
    prompt = """
Analyze this monster's trait synergy with selected moves:

Monster: Spark Knight (Electric type)
Trait: Static Charge - When hit by contact moves, 30% chance to paralyze attacker
Selected Moves:
1. Thunder Punch (Electric, Physical, 75 power) - Contact move
2. Wild Charge (Electric, Physical, 90 power, recoil) - Contact move
3. Volt Switch (Electric, Special, 70 power, switches out)
4. Iron Defense (Steel, Status, +2 Defense)

Return JSON with this exact structure:
{
  "synergy_moves": ["Thunder Punch", "Wild Charge"],
  "recommendation": ["Strategy 1", "Strategy 2", "General tip"]
}
"""

    try:
        print("Sending request to LLM...")
        print(f"Using temperature: 0.7, max_tokens: 4096\n")

        result = await client.generate_json(prompt, temperature=0.7)

        print(f"✅ SUCCESS! Received response:\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n{'='*60}")
        print("✅ LLM integration test PASSED")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"\n{'='*60}")
        print("❌ LLM integration test FAILED")
        print(f"{'='*60}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 Starting LLM Migration Test...\n")
    success = asyncio.run(test_llm())
    sys.exit(0 if success else 1)
