#!/bin/bash
# Export all Redis keys to a file for backup or inspection

set -e

OUTPUT_FILE="${1:-redis_keys_$(date +%Y%m%d_%H%M%S).txt}"

echo "📤 Redis Keys Export"
echo "==================="
echo ""

# Get total keys
TOTAL=$(redis-cli DBSIZE)

if [ "$TOTAL" -eq 0 ]; then
    echo "❌ No keys to export (cache is empty)"
    exit 1
fi

echo "Exporting $TOTAL keys to: $OUTPUT_FILE"
echo ""

# Export all keys
redis-cli KEYS "*" > "$OUTPUT_FILE"

echo "✅ Export complete!"
echo ""
echo "📊 Key breakdown:"
echo "  Monster analyses: $(grep -c "monster_trait:" "$OUTPUT_FILE" || echo 0)"
echo "  Team synergies: $(grep -c "team_synergy:" "$OUTPUT_FILE" || echo 0)"
echo "  Locks: $(grep -c "^lock:" "$OUTPUT_FILE" || echo 0)"
echo ""
echo "File: $OUTPUT_FILE"
echo "Size: $(wc -l < "$OUTPUT_FILE") lines"
