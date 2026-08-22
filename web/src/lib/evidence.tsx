"use client";

/**
 * The evidence for one concept, over the labels a reader chose.
 *
 * The comparison lets a reader narrow to the two products they are holding, and that
 * choice has to survive the click into a concept — a page that answers "where do these two
 * disagree" and then shows ten labels has quietly changed the question. The selection is
 * read from the same place the comparison writes it.
 *
 * Client only for that read. Everything below is the same markup the server rendered
 * before; nothing is fetched here, and a selection is a filter over what the page already
 * holds.
 *
 * Falls back to every label — on a first visit, in a fresh session, or if storage is
 * unavailable. Showing the whole comparison is always a correct answer; showing a subset
 * without being asked is not.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  manufacturer,
  type ConceptCell,
  type ConceptDetail,
  type ContextWindow,
  type ProductColumn,
} from "./api";
import { groupByWording, type WordingGroup } from "./finding";
import { PlacementBadge } from "./placement";
import { QuotePosition, SectionCoverage } from "./scope";
import { PlacementSpectrum } from "./spectrum";

export function Evidence({ detail }: { detail: ConceptDetail }) {
  const [chosen, setChosen] = useState<string[] | null>(null);

  useEffect(() => {
    try {
      const held = window.sessionStorage.getItem(`chosen:${detail.substance_id}`);
      if (!held) return;
      const ids: string[] = JSON.parse(held);
      const live = ids.filter((id) => detail.products.some((p) => p.external_id === id));
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (live.length) setChosen(live);
    } catch {
      // Storage can be unavailable or stale; every label is the honest default.
    }
  }, [detail.substance_id, detail.products]);

  const products = chosen
    ? detail.products.filter((p) => chosen.includes(p.external_id))
    : detail.products;
  const cells = chosen
    ? detail.cells.filter((c) => chosen.includes(c.product_external_id))
    : detail.cells;

  const byProduct = new Map(products.map((p) => [p.external_id, p]));
  const groups = groupByWording(cells, products);
  const narrowed = products.length < detail.products.length;

  return (
    <>
      {narrowed && (
        <p className="font-mono text-kicker text-accent">
          {products.length} of {detail.products.length} labels — as chosen on the comparison
        </p>
      )}

      <PlacementSpectrum cells={cells} products={products} />

      {/* One block per distinct wording, two abreast. A block per label turned ten
          manufacturers into a page nobody reaches the end of — and most of those blocks
          were the same sentence, because generics copy an SmPC verbatim. */}
      <ul className="section-break grid border-t border-rule lg:grid-cols-2">
        {groups.map((group) => (
          <li
            key={`${group.placement}|${group.cells[0].product_external_id}`}
            className="border-b border-rule lg:odd:border-r lg:odd:pr-10 lg:even:pl-10"
          >
            <Wording group={group} byProduct={byProduct} />
          </li>
        ))}
      </ul>
    </>
  );
}

/**
 * One wording, and every label that carries it.
 *
 * Grouped rather than repeated because the alternative misleads by volume: ten labels
 * carrying one copied sentence printed ten times reads as ten findings, and buries the
 * one label that words it differently. The grouping is byte-exact, so a block never
 * claims agreement it has not verified.
 *
 * Every member keeps its own offsets, revision and source link. The same sentence sits at
 * different indices in different labels, and a block that showed only the first member's
 * provenance would quietly drop the rest.
 */
function Wording({
  group,
  byProduct,
}: {
  group: WordingGroup<ConceptCell>;
  byProduct: Map<string, ProductColumn>;
}) {
  const [first] = group.cells;
  const shared = group.cells.length > 1;

  return (
    <section className="space-y-4 py-8">
      <div className="space-y-3">
        <PlacementBadge placement={group.placement} className="self-start" />
        <ul className="space-y-3">
          {group.cells.map((cell) => (
            <Speaker
              key={cell.product_external_id}
              cell={cell}
              product={byProduct.get(cell.product_external_id)}
            />
          ))}
        </ul>
      </div>

      {first.evidence ? (
        <div className="space-y-2">
          {first.context ? (
            <InContext context={first.context} />
          ) : (
            <blockquote className="border-l-2 border-rule pl-6 font-serif text-body">
              &ldquo;{first.evidence.quote}&rdquo;
            </blockquote>
          )}
          {/* The quote is identical in every member; the text around it is not, so the
              label it was taken from is named rather than implied. */}
          {shared && (
            <p className="text-kicker text-ink-muted">
              {group.cells.length === 2
                ? "Identical in both labels."
                : `Identical in all ${group.cells.length} labels.`}{" "}
              Surrounding text shown from {label(first, byProduct)}.
            </p>
          )}
        </div>
      ) : (
        <Absence product={byProduct.get(first.product_external_id)} />
      )}
    </section>
  );
}

/** A product's display name, falling back to its id when the column is missing. */
const label = (cell: ConceptCell, byProduct: Map<string, ProductColumn>) => {
  const product = byProduct.get(cell.product_external_id);
  return product ? manufacturer(product) : cell.product_external_id;
};

/** One label in a wording group: who it is, which revision, and where in it. */
function Speaker({
  cell,
  product,
}: {
  cell: ConceptCell;
  product: ProductColumn | undefined;
}) {
  const sourceUrl = cell.evidence?.source_url ?? product?.source_url ?? undefined;

  return (
    <li className="space-y-1">
      <p className="font-medium">
        {product ? (
          <Link
            href={`/products/${product.external_id}`}
            className="hover:text-accent hover:underline hover:underline-offset-4"
          >
            {manufacturer(product)}
          </Link>
        ) : (
          cell.product_external_id
        )}
      </p>
      <p className="font-mono text-meta text-ink-muted">
        {product?.variant ?? product?.name}
        {product?.revised ? ` · revised ${product.revised}` : " · revision unknown"}
      </p>
      {cell.evidence && cell.context && (
        <QuotePosition
          charStart={cell.evidence.char_start}
          charEnd={cell.evidence.char_end}
          sectionLength={cell.context.section_length}
          sectionCode={cell.evidence.section_code}
        />
      )}
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-block font-mono text-meta text-accent underline underline-offset-4"
        >
          Source SmPC ↗
        </a>
      )}
    </li>
  );
}

/**
 * The matched clause, marked inside the text it was sliced from.
 *
 * The span is taken at the offsets the API reports rather than by searching for the quote:
 * a clause that appears twice in a section would otherwise be highlighted in the wrong
 * place, which would misrepresent the very thing being demonstrated.
 *
 * An ellipsis is shown only on an end the window actually cut, so a reader can tell the
 * difference between text continuing and a section genuinely starting there.
 */
function InContext({ context }: { context: ContextWindow }) {
  const before = context.text.slice(0, context.quote_start);
  const match = context.text.slice(context.quote_start, context.quote_end);
  const after = context.text.slice(context.quote_end);

  return (
    <blockquote className="max-w-prose border-l-2 border-rule pl-6 font-serif text-body text-ink-muted">
      {context.truncated_start && <span aria-hidden>… </span>}
      {before}
      <mark className="animate-sweep bg-transparent text-ink decoration-accent/40 underline-offset-4">
        {match}
      </mark>
      {after}
      {context.truncated_end && <span aria-hidden> …</span>}
    </blockquote>
  );
}

/**
 * No quote, and no fill.
 *
 * The sections read are named inside the sentence rather than beneath it: without them
 * the claim reads as an omission from the label, which is a claim this project has not
 * checked and does not make.
 */
function Absence({ product }: { product: ProductColumn | undefined }) {
  const scanned = product?.scanned ?? [];
  return (
    <>
      <p className="border-l-2 border-dashed border-rule pl-6 text-ink-muted">
        No match in {scanned.length ? `sections ${scanned.join(", ")}` : "any section"} as
        read for this label. Not the same as the label being silent.
      </p>
      <SectionCoverage scanned={scanned} />
    </>
  );
}
