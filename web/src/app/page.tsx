import type { CSSProperties } from "react";
import { getSubstances } from "@/lib/api";
import { PLACEMENT_LEGEND } from "@/lib/placement";
import { Roster } from "@/lib/roster";

/** Degrees of splay between neighbouring chips in the placement fan. */
const ANGLE_PER_CHIP = 18;

/** How far each chip lifts out of the stack, along its own axis, in pixels. */
const LIFT_PER_CHIP = 18;

/**
 * The roster, and what a comparison of each substance would show.
 *
 * A card carries its strongest disagreements rather than only a count, so the choice of
 * what to open is made on the finding rather than on the name.
 *
 * The list itself is handed to `Roster`, which filters it as the reader types. That is
 * the one place in the application that runs in the browser; everything here, including
 * the fetch, still happens on the server.
 */
export default async function Home({ searchParams }: PageProps<"/">) {
  const { q } = await searchParams;
  const query = (Array.isArray(q) ? q[0] : q)?.trim() ?? "";

  const substances = await getSubstances();

  return (
    <div className="space-y-12">
      <header className="grid items-center gap-10 lg:grid-cols-[1fr_minmax(0,22rem)]">
        <div className="space-y-5">
        {/* Its own measure: inside the prose column a display size wraps to three uneven
            lines, and the strapline is the one thing on the page that must land cleanly. */}
        <h1 className="max-w-3xl font-serif text-display font-normal text-balance">
          Same drug. Different manufacturer. Different label.
        </h1>
        <p className="max-w-prose text-ink-muted">
          When a pharmacy dispenses a generic it substitutes whichever manufacturer&apos;s
          version is on the shelf, and everyone assumes same drug, same information.{" "}
          <span className="text-ink">Interchangeable?</span> compares the UK Summaries of
          Product Characteristics of every authorised product sharing an active substance
          and shows where the manufacturers disagree — with the quoted text behind every
          claim.
        </p>
        <p className="max-w-prose text-meta text-ink-muted">
          The question mark is deliberate. This asks whether these products really are
          interchangeable; it does not assert that they are not.
        </p>
        </div>
        <PlacementFan />
      </header>

      <Roster substances={substances} query={query} />
    </div>
  );
}

/**
 * The vocabulary itself, fanned out.
 *
 * Every cell on every comparison is one of these, so showing them here teaches the whole
 * grid before a reader meets it — and the header's right half was empty.
 *
 * Rendered from `PLACEMENT_LEGEND`, so it is necessarily the set the tables actually draw
 * and cannot drift from them. It asserts nothing about the corpus: these are the places a
 * concept can be filed, not a finding about any substance.
 */
function PlacementFan() {
  const chips = PLACEMENT_LEGEND.filter((style) => style.section);
  const middle = (chips.length - 1) / 2;

  return (
    <ul aria-hidden className="relative hidden h-52 lg:block">
      {chips.map((style, index) => {
        const offset = index - middle;
        return (
          <li
            key={style.label}
            style={
              {
                // Every card pivots on the same point at its left edge, so they splay
                // like a hand held at one corner. About their own centres they would
                // cross over. The lift is in the card's own rotated frame, so it clears
                // its neighbour rather than sliding along it; `.fan-chip` assembles both
                // into the transform and adds the hover slide.
                transformOrigin: "0% 50%",
                "--fan-angle": `${offset * ANGLE_PER_CHIP}deg`,
                "--fan-lift": `${offset * LIFT_PER_CHIP}px`,
                zIndex: index,
              } as CSSProperties
            }
            className={`fan-chip absolute top-1/2 left-0 flex w-60 items-baseline justify-end gap-4 rounded-sheet border px-4 py-3 font-mono text-meta ${style.className}`}
          >
            <span>{style.label}</span>
            <span className="opacity-80">{style.section}</span>
          </li>
        );
      })}
    </ul>
  );
}
