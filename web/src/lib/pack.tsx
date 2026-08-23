import { placementStyle } from "./placement";

/** The bars drawn on the strip. Five placements exist, so one is always plain. */
const CELLS = 6;

/**
 * A pack, drawn rather than photographed.
 *
 * No photograph of any product in this corpus exists, so this must read as a schematic and
 * never as a picture of a real box: rules and type, no logo, no brand colour. The printed
 * strings are set in serif because they are the label's own words, which is the same rule
 * every quotation on the site follows; the form is mono, because it is derived from the
 * name by a rule anyone can re-run.
 *
 * Presentational only, and it takes strings rather than a product: the walkthrough draws
 * one from a script and the index draws six hundred from the corpus, and one drawn object
 * used in both is what makes the index the same thing the walkthrough taught.
 *
 * `form` is nullable because the strength and form are read off the product's own name,
 * and not every name carries both. An unstated form is left unstated — never guessed from
 * a product that does state one.
 */
export function Pack({
  product,
  substance,
  form,
  holder,
  name,
  placements = [],
  glyph,
  children,
}: {
  product: string;
  substance: string;
  form: string | null;
  holder: string;
  /** The view-transition name, when this pack is one that travels between views. */
  name?: string;
  /**
   * The distinct sections this label files anything in, strongest first.
   *
   * Drawn into the blister bars, so a shelf of packs can be read across. Colour carries
   * which section, and the count carries how many — position carries neither, because the
   * bars fill in order rather than reserving a slot per section. That is deliberate: a
   * reserved empty slot would assert that this label files nothing there, and a card
   * states no scope, so it is not entitled to make an absence claim.
   *
   * Empty by default — the walkthrough draws the same pack to teach what a box is, and
   * colouring it there would answer the question the next beat is about to ask.
   */
  placements?: string[];
  /** The dose this label describes, drawn. */
  glyph?: React.ReactNode;
  /** What this particular label says, when the pack is one of several being compared. */
  children?: React.ReactNode;
}) {
  return (
    <div
      className="w-full rounded-sheet border border-rule p-5"
      style={{ viewTransitionName: name }}
    >
      {/* A blister strip that reports. A filled cell is a section this label files
          something in; the remainder stay as drawn, in the plain rule the whole schematic
          uses — never the dashed border absence wears, because a card carries no concept
          and so has nothing it could be absent about. */}
      <div className="flex gap-1.5">
        {Array.from({ length: CELLS }).map((_, index) => {
          const placement = placements[index];
          return (
            <span
              key={index}
              title={placement ? placementStyle(placement).detail : undefined}
              className={`h-2 flex-1 rounded-sheet border ${
                placement ? placementStyle(placement).className : "border-rule"
              }`}
            >
              {placement ? (
                <span className="sr-only">{placementStyle(placement).label}</span>
              ) : null}
            </span>
          );
        })}
      </div>
      {/* Always a row, drawn or not: a shelf whose cards are a line taller when their
          label happens to describe its tablet is a shelf that reads as broken. An
          undrawable dose says so with a rule rather than a blank. */}
      {glyph !== undefined ? (
        <div className="mt-5 flex h-8 items-center text-ink-muted">
          {glyph ?? <span aria-label="No dose described">&mdash;</span>}
        </div>
      ) : null}
      <p className="mt-5 font-serif text-quote leading-tight text-ink">{product}</p>
      <p className="mt-1 font-serif text-body text-ink-muted">{substance}</p>
      {form ? <p className="mt-1 font-mono text-kicker text-ink-muted">{form}</p> : null}
      {children ? <div className="mt-3">{children}</div> : null}
      <p className="mt-5 border-t border-rule pt-4 font-serif text-meta text-ink-muted">
        {holder}
      </p>
    </div>
  );
}
