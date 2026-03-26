import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import type { TeamOut } from '@/types';
import { useI18n } from '@/i18n';
import TeamCard from './TeamCard';
import { teamOutToShareData, buildShareUrl } from './sharePayload';

interface TeamShareModalProps {
  open: boolean;
  onClose: () => void;
  team: TeamOut;
  currentUsername?: string;  // pass user?.username if !user.is_guest; undefined otherwise
}

export default function TeamShareModal({ open, onClose, team, currentUsername }: TeamShareModalProps) {
  const { t, lang } = useI18n();
  const [includeUsername, setIncludeUsername] = useState(false);
  const [note, setNote] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const isComposingRef = useRef(false);   // sync ref for onChange — state update is async
  const preCompositionLength = useRef(0);
  const [imagesReady, setImagesReady] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const exportCanvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  // Use committed length during IME composition — excludes intermediate pinyin keystrokes
  const committedNoteLength = isComposing ? preCompositionLength.current : note.length;

  const username  = includeUsername ? currentUsername : undefined;
  // Memoize so button-click state changes (linkCopied, isExporting) don't
  // create new object references and re-trigger the canvas draw.
  const shareData = useMemo(() => teamOutToShareData(team, username), [team, username]);

  // Debounced note — only updates 300ms after the user stops typing.
  // The canvas draw (and shareUrl) depend on this, not on `note` directly,
  // so the canvas doesn't repaint on every keystroke.
  const [debouncedNote, setDebouncedNote] = useState('');
  useEffect(() => {
    const id = setTimeout(() => setDebouncedNote(note.trim()), 300);
    return () => clearTimeout(id);
  }, [note]);

  const shareUrl  = useMemo(() => buildShareUrl(team, username, debouncedNote || undefined), [team, username, debouncedNote]);

  // ResizeObserver for card preview scaling
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setScale(entry.contentRect.width / 1280);
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, [open]);

  // Reset state when modal opens.
  useEffect(() => {
    if (open) {
      setNote('');
      setDebouncedNote('');
      setIncludeUsername(false);
      setIsComposing(false);
      isComposingRef.current = false;
    }
  }, [open]);

  // Reset ready flag when share data changes (username toggle, team data).
  // Intentionally excludes debouncedNote — note changes don't reload images.
  useEffect(() => {
    setImagesReady(false);
  }, [shareData]);

  // On return from another app, reset any stuck isExporting state. On iOS the
  // tab can be frozen mid-export (canvas.toBlob callback not fired), leaving
  // isExporting=true permanently. The canvas is also redrawn by TeamCard's own
  // visibilitychange handler, so we don't need to reset imagesReady here.
  useEffect(() => {
    if (!open) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') setIsExporting(false);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [open]);

  const doExport = useCallback(async (): Promise<Blob | null> => {
    const canvas = exportCanvasRef.current;
    if (!canvas) return null;
    return new Promise<Blob | null>(resolve => canvas.toBlob(b => resolve(b), 'image/png'));
  }, []);

  const handleDownload = async () => {
    setIsExporting(true);
    try {
      const blob = await doExport();
      if (!blob) throw new Error('Export failed');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `team-${(team.name ?? 'team').replace(/[^a-z0-9\u4e00-\u9fff]/gi, '-')}.png`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('[TeamShare] download failed:', err);
      toast.error(t('share.exportError') ?? 'Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleCopyImage = async () => {
    setIsExporting(true);
    try {
      const blob = await doExport();
      if (!blob) throw new Error('Export failed');
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      toast.success(t('share.copyImageSuccess') ?? 'Image copied!');
    } catch (err) {
      console.error('[TeamShare] copy failed:', err);
      toast.error(t('share.exportError') ?? 'Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleMobileShare = async () => {
    setIsExporting(true);
    try {
      const blob = await doExport();
      if (!blob) throw new Error('Export failed');
      const file = new File([blob], 'team.png', { type: 'image/png' });
      await navigator.share({ files: [file] });
    } catch (err: unknown) {
      // AbortError = user cancelled — not an error
      if (err instanceof Error && err.name === 'AbortError') return;
      toast.error(t('share.exportError') ?? 'Export failed. Please try again.');
      await handleDownload();  // await so isExporting stays true until download finishes
    } finally {
      setIsExporting(false);
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      toast.success(t('share.linkCopied') ?? 'Link copied!');
    } catch {
      toast.error(t('share.copyError') ?? 'Copy failed. Please try again.');
    }
  };

  // Show Copy Image whenever the Clipboard API supports it — not tied to viewport width.
  const showCopyImage = typeof navigator !== 'undefined' && 'clipboard' in navigator && typeof ClipboardItem !== 'undefined';
  // pointer:coarse = touch device (phone/tablet); excludes desktop browsers that also expose navigator.share
  const showMobileShare = typeof navigator !== 'undefined' && 'share' in navigator
    && typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto py-4 px-2 sm:px-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl mx-auto flex flex-col max-h-[calc(100vh-2rem)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 shrink-0">
          <h2 className="text-lg font-semibold text-zinc-800">
            {t('share.modalTitle') ?? 'Share Team'}
          </h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 transition-colors cursor-pointer">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-3 py-4 sm:px-6 space-y-4 overflow-y-scroll">
          {/* Card preview — canvas IS the export; CSS scale for display only */}
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
              <TeamCard
                data={shareData}
                shareUrl={shareUrl}
                showQr={true}
                lang={lang}
                note={debouncedNote || undefined}
                canvasRef={exportCanvasRef}
                onReady={() => setImagesReady(true)}
              />
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

          {/* Username opt-in */}
          {currentUsername && (
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeUsername}
                onChange={e => setIncludeUsername(e.target.checked)}
                className="shrink-0 w-4 h-4 rounded border-zinc-300"
              />
              <span className="text-sm font-medium text-zinc-700">
                {t('share.includeUsername', { username: currentUsername })
                  ?? `Include my username (@${currentUsername}) in the share card`}
              </span>
            </label>
          )}

          {/* Custom note */}
          <div className="space-y-1">
            <label className="block text-sm font-medium text-zinc-700">
              {t('share.noteLabel') ?? 'Note (optional)'}
            </label>
            <textarea
              value={note}
              onChange={e => {
                // Don't truncate during IME composition — slicing mid-composition corrupts the IME state.
                // Truncation is applied in onCompositionEnd (and by the subsequent onChange in React 17+).
                if (isComposingRef.current) {
                  setNote(e.target.value);
                } else {
                  setNote(e.target.value.slice(0, 100));
                }
              }}
              onCompositionStart={() => {
                isComposingRef.current = true;
                preCompositionLength.current = note.length;
                setIsComposing(true);
              }}
              onCompositionEnd={e => {
                isComposingRef.current = false;
                setIsComposing(false);
                setNote(e.currentTarget.value.slice(0, 100));
              }}
              placeholder={t('share.notePlaceholder') ?? 'Add a note about your team…'}
              rows={2}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 placeholder:text-zinc-400 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-300"
            />
            <p className="text-right text-xs text-zinc-400">{committedNoteLength}/100</p>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2 justify-end pt-1">
            {/* Copy Link — always shown, instant */}
            <button
              onClick={handleCopyLink}
              className="flex-1 sm:flex-none h-9 px-2 sm:px-4 rounded-lg text-sm font-medium border-2 border-zinc-300 text-zinc-700 hover:bg-zinc-50 transition-colors cursor-pointer"
            >
              {linkCopied
                ? (t('share.linkCopied') ?? 'Copied!')
                : (t('share.copyLink') ?? 'Copy Link')}
            </button>

            {/* Copy Image */}
            {showCopyImage && (
              <button
                onClick={handleCopyImage}
                disabled={!imagesReady || isExporting}
                className="flex-1 sm:flex-none h-9 px-2 sm:px-4 rounded-lg text-sm font-medium border-2 border-zinc-300 text-zinc-700 hover:bg-zinc-50 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('share.copyImage') ?? 'Copy Image'}
              </button>
            )}

            {/* Download PNG — always shown */}
            <button
              onClick={handleDownload}
              disabled={!imagesReady || isExporting}
              className="flex-1 sm:flex-none h-9 px-2 sm:px-4 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('share.download') ?? 'Download PNG'}
            </button>

            {/* Share (Web Share API) — last, so it anchors the right on desktop */}
            {showMobileShare && (
              <button
                onClick={handleMobileShare}
                disabled={!imagesReady || isExporting}
                className="flex-1 sm:flex-none h-9 px-2 sm:px-4 rounded-lg text-sm font-medium bg-zinc-800 text-white hover:bg-zinc-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('share.mobileShare') ?? 'Share'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
