import Link from "next/link";
import {
  type Placement,
  PlacementBadge,
  placementStyle,
  SECTION_PLACEMENTS,
} from "@/lib/placement";

/**
 * What the words on every other screen mean.
 *
 * The comparison is only readable if three things are understood first: what a substance
 * is, what a placement claims, and why one placement wins when a concept sits in several
 * sections. None of that is inferable from a grid of coloured badges, and a reader who
 * guesses will guess that absence means the label omits something — the single reading
 * this project exists to prevent.
 *
 * Every badge and every ordering here is read from `lib/placement`, never restated. A
 * page that hardcoded its own copy of the vocabulary would drift from the table it claims
 * to explain, and would do it silently.
 */
export default function ReadingPage() {
  return (
    <div className="space-y-16">
      <header className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="space-y-4">
          <h1 className="font-serif text-title font-normal tracking-tight">How to read this</h1>
          {/* A key, not a sentence. Three definitions read as three definitions; the
              same three in prose have to be unpicked before they can be used. */}
          <table className="text-meta">
            <tbody>
              {[
                ["Column", <Term key="m">manufacturer</Term>],
                ["Row", <Term key="c">concept</Term>],
                [
                  "Cell",
                  <span key="p">
                    <Term>placement</Term> — contraindicated, warning, interaction…
                  </span>,
                ],
              ].map(([axis, means]) => (
                <tr key={String(axis)} className="border-b border-rule last:border-b-0">
                  <th
                    scope="row"
                    className="w-24 py-2 pr-6 text-left font-mono text-kicker text-ink-muted"
                  >
                    {axis}
                  </th>
                  <td className="py-2 text-ink-muted">{means}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="max-w-prose text-ink-muted">
            Every comparison is one <Term>substance</Term>. Where the columns of a row
            disagree, that row is a finding.
          </p>
        </div>
        <Scaffold />
      </header>

      <Section kicker="Substance" title="The active ingredient, and the reason a comparison is possible">
        <p>
          A substance is the molecule that does the therapeutic work (ramipril,
          metformin, ibuprofen). It is what a prescription is really for.
        </p>
        <p>
          A <strong className="font-medium text-ink">product</strong> is one
          manufacturer&rsquo;s authorised package of that substance:{" "}
          <em>Ramipril 5mg Tablets</em> from one holder, <em>Ramipril 5mg Hard Capsules</em>{" "}
          from another. One substance, many products, and those products are the columns.
        </p>
        <p>
          Asking whether one
          manufacturer&rsquo;s ibuprofen can stand in for another&rsquo;s is answerable.
          Asking whether ramipril can stand in for ibuprofen is not a question.
        </p>
        <Aside>
          <Distinction term="Not a brand">
            A brand is a product name. <em>Tritace</em> is ramipril; so is{" "}
            <em>Ramipril Aurobindo 5&nbsp;mg Tablets</em>. Same molecule, different box.
          </Distinction>
          <Distinction term="Not a drug class">
            An ATC code identifies the substance; its prefix identifies a class.{" "}
            <span className="font-mono">C09AA05</span> is ramipril,{" "}
            <span className="font-mono">C09AA</span> is every plain ACE inhibitor. Members
            of a class are not substitutes for one another.
          </Distinction>
          <Distinction term="Not a combination">
            A product containing two active substances belongs to neither
            substance&rsquo;s comparison, and is excluded rather than filed under one of
            them.
          </Distinction>
        </Aside>
      </Section>

      <Section kicker="Placement" title="Where a label files a fact — and how strongly it means it">
        <p>
          European labels are numbered and segregated by regulation. A fact in §4.3 (Contraindicated) bars the medicine outright; the same fact in
          §4.4 (Warning) permits it with care.
        </p>
        <dl className="animate-deal divide-y divide-rule border-y border-rule">
          {EVERY_PLACEMENT.map((placement) => (
            <div key={placement} className="grid gap-3 py-5 sm:grid-cols-[16rem_1fr]">
              <dt>
                <PlacementBadge placement={placement} />
              </dt>
              <dd className="text-ink-muted">
                {MEANINGS[placement] ?? placementStyle(placement).detail}
              </dd>
            </div>
          ))}
        </dl>
        {/* <Aside tone="accent">
          <p>
            <strong className="font-medium text-ink">
              Absence is the claim to read most carefully.
            </strong>{" "}
            It means the concept was not found in the sections that were scanned{" "}
            <em>for that manufacturer</em> not that the label omits it. A statement
            missing from §4.3 is very often present in §4.4, and the sections actually read
            are listed on every column for exactly this reason.
          </p>
        </Aside> */}
      </Section>

      <Section kicker="Precedence" title="Which section wins when a concept sits in several">
        <p>
          Labels repeat themselves. A manufacturer may contraindicate a condition in §4.3
          and discuss it again in §4.4 and §4.5. The cell shows the{" "}
          <strong className="font-medium text-ink">strongest</strong> placement, because
          showing the weakest would understate what the label says.
        </p>
        <ol className="animate-deal flex flex-wrap items-center gap-x-3 gap-y-3">
          {SECTION_PLACEMENTS.map((placement, index) => (
            <li key={placement} className="flex items-center gap-3">
              {index > 0 && <span aria-hidden className="text-ink-muted">&rsaquo;</span>}
              <PlacementBadge placement={placement} />
            </li>
          ))}
        </ol>
        <p>
          An absolute bar outranks a warning, which outranks the placements after it. Excipients rank last, as it implies that the concept is merely an ingredient.
        </p>
      </Section>

      <Section kicker="Concept" title="What a clause is about">
        <p>
          A concept is a clinical category: <span className="font-mono">renal</span>,{" "}
          <span className="font-mono">angioedema</span>,{" "}
          <span className="font-mono">pregnancy</span> — identified by word stems in the
          label&rsquo;s own prose. Matching is deterministic and hand-maintained; no
          language model reads these documents.
        </p>
      </Section>

      <footer className="border-t border-rule pt-8">
        <Link
          href="/"
          className="font-mono text-kicker text-accent hover:underline"
        >
          Browse the substances &rarr;
        </Link>
      </footer>
    </div>
  );
}

/**
 * What each placement *means*, as opposed to which section it is.
 *
 * Keyed by the placement itself, and deliberately partial: a placement added to the
 * pipeline before anyone writes its sentence here falls back to its own `detail` rather
 * than rendering blank, so the page degrades to terse instead of to silent.
 */
const MEANINGS: Partial<Record<Placement, string>> = {
  "4.3": "An absolute bar. The label says this medicine must not be given to this patient.",
  "4.4":
    "Permitted, with care. Monitor, adjust the dose, or weigh the risk — but not prohibited.",
  "4.5":
    "A statement about taking it alongside something else — another medicine, food, or alcohol.",
  "4.6":
    "Pregnancy, breastfeeding and fertility, which European labels give a section of their own.",
  "6.1":
    "Physically present in the product. Composition rather than a clinical judgement — and the reason two otherwise identical generics are not always interchangeable.",
  absent:
    "Not found in the sections read for this manufacturer. Not evidence that the label omits it.",
};

/**
 * Every placement a cell can carry, sections in precedence order and absence last.
 *
 * Built from `SECTION_PLACEMENTS` rather than listed, so a section added to the pipeline
 * appears here without this page being remembered — the failure that would otherwise show
 * a reader a badge the glossary does not explain.
 */
const EVERY_PLACEMENT: Placement[] = [...SECTION_PLACEMENTS, "absent"];

const Section = ({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children: React.ReactNode;
}) => (
  // Two columns: the heading holds the left margin and stays put while its prose scrolls
  // past, which is what the empty half of the page was for. A single measure of text down
  // the middle read as one undifferentiated wall.
  <section className="grid gap-x-12 gap-y-4 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
    <div className="space-y-2 lg:sticky lg:top-8 lg:self-start">
      <h2 className="font-mono text-kicker text-accent">{kicker}</h2>
      <h3 className="font-serif text-quote font-normal tracking-tight text-ink">{title}</h3>
    </div>
    <div className="max-w-prose space-y-4 text-ink-muted [&_p]:leading-relaxed">{children}</div>
  </section>
);

const Aside = ({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "accent";
}) => (
  <div
    className={`space-y-3 rounded-sheet border p-5 ${
      tone === "accent" ? "border-accent/40 bg-accent/5" : "border-rule"
    }`}
  >
    {children}
  </div>
);

const Distinction = ({ term, children }: { term: string; children: React.ReactNode }) => (
  <p>
    <strong className="font-medium text-ink">{term}.</strong> {children}
  </p>
);

const Term = ({ children }: { children: React.ReactNode }) => (
  <strong className="font-medium text-ink">{children}</strong>
);

/**
 * The comparison's shape, drawn beside the sentence that describes it.
 *
 * Three manufacturers and three concepts is enough to show what is being crossed; the real
 * grid is ten by thirty and teaches nothing at a glance. The cells use the real placement
 * colours, so the drawing is the vocabulary the rest of the page then names — and the one
 * disagreeing row is picked out, because a grid where every row matches would illustrate
 * the format while hiding the point of it.
 *
 * Decorative and `aria-hidden`: the paragraph beside it makes the same claim in words.
 */
const SHAPE: Placement[][] = [
  ["4.3", "4.3", "4.3"],
  ["4.3", "4.5", "4.5"],
  ["4.4", "4.4", "4.4"],
];

const Scaffold = () => (
  <figure aria-hidden className="hidden lg:block">
    <table className="w-full border-collapse text-kicker">
      <thead>
        <tr className="font-mono text-ink-muted">
          <th className="pb-2 text-left font-normal">Concepts</th>
          <th colSpan={3} className="border-l border-rule pb-2 pl-2 text-left font-normal">
            Manufacturers
          </th>
        </tr>
        <tr className="border-b border-rule font-mono text-ink-muted">
          <th />
          {["A", "B", "C"].map((maker) => (
            <th key={maker} className="p-2 text-left font-normal">
              {maker}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {SHAPE.map((row, at) => {
          const diverges = new Set(row).size > 1;
          return (
            <tr key={at} className="border-b border-rule">
              <th
                scope="row"
                className={`py-2 pr-3 text-left font-normal ${diverges ? "text-accent" : "text-ink-muted"}`}
              >
                {diverges ? "they disagree" : "they agree"}
              </th>
              {row.map((placement, column) => (
                <td key={column} className="p-1">
                  <span
                    className={`block h-5 rounded-sheet border ${placementStyle(placement).className}`}
                  />
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
    <figcaption className="mt-3 text-kicker text-ink-muted">
      One row, one concept. One column, one manufacturer. A row whose colours differ is a
      finding.
    </figcaption>
  </figure>
);
