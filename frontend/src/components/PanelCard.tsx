import type { ReactNode } from "react";

/**
 * Shared outer shell for the analysis-surface panels.
 *
 * Every panel on the `/build/analyze/:slot` page (TypeDefensePanel,
 * MoveCoveragePanel, EffectiveStatsPanel, MatchupPanel) used to inline
 * the same `<section class="rounded-lg border border-zinc-200 bg-white
 * shadow-sm p-4">...</section>` shell plus an optional title header in a
 * local `card()` render helper. Consolidating it here gives us:
 *
 *   - ONE place to tweak the card visuals (border color, shadow strength,
 *     padding) and have all panels stay in sync.
 *   - A titled/untitled split: three panels use the titled form; MatchupPanel
 *     has a custom grid layout that embeds a MonsterCard on the left, so it
 *     uses the untitled form and manages its own body layout.
 *   - A `className` escape hatch for panels that need to extend the outer
 *     shell (e.g. extra padding, override background).
 *
 * The component is deliberately thin — no loading/error slots, no fancy
 * header actions. Those stayed inside each panel's body, because each panel
 * has a different set of error states and different empty-state copy. Trying
 * to push those into the shell would force a too-generic API.
 */
interface PanelCardProps {
  /**
   * Optional title rendered as a panel header. If omitted, the card renders
   * no header and the caller owns the top of the content area.
   */
  title?: string;
  /** Extra classes merged onto the outer <section> element. */
  className?: string;
  children: ReactNode;
}

export default function PanelCard({ title, className, children }: PanelCardProps) {
  const outer = `rounded-lg border border-zinc-200 bg-white shadow-sm p-4${
    className ? " " + className : ""
  }`;
  return (
    <section className={outer}>
      {title && (
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg font-semibold text-zinc-800">{title}</span>
        </div>
      )}
      {children}
    </section>
  );
}
