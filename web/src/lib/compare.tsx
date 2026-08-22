"use client";

/**
 * The comparison, over the labels a reader chose.
 *
 * Everything a reader picks between sits here: the matrix, the concepts every chosen label
 * agrees on, and what those labels say about shelf life and storage. Choosing is why this
 * is the one interactive part of the page — an all-columns-at-once view answers "where do
 * these ten disagree", but nobody arrives with that question. They arrive holding two
 * boxes.
 *
 * Everything above it — what the substance is for, what the products look like — describes
 * the substance rather than any pair, and stays server-rendered and unchanged.
 *
 * Nothing is fetched here. The page already holds every product's placements and quotes,
 * so narrowing to a selection is a filter, never a request.
 */

import { useEffect, useState } from "react";
import { Section } from "@/lib/heading";
import Link from "next/link";
import {
  conceptLabel,
  manufacturer,
  type Matrix,
  type ProductColumn,
  type Row,
  type ValueSection,
} from "./api";
import { holderGroups, partition } from "./finding";
import { Makers } from "./icons";
import { PlacementBadge, PlacementChip } from "./placement";

export function Comparison({ matrix }: { matrix: Matrix }) {
  const [chosen, setChosen] = useState<string[]>(() =>
    matrix.products.map((product) => product.external_id),
  );

  /**
   * A narrowed comparison survives leaving the page and coming back.
   *
   * Held per substance for the session only: which two labels someone is holding is a
   * question they are asking now, not a preference worth remembering next week. Read after
   * mount rather than during render, because the server has no session storage and a
   * differing first paint would be a hydration mismatch.
   */
  const remembered = `chosen:${matrix.substance_id}`;

  useEffect(() => {
    try {
      const held = window.sessionStorage.getItem(remembered);
      if (!held) return;
      const ids: string[] = JSON.parse(held);
      const live = ids.filter((id) => matrix.products.some((p) => p.external_id === id));
      // Reading a browser store after mount is precisely what an effect is for; the rule
      // guards against effects that drive renders, and this runs once per substance.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (live.length) setChosen(live);
    } catch {
      // Storage can be unavailable or hold something stale; the full comparison is a
      // correct answer either way, so there is nothing to report.
    }
  }, [remembered, matrix.products]);

  const choose = (ids: string[]) => {
    setChosen(ids);
    try {
      window.sessionStorage.setItem(remembered, JSON.stringify(ids));
    } catch {
      // Not being able to remember is not a reason to refuse the change.
    }
  };

  const products = matrix.products.filter((product) => chosen.includes(product.external_id));
  const holders = new Set(products.map((product) => manufacturer(product)));

  // Value sections name holders, not products. A holder with several labels resolves to
  // its first: the page it opens carries the others in its own shelf.
  const labelOf = new Map(
    [...matrix.products].reverse().map((product) => [manufacturer(product), product.external_id]),
  );

  // Recomputed over the chosen labels, never filtered from the whole set: two products
  // that agree can both diverge from a third, and carrying the full comparison's verdict
  // into a pair would report a disagreement neither of them has.
  const rows: Row[] = matrix.rows.map((row) => {
    const cells = row.cells.filter((cell) => chosen.includes(cell.product_external_id));
    const placements = new Set(cells.map((cell) => cell.placement));
    return { ...row, cells, diverges: placements.size > 1 };
  });
  const { divergent, agreeing } = partition(rows);

  const values: ValueSection[] = matrix.values
    .map((section) => ({
      ...section,
      groups: section.groups
        .map((group) => ({
          ...group,
          manufacturers: group.manufacturers.filter((name) => holders.has(name)),
        }))
        .filter((group) => group.manufacturers.length > 0),
    }))
    .map((section) => ({
      ...section,
      collected: section.groups.reduce((n, group) => n + group.manufacturers.length, 0),
      total: holders.size,
    }))
    .filter((section) => section.groups.length > 0);

  return (
    <>
      <Chooser products={matrix.products} chosen={chosen} onChange={choose} />

      {products.length < 2 ? (
        <p className="max-w-prose text-ink-muted">
          Choose at least two labels above. A comparison of one is just a label — open it
          from the quick links instead.
        </p>
      ) : (
        <>
          {divergent.length > 0 ? (
            <section className="space-y-4">
              <Section>
                Disagreements — {divergent.length}
              </Section>
              <DivergenceTable matrix={matrix} rows={divergent} products={products} />
            </section>
          ) : (
            <section className="space-y-4">
              <Section>Disagreements</Section>
              <p className="max-w-prose text-ink-muted">
                Nowhere that was scanned. Every concept below sits in the same section on
                every label chosen.
              </p>
            </section>
          )}

          {agreeing.length > 0 && (
            <section className="section-break space-y-4">
              <Section>Agreements — {agreeing.length}</Section>
              <ul className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
                {agreeing.map((row) => (
                  <li key={row.concept}>
                    <Link
                      href={`/substances/${matrix.substance_id}/concepts/${encodeURIComponent(row.concept)}`}
                      className="flex items-baseline justify-between gap-3 border-b border-rule py-1.5 hover:text-accent"
                    >
                      <span>{conceptLabel(row.concept)}</span>
                      <PlacementBadge placement={row.cells[0]?.placement ?? "absent"} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <ValueSections sections={values} labelOf={labelOf} />
        </>
      )}
    </>
  );
}

/**
 * Which labels the comparison is over.
 *
 * Folded away, because it is a control rather than content: it is touched once, and open
 * it costs five rows between the description and the finding on every visit.
 *
 * Every label starts chosen. A default subset would mean the page chose what a reader is
 * comparing — and the counts above it, which are measured over all of them, would then
 * describe a different set from the grid below. Narrowing is the reader's move.
 */
function Chooser({
  products,
  chosen,
  onChange,
}: {
  products: ProductColumn[];
  chosen: string[];
  onChange: (chosen: string[]) => void;
}) {
  const all = products.map((product) => product.external_id);
  const narrowed = chosen.length < products.length;

  return (
    // Bordered and filled, because it is the one thing on the page a reader acts on.
    // Set like every other heading it read as another block of text and nobody found it.
    // Open by default: the labels being compared are part of reading the page, not a
    // setting behind a control. Collapsing is the reader's move once they have seen them.
    <details
      open
      className={`group rounded-sheet border bg-rule/30 px-5 py-4 ${
        narrowed ? "border-accent" : "border-rule"
      }`}
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <span className="flex items-center gap-3 font-serif text-quote text-ink">
          <span
            aria-hidden
            className={`h-6 w-1.5 shrink-0 rounded-sheet ${narrowed ? "bg-accent" : "bg-ink-muted"}`}
          />
          Comparing{" "}
          <span className={narrowed ? "text-accent" : undefined}>{chosen.length}</span>{" "}
          {chosen.length === 1 ? "product" : "products"}
        </span>
        <span className="rounded-sheet border border-rule bg-paper px-3 py-1 font-mono text-kicker tracking-widest text-ink-muted uppercase group-hover:border-accent group-hover:text-accent">
          <span className="group-open:hidden">Choose ↓</span>
          <span className="hidden group-open:inline">Collapse ↑</span>
        </span>
      </summary>

      <div className="mt-4 space-y-3">
        <div className="flex gap-4 font-mono text-kicker tracking-widest uppercase">
          <button
            type="button"
            onClick={() => onChange(all)}
            className="text-ink-muted hover:text-ink"
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-ink-muted hover:text-ink"
          >
            None
          </button>
        </div>

        <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((product) => {
            const picked = chosen.includes(product.external_id);
            return (
              <li key={product.external_id}>
                <label className="flex cursor-pointer items-baseline gap-3 border-b border-rule py-1.5">
                  <input
                    type="checkbox"
                    checked={picked}
                    onChange={() =>
                      onChange(
                        picked
                          ? chosen.filter((id) => id !== product.external_id)
                          : [...chosen, product.external_id],
                      )
                    }
                    className="accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-meta">{manufacturer(product)}</span>
                    <span className="block truncate font-mono text-kicker text-ink-muted">
                      {product.variant ?? product.name}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  );
}

/** Above this many columns a badge no longer fits, and the cells become chips. */
const COMPACT_ABOVE = 5;
/**
 * §6.3 and §6.4, quoted rather than judged.
 *
 * These sections state a value instead of filing a concept, so they never enter the
 * placement matrix — a shelf life is not a place a warning can live. They are shown
 * because two labels for one substance disagreeing on whether it needs refrigerating is
 * an interchangeability finding in its own right, and one a reader can evaluate directly.
 *
 * Every distinct wording is printed verbatim and attributed. Nothing here says the labels
 * require different things: "Do not store above 25°C" and "Store below 25°C" are the same
 * instruction, and only the reader can tell that apart from a real difference.
 */
function ValueSections({
  sections,
  labelOf,
}: {
  sections: ValueSection[];
  labelOf: Map<string, string>;
}) {
  if (sections.length === 0) return null;

  return (
    <section className="section-break space-y-4">
      <Section>Storage and shelf life</Section>
      <div className="space-y-8">
        {sections.map((section) => (
          <article key={section.code} className="space-y-3">
            <h3 className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-kicker tracking-widest text-ink-muted uppercase">
              <span>
                §{section.code} — {section.heading}
              </span>
              {section.groups.length > 1 && (
                <span className="rounded-sheet border border-accent px-2 py-0.5 text-accent">
                  {section.groups.length} different statements
                </span>
              )}
            </h3>

            {/* A card each, not rows of a list. A run of statements with their holders on
                a muted line underneath read as one table; the question is which brands say
                which thing, so each answer is its own object with its brands stacked in
                it. */}
            <ul className="animate-deal grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[...section.groups]
                .sort((a, b) => b.manufacturers.length - a.manufacturers.length)
                .map((group) => (
                  <li
                    key={group.text}
                    className={`flex flex-col gap-3 rounded-sheet border p-4 ${
                      section.groups.length > 1 ? "border-accent/40" : "border-rule"
                    }`}
                  >
                    <span className="space-y-0.5 font-serif text-body">
                      {group.text
                        .split(/\n+/)
                        .map((line) => line.trim())
                        .filter(Boolean)
                        .map((line) => (
                          <span key={line} className="block">
                            {line}
                          </span>
                        ))}
                    </span>
                    <span className="mt-auto space-y-1 border-t border-rule pt-2">
                      <span className="flex items-center gap-1.5 font-mono text-kicker text-accent">
                        <Makers />
                        From {group.manufacturers.length}{" "}
                        {group.manufacturers.length === 1 ? "manufacturer" : "manufacturers"}
                      </span>
                      {group.manufacturers.map((name) => (
                        <span key={name} className="block truncate font-mono text-kicker text-ink-muted">
                          <Maker name={name} labelOf={labelOf} />
                        </span>
                      ))}
                    </span>
                  </li>
                ))}
            </ul>

            {section.collected < section.total && (
              <p className="text-kicker text-ink-muted">
                {section.total - section.collected} of {section.total} have no §{section.code}{" "}
                collected — not evidence they state nothing.
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
/**
 * Products of one holder, kept adjacent and named once.
 *
 * Grouping is by `holder_id` where the label carries it, because `ma_holder` is free text
 * and two spellings of one company would otherwise read as two manufacturers — invisible
 * at three columns, certain at ten, and it would manufacture a divergence.
 *
 * The products are *not* merged. One holder's capsule and tablet disagree on seven
 * concepts in the collected corpus — all of them excipients, which is exactly what
 * changes between two formulations of the same molecule. Collapsing a holder into one
 * column would delete that, so the holder spans its products rather than replacing them.
 */
function DivergenceTable({
  matrix,
  rows,
  products,
}: {
  matrix: Matrix;
  rows: Row[];
  products: ProductColumn[];
}) {
  const groups = holderGroups(products);
  const ordered = groups.flatMap((g) => g.products);
  const compact = ordered.length > COMPACT_ABOVE;

  return (
    <div className="space-y-2">
      {/* A cut-off table on a phone reads as broken rather than as scrollable. */}
      <p className="font-mono text-kicker text-ink-muted md:hidden">
        scroll for all {ordered.length} products →
      </p>
      <div className="overflow-x-auto">
        <table className="w-max min-w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-20 bg-paper p-2 text-left font-normal">
                <span className="sr-only">Concept</span>
              </th>
              {groups.map((group) => (
                <th
                  key={group.name}
                  colSpan={group.products.length}
                  scope="colgroup"
                  className="border-l border-rule p-0 text-left align-bottom font-medium first:border-l-0"
                >
                  <Link
                    href={`/products/${group.products[0].external_id}`}
                    className="block h-full px-2 pt-2 hover:bg-rule/40 hover:text-accent"
                  >
                    {group.name}
                  </Link>
                </th>
              ))}
            </tr>
            <tr className="border-b border-rule">
              <th className="sticky left-0 z-10 bg-paper p-2" />
              {ordered.map((product) => (
                <th
                  key={product.external_id}
                  scope="col"
                  className="min-w-36 p-0 text-left align-bottom font-normal"
                >
                  {/* The cell is the target, not the text in it. A column heading is a
                      small thing to aim at, and the space around it was dead. */}
                  <Link
                    href={`/products/${product.external_id}`}
                    className="block h-full px-2 pt-2 pb-2 hover:bg-rule/40 hover:text-accent"
                  >
                    {/* Truncated: one eye-drop presentation ran to sixty characters and
                        widened its column past every other one on the page. */}
                    <span
                      title={product.variant ?? product.name}
                      className="block max-w-44 truncate font-mono text-meta underline underline-offset-4"
                    >
                      {product.variant ?? product.name}
                    </span>
                    <span className="block font-mono text-kicker text-ink-muted">
                      {product.revised ? product.revised : "revision unknown"}
                    </span>
                    {product.discontinued && (
                      <span className="block font-mono text-kicker text-accent">discontinued</span>
                    )}
                    {!compact && product.ma_number && (
                      <span className="block font-mono text-kicker text-ink-muted">
                        {product.ma_number}
                      </span>
                    )}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.concept} className="border-b border-rule align-top">
                <th className="sticky left-0 z-20 min-w-40 bg-paper p-2 pr-4 text-left font-normal">
                  <Link
                    href={`/substances/${matrix.substance_id}/concepts/${encodeURIComponent(row.concept)}`}
                    className="underline underline-offset-4 hover:text-accent"
                  >
                    {conceptLabel(row.concept)}
                  </Link>
                </th>
                {ordered.map((product, order) => {
                  const cell = row.cells.find((c) => c.product_external_id === product.external_id);
                  return (
                    <td key={product.external_id} className="px-1 py-2 text-center">
                      {cell &&
                        (compact ? (
                          <PlacementChip placement={cell.placement} delayMs={order * 70} />
                        ) : (
                          <PlacementBadge
                            placement={cell.placement}
                            className="animate-land"
                            delayMs={order * 70}
                          />
                        ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


/** A holder's name, linked to one of its labels wherever the name appears. */
export function Maker({ name, labelOf }: { name: string; labelOf: Map<string, string> }) {
  const id = labelOf.get(name);
  if (!id) return <>{name}</>;
  return (
    <Link href={`/products/${id}`} className="hover:text-accent hover:underline">
      {name}
    </Link>
  );
}
