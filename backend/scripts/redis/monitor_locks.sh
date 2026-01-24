#!/bin/bash
# Monitor Redis locks and rate limits in real-time
# Useful for debugging stampede protection and rate limiting
#
# Usage:
#   ./monitor_locks.sh           # Monitor all (locks + rate limits)
#   ./monitor_locks.sh locks     # Monitor locks only
#   ./monitor_locks.sh rate      # Monitor rate limits only

set -e

MODE="${1:-all}"

echo "🔒 Redis Lock & Rate Limit Monitor"
echo "==================================="
echo ""
echo "Mode: $MODE"
echo "Watching (Ctrl+C to stop)..."
echo ""

# Function to display status
display_status() {
    echo "🔒 Active Locks ($(date '+%H:%M:%S'))"
    echo "================================"
    echo ""

    if [ "$MODE" = "all" ] || [ "$MODE" = "locks" ]; then
        echo "📚 LLM Cache Locks:"
        LOCKS=$(redis-cli --scan --pattern "lock:*" 2>/dev/null)
        if [ -z "$LOCKS" ]; then
            echo "  ✅ No active locks"
        else
            echo "$LOCKS" | while read -r lock; do
                if [ -n "$lock" ]; then
                    TTL=$(redis-cli TTL "$lock")
                    echo "  🔐 $lock (TTL: ${TTL}s)"
                fi
            done
        fi
        echo ""
    fi

    if [ "$MODE" = "all" ] || [ "$MODE" = "rate" ]; then
        echo "⏱️  Rate Limits:"

        # Global IP rate limits
        GLOBAL=$(redis-cli --scan --pattern "ratelimit:global_ip:*" 2>/dev/null)
        if [ -n "$GLOBAL" ]; then
            echo "  Global IP:"
            echo "$GLOBAL" | while read -r key; do
                if [ -n "$key" ]; then
                    TTL=$(redis-cli TTL "$key")
                    IP=$(echo "$key" | sed 's/ratelimit:global_ip://')
                    echo "    🌐 $IP (${TTL}s remaining)"
                fi
            done
        fi

        # Per-team analysis rate limits
        ANALYSIS=$(redis-cli --scan --pattern "ratelimit:analysis:*" 2>/dev/null)
        if [ -n "$ANALYSIS" ]; then
            echo "  Per-Team Analysis:"
            echo "$ANALYSIS" | head -5 | while read -r key; do
                if [ -n "$key" ]; then
                    TTL=$(redis-cli TTL "$key")
                    echo "    📊 ...${key: -40} (${TTL}s)"
                fi
            done
            COUNT=$(echo "$ANALYSIS" | wc -l)
            if [ "$COUNT" -gt 5 ]; then
                echo "    ... and $((COUNT - 5)) more"
            fi
        fi

        if [ -z "$GLOBAL" ] && [ -z "$ANALYSIS" ]; then
            echo "  ✅ No active rate limits"
        fi
        echo ""
    fi

    echo "───────────────────────────────"
    echo "Press Ctrl+C to stop"
}

# Check if watch command exists
if ! command -v watch &> /dev/null; then
    echo "⚠️  'watch' command not found. Using alternative method..."
    echo ""

    while true; do
        clear
        display_status
        sleep 1
    done
else
    # Use watch for better display
    export -f display_status 2>/dev/null || true
    export MODE

    watch -n 1 "
        echo '🔒 Active Locks (\$(date \"+%H:%M:%S\"))'
        echo '================================'
        echo ''

        if [ '$MODE' = 'all' ] || [ '$MODE' = 'locks' ]; then
            echo '📚 LLM Cache Locks:'
            LOCKS=\$(redis-cli --scan --pattern 'lock:*' 2>/dev/null)
            if [ -z \"\$LOCKS\" ]; then
                echo '  ✅ No active locks'
            else
                echo \"\$LOCKS\" | while read -r lock; do
                    if [ -n \"\$lock\" ]; then
                        TTL=\$(redis-cli TTL \"\$lock\")
                        echo \"  🔐 \$lock (TTL: \${TTL}s)\"
                    fi
                done
            fi
            echo ''
        fi

        if [ '$MODE' = 'all' ] || [ '$MODE' = 'rate' ]; then
            echo '⏱️  Rate Limits:'

            GLOBAL=\$(redis-cli --scan --pattern 'ratelimit:global_ip:*' 2>/dev/null)
            if [ -n \"\$GLOBAL\" ]; then
                echo '  Global IP:'
                echo \"\$GLOBAL\" | while read -r key; do
                    if [ -n \"\$key\" ]; then
                        TTL=\$(redis-cli TTL \"\$key\")
                        IP=\$(echo \"\$key\" | sed 's/ratelimit:global_ip://')
                        echo \"    🌐 \$IP (\${TTL}s remaining)\"
                    fi
                done
            fi

            ANALYSIS=\$(redis-cli --scan --pattern 'ratelimit:analysis:*' 2>/dev/null)
            if [ -n \"\$ANALYSIS\" ]; then
                echo '  Per-Team Analysis:'
                echo \"\$ANALYSIS\" | head -5 | while read -r key; do
                    if [ -n \"\$key\" ]; then
                        TTL=\$(redis-cli TTL \"\$key\")
                        echo \"    📊 ...\${key: -40} (\${TTL}s)\"
                    fi
                done
                COUNT=\$(echo \"\$ANALYSIS\" | wc -l)
                if [ \"\$COUNT\" -gt 5 ]; then
                    echo \"    ... and \$((COUNT - 5)) more\"
                fi
            fi

            if [ -z \"\$GLOBAL\" ] && [ -z \"\$ANALYSIS\" ]; then
                echo '  ✅ No active rate limits'
            fi
            echo ''
        fi

        echo '───────────────────────────────'
        echo 'Press Ctrl+C to stop'
    "
fi
