import type { Metadata } from "next";
import Link from "next/link";
import { AppearanceRail } from "@/lib/appearance";
import { Comparison } from "@/lib/compare";
import { Carousel } from "@/lib/carousel";
import { notFound } from "next/navigation";
import {
  getMatrix,
  type ClauseCoverage,
  type IndicationGroup,
  type Matrix,
  type ProductColumn,
} from "@/lib/api";
import {
  holderGroups,
  partition,
  sharedScanned,
  UNCLASSIFIED,
} from "@/lib/finding";
import {
  ABSENT,
  PLACEMENT_LEGEND,
} from "@/lib/placement";

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
        {/* The links start level with the caveat, not below the indications: the column
            beside a three-line warning was otherwise empty. */}
        <div className="grid gap-10 lg:grid-cols-[1fr_minmax(0,18rem)]">
          <div className="space-y-5">
            <Classification products={matrix.products} />
            <Indications groups={matrix.indications} total={matrix.products.length} />
          </div>
          <AppearanceRail products={matrix.products} />
        </div>
      </header>

      <Comparison matrix={matrix} />

      <RecallGap clauses={matrix.clauses} substanceId={id} />

      <Provenance matrix={matrix} />
    </div>
  );
}

const Kicker = ({ children }: { children: React.ReactNode }) => (
  <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">{children}</h2>
);


/** How many of a wording's statements a card shows before deferring to the label itself. */
const STATEMENTS_SHOWN = 5;




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
/** One wording is a paragraph; ten are a shelf. Only the second needs moving parts. */
const Wordings = ({
  agreed,
  count,
  children,
}: {
  agreed: boolean;
  count: number;
  children: React.ReactNode;
}) =>
  agreed ? (
    <>{children}</>
  ) : (
    <Carousel label={`${count} wordings of what this substance is for`}>{children}</Carousel>
  );

function Indications({ groups, total }: { groups: IndicationGroup[]; total: number }) {
  if (groups.length === 0) return null;
  const carrying = groups.reduce((n, g) => n + g.manufacturers.length, 0);
  const agreed = groups.length === 1;

  return (
    <section className="max-w-prose space-y-3">
      <Kicker>
        {agreed
          ? "What it is for"
          : `What it is for — ${groups.length} labels word this differently`}
      </Kicker>
      {/* Sideways, not stacked. Ten wordings of one description is a screenful before the
          reader reaches the comparison, and each is a paraphrase of the last — so they
          cost one card's height between them and the reader moves along only if the
          differences interest them. Scroll snapping, no script. */}
      <Wordings agreed={agreed} count={groups.length}>
      {groups.map((group) => (
        <div
          key={group.manufacturers.join("|")}
          // Half the shelf each, less half the gap between them, so two sit exactly in
            // view and a third edge shows there is more.
            className={
              agreed
                ? "space-y-2"
                : "w-[calc(50%-0.75rem)] shrink-0 snap-start space-y-2"
            }
        >
          {!agreed && (
            <p className="font-mono text-kicker text-ink-muted">
              as stated by {group.manufacturers.join(", ")}
            </p>
          )}
          {/* Indented as the label indents it. Ten equal lines said this substance is
              authorised for ten things; it is authorised for five, two of them qualified. */}
          {/* Five, then a count. A card is a glance at how this label words it; the
              whole of §4.1 is on the label's own page, where nothing competes with it. */}
          <ul className="space-y-1">
            {group.statements.slice(0, STATEMENTS_SHOWN).map((statement) => (
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
          {group.statements.length > STATEMENTS_SHOWN && (
            <p className="font-mono text-kicker text-ink-muted">
              + {group.statements.length - STATEMENTS_SHOWN} more
            </p>
          )}
        </div>
      ))}
      </Wordings>
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
