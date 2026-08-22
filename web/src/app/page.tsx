import Link from "next/link";
import { getMatrix, getSubstances, manufacturer, type Matrix, type ProductColumn } from "@/lib/api";
import { DosageGlyph, undrawnBecause } from "@/lib/appearance";
import { featuredSubstance } from "@/lib/finding";
import { Roster } from "@/lib/roster";

/**
 * The roster, and what a comparison of each substance would show.
 *
 * A card carries its strongest disagreements rather than only a count, so the choice of
 * what to open is made on the finding rather than on the name.
 *
 * The list itself is handed to `Roster`, which filters it as the reader types. That is
 * the one place in the application that runs in the browser; everything here, including
 * the fetch, still happens on the server.
 */
export default async function Home({ searchParams }: PageProps<"/">) {
  const { q } = await searchParams;
  const query = (Array.isArray(q) ? q[0] : q)?.trim() ?? "";

  const substances = await getSubstances();
  // One extra read, for the hero: the roster carries names but not what a tablet looks
  // like, and the scene is two boxes rather than two strings.
  //
  // The substance whose labels disagree most, so the pair on show is a real pair — and
  // never at the cost of the page: the roster is the reason to be here, so a failing
  // matrix costs the decoration, not the list.
  const featured = featuredSubstance(substances);
  const staged = featured && featured.divergent > 0 ? await staged_for(featured.id) : null;

  return (
    <div className="space-y-12">
      <header className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)]">
        <div className="space-y-5">
        {/* Its own measure: inside the prose column a display size wraps to three uneven
            lines, and the strapline is the one thing on the page that must land cleanly. */}
        <h1 className="max-w-3xl font-serif text-display font-normal text-balance">
          Same drug. Different manufacturer. Different label.
        </h1>
        <p className="max-w-prose text-ink-muted">
          When a pharmacy dispenses a generic it substitutes whichever manufacturer&apos;s
          version is on the shelf, and everyone assumes same drug, same information.{" "}
          <span className="text-ink">Interchangeable?</span> compares the UK Summaries of
          Product Characteristics of every authorised product sharing an active substance
          and shows where the manufacturers disagree — with the quoted text behind every
          claim.
        </p>
        <p className="max-w-prose text-meta text-ink-muted">
          The question mark is deliberate. This asks whether these products really are
          interchangeable; it does not assert that they are not.
        </p>
        {/* Offered before the list, not buried in the nav: a grid of coloured badges is
            guessable, and the likeliest guess — that an unmarked cell means the label
            omits something — is the one reading this project exists to prevent. */}
        <Link
          href="/reading"
          className="inline-flex items-baseline gap-2 border-b border-accent pb-1 text-meta text-accent hover:border-ink hover:text-ink"
        >
          New here? Read how to read this first
          <span aria-hidden>→</span>
        </Link>
        </div>
        <SameDrug matrix={staged} />
      </header>

      <Roster substances={substances} query={query} />
    </div>
  );
}



/**
 * The proposition, staged.
 *
 * Two real labels of one substance, drawn as they describe themselves, with a not-equals
 * between them. Nothing is invented — the products, the manufacturers and the tablets all
 * come from the corpus, so the scene changes as it grows.
 *
 * Rotated in a perspective scene rather than given a drawn shadow: the point is two boxes
 * on a counter, and depth says that faster than prose can. Decorative and `aria-hidden`;
 * the strapline beside it makes the same claim in words.
 */
function SameDrug({ matrix }: { matrix: Matrix | null }) {
  const drawable = (matrix?.products ?? []).filter(
    (product) => product.appearance && undrawnBecause(product.appearance).length === 0,
  );
  // One card per holder: two strengths from one manufacturer, shown side by side as the
  // page's illustration of "different manufacturer", would be neither.
  const seen = new Set<string>();
  const distinct = drawable.filter((product) => {
    const holder = manufacturer(product);
    if (seen.has(holder)) return false;
    seen.add(holder);
    return true;
  });
  if (!matrix || distinct.length < 2) return null;
  const [first, second] = distinct;

  return (
    <div aria-hidden className="stage hidden items-center justify-center gap-6 lg:flex">
      <LabelCard substance={matrix.substance_name} product={first} side="left" />
      <LabelCard substance={matrix.substance_name} product={second} side="right" />
    </div>
  );
}

const LabelCard = ({
  substance,
  product,
  side,
}: {
  substance: string;
  product: ProductColumn;
  side: "left" | "right";
}) => (
  <article
    className={`stage-card w-40 shrink-0 space-y-2 rounded-sheet border border-rule bg-paper p-4 shadow-[0_18px_40px_-24px_rgba(0,0,0,0.55)] ${
      side === "left" ? "stage-left" : "stage-right"
    }`}
  >
    <p className="font-mono text-kicker tracking-widest text-ink-muted uppercase">{substance}</p>
    {product.appearance && (
      <span className="flex h-8 items-center">
        <DosageGlyph appearance={product.appearance} />
      </span>
    )}
    <p className="truncate font-serif text-body">{presentation(substance, product)}</p>
    <p className="truncate font-mono text-kicker text-ink-muted">{manufacturer(product)}</p>
  </article>
);


/**
 * What to call a product on a card the width of a box.
 *
 * `variant` is the strength and form and is what one wants — but it is null whenever the
 * name does not carry both, and falling back to the whole name put "Prednisolone 5…" on a
 * card beside "5mg Tablets". Stripping the substance the card already names leaves the two
 * reading alike.
 */
function presentation(substance: string, product: ProductColumn): string {
  if (product.variant) return product.variant;
  const stripped = product.name.replace(new RegExp(`^${substance}\\s*`, "i"), "").trim();
  return stripped || product.name;
}

/** The hero's matrix, or nothing. A decorative read must not be able to fail the page. */
async function staged_for(id: string): Promise<Matrix | null> {
  try {
    return await getMatrix(id);
  } catch {
    return null;
  }
}
