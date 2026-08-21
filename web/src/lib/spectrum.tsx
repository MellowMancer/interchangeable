/**
 * Where each manufacturer files one concept, drawn rather than described.
 *
 * Products run across and placements run down, so this reads as one row of the
 * comparison matrix opened out: the same manufacturers stand in the same order, and the
 * axis the reader has just been looking along is the one that changes. The sections run
 * in the order the SmPC prints them, which is a fact about the document. They are
 * deliberately not ordered from more to less binding: that holds for §4.3 against §4.5,
 * but §4.6 covers a different population rather than a lesser severity, and one label
 * across all five would overclaim.
 *
 * Absence is stated beneath the grid and never given a row. A sixth row would draw "we
 * did not look there" as somewhere a label puts things — and a product found nowhere
 * already says so, with an empty column.
 */

import { manufacturer, type Cell, type ProductColumn } from "./api";
import { placementStyle, SECTION_PLACEMENTS } from "./placement";

/** Stagger between marks, so a row fills in the order it reads. */
const LAND_STEP_MS = 90;

export function PlacementSpectrum({
  cells,
  products,
  className = "",
}: {
  cells: Cell[];
  products: ProductColumn[];
  className?: string;
}) {
  const filedAt = new Map(cells.map((cell) => [cell.product_external_id, cell.placement]));
  const absent = products.filter((product) => filedAt.get(product.external_id) === "absent");

  return (
    <figure className={`space-y-3 ${className}`}>
      <p className="font-mono text-kicker text-ink-muted md:hidden">
        scroll for all {products.length} products →
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">
            Which section of each manufacturer&apos;s label carries this concept
          </caption>
          <thead>
            <tr>
              <th className="w-44 p-2 text-left font-normal">
                <span className="sr-only">Section</span>
              </th>
              {products.map((product) => (
                <th key={product.external_id} scope="col" className="p-2 text-left font-normal">
                  <span className="block leading-tight">{manufacturer(product)}</span>
                  {/* A holder may hold several products, and they need not agree —
                      without the variant two of its columns read as one label twice. */}
                  <span className="block font-mono text-kicker text-ink-muted">
                    {product.variant ?? product.name}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SECTION_PLACEMENTS.map((placement) => {
              const style = placementStyle(placement);
              return (
                <tr key={placement} className="border-t border-rule">
                  <th scope="row" className="p-2 text-left font-normal">
                    <span className="block font-mono text-meta text-ink">{style.section}</span>
                    <span className="block text-kicker text-ink-muted lowercase">
                      {style.label}
                    </span>
                  </th>
                  {products.map((product, order) => (
                    <td key={product.external_id} className="p-2">
                      {filedAt.get(product.external_id) === placement && (
                        <span
                          title={style.detail}
                          style={{ animationDelay: `${order * LAND_STEP_MS}ms` }}
                          className={`animate-land block h-7 rounded-sheet border ${style.className}`}
                        >
                          <span className="sr-only">{style.label}</span>
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {absent.length > 0 && <AbsenceNote products={absent} />}
    </figure>
  );
}

/**
 * Who was looked at and not found, stated rather than drawn.
 *
 * Beneath the grid on purpose: a mark inside it would place absence somewhere on the
 * document axis, and "not in the sections we read" is not a location in a label.
 */
function AbsenceNote({ products }: { products: ProductColumn[] }) {
  const scanned = products[0].scanned ?? [];
  const named = products.map((product) => {
    const variant = product.variant ?? product.name;
    return variant ? `${manufacturer(product)} ${variant}` : manufacturer(product);
  });

  return (
    <figcaption className="text-kicker text-ink-muted">
      Not found in {scanned.length ? scanned.join(", ") : "any section"} as read here:{" "}
      {named.join(" · ")}. Not the same as the label being silent.
    </figcaption>
  );
}
