/**
 * Where each manufacturer files one concept, drawn rather than described.
 *
 * The product's whole subject is *position within a document*, which is spatial — so a
 * reader gets it faster from a mark in a column than from a sentence. The sections run
 * in the order the SmPC prints them, which is a fact about the document. They are
 * deliberately not labelled as an axis from more to less binding: that holds for §4.3
 * against §4.5, but §4.6 covers a different population rather than a lesser severity,
 * and one label across all four would overclaim.
 *
 * Absence gets a row with no mark and a stated reason, never a column of its own. A
 * fifth column would draw "we did not look there" as somewhere a label puts things.
 */

import { manufacturer, type Cell, type ProductColumn } from "./api";
import { placementStyle, SECTION_PLACEMENTS } from "./placement";

export function PlacementSpectrum({
  cells,
  products,
  className = "",
}: {
  cells: Cell[];
  products: ProductColumn[];
  className?: string;
}) {
  const byId = new Map(products.map((product) => [product.external_id, product]));

  return (
    <figure className={`space-y-3 ${className}`}>
      <p className="font-mono text-kicker text-ink-muted sm:hidden">
        scroll for every section →
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-lg border-collapse">
          <caption className="sr-only">
            Which section of each manufacturer&apos;s label carries this concept
          </caption>
          <thead>
            <tr>
              {SECTION_PLACEMENTS.map((placement) => {
                const style = placementStyle(placement);
                return (
                  <th key={placement} scope="col" className="p-2 pb-3 text-center font-normal">
                    <span className="block font-mono text-meta text-ink">{style.section}</span>
                    <span className="block text-kicker text-ink-muted lowercase">
                      {style.label}
                    </span>
                  </th>
                );
              })}
              <th scope="col" className="p-2 pb-3 text-left font-normal">
                <span className="sr-only">Manufacturer</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {cells.map((cell, order) => (
              <SpectrumRow
                key={cell.product_external_id}
                cell={cell}
                product={byId.get(cell.product_external_id)}
                order={order}
              />
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

function SpectrumRow({
  cell,
  product,
  order,
}: {
  cell: Cell;
  product: ProductColumn | undefined;
  order: number;
}) {
  const name = product ? manufacturer(product) : cell.product_external_id;
  const scanned = product?.scanned ?? [];

  return (
    <tr className="border-t border-rule">
      {SECTION_PLACEMENTS.map((placement) => {
        const here = cell.placement === placement;
        const style = placementStyle(placement);
        return (
          <td key={placement} className="border-r border-rule p-0 last:border-r-0">
            <div className="flex h-14 items-center justify-center">
              {here && (
                <span
                  title={style.detail}
                  style={{ animationDelay: `${order * 90}ms` }}
                  className={`animate-land h-7 w-full max-w-24 rounded-sheet border ${style.className}`}
                >
                  <span className="sr-only">{style.label}</span>
                </span>
              )}
            </div>
          </td>
        );
      })}
      <th scope="row" className="p-2 pl-4 text-left font-normal">
        <span className="block">{name}</span>
        {/* A holder may hold several products, and they need not agree — without the
            variant two of its rows read as the same label listed twice. */}
        {(product?.variant ?? product?.name) && (
          <span className="block font-mono text-kicker text-ink-muted">
            {product?.variant ?? product?.name}
          </span>
        )}
        {cell.placement === "absent" && (
          <span className="block text-kicker text-ink-muted">
            not found in {scanned.length ? scanned.join(", ") : "any section"} as read here
          </span>
        )}
      </th>
    </tr>
  );
}
