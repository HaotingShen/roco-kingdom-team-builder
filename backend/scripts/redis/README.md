# Redis Helper Scripts

Collection of utility scripts for managing Redis cache during development and testing.

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
- Key counts by type
- Memory usage
- Cache hit rate
- Keyspace information
- Server uptime

Use this to monitor cache performance and size.

---

### 3. `clear_cache.sh`
**Clear all analysis cache**

```bash
./clear_cache.sh
```

Removes:
- All monster trait analyses
- All team synergies
- All active locks

⚠️ **Use when:**
- Changed analysis prompts
- Modified LLM logic
- Updated game data
- Testing cache behavior

---

### 4. `inspect_latest.sh`
**View the most recent cached analysis**

```bash
./inspect_latest.sh
```

Displays:
- Cache key
- Time to live (TTL)
- Full JSON value (formatted)
- Summary of all cached items

Useful for verifying cache content and debugging.

---

### 5. `monitor_locks.sh`
**Watch active locks in real-time**

```bash
./monitor_locks.sh
```

Live monitoring of distributed locks (stampede protection).

**What to look for:**
- Locks should appear briefly (< 30 seconds)
- Multiple concurrent requests should show same lock
- Lock should disappear after analysis completes

Press `Ctrl+C` to stop.

---

### 6. `export_keys.sh`
**Export all Redis keys to a file**

```bash
# Export to default filename (timestamped)
./export_keys.sh

# Export to specific file
./export_keys.sh my_keys.txt
```

Creates a text file with all cache keys for backup or inspection.

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
./clear_cache.sh
```

## Common Workflows

### Workflow 1: Testing New Analysis Prompt

```bash
# Clear old cache
./clear_cache.sh

# Start server
# (in another terminal: uvicorn backend.main:app --reload)

# Run analysis via frontend

# Verify new cache
./inspect_latest.sh
```

### Workflow 2: Debugging Stampede Protection

```bash
# Terminal 1: Monitor locks
./monitor_locks.sh

# Terminal 2: Send multiple concurrent requests
# You should see locks appear/disappear
```

### Workflow 3: Performance Monitoring

```bash
# Clear cache for clean test
./clear_cache.sh

# Run test suite / load test

# Check performance
./stats.sh
# Look at "Cache Performance" section for hit rate
```

### Workflow 4: Daily Development

```bash
# Morning: Check Redis status
./check_connection.sh

# Check what's cached
./stats.sh

# Clear if needed
./clear_cache.sh
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
# Get all monster analyses
redis-cli KEYS "monster_trait:*"

# Count team synergies
redis-cli KEYS "team_synergy:*" | wc -l

# Clear specific key
redis-cli DEL "monster_trait:abc123..."

# Monitor all commands
redis-cli MONITOR
```

### Integration with Development

Add to your `package.json` or development scripts:

```bash
# Before running tests
npm run test:prepare && ./backend/scripts/redis/clear_cache.sh

# After deployment
./backend/scripts/redis/export_keys.sh backup_$(date +%Y%m%d).txt
```

## Environment Variables

Scripts use default Redis connection (`localhost:6379`).

To use different Redis instance:

```bash
# Set REDIS_CLI_URL environment variable
export REDIS_CLI_URL="redis://custom-host:6380"

# Or modify scripts to use -h and -p flags
redis-cli -h custom-host -p 6380 KEYS "*"
```

## Safety Notes

⚠️ **Production Usage:**
- Never use `KEYS *` in production (blocks server)
- Use `SCAN` instead for large datasets
- Be careful with `FLUSHDB` / `clear_cache.sh`
- Test scripts in development first

✅ **Development Usage:**
- Safe to use all scripts
- Clear cache frequently when testing
- Monitor locks to verify stampede protection
- Export keys before major changes
