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
export type Placement = "4.3" | "4.4" | "4.5" | "4.6" | "6.1" | "absent";

export type PlacementStyle = {
  label: string;
  /** The section number. Provenance only — shown where a claim is being checked, not
   *  where the list is being read: §4.3 tells a reader nothing they do not already get
   *  from the word beside it. */
  section: string | null;
  /** The same thing in words anyone has: one sentence, sentence case, standing on its own
   *  so it reads the same beside a chip, in a tooltip, or under a row label. The
   *  regulatory term is the finding and stays; this is for the reader who lacks it. */
  detail: string;
  className: string;
};

/** Exhaustive over `Placement`: a new member is a compile error until it is styled. */
const STYLES: Record<Placement, PlacementStyle> = {
  "4.3": {
    label: "Contraindicated",
    section: "§4.3",
    detail: "The label says it must not be used.",
    className: "bg-p43 text-p43-on border-p43",
  },
  "4.4": {
    label: "Warning",
    section: "§4.4",
    detail: "The label says it can be used, with care.",
    className: "bg-p44 text-p44-on border-p44",
  },
  "4.5": {
    label: "Interaction",
    section: "§4.5",
    detail: "The label says another medicine affects it.",
    className: "bg-p45 text-p45-on border-p45",
  },
  "4.6": {
    label: "Pregnancy",
    section: "§4.6",
    detail: "The label gives advice for pregnancy or breastfeeding.",
    className: "bg-p46 text-p46-on border-p46",
  },
  "6.1": {
    label: "Excipient",
    section: "§6.1",
    detail: "The label lists it as an ingredient, not a restriction.",
    className: "bg-p61 text-p61-on border-p61",
  },
  absent: {
    label: "Not in scanned sections",
    section: null,
    detail: "Not found in the sections collected. Not evidence the label omits it.",
    className: "bg-p-absent text-ink-muted border-dashed border-rule",
  },
};

/** Loud on purpose: silence here would be the UI inventing an absence. */
const UNKNOWN: PlacementStyle = {
  label: "Unrecognised",
  section: null,
  detail: "The API reported a placement this build does not know how to render.",
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
 * A placement at card size: its colour, and its word on demand.
 *
 * The roster is scanned, not read. Three full badges a row across seventy cards makes
 * CONTRAINDICATED and WARNING the loudest thing on the screen while saying nothing about
 * which substance is worth opening — the concept beside them is the part that varies.
 *
 * Colour is never the only channel: the word is the accessible name and the tooltip, and
 * the comparison this card links to spells every one of them out.
 */
export function PlacementPip({ placement }: { placement: string }) {
  const style = placementStyle(placement);
  return (
    <span
      title={style.detail}
      className={`inline-block h-3 w-6 rounded-sheet border ${style.className}`}
    >
      <span className="sr-only">{style.label}</span>
    </span>
  );
}

/**
 * A placement at column width, for a matrix too wide to carry a full badge.
 *
 * The word without its section code, which is the opposite of the obvious trade. The row
 * already names the concept, so what the cell must say is how binding the filing is —
 * and `CONTRAINDICATED` answers that where `§4.3` sends the reader to a legend, once per
 * cell, in a table whose whole purpose is being read across. The code is kept for anyone
 * checking the claim, in the accessible name and the tooltip.
 *
 * Absence keeps its own treatment here as everywhere: unfilled, dashed, and never a
 * colour. Shrinking a cell is a reason to say less, never a reason to say it differently.
 */
export function PlacementChip({
  placement,
  delayMs,
}: {
  placement: string;
  /** Entrance delay, so a row of chips lands in the order the table reads. */
  delayMs?: number;
}) {
  const style = placementStyle(placement);
  return (
    <span
      title={style.detail}
      style={delayMs === undefined ? undefined : { animationDelay: `${delayMs}ms` }}
      className={`animate-land inline-flex min-h-7 items-center justify-center rounded-sheet border px-2 py-1 text-center text-kicker tracking-wide ${style.className}`}
    >
      {/* The word, not the section code. The row already names the concept, so what a
          cell has to carry is how binding the filing is — and a bare code sends the
          reader to a legend for every cell of a table meant to be read across. The code
          stays for anyone checking the claim. */}
      <span aria-hidden>{style.section ? style.label : "—"}</span>
      <span className="sr-only">{style.detail}</span>
    </span>
  );
}

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
  delayMs,
}: {
  placement: string;
  className?: string;
  /** Entrance delay, so a row of badges lands in the order the table reads. */
  delayMs?: number;
}) {
  const style = placementStyle(placement);
  return (
    <span
      title={style.detail}
      style={delayMs === undefined ? undefined : { animationDelay: `${delayMs}ms` }}
      className={`inline-flex items-baseline gap-1.5 rounded-sheet border px-2 py-1 text-kicker tracking-wide ${style.className} ${className}`}
    >
      {/* The mark the footer's guide draws. Spelling out "Not in scanned sections" here
          left a reader looking up a phrase the guide no longer shows. */}
      {style.section ? (
        style.label
      ) : (
        <>
          <span aria-hidden>&mdash;</span>
          <span className="sr-only">{style.label}</span>
        </>
      )}
    </span>
  );
}
