/**
 * When each manufacturer last revised its label, on one axis.
 *
 * A five-year gap between two labels is the difference between "these manufacturers
 * disagree" and "one of them has not caught up", and that is a comparison of positions —
 * far easier to see than to read. The sentence this replaces said the same thing and made
 * the reader hold two dates in their head to feel the distance.
 *
 * Placed by year only. The publisher's own string is printed verbatim beside each marker
 * because that is what it published; a label whose string carries no year is listed as
 * unknown rather than guessed at, since treating unknown as old would invent staleness.
 */

import { manufacturer, type ProductColumn } from "./api";
import { revisionYear } from "./finding";

export function RevisionTimeline({ products }: { products: ProductColumn[] }) {
  const dated = products
    .map((product) => ({ product, year: revisionYear(product.revised) }))
    .filter((entry): entry is { product: ProductColumn; year: number } => entry.year !== null);
  const undated = products.filter((product) => revisionYear(product.revised) === null);

  if (dated.length < 2) return null;

  const years = dated.map((entry) => entry.year);
  const earliest = Math.min(...years);
  const latest = Math.max(...years);
  const span = latest - earliest;
  if (span === 0) return null;

  const sorted = [...dated].sort((a, b) => a.year - b.year);

  return (
    <figure className="space-y-4">
      <div className="space-y-2">
        {sorted.map(({ product, year }) => (
          <div key={product.external_id} className="grid grid-cols-[1fr_auto] items-center gap-4">
            <div className="relative h-7">
              <div className="absolute inset-x-0 top-1/2 border-t border-rule" />
              <div
                className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
                style={{ left: `${((year - earliest) / span) * 100}%` }}
              />
            </div>
            <p className="w-64 text-meta">
              <span className="font-mono text-ink-muted">{product.revised}</span>{" "}
              <span className="text-ink">{manufacturer(product)}</span>
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-[1fr_auto] gap-4">
        <div className="flex justify-between font-mono text-kicker text-ink-muted">
          <span>{earliest}</span>
          <span>{latest}</span>
        </div>
        <span className="w-64" />
      </div>

      <figcaption className="max-w-prose text-meta text-ink-muted">
        {span} {span === 1 ? "year" : "years"} separates the oldest label from the newest. A
        finding that appears on one label and not another may be a label that has not caught
        up rather than a disagreement.
        {undated.length > 0 && (
          <>
            {" "}
            {undated.map(manufacturer).join(", ")} carries no parseable revision year and is
            not placed — unknown, not old.
          </>
        )}
      </figcaption>
    </figure>
  );
}
