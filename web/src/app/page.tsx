import { redirect } from "next/navigation";
import { getSubstances } from "@/lib/api";

/**
 * Land on a populated matrix, not a search box.
 *
 * The most divergent collected substance is the one to show: judges look for about
 * thirty seconds, and an empty search box spends all of it. Deriving the choice rather
 * than naming a substance keeps the landing page correct as the roster grows.
 */
export default async function Home() {
  const substances = await getSubstances();
  // Most divergent first, not first-in-file: the landing screen exists to show a
  // disagreement, and ordering by roster position would relocate it whenever
  // substances.yaml is reordered, with nothing to catch it.
  const collected = substances
    .filter((s) => s.products > 0)
    .sort((a, b) => b.divergent - a.divergent || b.products - a.products)[0];

  if (!collected) {
    return (
      <div className="max-w-prose space-y-3">
        <h1 className="text-2xl font-semibold">Nothing collected yet</h1>
        <p className="text-slate-600 dark:text-slate-400">
          The roster lists {substances.length} substances, but no labels have been fetched.
          Run <code className="font-mono text-sm">ixq init</code> then{" "}
          <code className="font-mono text-sm">ixq run</code> to populate the comparison.
        </p>
      </div>
    );
  }

  redirect(`/substances/${collected.id}`);
}
