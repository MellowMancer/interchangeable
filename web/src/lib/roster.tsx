"use client";

/**
 * The roster, filtered as the reader types.
 *
 * The application's one client component, and it is here for a reason no server round
 * trip can meet: a list narrowing on each keystroke needs the keystroke. The page above
 * is still a Server Component, the products are still fetched on the server, and the
 * browser still never calls the API — this receives a list it is given and filters it.
 *
 * The form still posts to `/` with `q`, so pressing Enter, sharing the URL, or arriving
 * with JavaScript disabled all still search. Live filtering is layered over that rather
 * than replacing it.
 */

import { useDeferredValue, useMemo, useState } from "react";
import { Section } from "@/lib/heading";
import Link from "next/link";
import { manufacturer, type ProductSummary } from "./api";
import { DosageGlyph, undrawnBecause } from "./appearance";

/** Cards drawn before the reader asks for more. Enough to fill a large screen twice over. */
const PAGE = 60;
import { Pack } from "./pack";

/**
 * Whether a product answers to what was typed.
 *
 * Over the names on a box — the product, the substance inside it, and the holder who
 * makes it. Not over the concepts its label files: a reader searching this list is
 * looking for a medicine they have been handed, and matching "pregnancy" to every label
 * that happens to mention it returns a set nobody asked for.
 */
function matches(product: ProductSummary, query: string): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  return [product.name, product.substance_name, manufacturer(product)].some((printed) =>
    printed.toLowerCase().includes(needle),
  );
}

export function Roster({
  products,
  query,
}: {
  products: ProductSummary[];
  query: string;
}) {
  const [typed, setTyped] = useState(query);
  const term = typed.trim();

  /*
   * Filtered off a deferred copy of what was typed, and only when it changes.
   *
   * The list is every collected product, and each card is a drawn strip, a glyph and four
   * lines. Re-filtering all of them inside render on every keystroke made typing wait for
   * the list; deferring the term lets the field keep up and the list catch up behind it.
   */
  const settled = useDeferredValue(term);
  const matching = useMemo(
    () => products.filter((product) => matches(product, settled)),
    [products, settled],
  );

  /*
   * Every match is searchable; only the first `PAGE` of them are drawn.
   *
   * The whole list has to be in the browser for the field to filter without a round trip,
   * and that is cheap — it is the drawing that is not. Each card is a bar strip, an inline
   * drawing and four lines, and 744 of them is most of a two-megabyte document for a
   * screen nobody scrolls to the end of. The count above the grid always names the full
   * match, so what is on screen is never mistaken for what was found.
   */
  const [drawn, setDrawn] = useState(PAGE);
  // Adjusted during render rather than in an effect: a new search is a different list, and
  // showing its first page is part of producing it, not a reaction to having produced it.
  const [searched, setSearched] = useState(settled);
  if (searched !== settled) {
    setSearched(settled);
    setDrawn(PAGE);
  }
  const shown = useMemo(() => matching.slice(0, drawn), [matching, drawn]);
  const hidden = matching.length - shown.length;

  return (
    <>
      <form action="/" className="space-y-3">
        <label
          htmlFor="q"
          className="block font-mono text-kicker text-ink-muted"
        >
          Search {products.length} products
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

      {matching.length > 0 ? (
        <section className="space-y-6">
          <Section>
            {term ? `Matching (${matching.length})` : `All products (${matching.length})`}
          </Section>
          {/* Every one of these is a pack, drawn the way the walkthrough draws one, so a
              reader who took the tour meets the same object here. */}
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {shown.map((product) => (
              <li key={product.external_id}>
                <Link
                  href={`/products/${product.external_id}`}
                  className="block h-full rounded-sheet transition-transform hover:-translate-y-0.5 hover:bg-rule/30"
                >
                  <Pack
                    product={product.name}
                    substance={product.substance_name}
                    form={product.variant}
                    holder={manufacturer(product)}
                    placements={product.placements}
                    glyph={
                      product.appearance &&
                      undrawnBecause(product.appearance).length === 0 ? (
                        <DosageGlyph appearance={product.appearance} />
                      ) : null
                    }
                  />
                </Link>
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <button
              type="button"
              onClick={() => setDrawn((count) => count + PAGE)}
              className="w-full rounded-sheet border border-rule py-3 font-mono text-kicker text-ink-muted hover:border-ink hover:text-ink"
            >
              Show {Math.min(hidden, PAGE)} more · {hidden} not drawn
            </button>
          )}
        </section>
      ) : (
        <p className="max-w-prose text-ink-muted">
          Nothing on the roster matches <span className="text-ink">{term}</span>. Search
          runs over product names, the substances in them and the manufacturers who make
          them.
        </p>
      )}
    </>
  );
}
