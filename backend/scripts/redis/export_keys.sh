#!/bin/bash
# Export Redis keys to a file for backup or inspection
# Includes breakdown by namespace
#
# Usage:
#   ./export_keys.sh                  # Export to timestamped file
#   ./export_keys.sh backup.txt       # Export to specific file
#   ./export_keys.sh --values backup  # Export keys WITH values (JSON)

set -e

INCLUDE_VALUES=false
OUTPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --values)
            INCLUDE_VALUES=true
            shift
            ;;
        *)
            OUTPUT_FILE="$1"
            shift
            ;;
    esac
done

# Set default filename if not provided
if [ -z "$OUTPUT_FILE" ]; then
    if [ "$INCLUDE_VALUES" = true ]; then
        OUTPUT_FILE="redis_export_$(date +%Y%m%d_%H%M%S).json"
    else
        OUTPUT_FILE="redis_keys_$(date +%Y%m%d_%H%M%S).txt"
    fi
fi

echo "📤 Redis Keys Export"
echo "==================="
echo ""

# Check connection
PING=$(redis-cli ping 2>&1)
if [ "$PING" != "PONG" ]; then
    echo "❌ Cannot connect to Redis"
    exit 1
fi

# Get total keys
TOTAL=$(redis-cli DBSIZE | awk '{print $2}')

if [ "$TOTAL" = "0" ]; then
    echo "❌ No keys to export (cache is empty)"
    exit 1
fi

echo "Exporting $TOTAL keys to: $OUTPUT_FILE"
echo "Include values: $INCLUDE_VALUES"
echo ""

if [ "$INCLUDE_VALUES" = true ]; then
    # Export with values as JSON
    echo "{" > "$OUTPUT_FILE"
    echo "  \"exported_at\": \"$(date -Iseconds)\"," >> "$OUTPUT_FILE"
    echo "  \"total_keys\": $TOTAL," >> "$OUTPUT_FILE"
    echo "  \"keys\": {" >> "$OUTPUT_FILE"

    FIRST=true
    redis-cli --scan --pattern "*" | while read -r key; do
        if [ -n "$key" ]; then
            VALUE=$(redis-cli GET "$key" 2>/dev/null | sed 's/"/\\"/g' | tr '\n' ' ')
            TTL=$(redis-cli TTL "$key")

            if [ "$FIRST" = true ]; then
                FIRST=false
            else
                echo "," >> "$OUTPUT_FILE"
            fi

            printf '    "%s": {"value": "%s", "ttl": %s}' "$key" "$VALUE" "$TTL" >> "$OUTPUT_FILE"
        fi
    done

    echo "" >> "$OUTPUT_FILE"
    echo "  }" >> "$OUTPUT_FILE"
    echo "}" >> "$OUTPUT_FILE"
else
    # Export keys only
    redis-cli --scan --pattern "*" > "$OUTPUT_FILE"
fi

echo "✅ Export complete!"
echo ""

# Show breakdown
echo "📊 Key breakdown:"
echo ""

# LLM Cache
LLM_MONSTER=$(grep -c "llm_cache:monster_trait:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
LLM_TEAM=$(grep -c "llm_cache:team_synergy:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
LOCKS=$(grep -c "^lock:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "  📚 LLM Cache:"
echo "     Monster analyses: $LLM_MONSTER"
echo "     Team synergies:   $LLM_TEAM"
echo "     Locks:            $LOCKS"
echo ""

# Rate Limits
RATE_ANALYSIS=$(grep -c "ratelimit:analysis:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
RATE_GLOBAL=$(grep -c "ratelimit:global_ip:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "  ⏱️  Rate Limits:"
echo "     Per-team analysis: $RATE_ANALYSIS"
echo "     Global IP:         $RATE_GLOBAL"
echo ""

# Tier Quotas
TIER_USER=$(grep -c "tier:user:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
TIER_ANON_DEVICE=$(grep -c "tier:anon:device:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
TIER_ANON_IP=$(grep -c "tier:anon:ip:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
TIER_GUEST=$(grep -c "tier:guest_create:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "  📈 Tier Quotas:"
echo "     User quotas:     $TIER_USER"
echo "     Anon device:     $TIER_ANON_DEVICE"
echo "     Anon IP:         $TIER_ANON_IP"
echo "     Guest creation:  $TIER_GUEST"
echo ""

# Token Revocation
TOKENS=$(grep -c "revoked_token:" "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "  🔐 Token Revocation:"
echo "     Revoked tokens:  $TOKENS"
echo ""

echo "───────────────────────────────"
echo "File: $OUTPUT_FILE"
if [ "$INCLUDE_VALUES" = true ]; then
    echo "Size: $(wc -c < "$OUTPUT_FILE" | tr -d ' ') bytes"
else
    echo "Lines: $(wc -l < "$OUTPUT_FILE" | tr -d ' ')"
fi
