/**
 * Which finding to lead with, and how to say it.
 *
 * Every sentence this module produces is generated from the API response. Nothing here
 * names a substance, a manufacturer or a concept, so the landing screen retargets itself
 * as the corpus grows rather than going quietly stale.
 */

import {
  manufacturer,
  type DivergencePreview,
  type Evidence,
  type ProductColumn,
  type Row,
  type SubstanceSummary,
} from "./api";
import type { Placement } from "./placement";

/** A clause the lexicon did not match. Published as a recall gap, never a clinical concept. */
export const UNCLASSIFIED = "unclassified";

/**
 * How binding each placement is, most binding first.
 *
 * Used only to measure the distance between two placements in one row — the gap between
 * a contraindication and an interaction is the disagreement worth leading with.
 */
const BINDING_ORDER: Record<Placement, number> = {
  "4.3": 0,
  "4.4": 1,
  "4.5": 2,
  "4.6": 3,
  "6.1": 4,
  absent: 5,
};

const rank = (placement: string) => BINDING_ORDER[placement as Placement] ?? BINDING_ORDER.absent;


/** The substance to land on: most disagreements first, then most manufacturers. */
export const featuredSubstance = (substances: SubstanceSummary[]): SubstanceSummary | undefined =>
  substances
    .filter((substance) => substance.products > 0)
    .sort((a, b) => b.divergent - a.divergent || b.products - a.products)[0];

/**
 * Divergent rows, strongest finding first.
 *
 * A row containing `absent` is ranked below every row without one. Absence means the
 * concept was not found in the sections read for that manufacturer, which may only mean
 * it sits in a section nobody collected — so a one-sided row is weaker evidence of real
 * disagreement than two manufacturers filing the same fact under different sections.
 * Within each group the widest gap in binding force comes first.
 */
/**
 * How strong a finding a set of placements represents, strongest first.
 *
 * One rule, applied to matrix rows and to the roster's previews alike, so the concept a
 * card advertises is the concept the comparison leads with.
 */
export function strengthOf(placements: string[]): [number, number] {
  const ranks = placements.map(rank);
  const hasAbsent = placements.includes("absent") ? 1 : 0;
  return [hasAbsent, -(Math.max(...ranks) - Math.min(...ranks))];
}

const byStrength = (a: string[], b: string[]) => {
  const [absentA, spreadA] = strengthOf(a);
  const [absentB, spreadB] = strengthOf(b);
  return absentA - absentB || spreadA - spreadB;
};

export function rankedDivergences(rows: Row[]): Row[] {
  return rows
    .filter((row) => row.diverges && row.concept !== UNCLASSIFIED)
    .sort(
      (a, b) =>
        byStrength(
          a.cells.map((c) => c.placement),
          b.cells.map((c) => c.placement),
        ) || a.concept.localeCompare(b.concept),
    );
}

/** The roster's previews, strongest first and with the recall gap left out. */
export const rankedPreviews = (summary: SubstanceSummary): DivergencePreview[] =>
  summary.divergences
    .filter((preview) => preview.concept !== UNCLASSIFIED)
    .sort((a, b) => byStrength(a.placements, b.placements) || a.concept.localeCompare(b.concept));

/** Divergent, agreeing and the recall gap, kept apart because they are different claims. */
export function partition(rows: Row[]) {
  return {
    divergent: rankedDivergences(rows),
    agreeing: rows.filter((row) => !row.diverges && row.concept !== UNCLASSIFIED),
    unclassified: rows.find((row) => row.concept === UNCLASSIFIED) ?? null,
  };
}

/** The four-digit year a publisher's revision string ends in, when it carries one. */
export const revisionYear = (revised: string | null): number | null => {
  const match = revised?.match(/\b(\d{4})\b/);
  return match ? Number(match[1]) : null;
};

/** The sections read, when every label shares one scope; `null` when they differ. */
export function sharedScanned(products: ProductColumn[]): string[] | null {
  const scopes = new Set(products.map((product) => product.scanned.join(", ")));
  return scopes.size === 1 ? (products[0]?.scanned ?? []) : null;
}



/**
 * Which other manufacturers state this in byte-identical words, per product.
 *
 * An annotation rather than a merge. Generic SmPCs are frequently copied verbatim between
 * holders, and saying so is worth doing — but two labels carrying the same sentence carry
 * it at their own offsets, in their own section, of their own length. Collapsing them into
 * one block would show one label's provenance and silently drop the other's.
 *
 * Exact string equality, never similarity: "these two say the same thing" is only a safe
 * claim when the bytes match, and a near-match is a difference worth reading.
 */
export function identicalWording(
  cells: { product_external_id: string; evidence: Evidence | null }[],
  products: ProductColumn[],
): Map<string, string[]> {
  const byId = new Map(products.map((product) => [product.external_id, product]));
  const name = (id: string) => {
    const product = byId.get(id);
    return product ? manufacturer(product) : id;
  };

  const byQuote = new Map<string, string[]>();
  for (const cell of cells) {
    const quote = cell.evidence?.quote;
    if (!quote) continue;
    byQuote.set(quote, [...(byQuote.get(quote) ?? []), cell.product_external_id]);
  }

  const shared = new Map<string, string[]>();
  for (const ids of byQuote.values()) {
    if (ids.length < 2) continue;
    for (const id of ids) shared.set(id, ids.filter((other) => other !== id).map(name));
  }
  return shared;
}


/** One distinct wording, and every product whose label carries it. */
export type WordingGroup<T> = {
  /** The shared quote, or `null` when this group is an absence. */
  quote: string | null;
  placement: string;
  cells: T[];
};

/**
 * Cells grouped by the exact words their labels use.
 *
 * At three manufacturers this is a footnote; at ten it is the only readable structure.
 * Generics are frequently copied verbatim between holders, so ten labels are commonly two
 * or three distinct texts, and printing ten near-identical blocks buries the one that
 * differs.
 *
 * Grouping is exact string equality, never similarity — "these say the same thing" is only
 * safe when the bytes match. Absences group by the sections actually read as well, because
 * two absences over different scanned sets are different claims.
 *
 * Each member keeps its own offsets: the same sentence sits at different indices in
 * different labels, and a group that showed one member's provenance would drop the rest.
 */
export function groupByWording<
  T extends { product_external_id: string; placement: string; evidence: Evidence | null },
>(cells: T[], products: ProductColumn[]): WordingGroup<T>[] {
  const scannedOf = new Map(products.map((p) => [p.external_id, p.scanned.join(",")]));
  const groups = new Map<string, WordingGroup<T>>();

  for (const cell of cells) {
    const quote = cell.evidence?.quote ?? null;
    const key =
      quote === null
        ? `absent|${scannedOf.get(cell.product_external_id) ?? ""}`
        : `${cell.placement}|${quote}`;

    const existing = groups.get(key);
    if (existing) existing.cells.push(cell);
    else groups.set(key, { quote, placement: cell.placement, cells: [cell] });
  }

  return Array.from(groups.values()).sort(
    (a, b) => rank(a.placement) - rank(b.placement) || b.cells.length - a.cells.length,
  );
}
