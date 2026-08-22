/**
 * What each manufacturer's product looks like, drawn from its own label.
 *
 * No product photograph of any UK generic in this corpus exists — checked across EMC,
 * MHRA, dm+d, DailyMed, the manufacturers' own sites and UK pharmacies. What every label
 * does carry is section 3, the holder's regulated description of the object. Every glyph
 * here is generated from that text and nothing else.
 *
 * **It is a drawing, and it has to read as one.** Flat fills, one hairline outline, no
 * gradient and no shadow, with the sentence it came from printed beside it. A reader who
 * takes a drawn capsule for a photograph of the real product has been told something the
 * data does not support.
 *
 * Nothing is invented to fill a gap. A description whose colour or outline could not be
 * read is published with its text and no drawing — the same rule `unclassified` obeys for
 * clauses, because a visible gap beats a clean-looking result that quietly dropped what it
 * could not parse.
 */

import Link from "next/link";
import { manufacturer, type Appearance, type ProductColumn } from "./api";

/**
 * Colour word to fill. The product's colour vocabulary, and the only place it lives.
 *
 * Deliberately not the interface palette: every UI colour is a `light-dark()` pair in
 * `globals.css` and repaints with the theme, while these name a physical object and must
 * not. The hex sits in `globals.css` with everything else; this maps the label's word to
 * it.
 *
 * A word absent here returns nothing and the product falls to described-but-not-drawn.
 * There is no default fill, because a default fill is a claim about the product.
 */
const PRODUCT_COLOURS: Record<string, string> = {
  white: "var(--pc-white)",
  ivory: "var(--pc-ivory)",
  cream: "var(--pc-cream)",
  beige: "var(--pc-beige)",
  yellow: "var(--pc-yellow)",
  orange: "var(--pc-orange)",
  red: "var(--pc-red)",
  pink: "var(--pc-pink)",
  brown: "var(--pc-brown)",
  green: "var(--pc-green)",
  blue: "var(--pc-blue)",
  purple: "var(--pc-purple)",
  violet: "var(--pc-violet)",
  grey: "var(--pc-grey)",
  black: "var(--pc-black)",
};

/**
 * What a modifier does to the colour it qualifies.
 *
 * One entry per modifier rather than a token per combination: "pale red" and "dark brown"
 * would otherwise need a declaration each, and a label using a pairing nobody anticipated
 * would go undrawn for no good reason.
 */
const MODIFIERS: Record<string, string> = {
  "pale": "var(--pc-tint) 45%",
  "light": "var(--pc-tint) 45%",
  "off": "var(--pc-tint) 45%",
  "dark": "var(--pc-shade) 35%",
  "deep": "var(--pc-shade) 35%",
  "bright": "var(--pc-tint) 0%",
};

/** Why a description was not drawn, in the reader's words rather than the parser's. */
const NOT_DRAWN: Record<string, string> = {
  shape: "no outline stated",
  colour: "no colour recognised",
};

const CAP = "M60 13 H30 A15 15 0 0 0 30 43 H60 Z";
const BODY = "M60 13 H90 A15 15 0 0 1 90 43 H60 Z";

/** The outlines that can be drawn. A shape not here is one the label did not state. */
const SHAPES: Record<string, (fills: string[]) => React.ReactNode> = {
  capsule: (fills) => (
    <>
      <path d={CAP} style={{ fill: fills[0] }} />
      <path d={BODY} style={{ fill: fills[1] ?? fills[0] }} />
    </>
  ),
  oblong: (fills) => <rect x={25} y={16} width={70} height={24} rx={12} style={{ fill: fills[0] }} />,
  round: (fills) => <circle cx={60} cy={28} r={20} style={{ fill: fills[0] }} />,
};

/** One colour word as a fill, or `null` when this build does not know it. */
function fillFor(word: string): string | null {
  const parts = word.split(" ");
  const base = PRODUCT_COLOURS[parts[parts.length - 1]];
  if (!base) return null;
  if (parts.length === 1) return base;
  const shift = MODIFIERS[parts[0]];
  return shift ? `color-mix(in srgb, ${base}, ${shift})` : null;
}

/** Every colour as a fill, or `null` if any one of them is unknown here. */
function fillsFor(appearance: Appearance): string[] | null {
  const found = appearance.colours.map(fillFor);
  return found.length > 0 && found.every((fill) => fill !== null) ? (found as string[]) : null;
}

/**
 * Why this description is not drawn — empty when it is.
 *
 * The API's own reasons plus the ones only this build can know: a colour word the map
 * above does not carry is exactly as undrawable as a colour the parser never found, and
 * both must reach the reader rather than one silently becoming a default fill.
 */
export function undrawnBecause(appearance: Appearance): string[] {
  const reasons = new Set(appearance.unparsed);
  if (!SHAPES[appearance.shape ?? ""]) reasons.add("shape");
  if (!fillsFor(appearance)) reasons.add("colour");
  return Array.from(reasons, (reason) => NOT_DRAWN[reason] ?? reason);
}

/**
 * The drawing itself, or nothing when the label does not state enough to draw.
 *
 * Fixed proportions, never scaled by the stated dimensions. Two of the three labels in
 * this corpus state no size at all, so drawing one to scale beside two drawn to a guess
 * would make the guess look like a measurement.
 *
 * Left-aligned in its column rather than centred, so a drawing sits directly above the
 * text it was generated from instead of floating away from it.
 */
export function DosageGlyph({ appearance }: { appearance: Appearance }) {
  const fills = fillsFor(appearance);
  const draw = SHAPES[appearance.shape ?? ""];
  if (!fills || !draw) return null;

  return (
    <svg
      viewBox="0 0 120 56"
      preserveAspectRatio="xMinYMid meet"
      role="img"
      aria-label={`Schematic drawing generated from this label's description: ${appearance.source_text}`}
      className="h-14 w-full stroke-ink-muted"
      strokeWidth={1.5}
    >
      {draw(fills)}
    </svg>
  );
}

/**
 * The placeholder for a description this build cannot draw.
 *
 * Deliberately **not** a member of `SHAPES` and **not** a colour from `PRODUCT_COLOURS`.
 * It is drawn in an interface token that repaints with the theme, because every product
 * colour names a physical object: a grey bar filled with `--pc-grey` would read as a
 * drawn grey oblong tablet, which is a claim about the product rather than the absence of
 * one. It is also drawn short, faint, and without the hairline outline every real glyph
 * carries, so it cannot be mistaken for one at a glance.
 *
 * The reasons move to the metadata line rather than disappearing. The gap stays visible —
 * it just stops printing a sentence where a picture belongs.
 */
function NotDrawn({ reasons }: { reasons: string[] }) {
  return (
    <svg
      viewBox="0 0 120 56"
      preserveAspectRatio="xMinYMid meet"
      role="img"
      aria-label={`Not drawn — ${reasons.join(", ")}. The label's own description is printed beside it.`}
      className="h-14 w-full text-ink-muted"
    >
      <rect x={25} y={23} width={34} height={10} rx={5} fill="currentColor" opacity={0.45} />
    </svg>
  );
}

/**
 * Every manufacturer's product side by side — the point of the whole comparison, made
 * literal.
 *
 * Renders nothing at all when no label has a section 3 stored. An empty frame would
 * advertise a gap in the corpus as a gap in the labelling, and the collector has simply
 * not been asked for it yet.
 *
 * Labels that do carry one are shown; labels that do not are counted rather than given a
 * placeholder, so the reader can see the strip is partial without a row of empty boxes.
 */
export function AppearanceStrip({ products }: { products: ProductColumn[] }) {
  const described = products.filter((product) => product.appearance);
  if (described.length === 0) return null;

  return (
    <section className="space-y-6 border-t border-rule pt-10">
      <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
        What each manufacturer says its product looks like
      </h2>

      <ul className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        {described.map((product) => (
          <DescribedProduct key={product.external_id} product={product} />
        ))}
      </ul>

      <p className="max-w-prose text-meta text-ink-muted">
        Each drawing is generated from the section 3 text printed beside it — the
        manufacturer&apos;s own regulated description of the product. It is a schematic
        drawing, not a photograph, and not to scale: no photograph of any product in this
        corpus exists. Only what the text states is drawn, so a label giving no dimensions
        is drawn at no particular size.
        {described.length < products.length && (
          <> {described.length} of {products.length} labels have one collected.</>
        )}
      </p>
    </section>
  );
}

function DescribedProduct({ product }: { product: ProductColumn }) {
  const appearance = product.appearance;
  if (!appearance) return null;
  const reasons = undrawnBecause(appearance);

  return (
    <li className="space-y-3">
      <div className="flex h-14 items-center">
        {reasons.length === 0 ? (
          <DosageGlyph appearance={appearance} />
        ) : (
          <NotDrawn reasons={reasons} />
        )}
      </div>

      <h3 className="font-medium">{manufacturer(product)}</h3>

      <blockquote className="border-l-2 border-rule pl-4 font-serif text-meta">
        &ldquo;{appearance.source_text}&rdquo;
      </blockquote>

      <p className="font-mono text-kicker text-ink-muted">
        §3 · pharmaceutical form
        {appearance.length_mm !== null && appearance.width_mm !== null && (
          <> · {appearance.length_mm} × {appearance.width_mm} mm as stated</>
        )}
        {appearance.imprints.length > 0 && <> · imprinted {appearance.imprints.join(", ")}</>}
        {reasons.length > 0 && <> · not drawn: {reasons.join(", ")}</>}
      </p>
    </li>
  );
}

/**
 * The products at a glance, for a header rather than a section of its own.
 *
 * The same drawing as `AppearanceStrip`, without the §3 text beside it. On the comparison
 * screen the question is "what am I looking at" — seven labels, and whether they are
 * capsules or tablets — while the wording that justifies each drawing belongs with the
 * evidence, where a reader has already chosen to look closely.
 *
 * A separate component rather than a flag on the other: the two answer different
 * questions, and one of them must never lose the text it is derived from.
 */
export function AppearanceRail({ products }: { products: ProductColumn[] }) {
  const described = products.filter((product) => product.appearance);
  if (described.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="font-mono text-kicker tracking-widest text-ink-muted uppercase">
        Quick links
      </h2>

      {/* One column: this sits in a narrow column beside the indications, and the caller
          passes only the labels the comparison draws, so it is a short list rather than
          the six hundred pixels ten products made of it. */}
      <ul className="space-y-2">
        {described.map((product) => {
          const appearance = product.appearance;
          if (!appearance) return null;
          const undrawn = undrawnBecause(appearance);
          return (
            <li key={product.external_id}>
              <Link
                href={`/products/${product.external_id}`}
                className="flex items-center gap-3 rounded-sheet py-1 hover:bg-rule/40 hover:text-accent"
              >
              <span className="flex h-8 w-20 shrink-0 items-center">
                {undrawn.length === 0 ? (
                  <DosageGlyph appearance={appearance} />
                ) : (
                  // The same mark an unfilled cell carries elsewhere. The reason stays
                  // reachable rather than printed, so a rail of drawings is not broken up
                  // by a sentence.
                  <span title={undrawn.join(", ")} className="w-full text-center font-mono text-ink-muted">
                    <span aria-hidden>&mdash;</span>
                    <span className="sr-only">not drawn: {undrawn.join(", ")}</span>
                  </span>
                )}
              </span>
              <span className="min-w-0 text-meta">
                <span className="block truncate">{manufacturer(product)}</span>
                <span className="block truncate font-mono text-kicker text-ink-muted">
                  {product.variant ?? product.name}
                </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="text-kicker text-ink-muted">
        Drawn from each label&apos;s physical description. Actual tablet may vary.
      </p>
    </section>
  );
}
