/**
 * How a `Placement` is rendered.
 *
 * `ABSENT` must never be styleable as a mild warning: a reader who cannot tell "this
 * manufacturer warns about it" from "we did not find it in the sections we read" is being
 * told something the data does not support. So absence is the only greyed, dashed,
 * unfilled cell, and it is the only one whose label is a sentence rather than a word.
 */

export type PlacementStyle = { label: string; detail: string; className: string };

const STYLES: Record<string, PlacementStyle> = {
  "4.3": {
    label: "Contraindicated",
    detail: "Section 4.3 — contraindications",
    className: "bg-red-600 text-white border-red-700",
  },
  "4.4": {
    label: "Warning",
    detail: "Section 4.4 — warnings and precautions",
    className: "bg-amber-400 text-amber-950 border-amber-500",
  },
  "4.5": {
    label: "Interaction",
    detail: "Section 4.5 — interactions",
    className: "bg-sky-500 text-white border-sky-600",
  },
  "4.6": {
    label: "Pregnancy",
    detail: "Section 4.6 — pregnancy and lactation",
    className: "bg-violet-500 text-white border-violet-600",
  },
};

const ABSENT: PlacementStyle = {
  label: "Not in scanned sections",
  detail: "Not found in the sections collected — not evidence the label omits it",
  className:
    "bg-transparent text-slate-500 border-slate-400 border-dashed dark:text-slate-400",
};

export const placementStyle = (placement: string): PlacementStyle =>
  STYLES[placement] ?? ABSENT;

export const PLACEMENT_LEGEND = [...Object.entries(STYLES), ["absent", ABSENT] as const];
