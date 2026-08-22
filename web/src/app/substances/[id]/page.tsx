import type { Metadata } from "next";
import { Section } from "@/lib/heading";
import Link from "next/link";
import { AppearanceRail, DosageGlyph, undrawnBecause } from "@/lib/appearance";
import { Concepts, Diverges, Makers } from "@/lib/icons";
import { Comparison, Maker } from "@/lib/compare";
import { Carousel } from "@/lib/carousel";
import { notFound } from "next/navigation";
import {
  getMatrix,
  manufacturer,
  type IndicationGroup,
  type ProductColumn,
} from "@/lib/api";
import {
  holderGroups,
  partition,
} from "@/lib/finding";

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
          className="inline-block font-mono text-kicker text-ink-muted hover:text-ink"
        >
          ← All substances
        </Link>
        <h1 className="font-serif text-title font-normal tracking-tight">
          {matrix.substance_name}
        </h1>
        {/* The same three marks the roster card uses, so a substance reads the same on
            the list it came from and the page it opens. */}
        <dl className="flex flex-wrap items-center gap-x-5 font-mono text-meta text-ink-muted">
          <Count icon={<Makers />} term="manufacturers" value={holders} />
          <Count icon={<Concepts />} term="concepts read" value={concepts} />
          <Count
            icon={<Diverges />}
            term="concepts they disagree about"
            value={divergent.length}
            accent={divergent.length > 0}
          />
        </dl>
        {/* The links start level with the caveat, not below the indications: the column
            beside a three-line warning was otherwise empty. */}
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
          <div className="min-w-0 space-y-5">
            <Classification products={matrix.products} />
            <Indications groups={matrix.indications} products={matrix.products} />
          </div>
          <AppearanceRail products={matrix.products} />
        </div>
      </header>

      <Comparison matrix={matrix} />

      {/* The same shelf a label's own page carries, so arriving at a substance and
          arriving at one of its products both end with the rest of them. Quick links
          above is a list to navigate by; this is the set, drawn. */}
      <section className="section-break space-y-4">
        <Section>
          <span className="flex items-center gap-2">
            <Makers />
            All {matrix.substance_name} products ({matrix.products.length})
          </span>
        </Section>
        <ul className="animate-deal -mx-6 flex snap-x gap-4 overflow-x-auto px-6 pb-2">
          {matrix.products.map((product) => (
            <li key={product.external_id} className="w-64 shrink-0 snap-start">
              <ProductCard product={product} />
            </li>
          ))}
        </ul>
      </section>

    </div>
  );
}


/** How many of a wording's statements a card shows before deferring to the label itself. */
const STATEMENTS_SHOWN = 5;





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
    <Carousel
      label={`${count} wordings of what this substance is for`}
      heading={<Section>Indications ({count})</Section>}
      count={count}
    >
      {children}
    </Carousel>
  );

function Indications({
  groups,
  products,
}: {
  groups: IndicationGroup[];
  products: ProductColumn[];
}) {
  // Every holder named here is a label a reader can open.
  const labelOf = new Map(
    [...products].reverse().map((product) => [manufacturer(product), product.external_id]),
  );
  if (groups.length === 0) return null;
  const agreed = groups.length === 1;

  return (
    <section className="max-w-prose space-y-3">
      {agreed && <Section>Indications</Section>}
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
              as stated by{" "}
              {group.manufacturers.map((name, at) => (
                <span key={name}>
                  {at > 0 && ", "}
                  <Maker name={name} labelOf={labelOf} />
                </span>
              ))}
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
      <span className="font-mono break-all">{codes.join(", ")}</span>), so they may not be
      alternatives to one another.
    </p>
  );
}

/** One number about this substance, named for a screen reader and drawn for everyone else. */
const Count = ({
  icon,
  term,
  value,
  accent = false,
}: {
  icon: React.ReactNode;
  term: string;
  value: number;
  accent?: boolean;
}) => (
  <div title={`${value} ${term}`} className="flex items-center gap-1.5">
    <dt className="sr-only">{term}</dt>
    <span aria-hidden className={accent ? "text-accent" : undefined}>
      {icon}
    </span>
    <dd className={accent ? "text-accent" : undefined}>{value}</dd>
  </div>
);

/** One label of this substance, as a card on the shelf. */
function ProductCard({ product }: { product: ProductColumn }) {
  const drawable = product.appearance && undrawnBecause(product.appearance).length === 0;

  return (
    <Link
      href={`/products/${product.external_id}`}
      className="flex h-full flex-col gap-2 border border-rule p-4 transition-transform hover:-translate-y-0.5 hover:border-accent hover:bg-rule/30"
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
