import { redirect } from "next/navigation";
import { getSubstances } from "@/lib/api";

// Which substances have been collected changes as the pipeline runs, so this must be
// decided per request. Without it Next prerenders the redirect target at build time.
export const dynamic = "force-dynamic";

/**
 * Land on a populated matrix, not a search box.
 *
 * The first substance with products is the one to show: judges look for about thirty
 * seconds, and an empty search box spends all of it. Picking the first *collected*
 * substance rather than naming one keeps the landing page correct as the roster grows.
 */
export default async function Home() {
  const substances = await getSubstances();
  const collected = substances.find((s) => s.products > 0);

  if (!collected) {
    return (
      <div className="max-w-prose space-y-3">
        <h1 className="text-2xl font-semibold">Nothing collected yet</h1>
        <p className="text-slate-600 dark:text-slate-400">
          The roster lists {substances.length} substances, but no labels have been fetched.
          Run <code className="font-mono text-sm">ixq collect</code> and{" "}
          <code className="font-mono text-sm">ixq fetch</code> to populate the comparison.
        </p>
      </div>
    );
  }

  redirect(`/substances/${collected.id}`);
}
