/**
 * What was read, and where in it a quote falls.
 *
 * Both answer the question every absence claim depends on — "compared against what?" —
 * and both were previously sentences. A reader could not tell from "characters 836–1016"
 * whether that was the opening of a section or its tail, and the offsets are the
 * provenance guarantee, so being unable to picture them wasted the strongest thing the
 * page has.
 */

import { type ProductColumn } from "./api";
import { placementStyle, SECTION_PLACEMENTS } from "./placement";

/**
 * The sections collected for one label, against the sections a concept can be placed in.
 *
 * Drawn as the full set with the unread ones left hollow rather than as a list of what
 * was read: a list of four codes cannot show that a fifth was skipped, and the scope of
 * an absence is exactly what was *not* looked at.
 */
export function SectionCoverage({
  scanned,
  className = "",
}: {
  scanned: string[];
  className?: string;
}) {
  return (
    <ul className={`flex flex-wrap gap-1 ${className}`}>
      {SECTION_PLACEMENTS.map((placement) => {
        const read = scanned.includes(placement);
        const style = placementStyle(placement);
        return (
          <li
            key={placement}
            title={read ? `${style.detail} — read` : `${style.detail} — not collected`}
            className={`rounded-sheet border px-2 py-0.5 font-mono text-kicker ${
              read ? style.className : "border-dashed border-rule text-ink-muted"
            }`}
          >
            {style.section}
            <span className="sr-only">{read ? " read" : " not collected"}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Where a quote sits inside its section.
 *
 * The span is drawn to scale but floored at a visible width: a 180-character clause in a
 * 3,589-character section is a hairline, and a mark too thin to see would report the
 * position as absent.
 */
export function QuotePosition({
  charStart,
  charEnd,
  sectionLength,
  sectionCode,
}: {
  charStart: number;
  charEnd: number;
  sectionLength: number;
  sectionCode: string;
}) {
  const left = (charStart / sectionLength) * 100;
  const width = ((charEnd - charStart) / sectionLength) * 100;

  return (
    <figure className="max-w-prose space-y-1">
      <div className="relative h-2 rounded-sheet border border-rule">
        <div
          className="absolute inset-y-0 rounded-sheet bg-accent"
          style={{ left: `${left}%`, width: `${width}%`, minWidth: "2px" }}
        />
      </div>
      <figcaption className="font-mono text-kicker text-ink-muted">
        characters {charStart}–{charEnd} of {sectionLength} in §{sectionCode}
      </figcaption>
    </figure>
  );
}

/** The sections read for a label, named — the scope every absence on it is measured against. */
export const scopeOf = (product: ProductColumn | undefined) => product?.scanned ?? [];
