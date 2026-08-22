import type { Metadata } from "next";
import { Section } from "@/lib/heading";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getProduct,
  manufacturer,
  type ProductColumn,
  type ProductConcept,
  type ValueStatement,
} from "@/lib/api";
import { DosageGlyph, undrawnBecause } from "@/lib/appearance";
import { Concepts, Makers } from "@/lib/icons";
import { PlacementBadge } from "@/lib/placement";

/**
 * One label, on its own page.
 *
 * The project's claim is that any statement here can be checked against its source, and
 * until this route existed a label had no URL — a product was only ever a column inside a
 * comparison, so a finding could be read but never cited.
 *
 * It answers a different question from the matrix. The matrix asks where the
 * manufacturers disagree; this asks what one box in a reader's hand actually says.
 */
export async function generateMetadata({
  params,
}: PageProps<"/products/[id]">): Promise<Metadata> {
  const { id } = await params;
  const detail = await getProduct(id);
  if (!detail) return { title: "Not found" };
  return { title: `${detail.product.name} · ${detail.substance_name}` };
}

export default async function ProductPage({ params }: PageProps<"/products/[id]">) {
  const { id } = await params;
  const detail = await getProduct(id);
  if (!detail) notFound();

  const { product } = detail;

  return (
    <article className="space-y-12">
      <Link
        href={`/substances/${detail.substance_id}`}
        className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
      >
        ← Compare every {detail.substance_name}
      </Link>

      <Identity detail={detail} />

      <section className="space-y-4">
        <Section>
          <span className="flex items-center gap-2">
            <Concepts />
            Concepts — {detail.concepts.length}
          </span>
        </Section>
        {/* Two columns of collapsed rows: the placement is the answer, and the sentence
            behind it is one click away rather than thirty stacked quotes deep. */}
        <ul className="grid border-t border-rule lg:grid-cols-2">
          {detail.concepts.map((concept) => (
            <li
              key={concept.concept}
              className="border-b border-rule lg:odd:border-r lg:odd:pr-8 lg:even:pl-8"
            >
              <Concept concept={concept} sourceUrl={product.source_url} />
            </li>
          ))}
        </ul>
      </section>

      {detail.values.length > 0 && (
        <section className="section-break space-y-4">
          <Section>Storage and shelf life</Section>
          <div className="grid gap-10 lg:grid-cols-2">
            {detail.values.map((value) => (
              <Value key={value.code} value={value} />
            ))}
          </div>
        </section>
      )}

      {detail.siblings.length > 0 && (
        <section className="section-break space-y-4">
          <Section>
            <span className="flex items-center gap-2">
              <Makers />
              Other {detail.substance_name} labels — {detail.siblings.length}
            </span>
          </Section>
          <p className="max-w-prose text-meta text-ink-muted">
            The same active substance from another manufacturer. Whether they say the same
            things is what the comparison answers.
          </p>
          {/* Horizontal because the list is a shelf, not a ranking: nothing about the
              order says one is preferable to another. */}
          <ul className="-mx-6 flex snap-x gap-4 overflow-x-auto px-6 pb-2">
            {detail.siblings.map((sibling) => (
              <li key={sibling.external_id} className="w-64 shrink-0 snap-start">
                <Sibling product={sibling} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

/** What the box is: the drawing, the substance and strength, and what it is for. */
function Identity({ detail }: { detail: Awaited<ReturnType<typeof getProduct>> }) {
  if (!detail) return null;
  const { product } = detail;
  const drawable = product.appearance && undrawnBecause(product.appearance).length === 0;

  return (
    <header className="grid gap-8 border border-rule p-6 lg:grid-cols-[minmax(0,22rem)_1fr] lg:p-8">
      <div className="space-y-4">
        <div className="space-y-1">
          <p className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
            {detail.substance_name}
          </p>
          <h1 className="line-clamp-3 font-serif text-title font-normal tracking-tight">
            {product.name}
          </h1>
          <p className="font-mono text-meta text-ink-muted">
            {manufacturer(product)}
            {product.variant && ` · ${product.variant}`}
          </p>
        </div>

        {drawable && product.appearance && (
          <div className="space-y-2">
            <DosageGlyph appearance={product.appearance} />
            {/* Three lines, then a title: one ibuprofen description runs to four
                sentences and pushed everything under it off the first screen. */}
            <p
              title={product.appearance.source_text}
              className="line-clamp-3 max-w-prose text-kicker text-ink-muted"
            >
              {product.appearance.source_text}
            </p>
          </div>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-kicker text-ink-muted">
          {product.revised && <Fact term="Revised" value={product.revised} />}
          {product.listing_updated && (
            <Fact term="Source updated" value={product.listing_updated} />
          )}
          {product.ma_number && <Fact term="MA number" value={product.ma_number} />}
          {product.atc_code && <Fact term="ATC" value={product.atc_code} />}
          {product.legal_status && <Fact term="Legal status" value={product.legal_status} />}
        </dl>

        {product.source_url && (
          <a
            href={product.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-block font-mono text-meta text-accent underline underline-offset-4"
          >
            Source SmPC ↗
          </a>
        )}
      </div>

      <div className="space-y-3">
        <Section>Indications</Section>
        {detail.indications.length > 0 ? (
          <ul className="space-y-1">
            {detail.indications.map((statement) => (
              <li
                key={statement.text}
                className={
                  statement.depth === 0
                    ? "border-l-2 border-rule pl-4 text-meta"
                    : "ml-6 border-l border-rule pl-4 text-meta text-ink-muted"
                }
              >
                {statement.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-prose text-meta text-ink-muted">
            No section 4.1 has been collected for this label. Not a label without
            indications.
          </p>
        )}
      </div>
    </header>
  );
}

const Fact = ({ term, value }: { term: string; value: string }) => (
  <>
    <dt className="uppercase">{term}</dt>
    <dd className="text-ink">{value}</dd>
  </>
);

/** One concept, its placement, and the sentence behind it on request. */
function Concept({
  concept,
  sourceUrl,
}: {
  concept: ProductConcept;
  sourceUrl: string | null;
}) {
  const { evidence } = concept;

  return (
    <details className="group py-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-ink-muted group-open:text-ink">+</span>
          <span>{conceptLabel(concept.concept)}</span>
        </span>
        <PlacementBadge placement={concept.placement} />
      </summary>

      <div className="mt-3 space-y-2 pl-6">
        {evidence ? (
          <>
            <blockquote className="border-l-2 border-rule pl-4 font-serif text-body">
              &ldquo;{evidence.quote}&rdquo;
            </blockquote>
            {/* Offsets without the positional bar: this response does not carry the
                section's length, and drawing the bar against the quote's own end would
                claim every quote sits at the end of its section. The bar lives on the
                evidence screen, which has the denominator. */}
            <p className="font-mono text-kicker text-ink-muted">
              characters {evidence.char_start}–{evidence.char_end} in §
              {evidence.section_code}
            </p>
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
          </>
        ) : (
          <p className="text-meta text-ink-muted">
            Not found in the sections read for this label. Not the same as the label being
            silent.
          </p>
        )}
      </div>
    </details>
  );
}

/** §6.3 or §6.4, verbatim. */
function Value({ value }: { value: ValueStatement }) {
  return (
    <article className="space-y-3">
      <h3 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
        §{value.code} — {value.heading}
      </h3>
      <div className="space-y-1 border-y border-rule py-3 font-serif text-body">
        {value.text
          .split(/\n+/)
          .map((line) => line.trim())
          .filter(Boolean)
          .map((line) => (
            <p key={line}>{line}</p>
          ))}
      </div>
    </article>
  );
}

/** Another label of the same substance, as a card on the shelf. */
function Sibling({ product }: { product: ProductColumn }) {
  const drawable = product.appearance && undrawnBecause(product.appearance).length === 0;

  return (
    <Link
      href={`/products/${product.external_id}`}
      className="flex h-full flex-col gap-2 border border-rule p-4 hover:border-accent hover:bg-rule/30"
    >
      <span className="flex h-8 items-center">
        {drawable && product.appearance ? (
          <DosageGlyph appearance={product.appearance} />
        ) : (
          <span className="font-mono text-ink-muted">—</span>
        )}
      </span>
      <span className="text-meta">{manufacturer(product)}</span>
      <span className="font-mono text-kicker text-ink-muted">
        {product.variant ?? product.name}
      </span>
    </Link>
  );
}
