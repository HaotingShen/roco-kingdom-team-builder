import RichDescription from "@/components/RichDescription";
import type { Lang } from "@/i18n";

type Props = {
  lang: Lang;
  cname: string;
  desc: string;
  moveImg: string;
  typeImg: string | null;
  energyImg: string;
  catImg: string;
  energy: number | string | null;
  power: number | string | null;
  isDef: boolean;
  isSta: boolean;
  t: (key: string) => string;
};

/**
 * Inner content of a move card (image + type/name + energy + category + description).
 *
 * Language-aware mobile layout. Both languages can render either the stacked or grid layout —
 * the switchover point differs because English names are typically longer than Chinese ones:
 *  - English on <mvcard (450px): 3-row stacked layout — [type+name] / [energy+power] / [description].
 *  - Chinese on <400px: same 3-row stacked layout.
 *  - At or above each language's switchover width: the original 6-col / 2-row grid.
 */
export default function MoveCardInner({
  lang,
  cname,
  desc,
  moveImg,
  typeImg,
  energyImg,
  catImg,
  energy,
  power,
  isDef,
  isSta,
  t,
}: Props) {
  const isEn = lang === "en";

  const Image = (
    <img
      src={moveImg}
      alt={cname}
      width={80}
      height={80}
      className="h-full w-full object-contain"
      loading="lazy"
      onError={(e) => {
        (e.currentTarget as HTMLImageElement).style.display = "none";
      }}
    />
  );

  const categoryValue = isDef ? t("dex.defense") : isSta ? t("dex.status") : power ?? "—";

  return (
    <>
      {/* Mobile 3-row stacked layout. Used at <450px for English (mvcard) and <400px for Chinese,
          since Chinese move names are short enough that the grid layout still fits down to 400px. */}
      <div
        className={`
          grid
          ${isEn ? "mvcard:hidden" : "min-[400px]:hidden"}
          grid-cols-[70px_minmax(0,1fr)]
          grid-rows-[auto_auto_auto]
          items-start
          gap-x-2 gap-y-1
          text-[13px]
        `}
      >
        {/* Image (spans all 3 rows) */}
        <div className="row-[1/4] self-center h-[70px] w-[70px] rounded bg-zinc-100/60 overflow-hidden flex items-center justify-center">
          {Image}
        </div>

        {/* Row 1: type icon + move name */}
        <div className="col-[2] row-[1] min-w-0 self-center">
          <div className="flex items-center gap-1 min-w-0">
            {typeImg ? (
              <img
                src={typeImg}
                alt=""
                aria-hidden="true"
                width={30}
                height={30}
                className="block shrink-0 h-[26px] w-[26px] sm:h-[30px] sm:w-[30px]"
              />
            ) : null}
            <div className="font-medium whitespace-normal break-words min-w-0 leading-tight text-[15px] moves-md:text-sm">
              {cname}
            </div>
          </div>
        </div>

        {/* Row 2: energy + category, left-aligned under the name */}
        <div className="col-[2] row-[2] flex items-center gap-6 pl-1">
          <div className="flex items-center gap-[6px]">
            <img src={energyImg} alt="" aria-hidden="true" width={15} height={15} />
            <span className="text-[13px] tabular-nums">{energy ?? "—"}</span>
          </div>
          <div className="flex items-center gap-[6px]">
            <img src={catImg} alt="" aria-hidden="true" width={15} height={15} />
            <span className="text-[13px] tabular-nums">{categoryValue}</span>
          </div>
        </div>

        {/* Row 3: description */}
        <div className="col-[2] row-[3] text-[13px] text-zinc-600 pl-1">
          <RichDescription text={desc} />
        </div>
      </div>

      {/* Default 6-col / 2-row grid layout.
            - English: hidden below mvcard (450px); the stacked layout above takes over.
            - Chinese: hidden below 400px; the stacked layout above takes over.
            - Grid sizing is uniform across languages (70px image, 8px col-4 spacer on mobile,
              widening at sm/md/lg). */}
      <div
        className={`
          ${isEn ? "hidden mvcard:grid" : "hidden min-[400px]:grid"}
          grid-cols-[70px_minmax(0,1fr)_40px_8px_50px_4px]
          sm:grid-cols-[80px_minmax(0,1fr)_40px_12px_50px_4px]
          md:grid-cols-[80px_minmax(0,1fr)_40px_20px_50px_8px]
          lg:grid-cols-[80px_minmax(0,1fr)_40px_28px_50px_12px]
          grid-rows-[auto_auto]
          items-start
          gap-2
          text-[13px] sm:text-sm
        `}
      >
        {/* Image (spans both rows) */}
        <div className="row-[1/3] self-center h-[70px] w-[70px] sm:h-[80px] sm:w-[80px] rounded bg-zinc-100/60 overflow-hidden flex items-center justify-center">
          {Image}
        </div>

        {/* Type icon + Move name (col 2) */}
        <div className="col-[2] self-center min-w-0">
          <div className="flex items-center gap-1 min-w-0">
            {typeImg ? (
              <img
                src={typeImg}
                alt=""
                aria-hidden="true"
                width={30}
                height={30}
                className="block shrink-0 h-[26px] w-[26px] sm:h-[30px] sm:w-[30px]"
              />
            ) : null}
            <div className="font-medium whitespace-normal break-words min-w-0 leading-tight text-[15px] moves-md:text-sm">
              {cname}
            </div>
          </div>
        </div>

        {/* Energy icon + value (col 3) */}
        <div className="col-[3] self-center flex items-center justify-end gap-[6px]">
          <img src={energyImg} alt="" aria-hidden="true" width={15} height={15} />
          <span className="w-8 text-[13px] sm:text-xs text-left tabular-nums">{energy ?? "—"}</span>
        </div>

        {/* (col 4 is the spacer) */}

        {/* Category icon + power/label (col 5) */}
        <div className="col-[5] self-center flex items-center justify-end gap-x-[6px]">
          <img src={catImg} alt="" aria-hidden="true" width={15} height={15} />
          <span className="w-10 text-[13px] sm:text-xs text-left tabular-nums">{categoryValue}</span>
        </div>

        {/* (col 6 is the end spacer) */}

        {/* Description (row 2, spans full width from col 2 to end) */}
        <div className="row-[2/3] col-[2/-1] text-[13px] sm:text-sm text-zinc-600 pl-1">
          <RichDescription text={desc} />
        </div>
      </div>
    </>
  );
}