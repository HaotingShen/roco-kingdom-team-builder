#!/bin/bash
# Clear all analysis cache from Redis
# This removes all monster trait analyses, team synergies, and locks

set -e

echo "🗑️  Clearing Redis analysis cache..."
echo ""

# Count before clearing
MONSTER_COUNT=$(redis-cli KEYS "monster_trait:*" | wc -l)
TEAM_COUNT=$(redis-cli KEYS "team_synergy:*" | wc -l)
LOCK_COUNT=$(redis-cli KEYS "lock:*" | wc -l)

echo "Found:"
echo "  - Monster analyses: $MONSTER_COUNT"
echo "  - Team synergies: $TEAM_COUNT"
echo "  - Active locks: $LOCK_COUNT"
echo ""

if [ "$MONSTER_COUNT" -eq 0 ] && [ "$TEAM_COUNT" -eq 0 ] && [ "$LOCK_COUNT" -eq 0 ]; then
    echo "✅ Cache is already empty!"
    exit 0
fi

# Ask for confirmation
read -p "Clear all cache? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled."
    exit 1
fi

# Clear cache
echo "Clearing monster trait analyses..."
redis-cli --scan --pattern "monster_trait:*" | xargs -r redis-cli DEL > /dev/null 2>&1

echo "Clearing team synergies..."
redis-cli --scan --pattern "team_synergy:*" | xargs -r redis-cli DEL > /dev/null 2>&1

echo "Clearing locks..."
redis-cli --scan --pattern "lock:*" | xargs -r redis-cli DEL > /dev/null 2>&1

echo ""
echo "✅ Cache cleared successfully!"
echo "New cache size: $(redis-cli DBSIZE) keys"
