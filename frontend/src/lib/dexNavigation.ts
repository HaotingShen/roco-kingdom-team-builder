/**
 * Shared URL-query builder for the dex navigation context.
 *
 * The dex detail page (and its nested EvolutionTree) preserves a "return
 * context" through in-page navigation via URL params:
 *
 *   - `from=builder`                       → back to /build (team builder)
 *   - `from=analyze&slot=N`                → back to /build/analyze/N (slot analysis page)
 *   - `from=analysis`                      → Link to `back=` param (encoded matchup URL with ?tab=vsFeatured)
 *   - neither                              → back to the dex listing
 *
 * Optionally the original dex listing URL is preserved as `back=<encoded>`
 * so sort/filter state survives a round trip through a detail page.
 *
 * This helper centralises the param-construction logic so
 * `MonsterDetailPage`, `EvolutionTree`, and `MonsterInspector` can't drift
 * out of sync — which was the failure mode for the I1/I2 bugs (the target
 * and label for the back button derived from two separate conditionals
 * that could disagree when a `from=analyze` URL arrived without a `slot`).
 *
 * All fields are optional. The helper only emits params that are set.
 * Missing / null / undefined values are simply skipped.
 */

export interface DexForwardContext {
  /** Full encoded dex listing URL to return to (e.g. "/dex?tab=monsters&sort=base_spd"). */
  backRaw?: string | null;
  /** Dex listing tab (monsters / moves / traits / items). Used when `backRaw` is absent. */
  fromTab?: string;
  /** True if this dex view was launched from the team builder. */
  fromBuilder?: boolean;
  /** True if this dex view was launched from the per-slot monster analysis page. */
  fromAnalyze?: boolean;
  /** Slot index (as a string) when `fromAnalyze` is true. Required for the analyze-return link to work. */
  analyzeSlot?: string | null;
  /** True if this dex view was launched from the matchup panel (vs featured teams). Uses navigate(-1) to return. */
  fromMatchup?: boolean;
}

/**
 * Build the `?key=value&...` query string (without the leading `?`) that
 * encodes the given navigation context. Safe to concatenate directly after
 * a base URL; safe to pass to `<Link to={`?${qs}&extra=1`} />` since keys
 * and values are URL-encoded by URLSearchParams.
 */
export function buildDexForwardQuery(ctx: DexForwardContext): string {
  const fwd = new URLSearchParams();

  if (ctx.backRaw) {
    fwd.set("back", ctx.backRaw);
  } else if (ctx.fromTab) {
    fwd.set("tab", ctx.fromTab);
  }

  // fromBuilder and fromAnalyze are mutually exclusive in practice — a URL's
  // `from` param can only hold one value. Separate `if`s (not else-if) mean
  // the analyze path wins if both are somehow true, matching the pre-existing
  // inline behaviour in MonsterDetailPage / EvolutionTree.
  if (ctx.fromBuilder) {
    fwd.set("from", "builder");
  }
  if (ctx.fromAnalyze && ctx.analyzeSlot != null) {
    fwd.set("from", "analyze");
    fwd.set("slot", ctx.analyzeSlot);
  }
  if (ctx.fromMatchup) {
    fwd.set("from", "analysis");
  }

  return fwd.toString();
}
