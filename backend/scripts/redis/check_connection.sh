#!/bin/bash
# Check Redis connection and server status

set -e

echo "🔌 Redis Connection Check"
echo "========================="
echo ""

# Test connection
echo "Testing connection to Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo "  ✅ Redis is running and responding"
else
    echo "  ❌ Cannot connect to Redis"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if Redis is running:"
    echo "     sudo service redis-server status"
    echo ""
    echo "  2. Start Redis:"
    echo "     sudo service redis-server start"
    echo ""
    echo "  3. Check Redis logs:"
    echo "     sudo tail -f /var/log/redis/redis-server.log"
    exit 1
fi
echo ""

# Server info
echo "📋 Server Info:"
redis-cli INFO server | grep -E "redis_version|os|process_id|tcp_port" | sed 's/^/  /'
echo ""

# Configuration
echo "⚙️  Configuration:"
MAXMEMORY=$(redis-cli CONFIG GET maxmemory | tail -1)
MAXMEMORY_POLICY=$(redis-cli CONFIG GET maxmemory-policy | tail -1)

if [ "$MAXMEMORY" = "0" ]; then
    echo "  Max memory: Unlimited"
else
    echo "  Max memory: $MAXMEMORY bytes"
fi
echo "  Eviction policy: $MAXMEMORY_POLICY"
echo ""

# Current usage
echo "💾 Current Usage:"
redis-cli INFO memory | grep -E "used_memory_human|used_memory_peak_human" | sed 's/^/  /'
echo ""

# Database info
echo "🗄️  Database:"
DB_SIZE=$(redis-cli DBSIZE)
echo "  Total keys: $DB_SIZE"

if [ "$DB_SIZE" -gt 0 ]; then
    redis-cli INFO keyspace | grep -E "^db" | sed 's/^/  /'
fi
echo ""

echo "✅ Redis is healthy and ready!"
