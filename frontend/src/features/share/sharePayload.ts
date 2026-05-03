import type { TeamOut, ShareDecodeResponse } from '@/types';

interface SharePayloadMonster {
  id: number; p: number; lt: number; mv: number[]; t: number[];
}
interface SharePayload {
  v: number; n: string; mi: number; u?: string; no?: string;
  m: SharePayloadMonster[];
}

// UTF-8-safe base64url encode.
// MUST use TextEncoder — team names and usernames can contain Chinese characters,
// and btoa() only handles Latin-1 (throws DOMException on multi-byte chars).
function toBase64Url(str: string): string {
  const bytes = new TextEncoder().encode(str);
  const binary = Array.from(bytes, b => String.fromCharCode(b)).join('');
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// Encodes a saved TeamOut + optional username + optional note into a compact base64url payload string.
export function encodeSharePayload(team: TeamOut, includeUsername?: string, note?: string): string {
  const payload: SharePayload = {
    v: 1,
    n: (team.name ?? '').trim().slice(0, 16) || 'My Team',
    mi: team.magic_item.id,
    m: (team.user_monsters ?? []).slice(0, 6).map(um => ({
      id: um.monster.id,
      p: um.personality.id,
      lt: um.legacy_type.id,
      mv: [um.move1.id, um.move2.id, um.move3.id, um.move4.id],
      // Normalize to 0/10: backend only allows {0,7,8,9,10}, non-zero means "invested".
      // Importers receive +10 for any highlighted talent regardless of original exact value.
      t: [
        um.talent.hp_boost      >= 7 ? 10 : 0,
        um.talent.phy_atk_boost >= 7 ? 10 : 0,
        um.talent.mag_atk_boost >= 7 ? 10 : 0,
        um.talent.phy_def_boost >= 7 ? 10 : 0,
        um.talent.mag_def_boost >= 7 ? 10 : 0,
        um.talent.spd_boost     >= 7 ? 10 : 0,
      ],
    })),
  };
  if (includeUsername) payload.u = includeUsername;
  if (note) payload.no = note.trim().slice(0, 150);
  return toBase64Url(JSON.stringify(payload));
}

// Builds the full import URL.
// In TapTap builds VITE_ASSET_BASE_URL is https://rkteambuilder.com, so share links
// always point to the real site — not TapTap's CDN (which would be window.location.origin).
export function buildShareUrl(team: TeamOut, includeUsername?: string, note?: string): string {
  const base = import.meta.env.VITE_ASSET_BASE_URL || window.location.origin;
  return `${base}/import?t=${encodeSharePayload(team, includeUsername, note)}`;
}

// Converts a saved TeamOut to ShareDecodeResponse shape for use in the share modal preview.
// All moves in a saved team are already valid — no API call needed.
export function teamOutToShareData(team: TeamOut, sharedBy?: string): ShareDecodeResponse {
  return {
    team_name: (team.name ?? '').trim().slice(0, 16) || 'My Team',  // match encodeSharePayload truncation
    shared_by: sharedBy ?? null,
    note: null,  // note is not stored on the team — only present when decoded from a share URL
    magic_item: team.magic_item,
    monsters: (team.user_monsters ?? []).map(um => ({
      monster: um.monster,
      personality: um.personality,
      legacy_type: um.legacy_type,
      moves: [um.move1, um.move2, um.move3, um.move4],
      talent: um.talent,
      move_valid: [true, true, true, true],
    })),
  };
}
