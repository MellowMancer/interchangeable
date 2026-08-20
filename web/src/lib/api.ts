/** The HTTP seam. The UI never opens the database and never recomputes a comparison. */

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
  placement: string;
  evidence: Evidence | null;
};

export type Row = { concept: string; diverges: boolean; cells: Cell[] };

export type ProductColumn = {
  external_id: string;
  name: string;
  ma_holder: string | null;
  revised: string | null;
  source_url: string | null;
};

export type Matrix = {
  substance_id: string;
  scanned: string[];
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

/** `null` rather than a throw: an uncollected substance is a 404 the page renders. */
export async function getMatrix(id: string): Promise<Matrix | null> {
  const response = await fetch(`${BASE}/substances/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`/substances/${id} responded ${response.status}`);
  return response.json() as Promise<Matrix>;
}

/** How a manufacturer is named in the UI. Falls back so a column is never blank. */
export const manufacturer = (product: ProductColumn) =>
  product.ma_holder ?? product.name ?? product.external_id;
