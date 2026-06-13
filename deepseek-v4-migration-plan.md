# DeepSeek V4 Model Migration Plan — Team Analysis LLM

**Status:** Code changes APPLIED + audited (SAFE WITH CHANGES) · **Risk:** Low (behavioral parity) · **Hard deadline:** 2026‑07‑24 15:59 UTC
**Author:** Recreated 2026‑06‑13 from live DeepSeek docs + current codebase
**Audit:** Strict pre-implementation audit completed 2026‑06‑13. Verdict **SAFE WITH CHANGES** (the changes were folded into §6). Remaining before prod: the §7 Step 0 live smoke test, then deploy.
**Scope:** Migrate the production team‑analysis LLM from the soon‑to‑be‑retired `deepseek-reasoner` to **`deepseek-v4-flash` with thinking mode enabled**, with zero loss of analysis quality.

---

## 1. TL;DR

- DeepSeek released **V4 on 2026‑04‑24**. The old API model names **`deepseek-chat` and `deepseek-reasoner` will be fully retired and inaccessible after Jul 24, 2026, 15:59 UTC.**
- Your app uses **`deepseek-reasoner`** (thinking mode) as the analysis model (`backend/config.py:30`). **It will stop working in ~6 weeks** if not migrated.
- **Recommended target: `deepseek-v4-flash` + thinking mode.** This is *exactly what `deepseek-reasoner` already routes to today* — so the migration is behavior‑preserving, not a quality change. It only removes the deprecation risk.
- **Thinking mode is preserved** by passing `extra_body={"thinking": {"type": "enabled"}}` (+ `reasoning_effort="high"`) on each call. The model name no longer implies thinking — it's now an explicit request parameter, which is the one real code change.
- **No infra/base_url change.** Same `https://api.deepseek.com`, same `openai` SDK (1.97.1, already supports `extra_body` + `reasoning_effort`), same `response_format: json_object`, same `reasoning_content` extraction (your code already reads it: `llm_service.py:215`).
- Total change surface: **2 files of code + 1 host compose file**, ~20 lines. Instant rollback (legacy name still works until Jul 24).

---

## 2. Why this is happening (verified facts, June 2026)

Researched directly from `api-docs.deepseek.com` on 2026‑06‑13. Sources listed in §12.

### 2.1 Model landscape now

| Item | Value |
|---|---|
| Current models | **`deepseek-v4-flash`** (284B total / 13B active), **`deepseek-v4-pro`** (1.6T / 49B) |
| V4 release date | **2026‑04‑24** (V4 Preview Release) |
| Legacy names | `deepseek-chat`, `deepseek-reasoner` — **retire after 2026‑07‑24 15:59 UTC** |
| Legacy routing *today* | `deepseek-chat` → v4‑flash **non‑thinking**; `deepseek-reasoner` → v4‑flash **thinking** |
| Context length | **1M tokens** (both V4 models) |
| Max output | **384K tokens** |
| Base URLs | OpenAI‑compatible `https://api.deepseek.com` · Anthropic‑compatible `https://api.deepseek.com/anthropic` |
| Official migration note | *"Keep base_url, just update model to deepseek-v4-pro or deepseek-v4-flash."* — no breaking changes |

### 2.2 How thinking mode works on V4 (the crux)

On V3/legacy, thinking was implied by the **model name** (`deepseek-reasoner`). On V4, both models are dual‑mode and thinking is a **request parameter**:

```python
# OpenAI Python SDK — thinking goes in extra_body; reasoning_effort is a top-level kwarg
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[...],
    response_format={"type": "json_object"},
    extra_body={"thinking": {"type": "enabled"}},   # <-- preserves thinking mode
    reasoning_effort="high",                          # "high" (default) or "max"
)
```

- `thinking.type`: `"enabled"` | `"disabled"` (default **`enabled`**).
- `reasoning_effort`: allowed `"high"`, `"max"`. (`low`/`medium` → `high`; `xhigh` → `max`.) Default `high`.
- **Returns `reasoning_content` (chain‑of‑thought) alongside `content`** — same field your code already reads.
- **Single‑turn safety:** *"the intermediate assistant's `reasoning_content` does not need to participate in the context concatenation"* when there are no tool calls. RKTB analysis is single‑shot (one system + one user message, no tool calls), so the multi‑turn 400 pitfall **does not apply to us.**
- **Temperature is ignored in thinking mode:** *"Thinking mode does not support the `temperature`, `top_p`, `presence_penalty`, or `frequency_penalty` parameters … setting these parameters will not trigger an error but will also have no effect."* (Same as old `deepseek-reasoner` — no behavior change.)

### 2.3 Pricing (per 1M tokens, current)

| | input (cache hit) | input (cache miss) | output | concurrency |
|---|---|---|---|---|
| `deepseek-v4-flash` | $0.0028 | $0.14 | $0.28 | 2500 |
| `deepseek-v4-pro` | $0.003625 | $0.435 | $0.87 | 500 |

**Cost impact of this migration: ~zero.** Because `deepseek-reasoner` *already routes to `deepseek-v4-flash`*, you are already billed at v4‑flash rates today. Naming the model explicitly changes nothing on the invoice.

---

## 3. Current state in this codebase

| Concern | Current | File |
|---|---|---|
| Provider | `deepseek` (prod) | `docker-compose.prod.yml:11` |
| Model | `deepseek-reasoner` (env‑overridable, **not set in prod**, so code default is live) | `backend/config.py:30` |
| Base URL | `https://api.deepseek.com` | `backend/llm_service.py:54` |
| JSON output | `response_format={"type":"json_object"}` | `backend/llm_service.py:185` |
| Temperature gate | skipped when `"reasoner" in model` | `backend/llm_service.py:190` |
| `reasoning_content` | already extracted + logged | `backend/llm_service.py:215` |
| Cache metrics | `prompt_cache_hit/miss_tokens` already read | `backend/llm_service.py:245` |
| Max tokens | `ANALYSIS_MAX_TOKENS=32768` | `backend/config.py:35` |
| Timeout | `DEEPSEEK_TIMEOUT=200.0s` | `backend/config.py:31` |
| SDK | `openai==1.97.1` (supports `extra_body` + `reasoning_effort`) | `backend/requirements.txt` |
| Calls per analysis | 7 (6 per‑monster + 1 team‑wide) | `backend/config.py:56` |

**Only 3 places reference the old model name:** `config.py:29` (comment), `config.py:30` (the default), `llm_service.py:189` (comment). The blast radius is tiny.

> ⚠️ **Deployment nuance:** `docker-compose.prod.yml` lives **on the EC2 host** (`/home/ubuntu/rktb/`), not inside the Docker image. The CI/CD pipeline ships a new *image* but does **not** rewrite the host compose file. Therefore the **code‑default change in `config.py` is the primary migration lever** (it travels in the image); the compose env var is an optional, explicit override + rollback switch you set on the host.

---

## 4. Decision: which model?

**Migrate to `deepseek-v4-flash` (thinking enabled). Do not switch to v4‑pro as part of this migration.**

| Option | Quality vs today | Cost | Risk | Verdict |
|---|---|---|---|---|
| **`deepseek-v4-flash` + thinking** | **Identical** (it's what `deepseek-reasoner` already is) | unchanged | **Lowest** | ✅ **Do this** |
| `deepseek-v4-pro` + thinking | Higher (different, larger model) | ~3× output, 5× lower concurrency (500) | Medium — re‑validate quality, latency, JSON reliability | ⏭️ Optional future experiment, separate change |

Rationale for the risk‑free path: choosing the model your traffic *already resolves to* means output distribution, latency (~86–90s, comfortably under the CloudFront 120s limit), JSON reliability, and cache behavior are all unchanged. v4‑pro is a genuine quality upgrade but is a **product decision with its own validation**, not a deprecation fix — keep it out of the critical‑path migration.

---

## 5. The one real risk, and why it's contained

**Risk:** "Does `response_format: json_object` still work *with thinking mode enabled* on V4?" The docs don't state this combination explicitly, and the entire analysis pipeline depends on valid JSON.

**Why it's already de‑risked:**
1. `deepseek-reasoner` **is** v4‑flash‑thinking today, and your production app already calls it with `json_object` successfully on every analysis. So json_object + v4‑flash‑thinking is *already running in prod* — the migration just makes the routing explicit.
2. We still gate the cutover behind an explicit **local smoke test** (§7, Step 0) that asserts a real `json_object` + `thinking:enabled` call on `deepseek-v4-flash` returns parseable JSON **and** a non‑empty `reasoning_content`. We do not deploy until that passes.

Secondary risks and mitigations:

| Risk | Likelihood | Mitigation |
|---|---|---|
| Reasoning tokens push output past `max_tokens=32768` (truncated JSON) | Low (parity w/ today) | Monitor `finish_reason=='length'`; bump `ANALYSIS_MAX_TOKENS` to 65536 (no cost penalty — billed per actual token; V4 allows 384K) |
| Latency creeps over CloudFront 120s | Low (flash + parity) | Already mitigated today (silent retry, cache hit on retry). Keep `reasoning_effort="high"` (not `max`) |
| Passing `thinking`/`reasoning_effort` to **legacy** `deepseek-reasoner` during rollback errors | Low | Code gates the new params behind `model.startswith("deepseek-v4")`, so reverting the model name restores exact legacy behavior |
| `count_cacheable_tokens.py` uses the V3 tokenizer | N/A at runtime | Analysis‑only script; note as low‑priority follow‑up (refresh to V4 tokenizer later) |

---

## 6. Code changes (exact diffs)

### 6.1 `backend/config.py` — replace lines 29–31

```python
# DeepSeek Official API Configuration (production - for China access)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# Models (DeepSeek-V4, since 2026-04-24), dual-mode (thinking / non-thinking):
#   deepseek-v4-flash — fast, low-cost (284B/13B). What deepseek-reasoner already routes to.
#   deepseek-v4-pro   — highest quality (1.6T/49B), higher cost, lower concurrency.
# Legacy deepseek-chat / deepseek-reasoner are RETIRED after 2026-07-24 15:59 UTC.
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "200.0"))
# Thinking mode (V4): keep enabled to preserve reasoning-quality analysis.
DEEPSEEK_THINKING_ENABLED = os.getenv("DEEPSEEK_THINKING_ENABLED", "true").lower() == "true"
# reasoning_effort: "high" (default) or "max". Keep "high" to respect the CloudFront 120s budget.
DEEPSEEK_REASONING_EFFORT = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
```

### 6.2 `backend/llm_service.py` — import the new config

Added `DEEPSEEK_THINKING_ENABLED` and `DEEPSEEK_REASONING_EFFORT` to the existing `from backend.config import (...)` block.

### 6.3 `backend/llm_service.py` — extract a testable helper (audit adjustment §9.1–9.2)

Rather than inline the logic, the request-shaping was extracted into a **pure, unit-testable** module function `build_deepseek_request_kwargs(...)`, and `reasoning_effort` is passed **inside `extra_body`** (not as a top-level kwarg) to avoid coupling to the OpenAI SDK's `ReasoningEffort` Literal (which excludes `"max"`):

```python
def build_deepseek_request_kwargs(model, messages, max_tokens, temperature,
                                  thinking_enabled=None, reasoning_effort=None):
    if thinking_enabled is None:
        thinking_enabled = DEEPSEEK_THINKING_ENABLED
    if reasoning_effort is None:
        reasoning_effort = DEEPSEEK_REASONING_EFFORT
    is_v4 = model.startswith("deepseek-v4")
    kwargs = {
        "model": model, "messages": messages, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if is_v4:
        extra_body = {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}}
        if thinking_enabled:
            extra_body["reasoning_effort"] = reasoning_effort   # in extra_body, not top-level
        kwargs["extra_body"] = extra_body
    thinking_active = thinking_enabled if is_v4 else ("reasoner" in model.lower())
    if not thinking_active:
        kwargs["temperature"] = temperature
    return kwargs
```

`_generate_openai_compatible` now calls this helper. Everything below (the `create(**kwargs)` call, `reasoning_content` extraction, cache metrics) is **unchanged** — it already handles V4 thinking output. **Legacy `deepseek-reasoner` produces a byte-identical request (no `extra_body`, no `temperature`) → safe rollback.**

### 6.4 `docker-compose.prod.yml` — add explicit env (host file, after line 12)

```yaml
      - LLM_PROVIDER=deepseek
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_MODEL=deepseek-v4-flash
      - DEEPSEEK_THINKING_ENABLED=true
      - DEEPSEEK_REASONING_EFFORT=high
```

> `DEEPSEEK_MODEL` is **not a secret** → it does **not** go in SSM Parameter Store. It belongs in the compose file (or stays as the code default). This env var is your instant rollback switch.

---

## 7. Testing plan

### Step 0 — API smoke test (DONE ✅ — passed 2026‑06‑13)

Ran twice against the prod key (`/rktb/prod/DEEPSEEK_API_KEY`, personal AWS profile), total cost « 1¢:
- **Toy JSON:** `deepseek-v4-flash` + `thinking:enabled` + `json_object` → valid JSON `{"ok":true,"n":3}`, `reasoning_content` present, `finish_reason=stop`, 1.6s.
- **Schema-realistic:** returned exactly `{synergy_moves:[...], recommendation:[...]}` (both lists), `finish=stop` (no truncation at 4096), 223 reasoning tokens, 5.7s.
- **Finding:** V4 reports reasoning tokens at `usage.completion_tokens_details.reasoning_tokens` (not top-level). `llm_service.py` metadata extraction was fixed accordingly (commit 6726ea4) so `🧠 Thinking` logging is accurate.

This empirically closes risk **R2** (json_object + thinking) and **R4** (truncation). Original gate script for reference:

```bash
source ~/.venvs/rktb310/bin/activate
DEEPSEEK_API_KEY="$(aws ssm get-parameter --name /rktb/prod/DEEPSEEK_API_KEY --with-decryption --query Parameter.Value --output text --region ap-southeast-1 --profile personal)" \
python3 - <<'PY'
import os, json
from openai import OpenAI
c = OpenAI(base_url="https://api.deepseek.com", api_key=os.environ["DEEPSEEK_API_KEY"])
r = c.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role":"system","content":"Reply ONLY with JSON."},
        {"role":"user","content":'Return {"ok": true, "n": 3} as JSON.'},
    ],
    response_format={"type":"json_object"},
    extra_body={"thinking":{"type":"enabled"}},
    reasoning_effort="high",
    max_tokens=2048,
)
m = r.choices[0].message
print("content      :", m.content)
print("parsed JSON  :", json.loads(m.content))            # must not raise
print("has thinking :", bool(getattr(m, "reasoning_content", None)))  # must be True
print("finish       :", r.choices[0].finish_reason)        # expect 'stop', not 'length'
print("usage        :", r.usage)
PY
```

**Pass criteria:** `content` parses as JSON, `has thinking` is `True`, `finish` is `stop`. If all three hold, proceed.

### Step 1 — Unit tests (DONE)

A new offline test, `backend/tests/test_deepseek_request.py`, asserts the request-shaping matrix (v4-flash thinking on/off, v4-pro `max`, legacy `deepseek-reasoner`/`deepseek-chat` unchanged, json_object always forced).

```bash
cd backend && pytest tests/test_deepseek_request.py -v   # 6 passed
cd backend && pytest -q                                  # full suite
```

Result on 2026‑06‑13: **161 passed (incl. the 6 new), 21 failed, 20 skipped.** All 21 failures are in `test_type_relationships.py` and are **environmental only** — they require a live local PostgreSQL (`localhost/roco_db`) that wasn't running; they touch no LLM code and are unrelated to this change.

### Step 2 — Full local analysis against the real API

```bash
# from project root, with prod key exported as above and LLM_PROVIDER=deepseek
python3 -m uvicorn backend.main:app --reload --env-file backend/.env
```

Run one real team analysis through the UI (or curl `/team/analyze`). Verify in `backend/data/move_reports/` prompt logs / server logs:
- All 7 calls return valid JSON (analysis renders fully).
- Logs show `🧠 Thinking: <n>` tokens > 0 → thinking is active.
- Logs show `DeepSeek Cache: ... hit rate` → caching intact.
- Latency per call is in the ~10–20s range (≈ today).
- Optional: compare the produced analysis for 2–3 known teams against current prod output — should be materially equivalent.

---

## 8. Deployment plan

This rides the existing CI/CD path (push to `main` → GitHub Actions → ECR → EC2 image pull + restart). See `deployment-complete.md` and `ops-guide.md`.

1. **Branch + PR.** `git checkout -b feature/deepseek-v4-migration`, apply §6.1–6.3, commit. (Compose change §6.4 is host‑side, handled in step 4.)
2. **Merge to `main`** after review → CI builds and deploys the new image. The image now defaults to `deepseek-v4-flash` (code default), so prod migrates even without the compose env.
3. **Verify the running container picked it up:**
   ```bash
   ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
   cd /home/ubuntu/rktb
   docker compose -f docker-compose.prod.yml logs backend | grep "Initialized DeepSeek client"
   # expect: model: deepseek-v4-flash
   ```
4. **(Recommended) Pin it explicitly on the host** for clarity + rollback lever — edit `docker-compose.prod.yml` per §6.4, then:
   ```bash
   docker compose -f docker-compose.prod.yml up -d backend   # recreates with new env (~10s)
   ```
5. **Smoke test prod:** run one real analysis on rkteambuilder.com; confirm it completes and renders.
6. **Watch logs ~15 min:**
   ```bash
   docker compose -f docker-compose.prod.yml logs -f backend | grep -Ei "deepseek|thinking|error|length"
   ```
   The hourly error monitor (`check_errors_hourly.sh`) and daily digest will also catch regressions.

**Cache note:** No cache flush needed. `llm_cache:*` entries are keyed by prompt content, and the output JSON schema is unchanged, so cached results from `deepseek-reasoner` remain valid alongside new `deepseek-v4-flash` results.

---

## 9. Rollback (instant, low‑stakes)

Legacy `deepseek-reasoner` keeps working until **Jul 24, 2026 15:59 UTC**, so rollback is safe any time before then:

- **Fastest (host env):** set `DEEPSEEK_MODEL=deepseek-reasoner` in `docker-compose.prod.yml` and `docker compose -f docker-compose.prod.yml up -d backend`. The code gate (`is_v4`) automatically reverts to legacy behavior (no `thinking`/`reasoning_effort` params, no temperature).
- **Or git:** revert the merge commit → CI redeploys.

No DB migration, no cache invalidation, no secret rotation involved.

---

## 10. Cost impact

Effectively **none**. You are already billed at `deepseek-v4-flash` rates today (because `deepseek-reasoner` routes there). Current rates: input $0.14/M (cache miss) / $0.0028/M (cache hit), output $0.28/M. Your context‑caching work (`backend/scripts/analysis/`, `deepseek_v3_tokenizer/`) continues to apply — the cacheable prompt prefix still earns the cache‑hit rate.

---

## 11. Execution checklist

- [x] `backend/config.py` — default → `deepseek-v4-flash` + thinking config (§6.1)
- [x] `backend/llm_service.py` — import new config (§6.2) + `build_deepseek_request_kwargs` helper (§6.3)
- [x] `docker-compose.prod.yml` — env pinned (§6.4)
- [x] `backend/tests/test_deepseek_request.py` added; `pytest` green for it + no new regressions
- [x] **Step 0 smoke test passed** (toy + schema-realistic; JSON valid, `reasoning_content` present, `finish_reason=stop`)
- [x] **Local full end-to-end passed** (2026‑06‑13): seeded local Postgres + Redis, ran `_perform_team_analysis` with `deepseek-v4-flash`. Fresh run: `all_succeeded=True`, 7/7 calls, no partial errors, 37.2s. Cache-hit re-run: `actual_llm_calls=0`, 0.21s. team_synergy + all 6 per-monster analyses fully populated.
- [ ] PR reviewed + merged to `main`; CI deploy succeeds
- [ ] Prod logs show `model: deepseek-v4-flash`
- [ ] (Recommended) `docker-compose.prod.yml` env pinned on EC2 (§6.4)
- [ ] Prod analysis smoke test passes on rkteambuilder.com
- [ ] 15‑min log watch clean (no errors, no `finish_reason=length`)
- [ ] **Done before 2026‑07‑24** — target completion this week
- [ ] (Optional follow‑ups) evaluate `deepseek-v4-pro` for quality; refresh `count_cacheable_tokens.py` to a V4 tokenizer; consider `ANALYSIS_MAX_TOKENS=65536`

---

## 11b. Latency-coupling audit (faster analysis: ~40s vs old 2–3 min)

Audited every timing-coupled setting (repo + live AWS) since the new model is ~3× faster. **Conclusion: no config changes required — faster analysis is strictly safer.**

| Config | Value | Tuned for (slow era) | Effect of speed-up |
|---|---|---|---|
| CloudFront origin response timeout | **120s** (live-confirmed, API origin `origin-api`) | Old analysis hit 120–180s → CF 504 | ~40s now → 504/silent-retry path **dormant** |
| nginx `proxy_read_timeout` | 210s | Keep backend computing past CF 120s so result still cached | Pure headroom now |
| `DEEPSEEK_TIMEOUT` | 200s | Slow reasoner call | Single v4 call ~5–40s — headroom |
| `REDIS_LOCK_TIMEOUT`/blocking | 210s | Hold stampede lock across 2–3 min compute | Lock held ~40s — headroom |
| Per-team dedup `ratelimit:analysis:{ip}:{team}` | **60s** | **Intentionally < CF 120s** so CF-timeout retry (~120s) finds it expired (`main.py:4646`) | Analysis < 60s; re-submit = cache hit that bypasses anyway |
| TanStack mutation retry | once, 5xx only | Absorb CF 504 → retry hits warm cache | No 504 → no retry; guard remains for rare slow case |
| Frontend axios timeout | none (relies on CF 120s) | — | Returns ~40s |
| Quota double-charge guard | `actual_llm_calls>0 && successful>0` + `user_analyzed` dedup + atomic slot claim | Prevent double-charge on CF-timeout retry | Timing-independent; still correct |

**Key facts discovered:**
- The CF-timeout → silent-retry → cache-hit → charge-once machinery is a **safety net**, not the happy path; faster analysis stops exercising it but it still protects any analysis that exceeds 120s under load. Worst case = no worse than today.
- `ANALYSIS_RATE_LIMIT=1/2minutes` (SlowAPI `_apply_rate_limit_check`) is **defined but never called** → there is **no** "wait 2 min between analyses" throttle. The only per-request throttle is the 60s same-team key (a cache hit anyway). So no rate-limit wall from faster analyses.
- No ALB/API Gateway in the path (CloudFront → EC2 nginx direct); `/api/*` is **not** cached at CloudFront. uvicorn has no request timeout.

**Post-deploy watch (not a blocker):** confirm prod analyses (7 concurrent calls, China-peak load) stay < 120s; if any exceed it, the existing safety net handles it as today.

## 12. Sources (DeepSeek official docs, fetched 2026‑06‑13)

- Models & pricing — https://api-docs.deepseek.com/quick_start/pricing
- Thinking mode guide — https://api-docs.deepseek.com/guides/thinking_mode
- Reasoning model guide — https://api-docs.deepseek.com/guides/reasoning_model
- Chat Completion API reference — https://api-docs.deepseek.com/api/create-chat-completion
- V4 Preview Release announcement — https://api-docs.deepseek.com/news/news260424
- Docs home — https://api-docs.deepseek.com/

**Key verified quotes:**
- *"deepseek-chat & deepseek-reasoner will be fully retired and inaccessible after Jul 24th, 2026, 15:59 (UTC Time). (Currently routing to deepseek-v4-flash non-thinking/thinking)."*
- *"Keep base_url, just update model to deepseek-v4-pro or deepseek-v4-flash."*
- *"When using the OpenAI SDK, you need to pass the `thinking` parameter within `extra_body`."*
- *"Thinking mode does not support the `temperature`, `top_p`, `presence_penalty`, or `frequency_penalty` parameters."*

> ⚠️ The one combination DeepSeek's docs don't state explicitly is **`json_object` + thinking enabled**. It is de‑risked by the fact that production already does exactly this (via `deepseek-reasoner` → v4‑flash‑thinking) and by the §7 Step 0 gate. Do not skip Step 0.
