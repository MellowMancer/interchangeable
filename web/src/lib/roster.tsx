"use client";

/**
 * The roster, filtered as the reader types.
 *
 * The application's one client component, and it is here for a reason no server round
 * trip can meet: a list narrowing on each keystroke needs the keystroke. The page above
 * is still a Server Component, the substances are still fetched on the server, and the
 * browser still never calls the API — this receives a list it is given and filters it.
 *
 * The form still posts to `/` with `q`, so pressing Enter, sharing the URL, or arriving
 * with JavaScript disabled all still search. Live filtering is layered over that rather
 * than replacing it.
 */

import { useState } from "react";
import { Section } from "@/lib/heading";
import Link from "next/link";
import { conceptLabel, type SubstanceSummary } from "./api";
import { rankedPreviews } from "./finding";
import { Concepts, Diverges, Makers } from "./icons";
import { PlacementPip } from "./placement";

/** How many disagreements a card advertises before it defers to the comparison itself. */
const PREVIEW_LIMIT = 3;

/**
 * Whether a substance answers to what was typed.
 *
 * Over the names on a box — the substance, each product, and the holder who makes it.
 * Not over the concepts they disagree about: a reader searching this list is looking for
 * a medicine they have been handed, and matching "pregnancy" to every substance whose
 * labels happen to mention it returns a set nobody asked for.
 */
function matches(substance: SubstanceSummary, query: string): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  return (
    substance.name.toLowerCase().includes(needle) ||
    substance.labels.some((label) => label.toLowerCase().includes(needle))
  );
}

type Order = "divergent" | "name";

/**
 * How the roster can be ordered.
 *
 * Most disagreements first by default: the list exists to be chosen from, and the number
 * of concepts a substance's manufacturers file differently is the only thing on a card
 * that says which is worth opening. Ties fall back to the name so the order is stable.
 */
const ORDERS: Record<Order, (a: SubstanceSummary, b: SubstanceSummary) => number> = {
  divergent: (a, b) => b.divergent - a.divergent || a.name.localeCompare(b.name),
  name: (a, b) => a.name.localeCompare(b.name),
};

const ORDER_LABELS: [Order, string][] = [
  ["divergent", "Most disagreements"],
  ["name", "Name"],
];

export function Roster({
  substances,
  query,
}: {
  substances: SubstanceSummary[];
  query: string;
}) {
  const [typed, setTyped] = useState(query);
  const [order, setOrder] = useState<Order>("divergent");
  const term = typed.trim();

  const matching = substances.filter((substance) => matches(substance, term));
  const collected = matching
    .filter((substance) => substance.products > 0)
    .sort(ORDERS[order]);
  const uncollected = matching.filter((substance) => substance.products === 0);

  return (
    <>
      <form action="/" className="space-y-3">
        <label
          htmlFor="q"
          className="block font-mono text-kicker text-ink-muted"
        >
          Search {substances.length} substances
        </label>
        <div className="flex gap-3">
          <input
            id="q"
            type="search"
            name="q"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="a substance, a product, or who makes it"
            className="w-full rounded-sheet border border-rule bg-paper px-4 py-3.5 text-quote text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
          />
          {/* Kept although the list already filters: without scripting this button is the
              search, and it is also the page's only filled control. */}
          <button
            type="submit"
            className="shrink-0 rounded-sheet border border-accent bg-accent px-6 py-3.5 font-mono text-kicker text-paper hover:border-ink hover:bg-ink"
          >
            Search
          </button>
        </div>
        {term && (
          <button
            type="button"
            onClick={() => setTyped("")}
            className="text-meta text-accent underline underline-offset-4"
          >
            Clear
          </button>
        )}
      </form>

      {/* Beside the search rather than inside it: these narrow and reorder a list, which
          is a different act from looking something up, and the form still has to work
          without scripting. */}
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 font-mono text-kicker text-ink-muted">
        <label htmlFor="order" className="sr-only">
          Order the roster
        </label>
        <span aria-hidden>Order by</span>
        {/* A select, not two buttons: it is one choice from a list, and browsers already
            know how to say that — including on a phone, where a row of toggles is not it. */}
        <select
          id="order"
          value={order}
          onChange={(event) => setOrder(event.target.value as Order)}
          className="rounded-sheet border border-rule bg-paper px-2 py-1 font-mono text-kicker text-ink hover:border-accent focus:border-accent focus:outline-none"
        >
          {ORDER_LABELS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {collected.length > 0 && (
        <section className="space-y-6">
          <Section>
            {term ? `Collected — ${collected.length} matching` : `Collected — ${collected.length}`}
          </Section>
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
          <Section>On the roster, not yet collected — {uncollected.length}</Section>
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
          Nothing on the roster matches <span className="text-ink">{term}</span>. Search
          runs over substance names, product names and the manufacturers who make them.
        </p>
      )}
    </>
  );
}

function Card({ substance }: { substance: SubstanceSummary }) {
  const previews = rankedPreviews(substance);
  const shown = previews.slice(0, PREVIEW_LIMIT);
  const remaining = previews.length - shown.length;

  return (
    <Link
      href={`/substances/${substance.id}`}
      className="flex h-full flex-col gap-4 p-6 transition-transform hover:-translate-y-0.5 hover:bg-rule/30"
    >
      <header className="space-y-1.5">
        <h3 className="font-serif text-quote">{substance.name}</h3>
        <dl className="flex flex-wrap items-center gap-x-4 font-mono text-meta text-ink-muted">
          <Fact icon={<Makers />} term="manufacturers" value={substance.products} />
          <Fact icon={<Concepts />} term="concepts read" value={substance.concepts} />
          <Fact
            icon={<Diverges />}
            term="concepts they disagree about"
            value={substance.divergent}
            accent={substance.divergent > 0}
          />
        </dl>
      </header>

      {shown.length > 0 ? (
        <ul className="space-y-1.5">
          {shown.map((preview) => (
            <li key={preview.concept} className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate text-meta">{conceptLabel(preview.concept)}</span>
              <span className="flex shrink-0 gap-1">
                {preview.placements.map((placement) => (
                  <PlacementPip key={placement} placement={placement} />
                ))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-meta text-ink-muted">Agrees everywhere that was read.</p>
      )}

      <p className="mt-auto text-meta text-accent">
        {remaining > 0
          ? `Compare all ${substance.concepts} concepts  |  ${remaining} more disagreement${remaining === 1 ? "" : "s"} →`
          : `Compare all ${substance.concepts} concepts →`}
      </p>
    </Link>
  );
}


/** One number about a substance, named for a screen reader and drawn for everyone else. */
const Fact = ({
  icon,
  term,
  value,
  accent = false,
}: {
  icon: React.ReactNode;
  term: string;
  value: number;
  accent?: boolean;
}) => (
  // Titled on the group, so hovering the number explains it as readily as the icon.
  <div title={`${value} ${term}`} className="flex items-center gap-1.5">
    <dt className="sr-only">{term}</dt>
    <span aria-hidden className={accent ? "text-accent" : undefined}>
      {icon}
    </span>
    <dd className={accent ? "text-accent" : undefined}>{value}</dd>
  </div>
);
