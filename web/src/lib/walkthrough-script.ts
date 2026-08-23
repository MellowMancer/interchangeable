/**
 * What the walkthrough teaches, and the label text it teaches from.
 *
 * Content rather than markup, for one reason: every string below is a verbatim slice of a
 * real document in the corpus, and keeping them together is what makes that checkable. The
 * product id beside each group is the whole audit trail — one query against
 * `data/interchangeable.db` re-verifies the file.
 *
 * Ibuprofen rather than the obvious paracetamol. Paracetamol was not in the corpus when
 * this was written and now is, so the reason is no longer availability: it is that these
 * six labels are already read, quoted and checked here, and every string below has been
 * round-tripped against the database. Moving the example is a data change, not a copy
 * change, and is only worth making for a better finding — not for a more familiar name.
 *
 * The hero is a brand a reader recognises on purpose. The box says Nurofen and the
 * substance is ibuprofen, and that gap is the first thing this has to explain.
 */

import type { Placement } from "@/lib/placement";

/** The label every beat is drawn from. EMC product 10261. */
export const HERO = {
  product: "Nurofen Meltlets 200mg",
  fullName: "Nurofen Meltlets 200mg Orodispersible Tablets",
  holder: "Reckitt Benckiser Healthcare (UK) Ltd",
  substance: "Ibuprofen",
  /** §3, as the label states its own form. */
  form: "Orodispersible tablet",
};

export type Part = {
  term: string;
  value: string;
  gloss: string;
};

/**
 * The three things printed on a box, and which of them the site is organised by.
 *
 * This is the beat the whole application rests on: a reader who cannot separate the brand
 * from the substance cannot read a comparison, because the comparison is *of* the brands
 * *within* a substance.
 */
export const PARTS: Part[] = [
  {
    term: "Substance",
    value: "Ibuprofen",
    gloss:
      "The active ingredient — the part that actually does something. Every comparison here is one substance.",
  },
  {
    term: "Product",
    value: "Nurofen Meltlets 200mg",
    gloss:
      "One company's version of that substance. A brand name names a product, never the drug inside it.",
  },
  {
    term: "Manufacturer",
    value: "Reckitt Benckiser Healthcare (UK) Ltd",
    gloss: "The company holding the licence. Each one writes its own label.",
  },
];

export type LabelSection = {
  code: string;
  /** The heading as the SmPC prints it. */
  heading: string;
  /** The same thing in words a reader already has. */
  plain: string;
  quote: string;
  /** Placeholder lines drawn around the quote, so a section reads as part of a document. */
  bars: number;
};

/**
 * The label, as the document it is.
 *
 * Every quote is verbatim from product 10261. The headings are the official SmPC ones, so
 * a reader who opens the real label recognises what they are looking at.
 *
 * §4.8 Undesirable effects is deliberately not here. It is a real part of a real label and
 * this site does not collect it, so promising it in an explanation would misdescribe the
 * scope of every absence claim downstream.
 */
export const LABEL: LabelSection[] = [
  {
    code: "4.1",
    heading: "Therapeutic indications",
    plain: "what it is for",
    quote: "For the relief of headache and migraine.",
    bars: 2,
  },
  {
    code: "4.3",
    heading: "Contraindications",
    plain: "who must not take it",
    quote: "Hypersensitivity to ibuprofen or any of the excipients in the product.",
    bars: 3,
  },
  {
    code: "4.4",
    heading: "Special warnings and precautions for use",
    plain: "how to take it carefully",
    quote:
      "Renal impairment as renal function may further deteriorate (see sections 4.3 and 4.8).",
    bars: 4,
  },
  {
    code: "4.5",
    heading: "Interaction with other medicinal products",
    plain: "what else changes it",
    quote:
      "Cardiac glycosides: NSAIDs may exacerbate cardiac failure, reduce GFR and increase plasma glycoside levels.",
    bars: 3,
  },
  {
    code: "4.6",
    heading: "Fertility, pregnancy and lactation",
    plain: "advice for pregnancy",
    quote: "See section 4.4 regarding female fertility.",
    bars: 2,
  },
  {
    code: "6.1",
    heading: "List of excipients",
    plain: "what is in it",
    quote: "Mannitol (E420)",
    bars: 2,
  },
];

export type Clause = {
  placement: Placement;
  concept: string;
  quote: string;
};

/**
 * One clause per placement, all from the same label.
 *
 * Same product, five sections: the point is that a placement is *where a thing is filed*,
 * not how bad it is — and that only becomes visible when the label is held constant.
 */
export const CLAUSES: Clause[] = [
  {
    placement: "4.3",
    concept: "hypersensitivity",
    quote: "Hypersensitivity to ibuprofen or any of the excipients in the product.",
  },
  {
    placement: "4.4",
    concept: "renal",
    quote:
      "Renal impairment as renal function may further deteriorate (see sections 4.3 and 4.8).",
  },
  {
    placement: "4.5",
    concept: "cardiac",
    quote:
      "Cardiac glycosides: NSAIDs may exacerbate cardiac failure, reduce GFR and increase plasma glycoside levels.",
  },
  {
    placement: "4.6",
    concept: "fertility",
    quote: "See section 4.4 regarding female fertility.",
  },
  {
    placement: "6.1",
    concept: "polyol",
    quote: "Mannitol (E420)",
  },
];

export type Sibling = {
  name: string;
  /**
   * What to call it on a pack this narrow.
   *
   * The same trim the roster's own cards make with `presentation()`: the pack names the
   * substance on its own line, so repeating it in the title costs the strength and form
   * that actually tell two of these apart. `name` stays as the checkable identity.
   */
  short: string;
  /**
   * The dose form, as the phrase §3 uses for it.
   *
   * Not always §3's opening words — McNeil's reads `100 mg / 5ml Oral Suspension` — so
   * this is the form named in that section, never a prefix of it and never our own
   * word for it.
   */
  form: string;
  holder: string;
  /** The holder at column width, for a matrix six columns wide. */
  maker: string;
};

/**
 * Six real ibuprofen labels, in the order the matrix reads.
 *
 * `MATRIX` gives one cell per label in this order, so the two must be edited together —
 * they are one table split in two only because a pack needs more about a product than a
 * column header does.
 */
export const SIBLINGS: Sibling[] = [
  {
    name: "Ibuprofen 200mg film-coated tablets",
    short: "200mg film-coated tablets",
    form: "Film-coated tablet",
    holder: "Aurobindo Pharma - Milpharm Ltd.",
    maker: "Milpharm",
  },
  {
    name: "Nurofen Meltlets 200mg",
    short: "Nurofen Meltlets 200mg",
    form: "Orodispersible tablet",
    holder: "Reckitt Benckiser Healthcare (UK) Ltd",
    maker: "Reckitt",
  },
  {
    name: "Ibuprofen 200mg Coated Tablets",
    short: "200mg Coated Tablets",
    form: "Coated tablet",
    holder: "Wockhardt UK Ltd",
    maker: "Wockhardt",
  },
  {
    name: "Anadin Joint Pain 200mg Tablets",
    short: "Anadin Joint Pain 200mg",
    form: "Coated tablet",
    holder: "Haleon UK Trading Limited",
    maker: "Haleon",
  },
  {
    name: "Calprofen Ibuprofen Suspension",
    short: "Calprofen Suspension",
    form: "Oral suspension",
    holder: "McNeil Products Ltd",
    maker: "McNeil",
  },
  {
    name: "Ibuprofen 200 mg Tablet",
    short: "200 mg Tablet",
    form: "Sugar-coated tablet",
    holder: "Flamingo Pharma (UK) Ltd",
    maker: "Flamingo",
  },
];

export type MatrixRow = {
  concept: string;
  /** Where each label in `SIBLINGS` files it, resolved by the same precedence the site uses. */
  placements: Placement[];
};

/**
 * The comparison itself, at the size it fits in a paragraph.
 *
 * Six real concepts across the six labels above, read straight out of the corpus — two the
 * labels agree on, four they do not, and one (`alcohol`) where some say nothing at all.
 * That last one matters: absence has to appear here as its own unfilled mark, because a
 * walkthrough that only ever shows colours teaches that every cell is a claim.
 *
 * `breastfeeding` is last because the beat after this one pulls that row out.
 */
export const MATRIX: MatrixRow[] = [
  { concept: "hypersensitivity", placements: ["4.3", "4.3", "4.3", "4.3", "4.3", "4.3"] },
  { concept: "elderly", placements: ["4.4", "4.4", "4.4", "4.4", "4.4", "4.4"] },
  { concept: "alcohol", placements: ["4.4", "absent", "absent", "absent", "4.4", "absent"] },
  { concept: "fertility", placements: ["4.6", "4.4", "4.4", "4.4", "4.4", "4.4"] },
  { concept: "breastfeeding", placements: ["4.4", "4.6", "4.6", "4.6", "4.6", "4.6"] },
  { concept: "paediatric", placements: ["4.3", "4.4", "4.4", "4.4", "4.4", "4.4"] },
];

/** The concept the six labels disagree about, and the row the last beats pull out. */
export const DIVERGENT_CONCEPT = "paediatric";

/**
 * The sentence behind one mark, with the offsets that make it checkable.
 *
 * Pfizer's, because theirs is the strongest of the three answers and the shortest to read.
 * The span is the tail of §4.3 — 1309 to 1364 of 1364 characters — which is worth showing
 * rather than asserting: a reader who can see *where* in a section a clause sits can tell
 * a heading from a buried aside.
 */
export const EVIDENCE = {
  placement: "4.3" as Placement,
  maker: "Milpharm",
  quote:
    "Ibuprofen is contraindicated in children below 20 kg body weight or younger than 6 years of age (see section 4.2).",
  charStart: 822,
  charEnd: 936,
  sectionLength: 936,
};

/**
 * What the corpus holds, for the beat that closes on it.
 *
 * Hardcoded like everything else here, and re-checkable in one call:
 *
 *   curl -s localhost:8000/substances | python3 -c "import json,sys; d=json.load(sys.stdin); \
 *     print(len(d), sum(s['products'] for s in d), sum(s['divergent'] for s in d), \
 *           sum(1 for s in d if s['divergent'] > 0))"
 *
 * `everySubstanceDiverges` is the one worth stating out loud: it is not that some drugs
 * turn out to disagree, it is that every substance collected so far has at least one
 * concept its manufacturers file differently.
 */
export const CORPUS = {
  substances: 80,
  /** Products whose current label is stored — the ones the index can actually open. */
  products: 744,
  findings: 1007,
  everySubstanceDiverges: true,
};

/**
 * Labels collected for ibuprofen, of 119 products known.
 *
 * Six of these eight are shown, because `.animate-deal` stops staggering at six and a
 * longer sequence reads as a page still loading. The count is stated rather than implied
 * so the list never reads as the whole comparison.
 */
export const COLLECTED_LABELS = 8;
