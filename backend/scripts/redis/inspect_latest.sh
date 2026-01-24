#!/bin/bash
# Inspect Redis keys with detailed information
# Shows latest cached analysis or inspects specific key types
#
# Usage:
#   ./inspect_latest.sh           # Show latest LLM cache entry
#   ./inspect_latest.sh llm       # Show LLM cache summary
#   ./inspect_latest.sh rate      # Show rate limit keys
#   ./inspect_latest.sh tier      # Show tier quota keys
#   ./inspect_latest.sh tokens    # Show revoked tokens
#   ./inspect_latest.sh key <key> # Inspect specific key

set -e

# Function to count keys
count_keys() {
    redis-cli --scan --pattern "$1" 2>/dev/null | wc -l
}

# Function to format JSON if python3 is available
format_json() {
    if command -v python3 &> /dev/null; then
        python3 -m json.tool 2>/dev/null || cat
    else
        cat
    fi
}

# Function to show key details
inspect_key() {
    local key="$1"
    echo "📦 Key: $key"
    echo ""

    # Get TTL
    TTL=$(redis-cli TTL "$key")
    if [ "$TTL" -eq -1 ]; then
        echo "⏰ TTL: No expiration"
    elif [ "$TTL" -eq -2 ]; then
        echo "⏰ TTL: Key expired or doesn't exist"
        return
    else
        HOURS=$((TTL / 3600))
        MINUTES=$(((TTL % 3600) / 60))
        SECONDS=$((TTL % 60))
        if [ "$HOURS" -gt 0 ]; then
            echo "⏰ TTL: ${HOURS}h ${MINUTES}m ${SECONDS}s remaining"
        elif [ "$MINUTES" -gt 0 ]; then
            echo "⏰ TTL: ${MINUTES}m ${SECONDS}s remaining"
        else
            echo "⏰ TTL: ${SECONDS}s remaining"
        fi
    fi
    echo ""

    # Get type
    TYPE=$(redis-cli TYPE "$key")
    echo "📋 Type: $TYPE"
    echo ""

    # Get value
    echo "📄 Value:"
    case $TYPE in
        string)
            VALUE=$(redis-cli GET "$key")
            echo "$VALUE" | format_json
            ;;
        hash)
            redis-cli HGETALL "$key"
            ;;
        list)
            redis-cli LRANGE "$key" 0 -1
            ;;
        set)
            redis-cli SMEMBERS "$key"
            ;;
        zset)
            redis-cli ZRANGE "$key" 0 -1 WITHSCORES
            ;;
        *)
            echo "(unknown type)"
            ;;
    esac
}

# Function to list keys with TTL
list_keys_with_ttl() {
    local pattern="$1"
    local limit="${2:-10}"
    local keys=$(redis-cli --scan --pattern "$pattern" 2>/dev/null | head -$limit)

    if [ -z "$keys" ]; then
        echo "  (no keys found)"
        return
    fi

    echo "$keys" | while read -r key; do
        if [ -n "$key" ]; then
            TTL=$(redis-cli TTL "$key")
            if [ "$TTL" -eq -1 ]; then
                echo "  $key (no TTL)"
            elif [ "$TTL" -gt 0 ]; then
                echo "  $key (TTL: ${TTL}s)"
            fi
        fi
    done
}

# Main script
echo "🔍 Redis Key Inspector"
echo "======================"
echo ""

# Check connection
PING=$(redis-cli ping 2>&1)
if [ "$PING" != "PONG" ]; then
    echo "❌ Cannot connect to Redis"
    exit 1
fi

case "${1:-}" in
    llm)
        echo "📚 LLM Cache Summary"
        echo ""
        echo "Monster Trait Analyses ($(count_keys 'llm_cache:monster_trait:*')):"
        list_keys_with_ttl "llm_cache:monster_trait:*" 5
        echo ""
        echo "Team Synergies ($(count_keys 'llm_cache:team_synergy:*')):"
        list_keys_with_ttl "llm_cache:team_synergy:*" 5
        echo ""
        echo "Active Locks ($(count_keys 'lock:*')):"
        list_keys_with_ttl "lock:*" 5
        ;;

    rate)
        echo "⏱️  Rate Limit Keys"
        echo ""
        echo "Per-Team Analysis ($(count_keys 'ratelimit:analysis:*')):"
        list_keys_with_ttl "ratelimit:analysis:*" 10
        echo ""
        echo "Global IP ($(count_keys 'ratelimit:global_ip:*')):"
        list_keys_with_ttl "ratelimit:global_ip:*" 10
        ;;

    tier)
        echo "📈 Tier Quota Keys"
        echo ""
        echo "User Quotas ($(count_keys 'tier:user:*')):"
        list_keys_with_ttl "tier:user:*" 10
        echo ""
        echo "Anonymous Device ($(count_keys 'tier:anon:device:*')):"
        list_keys_with_ttl "tier:anon:device:*" 10
        echo ""
        echo "Anonymous IP ($(count_keys 'tier:anon:ip:*')):"
        list_keys_with_ttl "tier:anon:ip:*" 10
        echo ""
        echo "Guest Creation ($(count_keys 'tier:guest_create:*')):"
        list_keys_with_ttl "tier:guest_create:*" 10
        ;;

    tokens)
        echo "🔐 Revoked Token Keys"
        echo ""
        echo "Revoked Tokens ($(count_keys 'revoked_token:*')):"
        list_keys_with_ttl "revoked_token:*" 20
        ;;

    key)
        if [ -z "$2" ]; then
            echo "❌ Usage: $0 key <key_name>"
            exit 1
        fi
        inspect_key "$2"
        ;;

    *)
        # Default: Show latest LLM cache entry
        LATEST=$(redis-cli --scan --pattern "llm_cache:monster_trait:*" 2>/dev/null | head -1)

        if [ -z "$LATEST" ]; then
            # Try team synergy
            LATEST=$(redis-cli --scan --pattern "llm_cache:team_synergy:*" 2>/dev/null | head -1)
        fi

        if [ -z "$LATEST" ]; then
            echo "❌ No LLM cache entries found"
            echo ""
            echo "Try one of these:"
            echo "  ./inspect_latest.sh llm      # LLM cache summary"
            echo "  ./inspect_latest.sh rate     # Rate limits"
            echo "  ./inspect_latest.sh tier     # Tier quotas"
            echo "  ./inspect_latest.sh tokens   # Revoked tokens"
            echo "  ./inspect_latest.sh key <k>  # Specific key"
            exit 1
        fi

        inspect_key "$LATEST"
        echo ""
        echo "───────────────────────────────"
        echo ""
        echo "📊 Total Cached:"
        echo "  Monster analyses: $(count_keys 'llm_cache:monster_trait:*')"
        echo "  Team synergies:   $(count_keys 'llm_cache:team_synergy:*')"
        echo "  Rate limits:      $(count_keys 'ratelimit:*')"
        echo "  Tier quotas:      $(count_keys 'tier:*')"
        echo "  Revoked tokens:   $(count_keys 'revoked_token:*')"
        ;;
esac
