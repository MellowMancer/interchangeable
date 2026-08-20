import Link from "next/link";
import { notFound } from "next/navigation";
import { getMatrix, getSubstances, manufacturer } from "@/lib/api";
import { PLACEMENT_LEGEND, placementStyle } from "@/lib/placement";

export default async function SubstancePage({ params }: PageProps<"/substances/[id]">) {
  const { id } = await params;
  const [matrix, substances] = await Promise.all([getMatrix(id), getSubstances()]);
  if (!matrix) notFound();

  const divergent = matrix.rows.filter((row) => row.diverges);
  const name = substances.find((s) => s.id === id)?.name ?? id;

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">{name}</h1>
        <p className="max-w-prose text-slate-600 dark:text-slate-400">
          {matrix.products.length} manufacturers, {matrix.rows.length} concepts.{" "}
          {divergent.length === 0 ? (
            "They agree everywhere that was scanned."
          ) : (
            <>
              <strong className="text-slate-900 dark:text-slate-100">
                {divergent.length} disagree
              </strong>
              {" — those rows are first."}
            </>
          )}
        </p>
        <Scanned sections={matrix.scanned} />
      </header>

      <Switcher substances={substances} current={id} />

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white p-2 text-left align-bottom dark:bg-slate-950">
                Concept
              </th>
              {matrix.products.map((product) => (
                <th key={product.external_id} className="p-2 align-bottom">
                  <div className="font-medium">{manufacturer(product)}</div>
                  <div className="font-normal text-xs text-slate-500">
                    {product.revised ? `revised ${product.revised}` : "revision unknown"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr
                key={row.concept}
                className={
                  row.diverges
                    ? "bg-red-50/60 dark:bg-red-950/20"
                    : "border-t border-slate-100 dark:border-slate-900"
                }
              >
                <th className="sticky left-0 z-10 bg-inherit p-2 text-left font-normal">
                  <Link
                    href={`/substances/${id}/concepts/${encodeURIComponent(row.concept)}`}
                    className="hover:underline"
                  >
                    {row.concept.replace(/_/g, " ")}
                  </Link>
                  {row.diverges && (
                    <span className="ml-2 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
                      diverges
                    </span>
                  )}
                </th>
                {row.cells.map((cell) => {
                  const style = placementStyle(cell.placement);
                  return (
                    <td key={cell.product_external_id} className="p-2 text-center">
                      <span
                        title={style.detail}
                        className={`inline-block w-full rounded border px-2 py-1 text-xs ${style.className}`}
                      >
                        {style.label}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend />
    </div>
  );
}

/**
 * The scanned sections are part of the claim, not a caption.
 *
 * Every "not in scanned sections" cell is only meaningful against this list, so it sits
 * above the table rather than in a footnote.
 */
function Scanned({ sections }: { sections: string[] }) {
  return (
    <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      Sections read: <span className="font-mono">{sections.join(", ")}</span>. A cell
      saying <em>not in scanned sections</em> means the concept was not found in these —
      not that the label omits it.
    </p>
  );
}

function Switcher({
  substances,
  current,
}: {
  substances: { id: string; name: string; products: number }[];
  current: string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {substances.map((substance) => {
        const empty = substance.products === 0;
        const active = substance.id === current;
        if (empty) {
          return (
            <span
              key={substance.id}
              title="No labels collected yet"
              className="cursor-not-allowed rounded-full border border-dashed border-slate-300 px-3 py-1 text-sm text-slate-400 dark:border-slate-700"
            >
              {substance.name}
            </span>
          );
        }
        return (
          <Link
            key={substance.id}
            href={`/substances/${substance.id}`}
            className={`rounded-full border px-3 py-1 text-sm ${
              active
                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                : "border-slate-300 hover:border-slate-500 dark:border-slate-700"
            }`}
          >
            {substance.name}
          </Link>
        );
      })}
    </div>
  );
}

function Legend() {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-600 dark:text-slate-400">
      {PLACEMENT_LEGEND.map(([key, style]) => (
        <div key={key} className="flex items-center gap-2">
          <span className={`inline-block rounded border px-2 py-0.5 ${style.className}`}>
            {style.label}
          </span>
          <dd>{style.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
