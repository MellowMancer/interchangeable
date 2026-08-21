import type { Metadata } from "next";
import Link from "next/link";
import { AppearanceRail } from "@/lib/appearance";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getMatrix,
  manufacturer,
  type ClauseCoverage,
  type IndicationGroup,
  type Matrix,
  type ProductColumn,
  type Row,
  type ValueSection,
} from "@/lib/api";
import {
  partition,
  sharedScanned,
  UNCLASSIFIED,
} from "@/lib/finding";
import {
  ABSENT,
  PLACEMENT_LEGEND,
  PlacementBadge,
  PlacementChip,
} from "@/lib/placement";
import { RevisionTimeline } from "@/lib/timeline";

/**
 * Every concept, across every manufacturer.
 *
 * Disagreement is the content and agreement is the corroboration, so the two are drawn
 * differently: the rows that diverge get the table, and the rows that do not get a dense
 * list. Both are present and both are reachable — collapsing the agreeing rows into a
 * count would hide the evidence that the comparison works at all.
 */
/** The substance names the tab, so several open comparisons stay tellable apart. */
export async function generateMetadata({
  params,
}: PageProps<"/substances/[id]">): Promise<Metadata> {
  const { id } = await params;
  const matrix = await getMatrix(id);
  return { title: matrix?.substance_name ?? "Not found" };
}

export default async function SubstancePage({ params }: PageProps<"/substances/[id]">) {
  const { id } = await params;
  const matrix = await getMatrix(id);
  if (!matrix) notFound();

  const { divergent, agreeing } = partition(matrix.rows);
  const concepts = divergent.length + agreeing.length;
  // A holder may hold several products, and they need not agree with each other, so the
  // two counts are different facts and the table shows both.
  const holders = holderGroups(matrix.products).length;

  return (
    <div className="space-y-12">
      <header className="space-y-4">
        <Link
          href="/"
          className="inline-block font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
        >
          ← All substances
        </Link>
        <h1 className="font-serif text-title font-normal tracking-tight">
          {matrix.substance_name}
        </h1>
        <p className="font-mono text-meta text-ink-muted">
          {holders} manufacturers · {matrix.products.length} products · {concepts} concepts
          · {divergent.length === 0 ? "none disagree" : `${divergent.length} disagree`}
        </p>
        <Classification products={matrix.products} />
        <div className="grid gap-10 lg:grid-cols-[1fr_minmax(0,20rem)]">
          <Indications groups={matrix.indications} total={matrix.products.length} />
          <AppearanceRail products={matrix.products} />
        </div>
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

      <ValueSections sections={matrix.values} />

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
                  <PlacementBadge placement={row.cells[0]?.placement ?? "absent"} />
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

/**
 * §6.3 and §6.4, quoted rather than judged.
 *
 * These sections state a value instead of filing a concept, so they never enter the
 * placement matrix — a shelf life is not a place a warning can live. They are shown
 * because two labels for one substance disagreeing on whether it needs refrigerating is
 * an interchangeability finding in its own right, and one a reader can evaluate directly.
 *
 * Every distinct wording is printed verbatim and attributed. Nothing here says the labels
 * require different things: "Do not store above 25°C" and "Store below 25°C" are the same
 * instruction, and only the reader can tell that apart from a real difference.
 */
function ValueSections({ sections }: { sections: ValueSection[] }) {
  if (sections.length === 0) return null;

  return (
    <section className="space-y-6 border-t border-rule pt-10">
      <Kicker>What the labels state, in their own words</Kicker>
      <div className="grid gap-10 lg:grid-cols-2">
        {sections.map((section) => (
          <article key={section.code} className="space-y-3">
            {/* The app's voice, in the app's face: everything below is the label's own
                words in serif, and a heading set like them reads as one of them. */}
            <h3 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
              §{section.code} — {section.heading}
            </h3>
            <ul className="divide-y divide-rule border-y border-rule">
              {section.groups.map((group) => (
                <li key={group.text} className="flex flex-col gap-1 py-3">
                  {/* Serif, because these are the label's words and not ours. Blank lines
                      between the label's own lines are closed up — a paragraph break is
                      formatting, and left as-is it reads as two separate statements. */}
                  <div className="space-y-1 font-serif text-body">
                    {group.text
                      .split(/\n+/)
                      .map((line) => line.trim())
                      .filter(Boolean)
                      .map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                  </div>
                  <p className="font-mono text-kicker text-ink-muted">
                    {group.manufacturers.join(" · ")}
                  </p>
                </li>
              ))}
            </ul>
            {/* Stated rather than implied: a section three labels carry is not a section
                the other four contradict. */}
            <p className="text-kicker text-ink-muted">
              {section.collected === section.total
                ? `Stated by all ${section.total} labels.`
                : `Stated by ${section.collected} of ${section.total} labels; the rest have none collected.`}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

/** Above this many columns a badge no longer fits, and the cells become chips. */
const COMPACT_ABOVE = 5;

/**
 * Products of one holder, kept adjacent and named once.
 *
 * Grouping is by `holder_id` where the label carries it, because `ma_holder` is free text
 * and two spellings of one company would otherwise read as two manufacturers — invisible
 * at three columns, certain at ten, and it would manufacture a divergence.
 *
 * The products are *not* merged. One holder's capsule and tablet disagree on seven
 * concepts in the collected corpus — all of them excipients, which is exactly what
 * changes between two formulations of the same molecule. Collapsing a holder into one
 * column would delete that, so the holder spans its products rather than replacing them.
 */
function holderGroups(products: ProductColumn[]): { name: string; products: ProductColumn[] }[] {
  const groups: { key: string; name: string; products: ProductColumn[] }[] = [];
  for (const product of products) {
    const key = product.holder_id === null ? `name:${manufacturer(product)}` : `id:${product.holder_id}`;
    const held = groups.find((g) => g.key === key);
    if (held) held.products.push(product);
    else groups.push({ key, name: manufacturer(product), products: [product] });
  }
  return groups.map(({ name, products: p }) => ({ name, products: p }));
}

function DivergenceTable({ matrix, rows }: { matrix: Matrix; rows: Row[] }) {
  const groups = holderGroups(matrix.products);
  const ordered = groups.flatMap((g) => g.products);
  const compact = ordered.length > COMPACT_ABOVE;

  return (
    <div className="space-y-2">
      {/* A cut-off table on a phone reads as broken rather than as scrollable. */}
      <p className="font-mono text-kicker text-ink-muted md:hidden">
        scroll for all {ordered.length} products →
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-paper p-2 text-left font-normal">
                <span className="sr-only">Concept</span>
              </th>
              {groups.map((group) => (
                <th
                  key={group.name}
                  colSpan={group.products.length}
                  scope="colgroup"
                  className="border-l border-rule px-2 pt-2 text-left align-bottom font-medium first:border-l-0"
                >
                  {group.name}
                </th>
              ))}
            </tr>
            <tr className="border-b border-rule">
              <th className="sticky left-0 z-10 bg-paper p-2" />
              {ordered.map((product) => (
                <th
                  key={product.external_id}
                  scope="col"
                  className="px-2 pb-2 text-left align-bottom font-normal"
                >
                  <div className="font-mono text-meta">{product.variant ?? product.name}</div>
                  <div className="font-mono text-kicker text-ink-muted">
                    {product.revised ? product.revised : "revision unknown"}
                  </div>
                  {product.discontinued && (
                    <div className="font-mono text-kicker text-accent">discontinued</div>
                  )}
                  {!compact && product.ma_number && (
                    <div className="font-mono text-kicker text-ink-muted">{product.ma_number}</div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.concept} className="border-b border-rule align-top">
                <th className="sticky left-0 z-10 bg-paper p-2 pr-4 text-left font-normal">
                  <Link
                    href={`/substances/${matrix.substance_id}/concepts/${encodeURIComponent(row.concept)}`}
                    className="underline underline-offset-4 hover:text-accent"
                  >
                    {conceptLabel(row.concept)}
                  </Link>
                </th>
                {ordered.map((product, order) => {
                  const cell = row.cells.find((c) => c.product_external_id === product.external_id);
                  return (
                    <td key={product.external_id} className="px-1 py-2">
                      {cell &&
                        (compact ? (
                          <PlacementChip placement={cell.placement} />
                        ) : (
                          <PlacementBadge
                            placement={cell.placement}
                            className="animate-land"
                            delayMs={order * 70}
                          />
                        ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
          className="animate-grow-x bg-p45"
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

      {/* The API only builds a row for concepts that matched, so with nothing unmatched
          this link would lead to a 404 — an invitation to inspect an empty gap. */}
      {clauses.unclassified > 0 && (
        <Link
          href={`/substances/${substanceId}/concepts/${encodeURIComponent(UNCLASSIFIED)}`}
          className="inline-block text-meta text-accent underline underline-offset-4"
        >
          Inspect what went unmatched →
        </Link>
      )}
    </section>
  );
}

/**
 * What the labels say this substance is for.
 *
 * Shown, never diffed. §4.1 describes the substance rather than naming a section a safety
 * concept is filed in, so a difference here is different wording — not a divergence, and
 * not something the comparison's vocabulary reaches.
 *
 * When every label states the same indications this reads as the substance's own
 * description. When they do not, each wording is shown with the manufacturers carrying it
 * rather than one being picked to stand for the rest.
 */
function Indications({ groups, total }: { groups: IndicationGroup[]; total: number }) {
  if (groups.length === 0) return null;
  const carrying = groups.reduce((n, g) => n + g.manufacturers.length, 0);
  const agreed = groups.length === 1;

  return (
    <section className="max-w-prose space-y-3">
      <Kicker>{agreed ? "What it is for" : "What it is for — the labels differ"}</Kicker>
      {groups.map((group) => (
        <div key={group.manufacturers.join("|")} className="space-y-2">
          {!agreed && (
            <p className="font-mono text-kicker text-ink-muted">
              as stated by {group.manufacturers.join(", ")}
            </p>
          )}
          {/* Indented as the label indents it. Ten equal lines said this substance is
              authorised for ten things; it is authorised for five, two of them qualified. */}
          <ul className="space-y-1">
            {group.statements.map((statement) => (
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
        </div>
      ))}
      <p className="text-kicker text-ink-muted">
        Section 4.1, verbatim, collected for {carrying} of {total} labels.{" "}
        {agreed
          ? "Every one of those states these."
          : "Those labels do not state the same set."}
      </p>
    </section>
  );
}

/**
 * Whether these columns are the same medicine at all.
 *
 * The comparison assumes its columns are interchangeable candidates. Two different ATC
 * codes under one substance mean they are not, and that is worth saying out loud rather
 * than letting a reader infer agreement from a table that should never have been built.
 * Silent when every column agrees and nothing is in doubt.
 */
function Classification({ products }: { products: ProductColumn[] }) {
  const codes = [...new Set(products.map((p) => p.atc_code).filter(Boolean))];
  if (codes.length < 2) return null;
  return (
    <p className="max-w-prose border-l-2 border-accent pl-4 text-meta text-ink-muted">
      These products carry <span className="text-ink">different ATC codes</span> (
      <span className="font-mono">{codes.join(", ")}</span>), so they may not be
      alternatives to one another. A divergence below may be that rather than a
      disagreement.
    </p>
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
            <dd className="text-kicker text-ink-muted">{style.detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
