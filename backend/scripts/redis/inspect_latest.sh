#!/bin/bash
# Inspect the latest cached analysis

set -e

echo "🔍 Latest Cached Analysis"
echo "========================="
echo ""

# Check for monster trait analyses
LATEST=$(redis-cli --scan --pattern "monster_trait:*" | head -1)

if [ -z "$LATEST" ]; then
    echo "❌ No monster analyses found in cache"
    echo ""
    echo "Try:"
    echo "  - Run an analysis first"
    echo "  - Check team synergies: redis-cli KEYS 'team_synergy:*'"
    exit 1
fi

echo "📦 Cache Key:"
echo "  $LATEST"
echo ""

# Get TTL
TTL=$(redis-cli TTL "$LATEST")
if [ "$TTL" -eq -1 ]; then
    echo "⏰ TTL: No expiration"
elif [ "$TTL" -eq -2 ]; then
    echo "⏰ TTL: Key expired or doesn't exist"
else
    MINUTES=$((TTL / 60))
    SECONDS=$((TTL % 60))
    echo "⏰ TTL: ${MINUTES}m ${SECONDS}s remaining"
fi
echo ""

# Get value and format as JSON
echo "📄 Cached Value:"
VALUE=$(redis-cli GET "$LATEST")

if command -v python3 &> /dev/null; then
    echo "$VALUE" | python3 -m json.tool 2>/dev/null || echo "$VALUE"
else
    echo "$VALUE"
fi
echo ""

# Show all cached keys summary
TOTAL_MONSTER=$(redis-cli KEYS "monster_trait:*" | wc -l)
TOTAL_TEAM=$(redis-cli KEYS "team_synergy:*" | wc -l)
echo "📊 Total Cached:"
echo "  Monster analyses: $TOTAL_MONSTER"
echo "  Team synergies: $TOTAL_TEAM"
