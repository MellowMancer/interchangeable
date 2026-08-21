import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getConceptDetail,
  manufacturer,
  type ConceptCell,
  type ContextWindow,
  type ProductColumn,
} from "@/lib/api";
import { AppearanceStrip } from "@/lib/appearance";
import { identicalWording, UNCLASSIFIED } from "@/lib/finding";
import { PlacementBadge } from "@/lib/placement";
import { QuotePosition, SectionCoverage } from "@/lib/scope";
import { PlacementSpectrum } from "@/lib/spectrum";

/**
 * Why each manufacturer's cell says what it says, in the label's own words.
 *
 * The quote is shown inside the text that surrounds it, with the matched span marked.
 * That is the difference between asserting a quote was sliced from the section at those
 * offsets and letting a reader see that it was — which is the claim the whole project
 * rests on.
 *
 * Stacked full width rather than tiled: these are clinical sentences, and a three-column
 * grid squeezes them to a measure nobody can read.
 */
export async function generateMetadata({
  params,
}: PageProps<"/substances/[id]/concepts/[concept]">): Promise<Metadata> {
  const { id, concept } = await params;
  const detail = await getConceptDetail(id, concept);
  if (!detail) return { title: "Not found" };
  return { title: `${conceptLabel(detail.concept)} · ${detail.substance_name}` };
}

export default async function ConceptPage({
  params,
}: PageProps<"/substances/[id]/concepts/[concept]">) {
  const { id, concept } = await params;
  const detail = await getConceptDetail(id, concept);
  if (!detail) notFound();

  const byProduct = new Map(detail.products.map((p) => [p.external_id, p]));
  const isRecallGap = concept === UNCLASSIFIED;
  const shared = identicalWording(detail.cells, detail.products);

  return (
    <article className="space-y-10">
      <header className="space-y-4">
        <Link
          href={`/substances/${id}`}
          className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
        >
          ← {detail.substance_name}
        </Link>
        <h1 className="font-serif text-title font-normal tracking-tight">
          {conceptLabel(detail.concept)}
        </h1>
        <p className="max-w-prose text-ink-muted">
          {isRecallGap
            ? "Clauses that matched no concept in the lexicon — recorded and shown rather than dropped."
            : detail.diverges
              ? "These manufacturers do not place this the same way."
              : "Every manufacturer places this the same way."}
        </p>
      </header>

      <PlacementSpectrum cells={detail.cells} products={detail.products} />

      <AppearanceStrip products={detail.products} />

      <div className="divide-y divide-rule border-y border-rule">
        {detail.cells.map((cell) => (
          <Manufacturer
            key={cell.product_external_id}
            cell={cell}
            product={byProduct.get(cell.product_external_id)}
            sharedWith={shared.get(cell.product_external_id) ?? []}
          />
        ))}
      </div>
    </article>
  );
}

function Manufacturer({
  cell,
  product,
  sharedWith,
}: {
  cell: ConceptCell;
  product: ProductColumn | undefined;
  sharedWith: string[];
}) {
  const sourceUrl = cell.evidence?.source_url ?? product?.source_url ?? undefined;
  const name = product ? manufacturer(product) : cell.product_external_id;

  return (
    <section className="space-y-4 py-8">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-medium">{name}</h2>
          {sharedWith.length > 0 && (
            <p className="text-kicker text-ink-muted">
              identical wording to {sharedWith.join(", ")}
            </p>
          )}
          <p className="font-mono text-meta text-ink-muted">
            {product?.variant ?? product?.name}
            {product?.revised ? ` · revised ${product.revised}` : " · revision unknown"}
          </p>
        </div>
        <PlacementBadge placement={cell.placement} />
      </header>

      {cell.evidence ? (
        <>
          {cell.context ? (
            <InContext context={cell.context} />
          ) : (
            <blockquote className="max-w-prose border-l-2 border-rule pl-6 font-serif text-quote">
              &ldquo;{cell.evidence.quote}&rdquo;
            </blockquote>
          )}
          {cell.context && (
            <QuotePosition
              charStart={cell.evidence.char_start}
              charEnd={cell.evidence.char_end}
              sectionLength={cell.context.section_length}
              sectionCode={cell.evidence.section_code}
            />
          )}
          <p className="font-mono text-meta text-ink-muted">
            {sourceUrl && (
              <>
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-accent underline underline-offset-4"
                >
                  Source SmPC ↗
                </a>
              </>
            )}
          </p>
        </>
      ) : (
        <Absence product={product} sourceUrl={sourceUrl} />
      )}
    </section>
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
    <blockquote className="max-w-prose border-l-2 border-rule pl-6 font-serif text-quote text-ink-muted">
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
function Absence({
  product,
  sourceUrl,
}: {
  product: ProductColumn | undefined;
  sourceUrl: string | undefined;
}) {
  const scanned = product?.scanned ?? [];
  return (
    <>
      <p className="max-w-prose border-l-2 border-dashed border-rule pl-6 text-ink-muted">
        No match in {scanned.length ? `sections ${scanned.join(", ")}` : "any section"} as
        read for this label. Not the same as the label being silent.
      </p>
      <SectionCoverage scanned={scanned} />
      <p className="font-mono text-meta text-ink-muted">
        {sourceUrl && (
          <>
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="text-accent underline underline-offset-4"
            >
              Source SmPC ↗
            </a>
          </>
        )}
      </p>
    </>
  );
}
