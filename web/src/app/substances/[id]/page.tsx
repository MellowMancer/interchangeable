import Link from "next/link";
import { notFound } from "next/navigation";
import {
  conceptLabel,
  getMatrix,
  getSubstances,
  manufacturer,
  type ProductColumn,
  type SubstanceSummary,
} from "@/lib/api";
import { ABSENT, PLACEMENT_LEGEND, PlacementBadge } from "@/lib/placement";

const PILL = "rounded-full border px-3 py-1 text-sm";

export default async function SubstancePage({ params }: PageProps<"/substances/[id]">) {
  const { id } = await params;
  const [matrix, substances] = await Promise.all([getMatrix(id), getSubstances()]);
  if (!matrix) notFound();

  const divergent = matrix.rows.filter((row) => row.diverges).length;

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          {matrix.substance_name}
        </h1>
        <p className="max-w-prose text-slate-600 dark:text-slate-400">
          {matrix.products.length} manufacturers, {matrix.rows.length} concepts.{" "}
          {divergent === 0 ? (
            "They agree everywhere that was scanned."
          ) : (
            <>
              <strong className="text-slate-900 dark:text-slate-100">
                {divergent} disagree
              </strong>
              {" — those rows are first."}
            </>
          )}
        </p>
        <Scanned products={matrix.products} />
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
                  <div className="font-medium">{product.variant ?? product.name}</div>
                  <div className="font-normal text-xs text-slate-500">
                    {manufacturer(product)}
                  </div>
                  <div className="font-normal text-xs text-slate-500">
                    {product.revised ? `revised ${product.revised}` : "revision unknown"}
                  </div>
                  <div className="font-normal text-xs text-slate-500">
                    read {product.scanned.join(", ") || "nothing"}
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
                    {conceptLabel(row.concept)}
                  </Link>
                  {row.diverges && (
                    <span className="ml-2 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
                      diverges
                    </span>
                  )}
                </th>
                {row.cells.map((cell) => (
                  <td key={cell.product_external_id} className="p-2 text-center">
                    <PlacementBadge placement={cell.placement} className="w-full py-1" />
                  </td>
                ))}
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
 * Every absence cell is only meaningful against this list, so it sits above the table
 * rather than in a footnote — and quotes the badge's own label so the two cannot drift.
 */
function Scanned({ products }: { products: ProductColumn[] }) {
  const scopes = new Set(products.map((p) => p.scanned.join(", ")));
  const shared = scopes.size === 1 ? [...scopes][0] : null;
  return (
    <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      {shared ? (
        <>
          Sections read: <span className="font-mono">{shared}</span>.{" "}
        </>
      ) : (
        <>Sections read differ by manufacturer and are listed under each column. </>
      )}
      A cell saying <em>{ABSENT.label.toLowerCase()}</em> means the concept was not found
      in the sections read <em>for that manufacturer</em> — not that the label omits it.
    </p>
  );
}

function Switcher({
  substances,
  current,
}: {
  substances: SubstanceSummary[];
  current: string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {substances.map((substance) =>
        substance.products === 0 ? (
          <span
            key={substance.id}
            title="No labels collected yet"
            className={`${PILL} cursor-not-allowed border-dashed border-slate-300 text-slate-400 dark:border-slate-700`}
          >
            {substance.name}
          </span>
        ) : (
          <Link
            key={substance.id}
            href={`/substances/${substance.id}`}
            className={`${PILL} ${
              substance.id === current
                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                : "border-slate-300 hover:border-slate-500 dark:border-slate-700"
            }`}
          >
            {substance.name}
          </Link>
        ),
      )}
    </div>
  );
}

function Legend() {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-600 dark:text-slate-400">
      {PLACEMENT_LEGEND.map((style) => (
        <div key={style.label} className="flex items-center gap-2">
          <dt>
            <span className={`inline-block rounded border px-2 py-0.5 ${style.className}`}>
              {style.label}
            </span>
          </dt>
          <dd>{style.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
