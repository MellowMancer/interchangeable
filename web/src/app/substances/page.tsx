import Link from "next/link";
import { conceptLabel, getSubstances, type SubstanceSummary } from "@/lib/api";
import { rankedPreviews } from "@/lib/finding";
import { PlacementBadge } from "@/lib/placement";

/** How many disagreements a card advertises before it defers to the comparison itself. */
const PREVIEW_LIMIT = 3;

/**
 * Every substance on the roster, and what a comparison of it would show.
 *
 * A card carries its strongest disagreements rather than only a count, so the choice of
 * what to open is made on the finding rather than on the name. The roster is a scrolling
 * page rather than a row of switcher links because it grows with the corpus: eight names
 * fit on one line, a hundred do not.
 */
export default async function SubstancesPage() {
  const substances = await getSubstances();
  const collected = substances.filter((substance) => substance.products > 0);
  const uncollected = substances.filter((substance) => substance.products === 0);

  return (
    <div className="space-y-12">
      <header className="space-y-4">
        <h1 className="font-serif text-title font-normal tracking-tight">Substances</h1>
        <p className="max-w-prose text-ink-muted">
          Every authorised product sharing an active ingredient, compared. The concepts on
          a card are where its manufacturers place the same fact in different sections.
        </p>
      </header>

      {collected.length > 0 && (
        <section className="space-y-6">
          <Kicker>Collected — {collected.length}</Kicker>
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
    </div>
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
      className="flex h-full flex-col gap-4 p-6 hover:bg-rule/30"
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
