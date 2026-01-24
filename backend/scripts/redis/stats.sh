#!/bin/bash
# Display comprehensive Redis cache statistics
# Includes all key namespaces: llm_cache, ratelimit, tier, revoked_token

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

# Key counts by namespace
echo "🔑 Cache Keys by Namespace:"
TOTAL=$(redis-cli DBSIZE | awk '{print $2}')

# LLM Cache (llm_cache:*)
MONSTER=$(redis-cli --scan --pattern "llm_cache:monster_trait:*" 2>/dev/null | wc -l)
TEAM=$(redis-cli --scan --pattern "llm_cache:team_synergy:*" 2>/dev/null | wc -l)
LOCKS=$(redis-cli --scan --pattern "lock:*" 2>/dev/null | wc -l)
LLM_TOTAL=$((MONSTER + TEAM))

# Rate Limiting (ratelimit:*)
RATELIMIT_ANALYSIS=$(redis-cli --scan --pattern "ratelimit:analysis:*" 2>/dev/null | wc -l)
RATELIMIT_GLOBAL=$(redis-cli --scan --pattern "ratelimit:global_ip:*" 2>/dev/null | wc -l)
RATELIMIT_TOTAL=$((RATELIMIT_ANALYSIS + RATELIMIT_GLOBAL))

# Tier Quotas (tier:*)
TIER_USER=$(redis-cli --scan --pattern "tier:user:*" 2>/dev/null | wc -l)
TIER_ANON_DEVICE=$(redis-cli --scan --pattern "tier:anon:device:*" 2>/dev/null | wc -l)
TIER_ANON_IP=$(redis-cli --scan --pattern "tier:anon:ip:*" 2>/dev/null | wc -l)
TIER_GUEST_CREATE=$(redis-cli --scan --pattern "tier:guest_create:*" 2>/dev/null | wc -l)
TIER_TOTAL=$((TIER_USER + TIER_ANON_DEVICE + TIER_ANON_IP + TIER_GUEST_CREATE))

# Token Revocation (revoked_token:*)
REVOKED_TOKENS=$(redis-cli --scan --pattern "revoked_token:*" 2>/dev/null | wc -l)

echo "  Total keys: $TOTAL"
echo ""
echo "  📚 LLM Cache ($LLM_TOTAL keys):"
echo "     Monster analyses: $MONSTER"
echo "     Team synergies:   $TEAM"
echo "     Active locks:     $LOCKS"
echo ""
echo "  ⏱️  Rate Limits ($RATELIMIT_TOTAL keys):"
echo "     Per-team analysis: $RATELIMIT_ANALYSIS"
echo "     Global IP:         $RATELIMIT_GLOBAL"
echo ""
echo "  📈 Tier Quotas ($TIER_TOTAL keys):"
echo "     User quotas:       $TIER_USER"
echo "     Anon device:       $TIER_ANON_DEVICE"
echo "     Anon IP:           $TIER_ANON_IP"
echo "     Guest creation:    $TIER_GUEST_CREATE"
echo ""
echo "  🔐 Token Revocation:"
echo "     Revoked tokens:    $REVOKED_TOKENS"
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
    echo "  Cache hits:   $HITS"
    echo "  Cache misses: $MISSES"
    echo "  Hit rate:     ${HIT_RATE}%"
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
