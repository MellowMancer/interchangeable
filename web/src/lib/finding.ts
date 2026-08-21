/**
 * Which finding to lead with, and how to say it.
 *
 * Every sentence this module produces is generated from the API response. Nothing here
 * names a substance, a manufacturer or a concept, so the landing screen retargets itself
 * as the corpus grows rather than going quietly stale.
 */

import {
  manufacturer,
  type Cell,
  type DivergencePreview,
  type Evidence,
  type Matrix,
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

/** "A", "A and B", "A, B and C" — an Oxford-comma-free list, as UK usage expects. */
function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

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

/**
 * Who placed this where, in one sentence.
 *
 * Section numbers rather than glosses: the spectrum beside this names what each section
 * is, so spelling out "an absolute contraindication" again only repeats the picture.
 *
 * Absence gets its own clause and never the verb "records" — a manufacturer did not
 * record an absence, we failed to find the concept in what we read. The sections that
 * were read are named in the spectrum row for that label, which sits directly below.
 */
export function placementSummary(row: Row, products: ProductColumn[]): string {
  const byId = new Map(products.map((product) => [product.external_id, product]));
  const name = (cell: Cell) => {
    const product = byId.get(cell.product_external_id);
    return product ? manufacturer(product) : cell.product_external_id;
  };

  const placed = new Map<string, string[]>();
  const missing: string[] = [];
  for (const cell of row.cells) {
    if (cell.placement === "absent") missing.push(name(cell));
    else placed.set(cell.placement, [...(placed.get(cell.placement) ?? []), name(cell)]);
  }

  const clauses = Array.from(placed.entries())
    .sort(([a], [b]) => rank(a) - rank(b))
    .map(([placement, names], index) =>
      index === 0
        ? `${joinNames(names)} files this in §${placement}`
        : `${joinNames(names)} in §${placement}`,
    );

  if (missing.length) {
    clauses.push(`not found for ${joinNames(missing)} in the sections read`);
  }
  return `${clauses.join("; ")}.`;
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

/** The strongest finding in a matrix, or `null` when the manufacturers agree throughout. */
export const featuredRow = (matrix: Matrix): Row | null => rankedDivergences(matrix.rows)[0] ?? null;


/** One position, and every manufacturer whose label states it in exactly the same words. */
export type EvidenceGroup = {
  placement: string;
  cells: Cell[];
  products: ProductColumn[];
  /** The shared evidence, or `null` when this group is an absence. */
  evidence: Evidence | null;
  /** True when more than one manufacturer is here with byte-identical text. */
  shared: boolean;
};

/**
 * Manufacturers whose labels say the identical thing, shown once.
 *
 * Generic SmPCs are frequently copied verbatim between holders, so rendering each in
 * full repeats hundreds of characters and buries the one label that differs. Grouping is
 * on exact string equality, never similarity: "these two say the same thing" is only a
 * safe claim when the bytes match, and a near-match is a difference worth reading.
 *
 * Absences are grouped by the sections actually read as well as by placement, because
 * two absences over different scanned sets are different claims.
 */
export function groupEvidence(row: Row, products: ProductColumn[]): EvidenceGroup[] {
  const byId = new Map(products.map((product) => [product.external_id, product]));
  const groups = new Map<string, EvidenceGroup>();

  for (const cell of row.cells) {
    const product = byId.get(cell.product_external_id);
    const key =
      cell.placement === "absent"
        ? `absent|${(product?.scanned ?? []).join(",")}`
        : `${cell.placement}|${cell.evidence?.quote ?? ""}`;

    const existing = groups.get(key);
    if (existing) {
      existing.cells.push(cell);
      if (product) existing.products.push(product);
      existing.shared = true;
    } else {
      groups.set(key, {
        placement: cell.placement,
        cells: [cell],
        products: product ? [product] : [],
        evidence: cell.evidence,
        shared: false,
      });
    }
  }

  return Array.from(groups.values()).sort((a, b) => rank(a.placement) - rank(b.placement));
}

/** "A", "A and B", "A, B and C" — exported so a group can name its manufacturers. */
export const listNames = joinNames;
