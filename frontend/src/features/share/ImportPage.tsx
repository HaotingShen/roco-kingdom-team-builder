import { useState, useRef, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { toast } from 'sonner';
import type { ShareDecodeResponse, TeamCreate } from '@/types';
import { useI18n } from '@/i18n';
import { useAuthStore } from '@/features/auth/authStore';
import { useBuilderStore } from '@/features/builder/builderStore';
import { endpoints } from '@/lib/api';
import { QUERY_KEYS } from '@/lib/constants';
import TeamCard from './TeamCard';

export default function ImportPage() {
  const { t, lang } = useI18n();
  const { user } = useAuthStore();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('t') ?? '';

  const qc = useQueryClient();
  const loadFromImport = useBuilderStore(s => s.loadFromImport);
  const slots = useBuilderStore(s => s.slots);
  const [showOverwriteConfirm, setShowOverwriteConfirm] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [imagesReady, setImagesReady] = useState(false);

  // Redirect if no token
  useEffect(() => {
    if (!token) nav('/', { replace: true });
  }, [token, nav]);

  // Decode share payload
  const { data: decoded, isLoading, error } = useQuery<ShareDecodeResponse>({
    queryKey: ['share', token],
    queryFn: () => endpoints.decodeSharePayload(token).then(r => r.data),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });

  // ResizeObserver for card preview scaling
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = containerRef.current;
    if (!el || !decoded) return;
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setScale(entry.contentRect.width / 1280);
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, [decoded]);

  // Save to account mutation
  const saveTeam = useMutation({
    mutationFn: (payload: TeamCreate) => endpoints.createTeam(payload, lang).then(r => r.data),
    onSuccess: (team) => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.TEAMS });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.QUOTA });
      toast.success(t('import.success') ?? 'Team imported!');
      nav(`/teams/${team.id}`);
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 400) {
          setSaveError(t('import.duplicateName') ?? 'A team with this name already exists. Please rename it before saving.');
          return;
        }
        if (err.response?.status === 403) {
          setSaveError(err.response.data?.detail ?? 'Team limit reached.');
          return;
        }
        if (!err.response) {
          setSaveError(t('import.networkError') ?? 'Could not connect. Check your internet connection.');
          return;
        }
      }
      setSaveError(t('import.networkError') ?? 'Something went wrong.');
    },
  });

  const handleSave = () => {
    if (!decoded) return;
    setSaveError(null);

    // Block save if any move is invalid
    const invalidMoves: string[] = [];
    decoded.monsters.forEach(m => {
      m.move_valid.forEach((valid, i) => {
        if (!valid && m.moves[i]) {
          const moveName = lang === 'zh'
            ? (m.moves[i] as any)?.localized?.zh?.name ?? m.moves[i]!.name
            : m.moves[i]!.name;
          invalidMoves.push(moveName);
        }
      });
    });
    if (invalidMoves.length > 0) {
      setSaveError(
        t('import.invalidMovesDetail', { moves: invalidMoves.join(', ') })
        ?? `The following moves are no longer available: ${invalidMoves.join(', ')}. Load into builder first to replace them before saving.`
      );
      return;
    }

    const payload: TeamCreate = {
      name: decoded.team_name || 'Imported Team',
      magic_item_id: decoded.magic_item.id,
      user_monsters: decoded.monsters.map((m, i) => ({
        monster_id: m.monster.id,
        personality_id: m.personality.id,
        legacy_type_id: m.legacy_type.id,
        move1_id: m.moves[0]?.id ?? 0,
        move2_id: m.moves[1]?.id ?? 0,
        move3_id: m.moves[2]?.id ?? 0,
        move4_id: m.moves[3]?.id ?? 0,
        talent: {
          hp_boost: m.talent.hp_boost,
          phy_atk_boost: m.talent.phy_atk_boost,
          mag_atk_boost: m.talent.mag_atk_boost,
          phy_def_boost: m.talent.phy_def_boost,
          mag_def_boost: m.talent.mag_def_boost,
          spd_boost: m.talent.spd_boost,
        },
        position: i,
      })),
    };
    saveTeam.mutate(payload);
  };

  const handleLoadIntoBuilder = () => {
    if (!decoded) return;
    const hasDraft = slots.some(s => s.monster_id !== 0);
    if (hasDraft) {
      setShowOverwriteConfirm(true);
    } else {
      doLoad();
    }
  };

  const doLoad = () => {
    if (!decoded) return;
    loadFromImport(decoded);
    nav('/build');
  };

  // ── Error state ──────────────────────────────────────────────────────────

  if (error || (!isLoading && !decoded)) {
    let msg = t('import.networkError') ?? 'Could not connect. Check your internet connection.';
    if (axios.isAxiosError(error)) {
      const status = error.response?.status;
      const detail: string = error.response?.data?.detail ?? '';
      if (status === 422) {
        msg = detail.includes('no longer available')
          ? (t('import.gameDataRemoved') ?? 'Some content in this team is no longer available in the game.')
          : (t('import.invalidLink') ?? 'This share link is invalid or corrupted.');
      } else if (status === 429) {
        msg = t('import.rateLimited') ?? 'Too many requests. Please try again in a moment.';
      } else if (!error.response) {
        msg = t('import.networkError') ?? 'Could not connect. Check your internet connection.';
      }
    }
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-zinc-600">{msg}</p>
        <Link to="/" className="h-9 px-4 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors">
          {t('import.goHome') ?? 'Go Home'}
        </Link>
      </div>
    );
  }

  // ── Loading state ────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-zinc-300 border-t-zinc-600 rounded-full animate-spin" />
      </div>
    );
  }

  // ── Success state ────────────────────────────────────────────────────────

  const hasInvalidMoves = decoded!.monsters.some(m => m.move_valid.some(v => !v));

  const isLoggedIn = !!user;
  const isGuest = user?.is_guest;

  return (
    <div className="min-h-screen bg-zinc-50 py-4 px-2 sm:py-8 sm:px-4">
      <div className="max-w-3xl mx-auto space-y-3 sm:space-y-5">

        {/* Attribution */}
        {decoded!.shared_by && (
          <p className="text-sm text-zinc-500">
            {t('import.sharedBy') ?? 'Shared by'}{' '}
            <span className="font-medium text-zinc-700">@{decoded!.shared_by}</span>
          </p>
        )}

        {/* Invalid moves warning */}
        {hasInvalidMoves && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {t('import.invalidMoves') ?? 'Some moves in this team are no longer available. You can load this team into the builder but cannot save it directly until the missing moves are replaced.'}
          </div>
        )}

        {/* Card preview */}
        <div
          ref={containerRef}
          style={{ width: '100%', height: `${720 * scale}px`, overflow: 'hidden', position: 'relative', borderRadius: '8px' }}
        >
          <div style={{
            width: '1280px', height: '720px',
            transform: `scale(${scale})`,
            transformOrigin: 'top left',
            position: 'absolute', top: 0, left: 0,
          }}>
            <TeamCard data={decoded!} shareUrl={`${window.location.origin}/import?t=${token}`} showQr={true} lang={lang} note={decoded!.note ?? undefined} onReady={() => setImagesReady(true)} />
          </div>

          {/* Loading overlay — sits above canvas until images are ready */}
          {!imagesReady && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-zinc-900/70 rounded-lg">
              <svg className="w-8 h-8 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              <p className="text-sm text-white/80">
                {t('share.preparing') ?? 'Preparing card…'}
              </p>
            </div>
          )}
        </div>

        {/* Notes not imported note */}
        <p className="text-xs text-zinc-400 text-center">
          {t('import.noAnalysis') ?? 'Team notes are not included in the import — they only appear on the share image.'}
        </p>

        {/* Save error */}
        {saveError && (
          <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
            {saveError}
          </div>
        )}

        {/* CTAs */}
        {showOverwriteConfirm ? (
          <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
            <p className="text-sm text-zinc-700">
              {t('import.confirmOverwrite') ?? 'You have an unsaved team in the builder. Loading this imported team will replace it and any unsaved changes will be lost. Continue?'}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowOverwriteConfirm(false)}
                className="h-9 px-4 rounded-lg text-sm font-medium border-2 border-zinc-300 text-zinc-700 hover:bg-zinc-50 transition-colors cursor-pointer"
              >
                {t('common.cancel') ?? 'Cancel'}
              </button>
              <button
                onClick={doLoad}
                className="h-9 px-4 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors cursor-pointer"
              >
                {t('common.continue') ?? 'Continue'}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            {/* Load into builder — always shown */}
            <button
              onClick={handleLoadIntoBuilder}
              className="w-full sm:w-auto h-10 px-6 rounded-lg text-sm font-medium border-2 border-zinc-700 text-zinc-800 hover:bg-zinc-100 transition-colors cursor-pointer"
            >
              {t('import.loadIntoBuilder') ?? 'Load into Builder'}
            </button>

            {/* Save to account — logged-in users (registered or guest) */}
            {isLoggedIn && (
              <button
                onClick={handleSave}
                disabled={saveTeam.isPending}
                className="w-full sm:w-auto h-10 px-6 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saveTeam.isPending ? '…' : (t('import.saveToAccount') ?? 'Save to My Account')}
              </button>
            )}

            {/* Anonymous nudge */}
            {!isLoggedIn && !isGuest && (
              <Link
                to="/auth/register"
                className="w-full sm:w-auto h-10 px-6 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors flex items-center justify-center"
              >
                {t('import.createToSave') ?? 'Create a free account to save this team'} →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
