import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import { useSeoMeta } from "@/hooks/useSeoMeta";
import type { MoveOut, MonsterLiteOut, MoveLearnersOut, TypeOut } from "@/types";
import { typeIconUrl, monsterImageFallbackChain } from "@/lib/images";
import RichDescription from "@/components/RichDescription";

/* ---------- helpers ---------- */

function normalizeMoveCategory(category: string): string {
  const upper = category.toUpperCase();
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return upper;
}

const TYPE_COLORS: Record<string, string> = {
  normal: "border-l-slate-500",
  grass: "border-l-green-400",
  fire: "border-l-orange-600",
  water: "border-l-blue-500",
  light: "border-l-cyan-400",
  ground: "border-l-yellow-600",
  ice: "border-l-sky-500",
  dragon: "border-l-rose-500",
  electric: "border-l-yellow-400",
  poison: "border-l-purple-400",
  bug: "border-l-lime-400",
  fighting: "border-l-orange-400",
  flying: "border-l-teal-400",
  cute: "border-l-pink-400",
  ghost: "border-l-violet-500",
  dark: "border-l-pink-600",
  mechanical: "border-l-emerald-400",
  illusion: "border-l-indigo-300",
  leader: "border-l-zinc-400",
};

const CAT_TO_FILE: Record<string, string> = {
  PHY_ATTACK: "physical-attack",
  MAG_ATTACK: "magic-attack",
  DEFENSE: "defense",
  STATUS: "status",
};

/* ---------- sub-components ---------- */

function TypePill({ type }: { type: TypeOut }) {
  const { lang } = useI18n();
  const icon = typeIconUrl(type.name, 30);
  return (
    <span className="inline-flex h-6 items-center gap-0.5 rounded-full border border-zinc-200 bg-zinc-50 px-2 text-xs text-zinc-700">
      {icon ? <img src={icon} alt="" width={18} height={18} /> : null}
      {pickName(type as any, lang)}
    </span>
  );
}

function MonsterCard({ monster, backUrl }: { monster: MonsterLiteOut; backUrl: string }) {
  const { lang, t } = useI18n();
  const name = pickName(monster as any, lang) || monster.name;
  const formLabel = pickFormName(monster as any, lang);
  const title = [name, formLabel ? `(${formLabel})` : ""].filter(Boolean).join(" ");
  const fallbackChain = monsterImageFallbackChain(monster, 360);
  const src = fallbackChain[0] || "/monster-images/placeholder.png";

  return (
    <Link
      to={`/dex/monsters/${monster.id}?back=${encodeURIComponent(backUrl)}`}
      className="rounded-lg border border-zinc-200 bg-white p-3 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 flex flex-col items-center gap-2"
    >
      <img
        src={src}
        alt=""
        width={360}
        height={360}
        className="h-[80px] w-[80px] object-contain drop-shadow-sm"
        loading="lazy"
        data-fallback-step="0"
        onError={(e) => {
          const img = e.currentTarget as HTMLImageElement;
          const step = Number(img.dataset.fallbackStep || "0");
          const next = step + 1;
          if (next < fallbackChain.length) {
            img.dataset.fallbackStep = String(next);
            img.src = fallbackChain[next]!;
          } else if (img.src !== "/monster-images/placeholder.png") {
            img.src = "/monster-images/placeholder.png";
          }
        }}
      />
      <div
        className="text-xs font-semibold text-center text-zinc-800 leading-tight line-clamp-2 w-full"
        title={title}
      >
        {title}
      </div>
      <div className="flex flex-wrap gap-1 justify-center">
        {([monster.main_type, monster.sub_type].filter(Boolean) as TypeOut[]).map((tp) => (
          <TypePill key={tp.id} type={tp} />
        ))}
        {monster.is_leader_form ? (
          <span className="inline-flex h-6 items-center rounded-full border border-amber-300 bg-amber-50 px-2 text-xs text-amber-700">
            {t("labels.leader")}
          </span>
        ) : null}
      </div>
    </Link>
  );
}

function LearnerSection({
  title,
  monsters,
  backUrl,
}: {
  title: string;
  monsters: MonsterLiteOut[];
  backUrl: string;
}) {
  if (monsters.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-700 mb-3">
        {title}{" "}
        <span className="font-normal text-zinc-400">({monsters.length})</span>
      </h3>
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {monsters.map((m) => (
          <MonsterCard key={m.id} monster={m} backUrl={backUrl} />
        ))}
      </div>
    </div>
  );
}

/* ---------- page ---------- */

export default function MoveDetailPage() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const backRaw = sp.get("back");
  const backUrl = backRaw ?? "/dex?tab=moves";
  const { lang, t } = useI18n();

  const moveQuery = useQuery<MoveOut>({
    queryKey: ["move", id],
    queryFn: () => endpoints.moveById(id!).then((r) => r.data),
    enabled: !!id,
  });

  const learnersQuery = useQuery<MoveLearnersOut>({
    queryKey: ["move-learners", id],
    queryFn: () => endpoints.moveLearners(id!).then((r) => r.data),
    enabled: !!id,
  });

  const move = moveQuery.data as any;
  const learners = learnersQuery.data;

  const tp = move ? ((move.move_type || move.type) as TypeOut | null) : null;
  const moveName = move ? pickName(move, lang) || move.name || "" : "";
  const desc = move
    ? pickDesc(move, lang) || move.localized?.[lang]?.description || move.description || ""
    : "";
  const normalizedCat = move
    ? normalizeMoveCategory(move.move_category || move.category || "")
    : "";
  const energy = move ? (move.energy_cost ?? move.energy ?? null) : null;
  const power = move ? (move.power ?? null) : null;
  const isDef = normalizedCat === "DEFENSE";
  const isSta = normalizedCat === "STATUS";

  const isWillpower =
    move &&
    (move.name === "Willpower Impact" ||
      (pickName(move, "en") || "").toLowerCase() === "willpower impact" ||
      (pickName(move, "zh") || "") === "愿力冲击");

  const isFocus =
    move &&
    (move.name === "Focus" ||
      (pickName(move, "en") || "").toLowerCase() === "focus" ||
      (pickName(move, "zh") || "") === "聚能");

  const catImg = isWillpower
    ? "/move-sub-icons/conditional-attack.png"
    : `/move-sub-icons/${CAT_TO_FILE[normalizedCat] ?? "physical-attack"}.png`;

  const typeName = tp?.name?.toLowerCase() || "";
  const typeColorClass = typeName ? TYPE_COLORS[typeName] || "border-l-zinc-400" : "border-l-zinc-400";
  const typeImg = tp?.name ? typeIconUrl(tp.name, 30) : null;
  const moveNameZh = move ? pickName(move, "zh") || moveName : "";
  const moveImg = moveNameZh ? encodeURI(`/move-icons/${moveNameZh}.png`) : null;

  // URL of this page (passed as ?back= when linking to monster detail)
  const currentUrl = `/dex/moves/${id}?back=${encodeURIComponent(backUrl)}`;

  const catLabel = (() => {
    if (isWillpower) return t("dex.willpowerCat");
    if (isDef) return t("dex.defense");
    if (isSta) return t("dex.status");
    if (normalizedCat === "PHY_ATTACK") return t("dex.cat_phy");
    if (normalizedCat === "MAG_ATTACK") return t("dex.cat_mag");
    return normalizedCat;
  })();

  const totalLearners = learners
    ? learners.move_pool.length + learners.move_stones.length + learners.legacy.length
    : null;

  useSeoMeta({
    title: moveName
      ? lang === "zh"
        ? `${moveName} | 洛手配队器`
        : `${moveName} | RK Team Builder`
      : lang === "zh"
      ? "技能详情 | 洛手配队器"
      : "Move Detail | RK Team Builder",
    description: moveName
      ? lang === "zh"
        ? `${moveName} — 技能详情与可学习精灵 — 洛克王国: 世界。`
        : `${moveName} — move details and learnable monsters for Roco Kingdom: World.`
      : "",
    canonicalPath: id ? `/dex/moves/${id}` : "/dex",
  });

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Back button — same style as MonsterDetailPage */}
      <div>
        <Link
          to={backUrl}
          className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
        >
          <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
          <span className="text-zinc-700">{t("dex.backToMoves")}</span>
        </Link>
      </div>

      {/* Move header card */}
      {moveQuery.isLoading ? (
        <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-5 animate-pulse h-36" />
      ) : moveQuery.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-600">
          Move not found.
        </div>
      ) : move ? (
        <div
          className={`rounded-lg border border-zinc-200 bg-white shadow-sm p-5 border-l-4 ${typeColorClass}`}
        >
          <div>
            <div className="flex gap-4 items-start">
              {/* Move icon */}
              <div className="shrink-0 w-[85px] h-[85px] sm:w-24 sm:h-24 rounded-lg bg-zinc-100/60 overflow-hidden flex items-center justify-center">
                {moveImg && (
                  <img
                    src={moveImg}
                    alt={moveName}
                    width={96}
                    height={96}
                    className="h-full w-full object-contain"
                    onError={(e) => {
                      (e.currentTarget as HTMLImageElement).style.display = "none";
                    }}
                  />
                )}
              </div>

              {/* Details */}
              <div className="flex-1 min-w-0 space-y-2">
                {/* Type icon + name — slight negative margin to compensate for type icon's visual weight */}
                <div className="flex items-center gap-1 lg:gap-1.5 flex-wrap -ml-1">
                  {typeImg ? (
                    <img
                      src={typeImg}
                      alt=""
                      aria-hidden
                      className="shrink-0 w-8 h-8 sm:w-9 sm:h-9"
                    />
                  ) : null}
                  <h1 className="text-lg sm:text-xl lg:text-2xl font-bold text-zinc-900 break-words leading-tight">
                    {moveName}
                  </h1>
                </div>

                {/* Category · Energy · Power — use gap-x/gap-y to keep tight wrap */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-600">
                  <span className="inline-flex items-center gap-1.5">
                    <img src={catImg} alt="" aria-hidden width={16} height={16} />
                    {catLabel}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <img src="/move-sub-icons/energy.png" alt="" aria-hidden width={14} height={14} />
                    {energy ?? "—"}
                  </span>
                  {!isDef && !isSta && (
                    <span>
                      <span className="font-semibold">{t("dex.sort_power")}:</span> {power ?? "—"}
                    </span>
                  )}
                </div>

                {/* Description inside right column — visible at 425px+ */}
                {desc && (
                  <p className="hidden desc:block text-sm text-zinc-600 leading-relaxed"><RichDescription text={desc} /></p>
                )}
              </div>
            </div>

            {/* Description below full row — visible below 425px */}
            {desc && (
              <p className="desc:hidden mt-2 text-sm text-zinc-600 leading-relaxed"><RichDescription text={desc} /></p>
            )}
          </div>
        </div>
      ) : null}

      {/* Learners section */}
      <div className="space-y-2">
        <h2 className="text-base font-semibold text-zinc-800">
          {t("dex.learnersTitle")}
          {!isFocus && !isWillpower && totalLearners !== null && (
            <span className="ml-2 text-sm font-normal text-zinc-400">({totalLearners})</span>
          )}
        </h2>

        {learnersQuery.isLoading ? (
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 pt-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className="rounded-lg border border-zinc-200 bg-zinc-50 animate-pulse h-[148px]"
              />
            ))}
          </div>
        ) : learnersQuery.isError ? (
          <p className="text-sm text-red-500 pt-2">Failed to load learner data.</p>
        ) : learners ? (
          isFocus ? (
            <p className="text-sm text-zinc-500 pt-2">{t("dex.focusNote")}</p>
          ) : isWillpower ? (
            <p className="text-sm text-zinc-500 pt-2">{t("dex.willpowerNote")}</p>
          ) : totalLearners === 0 ? (
            <p className="text-sm text-zinc-500 pt-2">{t("dex.noLearners")}</p>
          ) : (
            <div className="space-y-8 pt-2">
              <LearnerSection
                title={t("dex.learnersPool")}
                monsters={learners.move_pool}
                backUrl={currentUrl}
              />
              <LearnerSection
                title={t("dex.learnersStone")}
                monsters={learners.move_stones}
                backUrl={currentUrl}
              />
              <LearnerSection
                title={t("dex.learnersLegacy")}
                monsters={learners.legacy}
                backUrl={currentUrl}
              />
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}
