#!/bin/bash
# Clear Redis cache with selective options
# Supports clearing specific namespaces or all cache
#
# Usage:
#   ./clear_cache.sh           # Interactive menu
#   ./clear_cache.sh llm       # Clear LLM cache only
#   ./clear_cache.sh rate      # Clear rate limits only
#   ./clear_cache.sh tier      # Clear tier quotas only
#   ./clear_cache.sh tokens    # Clear revoked tokens only
#   ./clear_cache.sh all       # Clear everything (with confirmation)

set -e

# Function to count keys
count_keys() {
    redis-cli --scan --pattern "$1" 2>/dev/null | wc -l
}

# Function to clear keys by pattern
clear_pattern() {
    local pattern="$1"
    local count=$(count_keys "$pattern")
    if [ "$count" -gt 0 ]; then
        redis-cli --scan --pattern "$pattern" | xargs -r redis-cli DEL > /dev/null 2>&1
        echo "  ✅ Cleared $count keys matching: $pattern"
    else
        echo "  ℹ️  No keys found matching: $pattern"
    fi
}

# Function to show counts
show_counts() {
    echo ""
    echo "📊 Current key counts:"
    echo ""
    echo "  📚 LLM Cache:"
    echo "     Monster analyses: $(count_keys 'llm_cache:monster_trait:*')"
    echo "     Team synergies:   $(count_keys 'llm_cache:team_synergy:*')"
    echo "     Active locks:     $(count_keys 'lock:*')"
    echo ""
    echo "  ⏱️  Rate Limits:"
    echo "     Per-team analysis: $(count_keys 'ratelimit:analysis:*')"
    echo "     Global IP:         $(count_keys 'ratelimit:global_ip:*')"
    echo ""
    echo "  📈 Tier Quotas:"
    echo "     User quotas:       $(count_keys 'tier:user:*')"
    echo "     Anon device:       $(count_keys 'tier:anon:device:*')"
    echo "     Anon IP:           $(count_keys 'tier:anon:ip:*')"
    echo "     Guest creation:    $(count_keys 'tier:guest_create:*')"
    echo ""
    echo "  🔐 Token Revocation:"
    echo "     Revoked tokens:    $(count_keys 'revoked_token:*')"
    echo ""
}

# Function to clear LLM cache
clear_llm() {
    echo "🗑️  Clearing LLM cache..."
    clear_pattern "llm_cache:monster_trait:*"
    clear_pattern "llm_cache:team_synergy:*"
    clear_pattern "lock:llm_cache:*"
    clear_pattern "lock:*"
}

# Function to clear rate limits
clear_rate_limits() {
    echo "🗑️  Clearing rate limits..."
    clear_pattern "ratelimit:analysis:*"
    clear_pattern "ratelimit:global_ip:*"
}

# Function to clear tier quotas
clear_tier_quotas() {
    echo "🗑️  Clearing tier quotas..."
    clear_pattern "tier:user:*"
    clear_pattern "tier:anon:device:*"
    clear_pattern "tier:anon:ip:*"
    clear_pattern "tier:guest_create:*"
}

# Function to clear revoked tokens
clear_revoked_tokens() {
    echo "🗑️  Clearing revoked tokens..."
    clear_pattern "revoked_token:*"
}

# Function to clear all
clear_all() {
    clear_llm
    echo ""
    clear_rate_limits
    echo ""
    clear_tier_quotas
    echo ""
    clear_revoked_tokens
}

# Main script
echo "🗑️  Redis Cache Cleaner"
echo "======================="

# Check connection
PING=$(redis-cli ping 2>&1)
if [ "$PING" != "PONG" ]; then
    echo "❌ Cannot connect to Redis"
    exit 1
fi

# Handle command-line argument
case "${1:-}" in
    llm)
        show_counts
        read -p "Clear LLM cache? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clear_llm
            echo ""
            echo "✅ LLM cache cleared!"
        else
            echo "❌ Cancelled."
        fi
        ;;
    rate)
        show_counts
        read -p "Clear rate limits? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clear_rate_limits
            echo ""
            echo "✅ Rate limits cleared!"
        else
            echo "❌ Cancelled."
        fi
        ;;
    tier)
        show_counts
        read -p "Clear tier quotas? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clear_tier_quotas
            echo ""
            echo "✅ Tier quotas cleared!"
        else
            echo "❌ Cancelled."
        fi
        ;;
    tokens)
        show_counts
        read -p "Clear revoked tokens? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clear_revoked_tokens
            echo ""
            echo "✅ Revoked tokens cleared!"
        else
            echo "❌ Cancelled."
        fi
        ;;
    all)
        show_counts
        echo "⚠️  WARNING: This will clear ALL cache data!"
        read -p "Clear ALL cache? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clear_all
            echo ""
            echo "✅ All cache cleared!"
            echo "New total: $(redis-cli DBSIZE)"
        else
            echo "❌ Cancelled."
        fi
        ;;
    *)
        # Interactive menu
        show_counts
        echo "Select what to clear:"
        echo ""
        echo "  1) LLM cache (analyses & locks)"
        echo "  2) Rate limits"
        echo "  3) Tier quotas"
        echo "  4) Revoked tokens"
        echo "  5) ALL (everything)"
        echo "  q) Quit"
        echo ""
        read -p "Choice [1-5/q]: " -n 1 -r
        echo
        echo ""

        case $REPLY in
            1)
                clear_llm
                echo ""
                echo "✅ LLM cache cleared!"
                ;;
            2)
                clear_rate_limits
                echo ""
                echo "✅ Rate limits cleared!"
                ;;
            3)
                clear_tier_quotas
                echo ""
                echo "✅ Tier quotas cleared!"
                ;;
            4)
                clear_revoked_tokens
                echo ""
                echo "✅ Revoked tokens cleared!"
                ;;
            5)
                echo "⚠️  WARNING: This will clear ALL cache data!"
                read -p "Are you sure? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    clear_all
                    echo ""
                    echo "✅ All cache cleared!"
                else
                    echo "❌ Cancelled."
                fi
                ;;
            q|Q)
                echo "Bye!"
                exit 0
                ;;
            *)
                echo "❌ Invalid choice."
                exit 1
                ;;
        esac
        ;;
esac

echo ""
echo "New total: $(redis-cli DBSIZE)"
