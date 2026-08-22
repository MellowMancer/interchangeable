import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getConceptDetail,
} from "@/lib/api";
import { UNCLASSIFIED } from "@/lib/finding";
import Link from "next/link";
import { Evidence } from "@/lib/evidence";

/**
 * Why each manufacturer's cell says what it says, in the label's own words.
 *
 * The quote is shown inside the text that surrounds it, with the matched span marked.
 * That is the difference between asserting a quote was sliced from the section at those
 * offsets and letting a reader see that it was — which is the claim the whole project
 * rests on.
 *
 * Stacked full width rather than tiled: these are clinical sentences, and a three-column
 * grid squeezes them to a measure nobody can read.
 */
export async function generateMetadata({
  params,
}: PageProps<"/substances/[id]/concepts/[concept]">): Promise<Metadata> {
  const { id, concept } = await params;
  const detail = await getConceptDetail(id, concept);
  if (!detail) return { title: "Not found" };
  return { title: `${conceptLabel(detail.concept)} · ${detail.substance_name}` };
}

export default async function ConceptPage({
  params,
}: PageProps<"/substances/[id]/concepts/[concept]">) {
  const { id, concept } = await params;
  const detail = await getConceptDetail(id, concept);
  if (!detail) notFound();

  const isRecallGap = concept === UNCLASSIFIED;

  return (
    <article className="space-y-10">
      <header className="space-y-4">
        <Link
          href={`/substances/${id}`}
          className="font-mono text-kicker text-ink-muted hover:text-ink"
        >
          ← {detail.substance_name}
        </Link>
        <h1 className="font-serif text-title font-normal tracking-tight">
          {conceptLabel(detail.concept)}
        </h1>
        <p className="max-w-prose text-ink-muted">
          {isRecallGap
            ? "Clauses that matched no concept in the lexicon — recorded and shown rather than dropped."
            : detail.diverges
              ? "These manufacturers do not place this the same way."
              : "Every manufacturer places this the same way."}
        </p>
      </header>

      <Evidence detail={detail} />

    </article>
  );
}
