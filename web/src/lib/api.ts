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
};

export type Matrix = {
  substance_id: string;
  substance_name: string;
  products: ProductColumn[];
  rows: Row[];
};

export type SubstanceSummary = {
  id: string;
  name: string;
  products: number;
  concepts: number;
  divergent: number;
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

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json() as Promise<T>;
}

export const getSubstances = () => get<SubstanceSummary[]>("/substances");
export const getCollectors = () => get<CollectorHealth[]>("/collectors");

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
