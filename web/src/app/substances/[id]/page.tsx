import Link from "next/link";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getMatrix,
  manufacturer,
  type ClauseCoverage,
  type Matrix,
  type Row,
} from "@/lib/api";
import {
  partition,
  sharedScanned,
  UNCLASSIFIED,
} from "@/lib/finding";
import { ABSENT, PLACEMENT_LEGEND, PlacementBadge, placementStyle } from "@/lib/placement";
import { RevisionTimeline } from "@/lib/timeline";

/**
 * Every concept, across every manufacturer.
 *
 * Disagreement is the content and agreement is the corroboration, so the two are drawn
 * differently: the rows that diverge get the table, and the rows that do not get a dense
 * list. Both are present and both are reachable — collapsing the agreeing rows into a
 * count would hide the evidence that the comparison works at all.
 */
export default async function SubstancePage({ params }: PageProps<"/substances/[id]">) {
  const { id } = await params;
  const matrix = await getMatrix(id);
  if (!matrix) notFound();

  const { divergent, agreeing } = partition(matrix.rows);
  const concepts = divergent.length + agreeing.length;

  return (
    <div className="space-y-12">
      <header className="space-y-4">
        <h1 className="font-serif text-title font-normal tracking-tight">
          {matrix.substance_name}
        </h1>
        <p className="font-mono text-meta text-ink-muted">
          {matrix.products.length} manufacturers · {concepts} concepts ·{" "}
          {divergent.length === 0 ? "none disagree" : `${divergent.length} disagree`}
        </p>
        <Link
          href="/substances"
          className="inline-block font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
        >
          ← All substances
        </Link>
      </header>

      {divergent.length > 0 ? (
        <section className="space-y-6">
          <Kicker>Where they disagree</Kicker>
          <DivergenceTable matrix={matrix} rows={divergent} />
        </section>
      ) : (
        <section className="space-y-4">
          <Kicker>Where they disagree</Kicker>
          <p className="max-w-prose text-ink-muted">
            Nowhere that was scanned. Every concept below sits in the same section on every
            label read.
          </p>
        </section>
      )}

      <section className="space-y-6 border-t border-rule pt-10">
        <Kicker>When each label was last revised</Kicker>
        <RevisionTimeline products={matrix.products} />
      </section>

      {agreeing.length > 0 && (
        <section className="space-y-6 border-t border-rule pt-10">
          <Kicker>Where they agree — {agreeing.length} concepts</Kicker>
          <ul className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
            {agreeing.map((row) => (
              <li key={row.concept}>
                <Link
                  href={`/substances/${id}/concepts/${encodeURIComponent(row.concept)}`}
                  className="flex items-baseline justify-between gap-3 border-b border-rule py-1.5 hover:text-accent"
                >
                  <span>{conceptLabel(row.concept)}</span>
                  <span className="font-mono text-meta text-ink-muted">
                    {placementStyle(row.cells[0]?.placement ?? "absent").section ?? "—"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <RecallGap clauses={matrix.clauses} substanceId={id} />

      <Provenance matrix={matrix} />
    </div>
  );
}

const Kicker = ({ children }: { children: React.ReactNode }) => (
  <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">{children}</h2>
);

function DivergenceTable({ matrix, rows }: { matrix: Matrix; rows: Row[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-rule">
            <th className="sticky left-0 z-10 bg-paper p-3 text-left align-bottom font-normal">
              <span className="sr-only">Concept</span>
            </th>
            {matrix.products.map((product) => (
              <th key={product.external_id} className="p-3 text-left align-bottom font-normal">
                <div className="font-medium">{manufacturer(product)}</div>
                <div className="font-mono text-meta text-ink-muted">
                  {product.variant ?? product.name}
                </div>
                <div className="font-mono text-meta text-ink-muted">
                  {product.revised ? `revised ${product.revised}` : "revision unknown"}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.concept} className="border-b border-rule align-top">
              <th className="sticky left-0 z-10 bg-paper p-3 text-left font-normal">
                <Link
                  href={`/substances/${matrix.substance_id}/concepts/${encodeURIComponent(row.concept)}`}
                  className="underline underline-offset-4 hover:text-accent"
                >
                  {conceptLabel(row.concept)}
                </Link>
              </th>
              {row.cells.map((cell) => (
                <td key={cell.product_external_id} className="p-3">
                  <PlacementBadge placement={cell.placement} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The recall gap, published rather than tuned away.
 *
 * Two counts drawn to scale, never a percentage: a ratio here would read as a claim about
 * how well the lexicon performs in general, and one substance cannot support that. The bar
 * says how much of this corpus fell through, which is a measurement of our own parser.
 *
 * `unclassified` is kept out of the concept list above for the same reason it is shown
 * here: it is not a clinical concept, and sorting it among real ones would present a
 * parser gap as a clinical finding.
 */
function RecallGap({ clauses, substanceId }: { clauses: ClauseCoverage; substanceId: string }) {
  const total = clauses.classified + clauses.unclassified;
  if (total === 0) return null;

  return (
    <section className="max-w-prose space-y-3 border-t border-rule pt-10">
      <Kicker>Recall gap</Kicker>

      <div className="flex h-6 overflow-hidden rounded-sheet border border-rule">
        <div
          className="bg-p45"
          style={{ width: `${(clauses.classified / total) * 100}%` }}
          title={`${clauses.classified} clauses matched a concept`}
        />
        <div
          className="border-l border-dashed border-rule"
          style={{ width: `${(clauses.unclassified / total) * 100}%` }}
          title={`${clauses.unclassified} clauses matched nothing`}
        />
      </div>

      <dl className="flex flex-wrap gap-x-6 font-mono text-meta">
        <div className="flex gap-2">
          <dt className="text-ink-muted">matched a concept</dt>
          <dd>{clauses.classified}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-ink-muted">matched nothing</dt>
          <dd>{clauses.unclassified}</dd>
        </div>
      </dl>

      <p className="text-meta text-ink-muted">
        Clauses matching no concept in the lexicon are recorded as{" "}
        <code className="font-mono text-ink">unclassified</code> rather than dropped. A
        visible gap is worth more than a clean-looking result that quietly lost what it
        could not parse.
      </p>

      <Link
        href={`/substances/${substanceId}/concepts/${encodeURIComponent(UNCLASSIFIED)}`}
        className="inline-block text-meta text-accent underline underline-offset-4"
      >
        Inspect what went unmatched →
      </Link>
    </section>
  );
}

function Provenance({ matrix }: { matrix: Matrix }) {
  const shared = sharedScanned(matrix.products);
  return (
    <section className="space-y-6 border-t border-rule pt-10">
      <p className="max-w-prose text-meta text-ink-muted">
        {shared ? (
          <>
            Sections read: <span className="font-mono text-ink">{shared.join(" · ")}</span>.{" "}
          </>
        ) : (
          <>Sections read differ by manufacturer. </>
        )}
        <em>{ABSENT.label}</em> means not found in what was read for that manufacturer —
        not that the label omits it.
      </p>

      <dl className="flex flex-wrap gap-x-6 gap-y-3 text-meta text-ink-muted">
        {PLACEMENT_LEGEND.map((style) => (
          <div key={style.label} className="flex items-center gap-2">
            <dt>
              <span
                className={`inline-flex items-baseline gap-1.5 rounded-sheet border px-2 py-1 text-kicker tracking-wide uppercase ${style.className}`}
              >
                {style.label}
                {style.section && <span className="font-mono opacity-80">{style.section}</span>}
              </span>
            </dt>
            <dd className="sr-only">{style.detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
