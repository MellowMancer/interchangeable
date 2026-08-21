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

import { useState } from "react";
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
import { PlacementBadge, PlacementChip } from "./placement";

const Kicker = ({ children }: { children: React.ReactNode }) => (
  <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">{children}</h2>
);

export function Comparison({ matrix }: { matrix: Matrix }) {
  const [chosen, setChosen] = useState<string[]>(() =>
    matrix.products.map((product) => product.external_id),
  );

  const products = matrix.products.filter((product) => chosen.includes(product.external_id));
  const holders = new Set(products.map((product) => manufacturer(product)));

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
      <Chooser products={matrix.products} chosen={chosen} onChange={setChosen} />

      {products.length < 2 ? (
        <p className="max-w-prose text-ink-muted">
          Choose at least two labels above. A comparison of one is just a label — open it
          from the quick links instead.
        </p>
      ) : (
        <>
          {divergent.length > 0 ? (
            <section className="space-y-6">
              <Kicker>
                Where they disagree — {divergent.length} of {rows.length} concepts
              </Kicker>
              <DivergenceTable matrix={matrix} rows={divergent} products={products} />
            </section>
          ) : (
            <section className="space-y-4">
              <Kicker>Where they disagree</Kicker>
              <p className="max-w-prose text-ink-muted">
                Nowhere that was scanned. Every concept below sits in the same section on
                every label chosen.
              </p>
            </section>
          )}

          {agreeing.length > 0 && (
            <section className="space-y-6 border-t border-rule pt-10">
              <Kicker>Where they agree — {agreeing.length} concepts</Kicker>
              <ul className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
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

          <ValueSections sections={values} />
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
    <details className="group space-y-3 border-t border-rule pt-8">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <span className="font-mono text-kicker tracking-widest uppercase">
          <span className={narrowed ? "text-accent" : "text-ink-muted"}>
            Comparing {chosen.length} of {products.length} labels
          </span>
        </span>
        <span className="font-mono text-kicker tracking-widest text-ink-muted uppercase group-open:hidden">
          choose ↓
        </span>
        <span className="hidden font-mono text-kicker tracking-widest text-ink-muted uppercase group-open:inline">
          done ↑
        </span>
      </summary>

      <div className="mt-3 space-y-3">
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
function ValueSections({ sections }: { sections: ValueSection[] }) {
  if (sections.length === 0) return null;

  return (
    <section className="space-y-6 border-t border-rule pt-10">
      <Kicker>What the labels state, in their own words</Kicker>
      <div className="grid gap-x-10 gap-y-6 lg:grid-cols-2">
        {sections.map((section) => (
          <article key={section.code} className="space-y-2">
            {/* The app's voice, in the app's face: everything below is the label's own
                words in serif, and a heading set like them reads as one of them. */}
            <h3 className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-kicker tracking-widest text-ink-muted uppercase">
              <span>
                §{section.code} — {section.heading}
              </span>
              {/* Said at the top, not inferred from the bottom. Two statements stacked
                  read as a list of properties unless something says they are rival
                  answers to one question. */}
              {section.groups.length > 1 && (
                <span className="rounded-sheet border border-accent px-2 py-0.5 text-accent">
                  {section.groups.length} different statements
                </span>
              )}
            </h3>
            {/* Commonest first, and led by how many labels say it. "Six say this, two say
                that" is the shape of the answer; a stack of equal paragraphs makes the
                reader count for themselves. */}
            <ul className="divide-y divide-rule border-y border-rule">
              {[...section.groups]
                .sort((a, b) => b.manufacturers.length - a.manufacturers.length)
                .map((group) => (
                  <li
                    key={group.text}
                    className="grid grid-cols-[3.5rem_1fr] items-baseline gap-x-4 py-2.5"
                  >
                    <span
                      className={`font-mono text-meta ${
                        section.groups.length > 1 ? "text-accent" : "text-ink-muted"
                      }`}
                    >
                      {group.manufacturers.length}
                      <span className="sr-only"> labels state</span>
                      <span aria-hidden className="text-ink-muted">
                        /{section.collected}
                      </span>
                    </span>
                    <span className="block min-w-0 space-y-0.5">
                      {/* The label's own words, in the label's own face. */}
                      <span className="block space-y-0.5 font-serif text-body">
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
                      <span
                        title={group.manufacturers.join(", ")}
                        className="block truncate font-mono text-kicker text-ink-muted"
                      >
                        {group.manufacturers.join(" · ")}
                      </span>
                    </span>
                  </li>
                ))}
            </ul>
            {/* Stated rather than implied: a section three labels carry is not a section
                the other four contradict. */}
            {/* "Stated by all 3 labels" meant all three state a shelf life; it read as
                all three stating the same one. Coverage and agreement are different
                claims and are now made separately. */}
            <p className="text-kicker text-ink-muted">
              {section.groups.length > 1
                ? `These ${section.collected} labels do not word this the same way.`
                : `All ${section.collected} labels word this the same way.`}
              {section.collected < section.total &&
                ` The other ${section.total - section.collected} have no ${section.heading.toLowerCase()} collected.`}
            </p>
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
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-paper p-2 text-left font-normal">
                <span className="sr-only">Concept</span>
              </th>
              {groups.map((group) => (
                <th
                  key={group.name}
                  colSpan={group.products.length}
                  scope="colgroup"
                  className="border-l border-rule px-2 pt-2 text-left align-bottom font-medium first:border-l-0"
                >
                  {group.name}
                </th>
              ))}
            </tr>
            <tr className="border-b border-rule">
              <th className="sticky left-0 z-10 bg-paper p-2" />
              {ordered.map((product) => (
                <th
                  key={product.external_id}
                  scope="col"
                  className="px-2 pb-2 text-left align-bottom font-normal"
                >
                  <Link
                    href={`/products/${product.external_id}`}
                    className="block font-mono text-meta underline underline-offset-4 hover:text-accent"
                  >
                    {product.variant ?? product.name}
                  </Link>
                  <div className="font-mono text-kicker text-ink-muted">
                    {product.revised ? product.revised : "revision unknown"}
                  </div>
                  {product.discontinued && (
                    <div className="font-mono text-kicker text-accent">discontinued</div>
                  )}
                  {!compact && product.ma_number && (
                    <div className="font-mono text-kicker text-ink-muted">{product.ma_number}</div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.concept} className="border-b border-rule align-top">
                <th className="sticky left-0 z-10 bg-paper p-2 pr-4 text-left font-normal">
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
                    <td key={product.external_id} className="px-1 py-2">
                      {cell &&
                        (compact ? (
                          <PlacementChip placement={cell.placement} />
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
