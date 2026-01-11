#!/bin/bash
# Monitor Redis locks in real-time
# Useful for debugging stampede protection

set -e

echo "🔒 Redis Lock Monitor"
echo "===================="
echo ""
echo "Watching for active locks (Ctrl+C to stop)..."
echo ""

# Check if watch command exists
if ! command -v watch &> /dev/null; then
    echo "⚠️  'watch' command not found. Using alternative method..."
    echo ""

    while true; do
        clear
        echo "🔒 Active Locks ($(date '+%H:%M:%S'))"
        echo "================================"
        echo ""

        LOCKS=$(redis-cli KEYS "lock:*")

        if [ -z "$LOCKS" ]; then
            echo "✅ No active locks"
        else
            echo "$LOCKS" | while read -r lock; do
                if [ -n "$lock" ]; then
                    TTL=$(redis-cli TTL "$lock")
                    echo "🔐 $lock"
                    echo "   TTL: ${TTL}s"
                    echo ""
                fi
            done
        fi

        sleep 1
    done
else
    # Use watch for better display
    watch -n 1 '
        echo "🔒 Active Locks"
        echo "=============="
        echo ""
        LOCKS=$(redis-cli KEYS "lock:*")
        if [ -z "$LOCKS" ]; then
            echo "✅ No active locks"
        else
            echo "$LOCKS" | while read -r lock; do
                if [ -n "$lock" ]; then
                    TTL=$(redis-cli TTL "$lock")
                    echo "🔐 $lock (TTL: ${TTL}s)"
                fi
            done
        fi
        echo ""
        echo "Press Ctrl+C to stop"
    '
fi
