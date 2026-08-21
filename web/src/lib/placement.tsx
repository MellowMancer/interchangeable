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
 *
 * Every colour here is a theme token, never a literal, so the whole placement palette is
 * repainted from `globals.css` without this file changing.
 */

/** Mirrors `Placement` in `ixq.domain.concept`. Adding a case there must break the build here. */
export type Placement = "4.3" | "4.4" | "4.5" | "4.6" | "absent";

export type PlacementStyle = {
  label: string;
  /** The section number, shown alongside the label so colour is never the only channel. */
  section: string | null;
  detail: string;
  className: string;
};

/** Exhaustive over `Placement`: a new member is a compile error until it is styled. */
const STYLES: Record<Placement, PlacementStyle> = {
  "4.3": {
    label: "Contraindicated",
    section: "§4.3",
    detail: "Section 4.3 — contraindications",
    className: "bg-p43 text-p43-on border-p43",
  },
  "4.4": {
    label: "Warning",
    section: "§4.4",
    detail: "Section 4.4 — warnings and precautions",
    className: "bg-p44 text-p44-on border-p44",
  },
  "4.5": {
    label: "Interaction",
    section: "§4.5",
    detail: "Section 4.5 — interactions",
    className: "bg-p45 text-p45-on border-p45",
  },
  "4.6": {
    label: "Pregnancy",
    section: "§4.6",
    detail: "Section 4.6 — pregnancy and lactation",
    className: "bg-p46 text-p46-on border-p46",
  },
  absent: {
    label: "Not in scanned sections",
    section: null,
    detail: "Not found in the sections collected — not evidence the label omits it",
    className: "bg-p-absent text-ink-muted border-dashed border-rule",
  },
};

/** Loud on purpose: silence here would be the UI inventing an absence. */
const UNKNOWN: PlacementStyle = {
  label: "Unrecognised",
  section: null,
  detail: "The API reported a placement this build does not know how to render",
  className: "bg-p-unknown text-p-unknown-on border-p-unknown",
};

export const ABSENT = STYLES.absent;

export const placementStyle = (placement: string): PlacementStyle =>
  STYLES[placement as Placement] ?? UNKNOWN;

export const PLACEMENT_LEGEND: PlacementStyle[] = Object.values(STYLES);

/**
 * The sections a concept can be placed in, in the order the SmPC prints them.
 *
 * Derived from `STYLES` rather than restated, so a new section added there appears in
 * every spectrum without this list being remembered. `absent` is excluded because it is
 * not a section: giving it a column would draw absence as a place a label puts things.
 */
export const SECTION_PLACEMENTS: Placement[] = (Object.keys(STYLES) as Placement[]).filter(
  (placement) => placement !== "absent",
);

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
      className={`inline-flex items-baseline gap-1.5 rounded-sheet border px-2 py-1 text-kicker tracking-wide uppercase ${style.className} ${className}`}
    >
      {style.label}
      {style.section && <span className="font-mono opacity-80">{style.section}</span>}
    </span>
  );
}
