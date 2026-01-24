# Redis Helper Scripts

Collection of utility scripts for managing Redis cache during development and testing.

## Redis Key Namespaces

The application uses Redis for multiple purposes, organized by namespace:

| Namespace | Purpose | TTL | Example Key |
|-----------|---------|-----|-------------|
| `llm_cache:monster_trait:` | Monster trait analyses | 1 hour | `llm_cache:monster_trait:a1b2c3...` |
| `llm_cache:team_synergy:` | Team synergy analyses | 1 hour | `llm_cache:team_synergy:d4e5f6...` |
| `lock:` | Stampede protection locks | 30 sec | `lock:llm_cache:monster_trait:...` |
| `ratelimit:analysis:` | Per-team analysis rate limit | 2 min | `ratelimit:analysis:192.168.1.1:abc123` |
| `ratelimit:global_ip:` | Global IP rate limit | 2 min | `ratelimit:global_ip:192.168.1.1` |
| `tier:user:` | User analysis quotas | 24h/30d | `tier:user:123:daily:2024-01-15` |
| `tier:anon:device:` | Anonymous device quotas | 24h | `tier:anon:device:xyz:daily:2024-01-15` |
| `tier:anon:ip:` | Anonymous IP quotas | 24h | `tier:anon:ip:192.168.1.1:daily:...` |
| `tier:guest_create:` | Guest creation rate limit | 24h | `tier:guest_create:ip:192.168.1.1:...` |
| `revoked_token:` | Revoked JWT tokens | Token exp | `revoked_token:jti-abc123...` |

## Prerequisites

- Redis server installed and running
- `redis-cli` command available in PATH
- Bash shell (Linux/macOS/WSL2)

## Scripts

### 1. `check_connection.sh`
**Check Redis server status and configuration**

```bash
./check_connection.sh
```

Use this first to verify Redis is running and properly configured.

---

### 2. `stats.sh`
**Display comprehensive cache statistics**

```bash
./stats.sh
```

Shows:
- Connection status
- Key counts by namespace (LLM cache, rate limits, tier quotas, tokens)
- Memory usage
- Cache hit rate
- Keyspace information
- Server uptime

---

### 3. `clear_cache.sh`
**Clear Redis cache with selective options**

```bash
# Interactive menu
./clear_cache.sh

# Clear specific namespace
./clear_cache.sh llm       # LLM cache only
./clear_cache.sh rate      # Rate limits only
./clear_cache.sh tier      # Tier quotas only
./clear_cache.sh tokens    # Revoked tokens only
./clear_cache.sh all       # Everything (with confirmation)
```

**When to clear:**
- `llm`: Changed analysis prompts, modified LLM logic, updated game data
- `rate`: Testing rate limiting, user reported stuck rate limit
- `tier`: Reset user quotas for testing
- `tokens`: Clear expired token revocations (usually not needed)
- `all`: Full reset for clean testing

---

### 4. `inspect_latest.sh`
**Inspect Redis keys with detailed information**

```bash
# Show latest LLM cache entry
./inspect_latest.sh

# Show specific namespace
./inspect_latest.sh llm       # LLM cache summary
./inspect_latest.sh rate      # Rate limit keys
./inspect_latest.sh tier      # Tier quota keys
./inspect_latest.sh tokens    # Revoked tokens

# Inspect specific key
./inspect_latest.sh key "llm_cache:monster_trait:abc123"
```

Displays:
- Key name and type
- TTL remaining
- Formatted value (JSON prettified)
- Summary counts

---

### 5. `monitor_locks.sh`
**Watch locks and rate limits in real-time**

```bash
# Monitor everything
./monitor_locks.sh

# Monitor specific type
./monitor_locks.sh locks    # Locks only
./monitor_locks.sh rate     # Rate limits only
```

Live monitoring useful for:
- Debugging stampede protection
- Verifying rate limit enforcement
- Testing concurrent requests

Press `Ctrl+C` to stop.

---

### 6. `export_keys.sh`
**Export Redis keys to a file**

```bash
# Export keys only (timestamped filename)
./export_keys.sh

# Export to specific file
./export_keys.sh backup.txt

# Export with values (JSON format)
./export_keys.sh --values backup.json
```

Creates a file with all cache keys, with breakdown by namespace.

---

## Quick Start

```bash
# 1. Check Redis is running
./check_connection.sh

# 2. View current cache stats
./stats.sh

# 3. Run your analysis (via frontend or API)

# 4. Inspect what was cached
./inspect_latest.sh

# 5. Monitor locks during concurrent requests
./monitor_locks.sh

# 6. Clear cache before testing new prompt
./clear_cache.sh llm
```

## Common Workflows

### Workflow 1: Testing New Analysis Prompt

```bash
# Clear old LLM cache
./clear_cache.sh llm

# Start server (in another terminal)
# uvicorn backend.main:app --reload --env-file backend/.env

# Run analysis via frontend

# Verify new cache
./inspect_latest.sh
```

### Workflow 2: Debugging Rate Limiting

```bash
# Terminal 1: Monitor rate limits
./monitor_locks.sh rate

# Terminal 2: Make API requests
# You should see rate limit keys appear with TTL

# Clear rate limits if stuck
./clear_cache.sh rate
```

### Workflow 3: Debugging Stampede Protection

```bash
# Terminal 1: Monitor locks
./monitor_locks.sh locks

# Terminal 2: Send multiple concurrent requests
# You should see locks appear/disappear

# What to look for:
# - Locks should appear briefly (< 30 seconds)
# - Multiple concurrent requests should share same lock
# - Lock should disappear after analysis completes
```

### Workflow 4: Testing User Quotas

```bash
# Check current tier quotas
./inspect_latest.sh tier

# Clear quotas for fresh testing
./clear_cache.sh tier

# Run analyses and check quota keys
./stats.sh
```

### Workflow 5: Performance Monitoring

```bash
# Clear cache for clean test
./clear_cache.sh all

# Run test suite / load test

# Check performance
./stats.sh
# Look at "Cache Performance" section for hit rate
```

## Making Scripts Executable

If you get "Permission denied" errors:

```bash
chmod +x *.sh
```

Or run with bash:

```bash
bash stats.sh
```

## Troubleshooting

**"redis-cli: command not found"**
```bash
# Install Redis tools
sudo apt install redis-tools
```

**"Cannot connect to Redis"**
```bash
# Start Redis server
sudo service redis-server start

# Or using Docker
docker start redis
```

**"No keys in cache"**
- Run an analysis via the frontend first
- Check if Redis is connected (see backend logs)
- Verify `REDIS_URL` in `.env` file

## Advanced Usage

### Direct Redis Commands

All scripts use `redis-cli` internally. You can run commands directly:

```bash
# Get all LLM cache keys
redis-cli --scan --pattern "llm_cache:*"

# Count rate limit keys
redis-cli --scan --pattern "ratelimit:*" | wc -l

# Check specific key TTL
redis-cli TTL "ratelimit:global_ip:192.168.1.1"

# Delete specific key
redis-cli DEL "tier:user:123:daily:2024-01-15"

# Monitor all commands (real-time)
redis-cli MONITOR
```

### Key Patterns Reference

```bash
# LLM Cache
redis-cli --scan --pattern "llm_cache:monster_trait:*"
redis-cli --scan --pattern "llm_cache:team_synergy:*"
redis-cli --scan --pattern "lock:*"

# Rate Limiting
redis-cli --scan --pattern "ratelimit:analysis:*"
redis-cli --scan --pattern "ratelimit:global_ip:*"

# Tier Quotas
redis-cli --scan --pattern "tier:user:*"
redis-cli --scan --pattern "tier:anon:device:*"
redis-cli --scan --pattern "tier:anon:ip:*"
redis-cli --scan --pattern "tier:guest_create:*"

# Token Revocation
redis-cli --scan --pattern "revoked_token:*"
```

## Environment Variables

Scripts use default Redis connection (`localhost:6379`).

To use different Redis instance:

```bash
# Set REDIS_CLI_URL environment variable
export REDIS_CLI_URL="redis://custom-host:6380"

# Or modify scripts to use -h and -p flags
redis-cli -h custom-host -p 6380 --scan --pattern "*"
```

## Safety Notes

**Production Usage:**
- Never use `KEYS *` in production (blocks server) - scripts use `SCAN` instead
- Be careful with `clear_cache.sh all` - clears everything
- `tier` clearing resets user quotas
- `tokens` clearing invalidates token revocations (security implications)

**Development Usage:**
- Safe to use all scripts
- Clear LLM cache frequently when testing prompts
- Monitor locks to verify stampede protection
- Export keys before major changes

## Integration

Add to your development scripts:

```bash
# Before running tests
./backend/scripts/redis/clear_cache.sh llm

# After deployment (backup)
./backend/scripts/redis/export_keys.sh backup_$(date +%Y%m%d).txt

# CI/CD pre-test step
./backend/scripts/redis/check_connection.sh || exit 1
```
