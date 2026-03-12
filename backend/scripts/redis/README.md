# Redis Scripts

Scripts for managing Redis cache in development.

## Quick Start

```bash
./redis.sh              # Show status
./redis.sh show         # Show all keys
./redis.sh show quota   # Show detailed quota breakdown
./redis.sh clear        # Interactive clear menu
./redis.sh reset        # Clear everything (for DB reset)
./redis.sh watch        # Monitor live
```

## What Redis Stores

| Type | Purpose | When to Clear |
|------|---------|---------------|
| **cache** | LLM analysis results | Changed prompts, updated game data |
| **rate** | 2-minute cooldowns | User stuck on rate limit |
| **quota** | Usage counts & caps | Testing quotas, reset after DB wipe |
| **tokens** | Logged-out sessions | Never (security risk) |

## Detailed Key Breakdown

### LLM Cache (`llm_cache:*`) - 1hr TTL

| Key Pattern | Purpose |
|-------------|---------|
| `llm_cache:monster_trait:{hash}` | Per-monster trait synergy analysis |
| `llm_cache:team_synergy:{hash}` | Team-wide synergy analysis |
| `lock:{key}` | Distributed lock for concurrent requests |

Same team + language = instant cached response (no LLM call).

### Rate Limits (`ratelimit:*`) - 1min TTL

| Key Pattern | Purpose |
|-------------|---------|
| `ratelimit:analysis:{ip}:{team_hash}` | Per-team cooldown (prevents concurrent duplicate submissions) |

Prevents concurrent duplicate LLM calls for the same team from the same IP.

### Usage Quotas (`tier:*`)

#### Per-User Quotas (daily/monthly limits per tier)

| Key Pattern | Purpose | Limits |
|-------------|---------|--------|
| `tier:user:{id}:daily:{date}` | Registered user daily count | Guest: 3, Free: 5, Premium: 20 |
| `tier:user:{id}:monthly:{date}` | Registered user monthly count | Guest: 30, Free: 100, Premium: 500 |
| `tier:anon:device:{id}:daily:{date}` | Anonymous by device ID | 1/day |
| `tier:anon:device:{id}:monthly:{date}` | Anonymous by device ID | 5/month |
| `tier:anon:ip:{ip}:daily:{date}` | Anonymous by IP (fallback) | 1/day |
| `tier:anon:ip:{ip}:monthly:{date}` | Anonymous by IP (fallback) | 5/month |

**Note:** Guest/Free/Premium users all use `tier:user:*` keys. The tier itself is stored in PostgreSQL (`users.subscription_tier`), not Redis.

#### Cross-Account Caps (prevents multi-account abuse)

| Key Pattern | Purpose | Limit |
|-------------|---------|-------|
| `tier:device:{id}:daily:{date}` | All accounts on device | 5/day |
| `tier:ip:{ip}:daily:{date}` | All accounts from IP | 15/day |
| `tier:guest_create:ip:{ip}:{date}` | Guest account creation | 2/day |

These caps apply across ALL accounts. Even with 3 free accounts, you can only run 5 analyses/day from the same device.

Premium/Unlimited users are exempt from cross-account caps.

### Revoked Tokens (`revoked_token:*`)

| Key Pattern | Purpose |
|-------------|---------|
| `revoked_token:{jti}` | JWT ID of logged-out session |

Prevents reuse of old tokens. TTL matches JWT expiry.

## Tier Limits Reference

| Tier | Daily | Monthly | Teams | Cross-Account Exempt? |
|------|-------|---------|-------|----------------------|
| anonymous | 1 | 5 | 0 | No |
| guest | 3 | 30 | 3 | No |
| free | 5 | 100 | 100 | No |
| premium | 20 | 500 | 500 | **Yes** |
| unlimited | ∞ | ∞ | ∞ | **Yes** |

## Common Workflows

### After Deleting All Users from Database
```bash
./redis.sh reset
# Clears quotas, tokens, everything
```

### Testing Rate Limits
```bash
./redis.sh clear rate
```

### Changed LLM Prompts
```bash
./redis.sh clear cache
```

### Reset All Quotas (for testing)
```bash
./redis.sh clear quota
```

### Monitor During Load Test
```bash
./redis.sh watch
```

## Display Shorthand

The script shortens long keys for display:

| Full Key | Displayed As |
|----------|--------------|
| `llm_cache:monster_trait:{hash}` | `cache:monster:{hash}` |
| `llm_cache:team_synergy:{hash}` | `cache:team:{hash}` |
| `ratelimit:analysis:{ip}:{hash}` | `rate:team:{ip}:{hash}` |
| `tier:user:{id}:...` | `user:{id}:...` |
| `tier:anon:device:{id}:...` | `anon:device:{id}:...` |
| `tier:anon:ip:{ip}:...` | `anon:ip:{ip}:...` |
| `tier:device:{id}:...` | `cap:device:{id}:...` |
| `tier:ip:{ip}:...` | `cap:ip:{ip}:...` |
| `tier:guest_create:ip:{ip}:...` | `guest_create:{ip}:...` |
