import Link from "next/link";
import {
  conceptLabel,
  getMatrix,
  getSubstances,
  manufacturer,
  type Matrix,
} from "@/lib/api";
import { AppearanceStrip } from "@/lib/appearance";
import {
  featuredRow,
  featuredSubstance,
  groupEvidence,
  listNames,
  placementSummary,
  sharedScanned,
  type EvidenceGroup,
} from "@/lib/finding";
import { PlacementBadge } from "@/lib/placement";
import { SectionCoverage } from "@/lib/scope";
import { PlacementSpectrum } from "@/lib/spectrum";

/**
 * Land on a finding, not a search box.
 *
 * Judges look for about thirty seconds, and an empty search box spends all of it. Which
 * substance and which concept appear here are both derived from the corpus, so this page
 * follows the strongest disagreement as the roster grows rather than freezing on the one
 * that happened to be collected first.
 */
export default async function Home() {
  const substances = await getSubstances();
  const featured = featuredSubstance(substances);
  if (!featured) return <NothingCollected count={substances.length} />;

  const matrix = await getMatrix(featured.id);
  if (!matrix) return <NothingCollected count={substances.length} />;

  const row = featuredRow(matrix);
  if (!row) return <NoDisagreement matrix={matrix} />;

  return (
    <article className="space-y-12">
      <header className="space-y-6">
        <p className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
          Finding · {matrix.substance_name} · {conceptLabel(row.concept)}
        </p>

        <h1 className="max-w-3xl font-serif text-display font-normal tracking-tight text-balance">
          Same drug. Different manufacturer. Different label.
        </h1>

        <p className="max-w-prose text-ink-muted">
          {placementSummary(row, matrix.products)}
        </p>
      </header>

      <AppearanceStrip products={matrix.products} />

      <PlacementSpectrum cells={row.cells} products={matrix.products} />

      <section className="divide-y divide-rule border-y border-rule">
        {groupEvidence(row, matrix.products).map((group) => (
          <Position key={`${group.placement}-${group.cells[0].product_external_id}`} group={group} />
        ))}
      </section>

      <Provenance matrix={matrix} />

      <section className="max-w-prose space-y-4 border-t border-rule pt-8">
        <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
          What this does not say
        </h2>
        <p className="text-ink-muted">
          One finding, not a rate — a rate needs a far larger run than has been done.
        </p>
        <p className="text-ink-muted">
          A concept not found is reported against the sections actually read for that
          label, never as an omission from the label.
        </p>
      </section>
    </article>
  );
}

/**
 * One position, and the label text behind it.
 *
 * Manufacturers whose labels carry byte-identical wording share a block. Generic SmPCs
 * are frequently copied verbatim between holders, so printing each in full repeats
 * hundreds of characters and buries the one label that differs.
 */
function Position({ group }: { group: EvidenceGroup }) {
  const names = group.products.length
    ? group.products.map(manufacturer)
    : group.cells.map((cell) => cell.product_external_id);
  const scanned = group.products[0]?.scanned ?? [];

  return (
    <div className="space-y-3 py-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-medium">{listNames(names)}</h2>
          {group.shared && (
            <p className="text-kicker text-ink-muted">
              identical wording on {names.length} labels
            </p>
          )}
        </div>
        <PlacementBadge placement={group.placement} />
      </header>

      {group.evidence ? (
        <>
          <blockquote className="max-w-prose border-l-2 border-rule pl-6 font-serif text-quote">
            &ldquo;{group.evidence.quote}&rdquo;
          </blockquote>
          <p className="font-mono text-meta text-ink-muted">
            §{group.evidence.section_code} · chars {group.evidence.char_start}&ndash;
            {group.evidence.char_end}
          </p>
        </>
      ) : (
        <p className="max-w-prose border-l-2 border-dashed border-rule pl-6 text-ink-muted">
          Not found in {scanned.length ? `sections ${scanned.join(", ")}` : "any section"} as
          read for {names.length === 1 ? "this label" : "these labels"}. There is no quote
          because there was no match in what was read — which is not the same as the label
          being silent.
        </p>
      )}

      <ul className="flex flex-wrap gap-x-5 gap-y-1">
        {group.products.map((product) =>
          product.source_url ? (
            <li key={product.external_id}>
              <a
                href={product.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="font-mono text-meta text-accent underline underline-offset-4"
              >
                {manufacturer(product)} SmPC ↗
              </a>
            </li>
          ) : null,
        )}
      </ul>
    </div>
  );
}

/**
 * The scanned sections are part of the claim, not a caption.
 *
 * Every absence is only meaningful against this list, so it sits with the finding rather
 * than in a footnote.
 */
function Provenance({ matrix }: { matrix: Matrix }) {
  const shared = sharedScanned(matrix.products);
  return (
    <section className="flex flex-wrap items-baseline justify-between gap-4 border-b border-rule pb-8">
      <div className="max-w-prose space-y-2">
        {shared ? (
          <SectionCoverage scanned={shared} />
        ) : (
          <p className="text-meta text-ink-muted">Sections read differ by manufacturer.</p>
        )}
        <p className="text-meta text-ink-muted">
          Sections read. An absence means not found in these — never that the label omits
          it. Every quote is sliced from the stored text at the offsets shown, so any claim
          here can be checked against its source.
        </p>
      </div>
      <Link
        href={`/substances/${matrix.substance_id}`}
        className="text-accent underline underline-offset-4"
      >
        See all {matrix.rows.length} concepts compared →
      </Link>
    </section>
  );
}

function NoDisagreement({ matrix }: { matrix: Matrix }) {
  return (
    <div className="max-w-prose space-y-4">
      <h1 className="font-serif text-title font-normal">
        {matrix.substance_name}: no disagreement found
      </h1>
      <p className="text-ink-muted">
        Across {matrix.products.length} manufacturers and {matrix.rows.length} concepts,
        every label places each concept in the same section — in the sections that were
        read. That is a finding too.
      </p>
      <Link
        href={`/substances/${matrix.substance_id}`}
        className="inline-block text-accent underline underline-offset-4"
      >
        See the comparison →
      </Link>
    </div>
  );
}

function NothingCollected({ count }: { count: number }) {
  return (
    <div className="max-w-prose space-y-4">
      <h1 className="font-serif text-title font-normal">Nothing collected yet</h1>
      <p className="text-ink-muted">
        The roster lists {count} substances, but no labels have been fetched. Run{" "}
        <code className="font-mono text-meta text-ink">ixq init</code> then{" "}
        <code className="font-mono text-meta text-ink">ixq run</code> to populate the
        comparison.
      </p>
    </div>
  );
}
