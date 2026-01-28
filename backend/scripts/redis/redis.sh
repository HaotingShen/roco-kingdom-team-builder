#!/bin/bash
# ============================================================================
# Redis Management Tool
# ============================================================================
# Unified interface for managing Redis cache in the Roco Kingdom Team Builder
#
# Usage:
#   ./redis.sh                  Show status overview
#   ./redis.sh stats            Show aggregate usage statistics
#   ./redis.sh show             Show all keys with values
#   ./redis.sh show <type>      Show keys of specific type
#   ./redis.sh clear            Interactive clear menu
#   ./redis.sh clear <type>     Clear specific key type
#   ./redis.sh clear all        Clear everything
#   ./redis.sh reset            Clear all (same as 'clear all', for DB reset)
#   ./redis.sh watch            Monitor locks/rate limits live
#
# <type>: cache, rate, quota, tokens
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Check Redis connection
check_redis() {
    if ! redis-cli ping > /dev/null 2>&1; then
        echo -e "${RED}Error: Cannot connect to Redis${NC}"
        echo ""
        echo "Start Redis with: sudo service redis-server start"
        exit 1
    fi
}

# Count keys matching pattern
count_keys() {
    redis-cli --scan --pattern "$1" 2>/dev/null | wc -l
}

# Clear keys matching pattern
clear_pattern() {
    local pattern="$1"
    local count=$(count_keys "$pattern")
    if [ "$count" -gt 0 ]; then
        redis-cli --scan --pattern "$pattern" | xargs -r redis-cli DEL > /dev/null 2>&1
        echo -e "  ${GREEN}✓${NC} Cleared $count keys: $pattern"
    fi
}

# ============================================================================
# STATUS COMMAND
# ============================================================================
cmd_status() {
    echo -e "${BOLD}Redis Status${NC}"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    # Connection
    echo -e "${GREEN}●${NC} Connected to Redis"
    echo ""

    # Counts with explanations
    local cache_monster=$(count_keys 'llm_cache:monster_trait:*')
    local cache_team=$(count_keys 'llm_cache:team_synergy:*')
    local locks=$(count_keys 'lock:*')
    local rate_team=$(count_keys 'ratelimit:analysis:*')
    local rate_global=$(count_keys 'ratelimit:global_ip:*')
    local quota_user=$(count_keys 'tier:user:*')
    local quota_anon_device=$(count_keys 'tier:anon:device:*')
    local quota_anon_ip=$(count_keys 'tier:anon:ip:*')
    local guest_create=$(count_keys 'tier:guest_create:*')
    local cap_device=$(count_keys 'tier:device:*')
    local cap_ip=$(count_keys 'tier:ip:*')
    local tokens=$(count_keys 'revoked_token:*')

    echo -e "${CYAN}LLM Cache${NC} ${DIM}(analysis results, 1hr TTL)${NC}"
    echo "  Monster analyses: $cache_monster"
    echo "  Team synergies:   $cache_team"
    [ "$locks" -gt 0 ] && echo -e "  Active locks:     $locks ${DIM}(in-progress analyses)${NC}"
    echo ""

    echo -e "${CYAN}Rate Limits${NC} ${DIM}(prevents spam, 2min TTL)${NC}"
    echo "  Per-team:   $rate_team"
    echo "  Per-IP:     $rate_global"
    echo ""

    echo -e "${CYAN}Usage Quotas${NC} ${DIM}(daily/monthly limits per tier)${NC}"
    echo -e "  Registered users: $quota_user ${DIM}(guest/free/premium)${NC}"
    echo -e "  Anonymous:        $((quota_anon_device + quota_anon_ip)) ${DIM}(device: $quota_anon_device, IP: $quota_anon_ip)${NC}"
    echo ""

    echo -e "${CYAN}Cross-Account Caps${NC} ${DIM}(daily limits across all accounts)${NC}"
    echo -e "  Device caps:    $cap_device ${DIM}(5/day per device)${NC}"
    echo -e "  IP caps:        $cap_ip ${DIM}(15/day fallback)${NC}"
    echo -e "  Guest creation: $guest_create ${DIM}(2/day per IP)${NC}"
    echo ""

    echo -e "${CYAN}Security${NC}"
    echo -e "  Revoked tokens: $tokens ${DIM}(logged-out sessions)${NC}"
    echo ""

    # Total
    local total=$(redis-cli DBSIZE)
    echo "────────────────────────────────────────────────────────────────────"
    echo -e "Total keys: ${BOLD}$total${NC}"
    echo ""
    echo -e "${DIM}Use './redis.sh show quota' for detailed usage counts${NC}"
}

# Sum all values for keys matching a pattern
sum_key_values() {
    local pattern="$1"
    local total=0
    local keys=$(redis-cli --scan --pattern "$pattern" 2>/dev/null)
    if [ -n "$keys" ]; then
        while read -r key; do
            if [ -n "$key" ]; then
                local val=$(redis-cli GET "$key" 2>/dev/null)
                if [[ "$val" =~ ^[0-9]+$ ]]; then
                    total=$((total + val))
                fi
            fi
        done <<< "$keys"
    fi
    echo "$total"
}

# ============================================================================
# STATS COMMAND - Show aggregate usage statistics
# ============================================================================
cmd_stats() {
    echo -e "${BOLD}Usage Statistics${NC}"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    # Today's date for filtering
    local today=$(date -u +%Y-%m-%d)
    local month=$(date -u +%Y-%m)

    echo -e "${CYAN}Today's Usage${NC} ${DIM}($today UTC)${NC}"
    echo ""

    # Registered users today
    local user_daily_total=$(sum_key_values "tier:user:*:daily:$today")
    local user_daily_count=$(count_keys "tier:user:*:daily:$today")
    echo -e "  Registered users: ${BOLD}$user_daily_total${NC} analyses ${DIM}($user_daily_count unique users)${NC}"

    # Anonymous today
    local anon_device_daily=$(sum_key_values "tier:anon:device:*:daily:$today")
    local anon_ip_daily=$(sum_key_values "tier:anon:ip:*:daily:$today")
    local anon_device_count=$(count_keys "tier:anon:device:*:daily:$today")
    local anon_ip_count=$(count_keys "tier:anon:ip:*:daily:$today")
    echo -e "  Anonymous:        ${BOLD}$anon_device_daily${NC} by device, ${BOLD}$anon_ip_daily${NC} by IP ${DIM}($anon_device_count devices, $anon_ip_count IPs)${NC}"

    # Guest creations today
    local guest_create_total=$(sum_key_values "tier:guest_create:ip:*:$today")
    local guest_create_ips=$(count_keys "tier:guest_create:ip:*:$today")
    echo -e "  Guest creations:  ${BOLD}$guest_create_total${NC} ${DIM}(from $guest_create_ips IPs)${NC}"

    # Cross-account caps today
    local cap_device_total=$(sum_key_values "tier:device:*:daily:$today")
    local cap_ip_total=$(sum_key_values "tier:ip:*:daily:$today")
    echo -e "  Device cap usage: ${BOLD}$cap_device_total${NC} (across all accounts)"
    echo -e "  IP cap usage:     ${BOLD}$cap_ip_total${NC} (across all accounts)"
    echo ""

    echo -e "${CYAN}This Month${NC} ${DIM}($month)${NC}"
    echo ""

    # Registered users this month
    local user_monthly_total=$(sum_key_values "tier:user:*:monthly:$month")
    local user_monthly_count=$(count_keys "tier:user:*:monthly:$month")
    echo -e "  Registered users: ${BOLD}$user_monthly_total${NC} analyses ${DIM}($user_monthly_count unique users)${NC}"

    # Anonymous this month
    local anon_device_monthly=$(sum_key_values "tier:anon:device:*:monthly:$month")
    local anon_ip_monthly=$(sum_key_values "tier:anon:ip:*:monthly:$month")
    echo -e "  Anonymous:        ${BOLD}$anon_device_monthly${NC} by device, ${BOLD}$anon_ip_monthly${NC} by IP"
    echo ""

    echo -e "${CYAN}Rate Limited Now${NC}"
    local rate_count=$(count_keys "ratelimit:global_ip:*")
    if [ "$rate_count" -eq 0 ]; then
        echo -e "  ${GREEN}No one is rate limited${NC}"
    else
        echo -e "  ${YELLOW}$rate_count IPs currently blocked${NC} (2min cooldown)"
    fi
    echo ""
}

# ============================================================================
# SHOW COMMAND
# ============================================================================
show_keys_with_ttl() {
    local pattern="$1"
    local limit="${2:-10}"
    local show_value="${3:-false}"  # Whether to show the stored value
    local keys=$(redis-cli --scan --pattern "$pattern" 2>/dev/null | head -$limit)

    if [ -z "$keys" ]; then
        echo -e "  ${DIM}(none)${NC}"
        return
    fi

    echo "$keys" | while read -r key; do
        if [ -n "$key" ]; then
            local ttl=$(redis-cli TTL "$key")
            local ttl_str=""
            if [ "$ttl" -gt 3600 ]; then
                ttl_str="$((ttl / 3600))h"
            elif [ "$ttl" -gt 60 ]; then
                ttl_str="$((ttl / 60))m"
            elif [ "$ttl" -gt 0 ]; then
                ttl_str="${ttl}s"
            else
                ttl_str="no TTL"
            fi
            # Shorten key for display
            local short_key=$(echo "$key" | sed 's/llm_cache:monster_trait:/cache:monster:/; s/llm_cache:team_synergy:/cache:team:/; s/ratelimit:analysis:/rate:team:/; s/ratelimit:global_ip:/rate:ip:/; s/tier:anon:device:/anon:device:/; s/tier:anon:ip:/anon:ip:/; s/tier:user:/user:/; s/tier:guest_create:ip:/guest_create:/; s/tier:device:/cap:device:/; s/tier:ip:/cap:ip:/')

            if [ "$show_value" = "true" ]; then
                local value=$(redis-cli GET "$key" 2>/dev/null)
                echo -e "  ${short_key} = ${BOLD}${value}${NC} ${DIM}(${ttl_str})${NC}"
            else
                echo -e "  ${short_key} ${DIM}(${ttl_str})${NC}"
            fi
        fi
    done
}

# Show quota keys with values and limits
show_quota_keys() {
    local pattern="$1"
    local limit="${2:-10}"
    local max_limit="$3"  # The tier limit (e.g., 5 for daily cap)
    local keys=$(redis-cli --scan --pattern "$pattern" 2>/dev/null | head -$limit)

    if [ -z "$keys" ]; then
        echo -e "  ${DIM}(none)${NC}"
        return
    fi

    echo "$keys" | while read -r key; do
        if [ -n "$key" ]; then
            local ttl=$(redis-cli TTL "$key")
            local value=$(redis-cli GET "$key" 2>/dev/null)
            local ttl_str=""
            if [ "$ttl" -gt 3600 ]; then
                ttl_str="$((ttl / 3600))h"
            elif [ "$ttl" -gt 60 ]; then
                ttl_str="$((ttl / 60))m"
            elif [ "$ttl" -gt 0 ]; then
                ttl_str="${ttl}s"
            else
                ttl_str="no TTL"
            fi

            # Shorten key for display - extract the identifier
            local short_key=$(echo "$key" | sed 's/llm_cache:monster_trait:/cache:monster:/; s/llm_cache:team_synergy:/cache:team:/; s/ratelimit:analysis:/rate:team:/; s/ratelimit:global_ip:/rate:ip:/; s/tier:anon:device:/anon:device:/; s/tier:anon:ip:/anon:ip:/; s/tier:user:/user:/; s/tier:guest_create:ip:/guest_create:/; s/tier:device:/cap:device:/; s/tier:ip:/cap:ip:/')

            # Color based on usage
            local usage_str=""
            if [ -n "$max_limit" ] && [ "$max_limit" != "0" ]; then
                if [ "$value" -ge "$max_limit" ]; then
                    usage_str="${RED}${value}/${max_limit}${NC}"
                elif [ "$value" -ge $((max_limit * 80 / 100)) ]; then
                    usage_str="${YELLOW}${value}/${max_limit}${NC}"
                else
                    usage_str="${GREEN}${value}/${max_limit}${NC}"
                fi
                echo -e "  ${short_key}: ${usage_str} ${DIM}(${ttl_str})${NC}"
            else
                echo -e "  ${short_key}: ${BOLD}${value}${NC} ${DIM}(${ttl_str})${NC}"
            fi
        fi
    done
}

cmd_show() {
    local type="${1:-all}"

    echo -e "${BOLD}Redis Keys${NC}"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    case "$type" in
        cache|llm)
            echo -e "${CYAN}LLM Cache${NC}"
            echo -e "${DIM}Cached analysis results. Same team = instant response (no LLM call).${NC}"
            echo ""
            echo "Monster Analyses ($(count_keys 'llm_cache:monster_trait:*')):"
            show_keys_with_ttl "llm_cache:monster_trait:*" 5
            echo ""
            echo "Team Synergies ($(count_keys 'llm_cache:team_synergy:*')):"
            show_keys_with_ttl "llm_cache:team_synergy:*" 5
            echo ""
            echo "Locks ($(count_keys 'lock:*')):"
            show_keys_with_ttl "lock:*" 5
            ;;
        rate)
            echo -e "${CYAN}Rate Limits${NC}"
            echo -e "${DIM}Prevents rapid-fire requests. Resets after 2 minutes.${NC}"
            echo ""
            echo "Per-Team ($(count_keys 'ratelimit:analysis:*')):"
            echo -e "${DIM}Same team = blocked for 2min (use cache instead)${NC}"
            show_keys_with_ttl "ratelimit:analysis:*" 10
            echo ""
            echo "Per-IP ($(count_keys 'ratelimit:global_ip:*')):"
            echo -e "${DIM}Any analysis = blocked for 2min${NC}"
            show_keys_with_ttl "ratelimit:global_ip:*" 10
            ;;
        quota|tier)
            echo -e "${CYAN}Usage Quotas${NC}"
            echo -e "${DIM}Daily/monthly analysis limits. Format: used/limit${NC}"
            echo ""
            echo -e "${YELLOW}── Registered Users (guest/free/premium) ──${NC}"
            echo ""
            echo "Daily ($(count_keys 'tier:user:*:daily:*')):"
            echo -e "${DIM}Limit depends on tier: guest=3, free=5, premium=20${NC}"
            show_quota_keys "tier:user:*:daily:*" 10
            echo ""
            echo "Monthly ($(count_keys 'tier:user:*:monthly:*')):"
            echo -e "${DIM}Limit depends on tier: guest=30, free=100, premium=500${NC}"
            show_quota_keys "tier:user:*:monthly:*" 10
            echo ""
            echo -e "${YELLOW}── Anonymous (no account) ──${NC}"
            echo ""
            echo "Daily by Device ($(count_keys 'tier:anon:device:*:daily:*')):"
            show_quota_keys "tier:anon:device:*:daily:*" 10 1
            echo ""
            echo "Daily by IP ($(count_keys 'tier:anon:ip:*:daily:*')):"
            show_quota_keys "tier:anon:ip:*:daily:*" 10 1
            echo ""
            echo "Monthly by Device ($(count_keys 'tier:anon:device:*:monthly:*')):"
            show_quota_keys "tier:anon:device:*:monthly:*" 10 5
            echo ""
            echo "Monthly by IP ($(count_keys 'tier:anon:ip:*:monthly:*')):"
            show_quota_keys "tier:anon:ip:*:monthly:*" 10 5
            echo ""
            echo -e "${YELLOW}── Cross-Account Caps ──${NC}"
            echo -e "${DIM}Limits across ALL accounts on same device/IP${NC}"
            echo ""
            echo "Device Daily ($(count_keys 'tier:device:*')):"
            show_quota_keys "tier:device:*" 10 5
            echo ""
            echo "IP Daily ($(count_keys 'tier:ip:*')):"
            show_quota_keys "tier:ip:*" 10 15
            echo ""
            echo -e "${YELLOW}── Guest Creation ──${NC}"
            echo ""
            echo "Per IP ($(count_keys 'tier:guest_create:*')):"
            echo -e "${DIM}Prevents 'Clear Guest Data' abuse${NC}"
            show_quota_keys "tier:guest_create:*" 10 2
            ;;
        tokens)
            echo -e "${CYAN}Revoked Tokens${NC}"
            echo -e "${DIM}Logged-out JWT tokens. Prevents reuse until expiry.${NC}"
            echo ""
            echo "Revoked ($(count_keys 'revoked_token:*')):"
            show_keys_with_ttl "revoked_token:*" 20
            ;;
        all|*)
            echo -e "${CYAN}All Keys by Type${NC}"
            echo ""
            echo "LLM Cache ($(count_keys 'llm_cache:*')):"
            echo -e "${DIM}Cached analysis results → instant repeat requests${NC}"
            show_keys_with_ttl "llm_cache:*" 3
            echo ""
            echo "Rate Limits ($(count_keys 'ratelimit:*')):"
            echo -e "${DIM}Spam prevention → 2min cooldown per analysis${NC}"
            show_keys_with_ttl "ratelimit:*" 3 "true"
            echo ""
            local quota_user=$(count_keys 'tier:user:*')
            local quota_anon=$(( $(count_keys 'tier:anon:device:*') + $(count_keys 'tier:anon:ip:*') ))
            local caps=$(( $(count_keys 'tier:device:*') + $(count_keys 'tier:ip:*') + $(count_keys 'tier:guest_create:*') ))
            echo "Quotas ($(count_keys 'tier:*')):"
            echo -e "${DIM}User: $quota_user | Anonymous: $quota_anon | Caps: $caps (use 'show quota' for details)${NC}"
            show_quota_keys "tier:*" 5
            echo ""
            echo "Tokens ($(count_keys 'revoked_token:*')):"
            echo -e "${DIM}Logout tracking → prevents token reuse${NC}"
            show_keys_with_ttl "revoked_token:*" 3
            ;;
    esac
    echo ""
}

# ============================================================================
# CLEAR COMMAND
# ============================================================================
cmd_clear() {
    local type="${1:-menu}"

    echo -e "${BOLD}Clear Redis Keys${NC}"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    case "$type" in
        cache|llm)
            echo "Clearing LLM cache..."
            clear_pattern "llm_cache:monster_trait:*"
            clear_pattern "llm_cache:team_synergy:*"
            clear_pattern "lock:*"
            echo -e "\n${GREEN}Done!${NC} New analyses will call LLM (not cached)."
            ;;
        rate)
            echo "Clearing rate limits..."
            clear_pattern "ratelimit:analysis:*"
            clear_pattern "ratelimit:global_ip:*"
            echo -e "\n${GREEN}Done!${NC} Users can analyze immediately."
            ;;
        quota|tier)
            echo "Clearing usage quotas..."
            clear_pattern "tier:user:*"
            clear_pattern "tier:anon:device:*"
            clear_pattern "tier:anon:ip:*"
            clear_pattern "tier:guest_create:*"
            clear_pattern "tier:device:*"
            clear_pattern "tier:ip:*"
            echo -e "\n${GREEN}Done!${NC} All quotas and caps reset to 0."
            ;;
        tokens)
            echo "Clearing revoked tokens..."
            clear_pattern "revoked_token:*"
            echo -e "\n${GREEN}Done!${NC} Warning: Logged-out tokens can now be reused!"
            ;;
        all|reset)
            echo -e "${YELLOW}This will clear ALL Redis data:${NC}"
            echo "  - LLM cache (analyses must be regenerated)"
            echo "  - Rate limits (users can spam requests)"
            echo "  - Quotas (monthly limits reset)"
            echo "  - Tokens (logged-out sessions become valid)"
            echo ""
            read -p "Type 'yes' to confirm: " confirm
            if [ "$confirm" = "yes" ]; then
                echo ""
                clear_pattern "llm_cache:*"
                clear_pattern "lock:*"
                clear_pattern "ratelimit:*"
                clear_pattern "tier:*"
                clear_pattern "revoked_token:*"
                echo -e "\n${GREEN}Done!${NC} Redis is now empty."
            else
                echo -e "\n${YELLOW}Cancelled.${NC}"
            fi
            ;;
        menu|*)
            echo "What to clear?"
            echo ""
            echo "  1) cache   - LLM analysis results (forces new LLM calls)"
            echo "  2) rate    - Rate limits (removes 2min cooldowns)"
            echo "  3) quota   - Usage quotas (resets monthly limits)"
            echo "  4) tokens  - Revoked tokens (security risk!)"
            echo "  5) all     - Everything"
            echo "  q) Cancel"
            echo ""
            read -p "Choice: " choice
            echo ""
            case "$choice" in
                1|cache) cmd_clear cache ;;
                2|rate) cmd_clear rate ;;
                3|quota) cmd_clear quota ;;
                4|tokens) cmd_clear tokens ;;
                5|all) cmd_clear all ;;
                *) echo "Cancelled." ;;
            esac
            ;;
    esac
    echo ""
}

# ============================================================================
# WATCH COMMAND
# ============================================================================
cmd_watch() {
    echo -e "${BOLD}Watching Redis${NC} (Ctrl+C to stop)"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    while true; do
        clear
        echo -e "${BOLD}Redis Live Monitor${NC} $(date '+%H:%M:%S')"
        echo "════════════════════════════════════════════════════════════════════"
        echo ""

        # Active locks
        echo -e "${CYAN}Active Locks${NC} ${DIM}(in-progress LLM calls)${NC}"
        local locks=$(redis-cli --scan --pattern "lock:*" 2>/dev/null)
        if [ -z "$locks" ]; then
            echo -e "  ${GREEN}None${NC} - no analyses in progress"
        else
            echo "$locks" | while read -r key; do
                local ttl=$(redis-cli TTL "$key")
                echo -e "  ${YELLOW}●${NC} $key (${ttl}s)"
            done
        fi
        echo ""

        # Rate limits
        echo -e "${CYAN}Rate Limits${NC} ${DIM}(blocked users)${NC}"
        local rates=$(redis-cli --scan --pattern "ratelimit:global_ip:*" 2>/dev/null)
        if [ -z "$rates" ]; then
            echo -e "  ${GREEN}None${NC} - no one is rate limited"
        else
            echo "$rates" | while read -r key; do
                local ttl=$(redis-cli TTL "$key")
                local ip=$(echo "$key" | sed 's/ratelimit:global_ip://')
                echo -e "  ${RED}●${NC} $ip blocked for ${ttl}s"
            done
        fi
        echo ""

        echo "────────────────────────────────────────────────────────────────────"
        echo "Press Ctrl+C to stop"

        sleep 1
    done
}

# ============================================================================
# HELP
# ============================================================================
cmd_help() {
    echo -e "${BOLD}Redis Management Tool${NC}"
    echo ""
    echo "Usage: ./redis.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  (none), status  Show overview of all Redis data"
    echo "  stats           Show aggregate usage statistics (totals)"
    echo "  show [type]     Show individual keys with values"
    echo "  clear [type]    Clear keys (interactive if no type)"
    echo "  reset           Clear all keys (alias for 'clear all')"
    echo "  watch           Monitor locks/rate limits in real-time"
    echo "  help            Show this help"
    echo ""
    echo "Types for show/clear:"
    echo "  cache    LLM analysis results"
    echo "  rate     Rate limit cooldowns"
    echo "  quota    Usage quotas and caps"
    echo "  tokens   Revoked JWT tokens"
    echo "  all      Everything"
    echo ""
    echo "Examples:"
    echo "  ./redis.sh                    # Status overview"
    echo "  ./redis.sh stats              # See total analyses today/month"
    echo "  ./redis.sh show quota         # See per-user/device usage"
    echo "  ./redis.sh clear rate         # Remove rate limits"
    echo "  ./redis.sh reset              # Clear everything"
}

# ============================================================================
# MAIN
# ============================================================================
check_redis

case "${1:-status}" in
    status|s)
        cmd_status
        ;;
    stats)
        cmd_stats
        ;;
    show|list|ls)
        cmd_show "$2"
        ;;
    clear|rm|delete)
        cmd_clear "$2"
        ;;
    reset)
        cmd_clear all
        ;;
    watch|monitor)
        cmd_watch
        ;;
    help|-h|--help)
        cmd_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        cmd_help
        exit 1
        ;;
esac
