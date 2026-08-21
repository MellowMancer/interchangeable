/**
 * How a `Placement` is rendered.
 *
 * `ABSENT` must never be styleable as a mild warning: a reader who cannot tell "this
 * manufacturer warns about it" from "we did not find it in the sections we read" is being
 * told something the data does not support. So absence is the only greyed, dashed,
 * unfilled entry, and the only one whose label is a sentence rather than a word.
 *
 * Absence is a key in the table rather than a fallback appended to it. A value the table
 * does not know is a *different* failure — the server's vocabulary grew and this file did
 * not — and rendering it as absence would make the UI assert "not found" about a concept
 * that was found. It gets its own loud state instead.
 */

/** Mirrors `Placement` in `ixq.domain.concept`. Adding a case there must break the build here. */
export type Placement = "4.3" | "4.4" | "4.5" | "4.6" | "6.1" | "absent";

export type PlacementStyle = { label: string; detail: string; className: string };

/** Exhaustive over `Placement`: a new member is a compile error until it is styled. */
const STYLES: Record<Placement, PlacementStyle> = {
  "4.3": {
    label: "Contraindicated",
    detail: "Section 4.3 — contraindications",
    className: "bg-red-600 text-white border-red-700",
  },
  "4.4": {
    label: "Warning",
    detail: "Section 4.4 — warnings and precautions",
    className: "bg-amber-400 text-amber-950 border-amber-500",
  },
  "4.5": {
    label: "Interaction",
    detail: "Section 4.5 — interactions",
    className: "bg-sky-500 text-white border-sky-600",
  },
  "4.6": {
    label: "Pregnancy",
    detail: "Section 4.6 — pregnancy and lactation",
    className: "bg-violet-500 text-white border-violet-600",
  },
  "6.1": {
    label: "Excipient",
    detail: "Section 6.1 — listed as an ingredient, not a clinical restriction",
    className: "bg-teal-600 text-white border-teal-700",
  },
  absent: {
    label: "Not in scanned sections",
    detail: "Not found in the sections collected — not evidence the label omits it",
    className:
      "bg-transparent text-slate-500 border-slate-400 border-dashed dark:text-slate-400",
  },
};

/** Loud on purpose: silence here would be the UI inventing an absence. */
const UNKNOWN: PlacementStyle = {
  label: "Unrecognised",
  detail: "The API reported a placement this build does not know how to render",
  className: "bg-fuchsia-700 text-white border-fuchsia-900",
};

export const ABSENT = STYLES.absent;

export const placementStyle = (placement: string): PlacementStyle =>
  STYLES[placement as Placement] ?? UNKNOWN;

export const PLACEMENT_LEGEND: PlacementStyle[] = Object.values(STYLES);

/**
 * The one place a placement becomes markup.
 *
 * Every screen mounts the same element, so the guarantee that absence renders unfilled
 * and dashed cannot be lost by a call site forgetting to spread `className` — and the
 * legend is necessarily a swatch of what the table actually draws.
 */
export function PlacementBadge({
  placement,
  className = "",
}: {
  placement: string;
  className?: string;
}) {
  const style = placementStyle(placement);
  return (
    <span
      title={style.detail}
      className={`inline-block rounded border px-2 py-0.5 text-xs ${style.className} ${className}`}
    >
      {style.label}
    </span>
  );
}
