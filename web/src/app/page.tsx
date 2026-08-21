import type { CSSProperties } from "react";
import Link from "next/link";
import { conceptLabel, getSubstances, type SubstanceSummary } from "@/lib/api";
import { rankedPreviews } from "@/lib/finding";
import { PLACEMENT_LEGEND, PlacementBadge } from "@/lib/placement";

/** Degrees of splay between neighbouring chips in the placement fan. */
const ANGLE_PER_CHIP = 18;

/** How far each chip lifts out of the stack, along its own axis, in pixels. */
const LIFT_PER_CHIP = 18;

/** How many disagreements a card advertises before it defers to the comparison itself. */
const PREVIEW_LIMIT = 3;

/**
 * The roster, and what a comparison of each substance would show.
 *
 * A card carries its strongest disagreements rather than only a count, so the choice of
 * what to open is made on the finding rather than on the name.
 *
 * Search is a plain GET form read from the query string, not a client component: the
 * whole application is server-rendered, and a filter over a list the server already holds
 * does not need to become the first piece of client state in it.
 */
export default async function Home({ searchParams }: PageProps<"/">) {
  const { q } = await searchParams;
  const query = (Array.isArray(q) ? q[0] : q)?.trim() ?? "";

  const substances = await getSubstances();
  const matching = substances.filter((substance) => matches(substance, query));
  const collected = matching.filter((substance) => substance.products > 0);
  const uncollected = matching.filter((substance) => substance.products === 0);

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

      <Search query={query} total={substances.length} />

      {collected.length > 0 && (
        <section className="space-y-6">
          <Kicker>
            {query ? `Collected — ${collected.length} matching` : `Collected — ${collected.length}`}
          </Kicker>
          <ul className="grid border-t border-rule md:grid-cols-2">
            {collected.map((substance) => (
              <li
                key={substance.id}
                className="border-b border-rule md:odd:border-r md:odd:last:border-r-0"
              >
                <Card substance={substance} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {uncollected.length > 0 && (
        <section className="space-y-4 border-t border-rule pt-10">
          <Kicker>On the roster, not yet collected — {uncollected.length}</Kicker>
          <p className="max-w-prose text-meta text-ink-muted">
            Configured but not yet fetched, so there is nothing to compare. Not a finding
            of agreement.
          </p>
          <ul className="flex flex-wrap gap-x-5 gap-y-2 font-mono text-meta text-ink-muted">
            {uncollected.map((substance) => (
              <li key={substance.id}>{substance.name}</li>
            ))}
          </ul>
        </section>
      )}

      {matching.length === 0 && (
        <p className="max-w-prose text-ink-muted">
          Nothing on the roster matches <span className="text-ink">{query}</span>. Search
          runs over substance names and the concepts their manufacturers disagree about.
        </p>
      )}
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

/**
 * Matches a substance name or any concept its manufacturers disagree about.
 *
 * Searching a symptom is the question a reader actually has — "where do these labels
 * disagree about pregnancy?" — and matching only names would answer it with nothing.
 */
function matches(substance: SubstanceSummary, query: string): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  return (
    substance.name.toLowerCase().includes(needle) ||
    substance.divergences.some((d) => conceptLabel(d.concept).toLowerCase().includes(needle))
  );
}

function Search({ query, total }: { query: string; total: number }) {
  return (
    <form action="/" className="space-y-3">
      <label
        htmlFor="q"
        className="block font-mono text-kicker tracking-widest text-ink-muted uppercase"
      >
        Search {total} substances
      </label>
      <div className="flex gap-3">
        <input
          id="q"
          type="search"
          name="q"
          defaultValue={query}
          placeholder="a substance, or a concept they disagree about"
          className="w-full rounded-sheet border border-rule bg-paper px-4 py-3.5 text-quote text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        />
        {/* The page's only filled control. In a document idiom prominence comes from
            scale and a single solid mark, not from adding chrome to everything. */}
        <button
          type="submit"
          className="shrink-0 rounded-sheet border border-accent bg-accent px-6 py-3.5 font-mono text-kicker tracking-widest text-paper uppercase hover:border-ink hover:bg-ink"
        >
          Search
        </button>
      </div>
      {query && (
        <Link href="/" className="inline-block text-meta text-accent underline underline-offset-4">
          Clear
        </Link>
      )}
    </form>
  );
}

const Kicker = ({ children }: { children: React.ReactNode }) => (
  <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">{children}</h2>
);

function Card({ substance }: { substance: SubstanceSummary }) {
  const previews = rankedPreviews(substance);
  const shown = previews.slice(0, PREVIEW_LIMIT);
  const remaining = previews.length - shown.length;

  return (
    <Link
      href={`/substances/${substance.id}`}
      className="flex h-full flex-col gap-4 p-6 transition-transform hover:-translate-y-0.5 hover:bg-rule/30"
    >
      <header className="space-y-1">
        <h3 className="font-serif text-quote">{substance.name}</h3>
        <p className="font-mono text-meta text-ink-muted">
          {substance.products} manufacturers · {substance.concepts} concepts ·{" "}
          {substance.divergent === 0 ? "none disagree" : `${substance.divergent} disagree`}
        </p>
      </header>

      {shown.length > 0 ? (
        <ul className="space-y-2">
          {shown.map((preview) => (
            <li key={preview.concept} className="flex flex-wrap items-center gap-2">
              <span className="min-w-40 text-meta">{conceptLabel(preview.concept)}</span>
              {preview.placements.map((placement) => (
                <PlacementBadge key={placement} placement={placement} />
              ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-meta text-ink-muted">Agrees everywhere that was read.</p>
      )}

      <p className="mt-auto text-meta text-accent">
        {remaining > 0
          ? `Compare all ${substance.concepts} concepts — ${remaining} more disagreement${remaining === 1 ? "" : "s"} →`
          : `Compare all ${substance.concepts} concepts →`}
      </p>
    </Link>
  );
}
