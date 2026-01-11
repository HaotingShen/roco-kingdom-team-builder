#!/bin/bash
# Display Redis cache statistics

set -e

echo "📊 Redis Cache Statistics"
echo "=========================="
echo ""

# Connection info
echo "🔌 Connection:"
PING=$(redis-cli ping 2>&1)
if [ "$PING" = "PONG" ]; then
    echo "  ✅ Redis is running"
else
    echo "  ❌ Redis is not responding"
    exit 1
fi
echo ""

# Key counts
echo "🔑 Cache Keys:"
TOTAL=$(redis-cli DBSIZE)
MONSTER=$(redis-cli KEYS "monster_trait:*" | grep -c "^monster_trait:" || true)
TEAM=$(redis-cli KEYS "team_synergy:*" | grep -c "^team_synergy:" || true)
LOCKS=$(redis-cli KEYS "lock:*" | grep -c "^lock:" || true)

echo "  Total keys: $TOTAL"
echo "  Monster analyses: $MONSTER"
echo "  Team synergies: $TEAM"
echo "  Active locks: $LOCKS"
echo ""

# Memory usage
echo "💾 Memory Usage:"
redis-cli INFO memory | grep -E "used_memory_human|used_memory_peak_human" | sed 's/^/  /'
echo ""

# Hit rate
echo "📈 Cache Performance:"
HITS=$(redis-cli INFO stats | grep keyspace_hits | cut -d: -f2 | tr -d '\r')
MISSES=$(redis-cli INFO stats | grep keyspace_misses | cut -d: -f2 | tr -d '\r')
TOTAL_REQUESTS=$((HITS + MISSES))

if [ "$TOTAL_REQUESTS" -gt 0 ]; then
    HIT_RATE=$(awk "BEGIN {printf \"%.2f\", ($HITS / $TOTAL_REQUESTS) * 100}")
    echo "  Cache hits: $HITS"
    echo "  Cache misses: $MISSES"
    echo "  Hit rate: ${HIT_RATE}%"
else
    echo "  No cache requests yet"
fi
echo ""

# Keyspace info
echo "🕐 Keyspace Info:"
redis-cli INFO keyspace | grep -E "^db" | sed 's/^/  /'

# If no keyspace info, show message
if [ -z "$(redis-cli INFO keyspace | grep -E '^db')" ]; then
    echo "  No keys in database"
fi
echo ""

# Recent activity
echo "⏱️  Uptime:"
redis-cli INFO server | grep uptime_in_days | sed 's/^/  /'
