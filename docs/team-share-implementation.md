# Team Share Feature — Implementation Reference

This document describes the current (as-built) implementation of the team sharing feature.

---

## Overview

Sharing is **stateless and serverless**. No share tokens are stored in the database. The entire team snapshot is encoded into a base64url string that is passed as a URL query parameter. The backend decodes and validates the payload on every access — it never stores share links.

**Share URL format:** `https://rkteambuilder.com/import?t={base64urlPayload}`

---

## Payload Format

### Encoding (`frontend/src/features/share/sharePayload.ts`)

The payload is a JSON object, UTF-8 encoded, then base64url encoded (standard base64 with `+`→`-`, `/`→`_`, padding stripped).

```typescript
interface SharePayload {
  v: number;              // version, always 1
  n: string;              // team name (max 16 chars)
  mi: number;             // magic item ID
  u?: string;             // username if opted in (max 32 chars)
  no?: string;            // custom note (max 100 chars)
  m: SharePayloadMonster[]; // exactly 6 monsters
}

interface SharePayloadMonster {
  id: number;   // monster ID
  p: number;    // personality ID
  lt: number;   // legacy type ID
  mv: number[]; // 4 move IDs
  t: number[];  // 6 talent values: 0 (not invested) or 10 (invested)
}
```

Talent encoding: any value `>= 7` is normalized to `10`, else `0`. The backend accepts `{0, 7, 8, 9, 10}`.

### Size limit

Backend enforces a hard limit of **2048 characters** on the encoded payload.

---

## Backend: Decode Endpoint

**File:** `backend/main.py` (~line 5980)

```
GET /share/decode?t={base64urlPayload}
```

- **Auth:** None (fully public)
- **Rate limit:** 30 requests/minute per IP
- **Response model:** `schemas.ShareDecodeResponse`

### Validation steps

1. Reject payload > 2048 chars
2. Base64url decode, UTF-8 parse (supports Chinese team names)
3. Structural checks:
   - `v == 1`
   - `n`: string
   - `mi`: int
   - `m`: array of exactly 6 monsters
   - Each monster: `id`, `p`, `lt`, `mv` (4 items), `t` (6 items)
4. Talent values: each must be in `{0, 7, 8, 9, 10}`; each monster must have at least 1 non-zero value
5. All validation failures return **HTTP 422**

### Data resolution (per-request, no caching)

For each decoded payload the backend:
1. Fetches magic item by `mi` (404 → 422)
2. For each of 6 monsters:
   - Fetches monster by `id`
   - Fetches personality by `p`
   - Fetches legacy type by `lt`
   - For each of 4 moves (`mv`):
     - Checks move exists in DB (deleted → `null` in response, does not abort)
     - Checks if move is in valid pools: `move_pool`, `move_stones`, or `legacy_moves`
     - Sets `move_valid[i] = false` if move exists but not in any valid pool
3. Reconstructs a synthetic `TalentOut` (ID = 0, not a real DB record)

### Response schemas (`backend/schemas.py` ~line 746)

```python
class SharedMonsterData(BaseModel):
    monster: MonsterLiteOut
    personality: PersonalityOut
    legacy_type: TypeOut
    moves: List[Optional[MoveOut]]   # null if move was deleted from DB
    talent: TalentOut
    move_valid: List[bool]           # length 4; false = move exists but not available for this monster

class ShareDecodeResponse(BaseModel):
    team_name: str
    shared_by: Optional[str] = None  # username if sharer opted in
    note: Optional[str] = None       # custom note (max 150 chars decoded)
    magic_item: MagicItemOut
    monsters: List[SharedMonsterData]  # always 6
```

Logging on success: team name, `shared_by`, count of invalid moves.

---

## Frontend: Share Generation

### Entry points

**1. Saved Team Page** (`frontend/src/features/teams/SavedTeamPage.tsx`)
- Share button always available on any saved team
- Immediately opens `TeamShareModal` with the saved `TeamOut`

**2. Builder Page** (`frontend/src/features/builder/BuilderPage.tsx`)
- Share button is always rendered; color indicates readiness
  - **Indigo (active):** team is shareable
  - **Grey (inactive):** team is incomplete or analysis is in progress
- `shareReady = (teamId && !queryError ? (!isLoading && !!data) : teamIsReady) && !isAnalyzing`

### Builder share button click logic

Conditions checked in order:

| State | Behaviour |
|---|---|
| `isAnalyzing` | Toast: "请等待分析完成后再分享" |
| `teamId` exists, query loading | Toast: "队伍数据加载中，请稍候" |
| Team incomplete (no `teamId` or query error) | Toast with specific missing field message |
| `teamId` exists, not dirty, query loaded | Opens `TeamShareModal` directly |
| `teamId` exists, dirty, team complete | Opens "Update & Share" confirmation dialog |
| `teamId` exists, query errored, team complete | Falls through to "Create & Share" dialog |
| No `teamId`, team complete | Opens "Create & Share" dialog |

### "Update & Share" dialog (builder, has changes)

- Shows saved team name (DB version, not dirty name)
- On confirm: saves team → opens `TeamShareModal` with fresh data
- On duplicate name error: shows inline error, share modal does NOT open; flag resets on failure

### "Create & Share" dialog (builder, no saved team)

- On confirm: creates team → opens `TeamShareModal`
- On duplicate name: error "名为「xxx」的队伍已存在，请从「我的队伍」中打开以分享"
- On team limit reached (403): shows limit error
- If user is not logged in: opens `SaveTeamModal` (auth flow)
  - Guest account created → team saved → share modal opens (flag preserved across auth flow)
  - Modal dismissed → `saveAndShareMode` cleared, share modal does NOT open

---

## Frontend: TeamShareModal

**File:** `frontend/src/features/share/TeamShareModal.tsx`

```typescript
interface TeamShareModalProps {
  open: boolean;
  onClose: () => void;
  team: TeamOut;
  currentUsername?: string;  // provided for non-guest logged-in users
}
```

### Features

**Username opt-in**
- Checkbox shown only when `currentUsername` is provided (not for guest users)
- When enabled: username encoded in payload as `u` field, shown as `@username` on card
- Updates QR code and share URL in real time

**Custom note**
- Textarea, max 100 chars (frontend limit; backend allows 150)
- Handles IME composition for Chinese/Japanese (uses `committedNoteLength` to count only committed characters)
- Debounced 300ms before triggering canvas redraw

**Team card canvas (preview)**
- Renders at **1280×720** (16:9)
- CSS-scaled to fit viewport via `ResizeObserver`
- All images must load before export buttons are enabled ("Preparing export…" shown while loading)

**Export actions**

| Button | Behaviour | Availability |
|---|---|---|
| 复制链接 | Copies `/import?t=…` URL to clipboard | Always |
| 复制图片 | Copies PNG via ClipboardItem API | Desktop only; hidden on mobile; hidden if non-HTTPS |
| 下载图片 | Downloads `team-{name}.png` | Desktop; disabled while images loading |
| Share (mobile) | Web Share API with PNG file | Mobile only (touch device) |

Mobile share: `AbortError` silently ignored; other errors fall back to download.

Download filename: team name with non-alphanumeric/non-CJK characters replaced by `-`.

**iOS workaround:** `visibilitychange` handler resets stuck `isExporting` state when app is backgrounded during export.

---

## Frontend: Import Page

**File:** `frontend/src/features/share/ImportPage.tsx`
**Route:** `/import` (`frontend/src/router.tsx:41`)

### Flow

1. Read `t` query param; redirect to home if missing
2. Call `GET /share/decode?t={t}` via React Query
   - `retry: false`, `staleTime: Infinity` (no refetch)
   - Query key: `['share', token]`
3. Display decoded team preview using `ShareDecodeResponse`
4. Show attribution: "Shared by @{username}" if `shared_by` is set

### Invalid move handling

- `move_valid` flags checked for each monster's 4 moves
- If any `move_valid[i] === false`: save button is blocked
- Error message lists the invalid move names
- User must "Load into Builder" to fix moves manually before saving

### Save to account

- Constructs `TeamCreate` from `ShareDecodeResponse`
- `POST /teams` (requires auth)
- Handles:
  - 400 duplicate name
  - 403 team limit reached
  - Network errors
- On success: invalidates `teams` and `quota` queries, redirects to saved team

### Load into builder

- Checks for unsaved draft, confirms if present
- Calls `loadFromImport(decoded)` on `builderStore`
- Navigates to `/build`

### Error states

| Code | Cause | Message |
|---|---|---|
| 422 | Invalid payload or game data removed | "无效链接" / data unavailable |
| 429 | Rate limited | Rate limit message |

---

## Team Card Visual Rendering

**File:** `frontend/src/features/share/TeamCard.tsx`

**Canvas layout (1280×720):**
- Left zone: 886px — 2×3 monster grid (440px per cell)
- Right sidebar: 374px — magic item, QR code, team name, note

**Per-monster cell:**
- 4px type color stripe (top)
- 88px portrait sprite
- Name (18-20px), type pill, personality, talent chips
- Move band (bottom): 4 move icons (52px each)
- Invalid move slot: red background

**Color scheme:** Dark theme (`#0b1120` background), type badges from `TYPE_COLORS` map

**QR code:** Always rendered in right sidebar; points to the full share URL (including username/note if set)

---

## TypeScript Types

**File:** `frontend/src/types.ts` (~line 425)

```typescript
export interface SharedMonsterData {
  monster: MonsterLiteOut;
  personality: PersonalityOut;
  legacy_type: TypeOut;
  moves: (MoveOut | null)[];   // null = deleted move
  talent: TalentOut;
  move_valid: boolean[];       // length 4
}

export interface ShareDecodeResponse {
  team_name: string;
  shared_by: string | null;
  note: string | null;
  magic_item: MagicItemOut;
  monsters: SharedMonsterData[];  // length 6
}
```

**API client** (`frontend/src/lib/api.ts:346`):
```typescript
decodeSharePayload: (t: string) =>
  api.get("/share/decode", { params: { t } })
```

---

## Security & Authorization

| Concern | Handling |
|---|---|
| Generating share links | No backend call; pure client-side encoding |
| Decoding shared teams | No auth required; public |
| Saving imported team | Auth required (standard `create_team` flow) |
| Payload size | 2048 char hard cap on backend |
| Input validation | Done on backend; frontend adds UX limits only |
| Rate limiting | 30/min per IP on `/share/decode` |
| Ownership | No check on reading; auth check on saving |

---

## Link Longevity

- **No expiry** — links work indefinitely
- **Validity depends on current game data**: if a monster, move, type, or magic item is deleted from the DB, the link returns 422
- **No archival** — shared teams always reflect current game state, not the state at time of sharing
- `move_valid` flags handle the partial case: move exists in DB but is no longer in the valid pool for that monster

---

## What Is NOT in This Feature

- No share tokens stored in the database
- No `Team.share_token` column
- No expiry timestamps
- No access logs per share link
- No view counts
- No "unshare" / revoke mechanism
- No server-side caching of decoded payloads
