import Link from "next/link";
import { conceptLabel, getMatrix, getSubstances, type Matrix, type Row, type SubstanceSummary } from "@/lib/api";
import { AppearanceStrip } from "@/lib/appearance";
import { featuredSubstance, rankedDivergences, rankedPreviews } from "@/lib/finding";
import { PlacementSpectrum } from "@/lib/spectrum";
import { PlacementBadge } from "@/lib/placement";

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
  const featured = featuredSubstance(substances);
  const matrix = featured ? await getMatrix(featured.id) : null;
  const top = matrix ? (rankedDivergences(matrix.rows)[0] ?? null) : null;
  const matching = substances.filter((substance) => matches(substance, query));
  const collected = matching.filter((substance) => substance.products > 0);
  const uncollected = matching.filter((substance) => substance.products === 0);

  return (
    <div className="space-y-12">
      <header className="space-y-5">
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
      </header>

      {matrix && top && <Hero matrix={matrix} row={top} />}

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
 * The sharpest disagreement in the corpus, shown rather than described.
 *
 * Derived — most divergent substance, then its strongest-ranked concept — so the landing
 * screen follows the corpus instead of freezing on whatever was collected first. It is
 * the finding itself, not a link to it: a reader who never scrolls has still seen the
 * thing the project exists to show.
 */
function Hero({ matrix, row }: { matrix: Matrix; row: Row }) {
  return (
    <section className="space-y-8 border-y border-rule py-10">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <p className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
          {matrix.substance_name} · {conceptLabel(row.concept)}
        </p>
        <Link
          href={`/substances/${matrix.substance_id}/concepts/${encodeURIComponent(row.concept)}`}
          className="text-meta text-accent underline underline-offset-4"
        >
          Read the quoted text behind this →
        </Link>
      </div>

      <PlacementSpectrum cells={row.cells} products={matrix.products} />

      <AppearanceStrip products={matrix.products} />
    </section>
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
    <form action="/" className="max-w-prose space-y-2">
      <label htmlFor="q" className="block font-mono text-kicker tracking-widest text-ink-muted uppercase">
        Search {total} substances
      </label>
      <div className="flex gap-3">
        <input
          id="q"
          type="search"
          name="q"
          defaultValue={query}
          placeholder="a substance, or a concept they disagree about"
          className="w-full rounded-sheet border border-rule bg-paper px-3 py-2 text-body text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-sheet border border-rule px-4 py-2 font-mono text-kicker tracking-widest uppercase hover:border-accent hover:text-accent"
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
