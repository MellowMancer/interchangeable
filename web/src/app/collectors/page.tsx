import { getCollectors, type Heal } from "@/lib/api";

// Heal history is live operational state; a build-time snapshot of it would be a lie.
export const dynamic = "force-dynamic";

/**
 * What Scraper Studio is running and how it has held up.
 *
 * A collector with no baseline is reported as unobserved, never as healthy: the engine
 * has simply not seen it yet, and drawing a green tick would invent an observation.
 */
export default async function CollectorsPage() {
  const collectors = await getCollectors();

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Collector health</h1>
        <p className="max-w-prose text-slate-600 dark:text-slate-400">
          Each collector is a Bright Data Scraper Studio template. When a page&apos;s
          structure drifts, <code className="font-mono text-sm">bdheal</code> repairs it in
          place — the collector ID never changes, so nothing downstream notices.
        </p>
      </header>

      <div className="space-y-4">
        {collectors.map((collector) => (
          <article
            key={collector.id}
            className="rounded-lg border border-slate-200 p-4 dark:border-slate-800"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-mono text-sm">{collector.id}</h2>
              <span className="text-xs text-slate-500">
                {collector.source} · {collector.kind}
              </span>
            </div>

            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
              {collector.baseline_captured_at ? (
                <>
                  Baseline captured {collector.baseline_captured_at} over{" "}
                  {collector.baseline_row_count} rows.
                </>
              ) : (
                <span className="text-slate-500">
                  No baseline yet — this collector has not been run through the engine, so
                  there is nothing to compare against. Not the same as healthy.
                </span>
              )}
            </p>

            <HealHistory heals={collector.heals} />
          </article>
        ))}
      </div>
    </div>
  );
}

function HealHistory({ heals }: { heals: Heal[] }) {
  if (heals.length === 0) {
    return <p className="mt-3 text-sm text-slate-500">No heals recorded.</p>;
  }
  return (
    <ol className="mt-3 space-y-2">
      {heals.map((heal) => (
        <li
          key={`${heal.created_at}-${heal.status}`}
          className="flex flex-wrap items-baseline gap-x-3 text-sm"
        >
          <span
            className={`rounded px-1.5 py-0.5 text-xs ${
              heal.promoted
                ? "bg-emerald-600 text-white"
                : "border border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-400"
            }`}
          >
            {heal.status}
          </span>
          <time className="text-slate-500">{heal.created_at}</time>
          {heal.failure_class && (
            <span className="text-slate-600 dark:text-slate-400">
              diagnosed {heal.failure_class.replace(/_/g, " ")}
            </span>
          )}
          {heal.attempts > 1 && (
            <span className="text-slate-500">{heal.attempts} attempts</span>
          )}
          {heal.error && <span className="text-red-600">{heal.error}</span>}
        </li>
      ))}
    </ol>
  );
}
