import Link from "next/link";
import { notFound } from "next/navigation";
import { columnLabel, conceptLabel, getMatrix, getSubstances, substanceName } from "@/lib/api";
import { PlacementBadge } from "@/lib/placement";

/**
 * Why each manufacturer's cell says what it says, side by side.
 *
 * The offsets are shown because they are the guarantee: the quote is a slice of the
 * stored section text at exactly those indices, so a reader can check it rather than
 * trust it.
 */
export default async function ConceptPage({
  params,
}: PageProps<"/substances/[id]/concepts/[concept]">) {
  const { id, concept } = await params;
  const decoded = decodeURIComponent(concept);
  const [matrix, substances] = await Promise.all([getMatrix(id), getSubstances()]);
  if (!matrix) notFound();

  const row = matrix.rows.find((r) => r.concept === decoded);
  if (!row) notFound();

  const byProduct = new Map(matrix.products.map((p) => [p.external_id, p]));

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          href={`/substances/${id}`}
          className="text-sm text-slate-600 hover:underline dark:text-slate-400"
        >
          ← {substanceName(substances, id)}
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">
          {conceptLabel(decoded)}
        </h1>
        <p className="text-slate-600 dark:text-slate-400">
          {row.diverges
            ? "These manufacturers do not place this the same way."
            : "Every manufacturer places this the same way."}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {row.cells.map((cell) => {
          const product = byProduct.get(cell.product_external_id);
          const sourceUrl = cell.evidence?.source_url ?? product?.source_url ?? undefined;
          return (
            <article
              key={cell.product_external_id}
              className="flex flex-col gap-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
            >
              <header className="space-y-1">
                <h2 className="font-medium">
                  {product ? columnLabel(product) : cell.product_external_id}
                </h2>
                <PlacementBadge placement={cell.placement} />
              </header>

              {cell.evidence ? (
                <>
                  <blockquote className="border-l-2 border-slate-300 pl-3 text-sm italic dark:border-slate-700">
                    {cell.evidence.quote}
                  </blockquote>
                  <dl className="text-xs text-slate-500">
                    <div className="flex gap-2">
                      <dt>Section</dt>
                      <dd className="font-mono">{cell.evidence.section_code}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt>Characters</dt>
                      <dd className="font-mono">
                        {cell.evidence.char_start}–{cell.evidence.char_end}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <p className="text-sm text-slate-500">
                  Not found in {product?.scanned.join(", ") || "any section read"}. There
                  is no quote because there was no match in what was read for this
                  label — which is not the same as the label being silent.
                </p>
              )}

              {sourceUrl && (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-auto text-sm text-sky-700 hover:underline dark:text-sky-400"
                >
                  Source SmPC ↗
                </a>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
