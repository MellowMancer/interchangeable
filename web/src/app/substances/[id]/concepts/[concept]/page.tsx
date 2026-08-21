import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getConceptDetail,
  manufacturer,
  type ConceptCell,
  type ContextWindow,
  type ProductColumn,
} from "@/lib/api";
import { groupByWording, UNCLASSIFIED, type WordingGroup } from "@/lib/finding";
import { PlacementBadge } from "@/lib/placement";
import { QuotePosition, SectionCoverage } from "@/lib/scope";
import Link from "next/link";
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
  const groups = groupByWording(detail.cells, detail.products);

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

      {/* One block per distinct wording, two abreast. A block per label turned ten
          manufacturers into a page nobody reaches the end of — and most of those blocks
          were the same sentence, because generics copy an SmPC verbatim. */}
      <ul className="grid border-t border-rule lg:grid-cols-2">
        {groups.map((group) => (
          <li
            key={`${group.placement}|${group.cells[0].product_external_id}`}
            className="border-b border-rule lg:odd:border-r lg:odd:pr-10 lg:even:pl-10"
          >
            <Wording group={group} byProduct={byProduct} />
          </li>
        ))}
      </ul>
    </article>
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
      <p className="font-medium">{product ? manufacturer(product) : cell.product_external_id}</p>
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
