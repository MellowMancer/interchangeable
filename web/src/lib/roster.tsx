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

import { useState } from "react";
import { Section } from "@/lib/heading";
import Link from "next/link";
import { manufacturer, type ProductSummary } from "./api";
import { DosageGlyph, undrawnBecause } from "./appearance";
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

  const matching = products.filter((product) => matches(product, term));

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
            {matching.map((product) => (
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
