/** The HTTP seam. The UI never opens the database and never recomputes a comparison. */

import type { Placement } from "./placement";

const BASE = process.env.API_URL ?? "http://localhost:8000";

export type Evidence = {
  quote: string;
  section_code: string;
  char_start: number;
  char_end: number;
  source_url: string;
};

export type Cell = {
  product_external_id: string;
  placement: Placement;
  evidence: Evidence | null;
};

export type Row = { concept: string; diverges: boolean; cells: Cell[] };

/**
 * What one manufacturer says its product looks like, from section 3 of its own label.
 *
 * No photograph of any product in this corpus exists, so this is the only description
 * there is. `source_text` is the section verbatim and is always present: a description
 * the parser could not read is still published, never dropped.
 *
 * `length_mm` and `width_mm` are `null` on a label stating no dimensions — unknown, and
 * never a size borrowed from a product that does state one.
 */
export type Appearance = {
  source_text: string;
  shape: string | null;
  /** Colour words as the label writes them, cap first where it binds one. */
  colours: string[];
  length_mm: number | null;
  width_mm: number | null;
  imprints: string[];
  /** What could not be read, named. Empty means fully parsed, not nothing to say. */
  unparsed: string[];
};

export type ProductColumn = {
  external_id: string;
  name: string;
  /** Strength and form, e.g. "2.5mg Capsules"; null when the name does not carry both. */
  variant: string | null;
  ma_holder: string | null;
  /** The source's own id for the holder. Two spellings of one company share one id. */
  holder_id: number | null;
  /** The publisher's own revision date, from section 10 of the label. */
  revised: string | null;
  /** When the source last touched its record — a different question from `revised`. */
  listing_updated: string | null;
  atc_code: string | null;
  legal_status: string | null;
  ma_number: string | null;
  /** `null` means the label predates this field — not that the product is live. */
  discontinued: boolean | null;
  source_url: string | null;
  /** Sections read for THIS label. An absence in this column means absent from these. */
  scanned: string[];
  /** Section 3, when one has been collected. Never in `scanned` — it is not a placement. */
  appearance: Appearance | null;
};

/** The recall gap as two counts. Never a ratio — one substance cannot support one. */
export type ClauseCoverage = { classified: number; unclassified: number };

/** One §4.1 wording, and the manufacturers whose labels carry it. */
/** One indication, and how deeply the label itself nested it. */
export type IndicationStatement = { text: string; depth: number };

export type IndicationGroup = {
  statements: IndicationStatement[];
  manufacturers: string[];
};

export type Matrix = {
  substance_id: string;
  substance_name: string;
  products: ProductColumn[];
  rows: Row[];
  indications: IndicationGroup[];
  values: ValueSection[];
  clauses: ClauseCoverage;
};

/** Where one concept sits in one label, with the sentence that put it there. */
export type ProductConcept = {
  concept: string;
  placement: string;
  evidence: Evidence | null;
};

/** One value section as a single label states it. */
export type ValueStatement = { code: string; heading: string; text: string };

export type ProductDetail = {
  substance_id: string;
  substance_name: string;
  product: ProductColumn;
  siblings: ProductColumn[];
  indications: IndicationStatement[];
  concepts: ProductConcept[];
  values: ValueStatement[];
};

/** One disagreement, named but not evidenced — enough to preview a comparison. */
export type DivergencePreview = { concept: string; placements: string[] };

export type ValueGroup = {
  text: string;
  manufacturers: string[];
};

/** One value section across a substance's labels, grouped by the exact words used. */
export type ValueSection = {
  code: string;
  heading: string;
  groups: ValueGroup[];
  collected: number;
  total: number;
};

export type SubstanceSummary = {
  id: string;
  name: string;
  products: number;
  concepts: number;
  divergent: number;
  divergences: DivergencePreview[];
  /** Product names and MA holders on this substance's current labels, for searching. */
  labels: string[];
};

export type Heal = {
  status: string;
  created_at: string;
  promoted: boolean;
  failure_class: string | null;
  attempts: number;
  error: string | null;
};

export type CollectorHealth = {
  id: string;
  kind: string;
  source: string;
  baseline_captured_at: string | null;
  baseline_row_count: number | null;
  heals: Heal[];
};

/**
 * One mutation case on the controlled fixture site.
 *
 * A case that was never scored carries `null` for `field_accuracy` and
 * `non_regression_passed` — which is not the same as scoring zero, and the screen must
 * not render the two alike.
 */
export type BenchCase = {
  case_id: string;
  mutation: string;
  expected_signals: string[];
  caught_by: string | null;
  fired_kinds: string[];
  healed: boolean;
  field_accuracy: number | null;
  non_regression_passed: boolean | null;
  attempts: number;
  elapsed_s: number;
  completed_at: string | null;
};

export type BenchRun = { run_id: string; cases: BenchCase[] };

/**
 * A window of the stored section text with the quote's position inside it.
 *
 * `quote_start` and `quote_end` index into `text`, not into the section — so the span can
 * be marked without searching for it, and a quote that appears twice cannot be highlighted
 * in the wrong place.
 */
export type ContextWindow = {
  text: string;
  quote_start: number;
  quote_end: number;
  truncated_start: boolean;
  truncated_end: boolean;
  /** The whole section's length, so a quote can be placed within it rather than only shown. */
  section_length: number;
};

export type ConceptCell = Cell & { context: ContextWindow | null };

export type ConceptDetail = {
  substance_id: string;
  substance_name: string;
  concept: string;
  diverges: boolean;
  products: ProductColumn[];
  cells: ConceptCell[];
};

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json() as Promise<T>;
}

export const getSubstances = () => get<SubstanceSummary[]>("/substances");
export const getCollectors = () => get<CollectorHealth[]>("/collectors");
export const getBenchmark = () => get<BenchRun[]>("/benchmark");

/** `null` rather than a throw: an unknown product is a 404 the page renders. */
export async function getProduct(id: string): Promise<ProductDetail | null> {
  const response = await fetch(`${BASE}/products/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`/products/${id} responded ${response.status}`);
  return response.json() as Promise<ProductDetail>;
}

/** `null` rather than a throw: an unmatched concept is a 404 the page renders. */
export async function getConceptDetail(
  id: string,
  concept: string,
): Promise<ConceptDetail | null> {
  const path = `/substances/${encodeURIComponent(id)}/concepts/${encodeURIComponent(concept)}`;
  const response = await fetch(`${BASE}${path}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json() as Promise<ConceptDetail>;
}

/**
 * `null` rather than a throw: an uncollected substance is a 404 the page renders.
 *
 * Deliberately not folded into `get` — parameterising it for one caller's 404 would make
 * every other call site read worse. The cost is that changes to `get` must be repeated
 * here, which is why the two are adjacent.
 */
export async function getMatrix(id: string): Promise<Matrix | null> {
  const path = `/substances/${encodeURIComponent(id)}`;
  const response = await fetch(`${BASE}${path}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json() as Promise<Matrix>;
}

/**
 * How a manufacturer is named — the same rule the MCP server and CLI apply.
 *
 * Never falls back to the product name: that is a different kind of thing, and dropping
 * one into a column of company names is indistinguishable from a real holder.
 */
export const manufacturer = (product: ProductColumn) =>
  product.ma_holder ?? product.external_id;

/**
 * A column heading. One manufacturer may hold several strengths of the same substance,
 * so the variant leads: it is what distinguishes two otherwise identical columns.
 */
export const columnLabel = (product: ProductColumn) =>
  product.variant ? `${product.variant} · ${manufacturer(product)}` : product.name;

/** Concept ids are lexicon keys (`metabolic_acidosis`); every screen shows them the same way. */
export const conceptLabel = (concept: string) => concept.replace(/_/g, " ");
