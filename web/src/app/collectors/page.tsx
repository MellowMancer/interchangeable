import type { Metadata } from "next";
import { Section } from "@/lib/heading";
import { getBenchmark, getCollectors, type BenchCase, type BenchRun, type Heal } from "@/lib/api";

export const metadata: Metadata = { title: "Reliability" };

/**
 * What Scraper Studio is running, and how the repair loop has actually scored.
 *
 * A collector with no baseline is reported as unobserved, never as healthy: the engine
 * has simply not seen it yet, and drawing a green tick would invent an observation.
 *
 * The benchmark is reported case by case, failures included. A screen that showed only
 * the case that repaired cleanly would be a claim rather than a measurement, and the
 * rows behind it are one query away for anyone who looks.
 */
export default async function CollectorsPage() {
  const [collectors, runs] = await Promise.all([getCollectors(), getBenchmark()]);

  return (
    <div className="space-y-12">
      <header className="space-y-4">
        <h1 className="font-serif text-title font-normal tracking-tight">Reliability</h1>
        <p className="max-w-prose text-ink-muted">
          Each collector is a Bright Data Scraper Studio template. When a page&apos;s
          structure drifts, <code className="font-mono text-meta text-ink">bdheal</code>{" "}
          repairs it in place — the collector ID never changes, so nothing downstream
          notices.
        </p>
      </header>

      <section className="space-y-6">
        <Section>Live collectors</Section>
        <div className="divide-y divide-rule border-y border-rule">
          {collectors.map((collector) => (
            <article key={collector.id} className="space-y-3 py-6">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h3 className="font-mono">{collector.id}</h3>
                <span className="font-mono text-meta text-ink-muted">
                  {collector.source} · {collector.kind}
                </span>
              </div>

              <p className="text-meta text-ink-muted">
                {collector.baseline_captured_at ? (
                  <>
                    Baseline captured {observed(collector.baseline_captured_at)} over{" "}
                    {collector.baseline_row_count}{" "}
                    {collector.baseline_row_count === 1 ? "row" : "rows"}.
                  </>
                ) : (
                  <>No baseline yet — never observed, which is not the same as healthy.</>
                )}
              </p>

              <HealHistory heals={collector.heals} />
            </article>
          ))}
        </div>
      </section>

      <section className="space-y-6 border-t border-rule pt-10">
        <Section>Controlled benchmark</Section>
        <p className="max-w-prose text-ink-muted">
          <span className="font-mono text-meta text-ink">medicines.org.uk</span> cannot be
          broken on cue, so the repair loop is measured against a fixture site we control —
          a different store from the live collectors above, deliberately.
        </p>

        <BenchmarkSummary runs={runs} />

        {runs.length === 0 ? (
          <p className="text-meta text-ink-muted">
            No benchmark run recorded. Nothing has been measured, which is not the same as
            nothing having failed.
          </p>
        ) : (
          runs.map((run) => <Run key={run.run_id} run={run} />)
        )}
      </section>
    </div>
  );
}

/**
 * The whole benchmark in one line, before the run-by-run detail.
 *
 * Runs are listed oldest first because that is the order they happened in, which means
 * an early failing run is the first thing on screen. Totalling across every run first
 * stops that ordering from reading as the final result — in either direction.
 */
function BenchmarkSummary({ runs }: { runs: BenchRun[] }) {
  const cases = runs.flatMap((run) => run.cases);
  if (cases.length === 0) return null;

  const detected = cases.filter((benchCase) => benchCase.caught_by !== null).length;
  const repaired = cases.filter((benchCase) => benchCase.healed).length;
  const verified = cases.filter((benchCase) => benchCase.non_regression_passed === true).length;

  return (
    <p className="max-w-prose border-l-2 border-rule pl-4 text-meta text-ink-muted">
      <span className="text-ink">
        {cases.length} cases across {runs.length} {runs.length === 1 ? "run" : "runs"}:{" "}
        {detected} detected, {repaired} repaired, {verified} verified against the old layout.
      </span>{" "}
      Every case is listed, including the ones nothing caught. A signal chip is filled when
      that detector fired, outlined when it was expected and stayed silent — an outlined
      chip is a published coverage gap. <em>Non-regression</em> means the repair still works
      against the layout it was built for, so it was not overfitted to the break.
    </p>
  );
}

/**
 * One run's cases, with the run's own arithmetic above them.
 *
 * The counts are computed from the cases on screen rather than stated, so the summary
 * cannot drift from the table it summarises.
 */
function Run({ run }: { run: BenchRun }) {
  const detected = run.cases.filter((c) => c.caught_by !== null).length;
  const repaired = run.cases.filter((c) => c.healed).length;
  const verified = run.cases.filter((c) => c.non_regression_passed === true).length;

  return (
    <article className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-2">
        <h3 className="font-mono text-meta tracking-widest uppercase">run {run.run_id}</h3>
        <p className="font-mono text-meta text-ink-muted">
          {run.cases.length} cases · {detected} detected · {repaired} repaired ·{" "}
          {verified} verified against the old layout
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-meta">
          <thead>
            <tr className="border-b border-rule text-left text-ink-muted">
              <th className="py-2 pr-4 font-normal">Mutation</th>
              <th className="py-2 pr-4 font-normal">Signals</th>
              <th className="py-2 pr-4 font-normal">Outcome</th>
              <th className="py-2 font-normal">Attempts</th>
            </tr>
          </thead>
          <tbody>
            {run.cases.map((benchCase) => (
              <tr key={benchCase.case_id} className="border-b border-rule align-top">
                <td className="py-3 pr-4">
                  <span className="block font-mono">{benchCase.mutation}</span>
                  {benchCase.case_id !== benchCase.mutation && (
                    <span className="block font-mono text-kicker text-ink-muted">
                      case {benchCase.case_id}
                    </span>
                  )}
                </td>
                <td className="py-3 pr-4">
                  <Signals
                    expected={benchCase.expected_signals}
                    fired={benchCase.fired_kinds}
                  />
                </td>
                <td className="py-3 pr-4">
                  <Outcome benchCase={benchCase} />
                </td>
                <td className="py-3 font-mono text-ink-muted">{benchCase.attempts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

/**
 * Which detectors the generator declared, and which actually fired.
 *
 * Drawn as one row of chips rather than two columns of comma-separated names, because the
 * subject is the *disagreement* between the two lists — a signal expected but silent is
 * the coverage gap, and a signal that fired unexpectedly is a detector nobody declared.
 * Reading that off two text columns means diffing them by eye on every row.
 */
function Signals({ expected, fired }: { expected: string[]; fired: string[] }) {
  const kinds = Array.from(new Set([...expected, ...fired])).sort();
  if (kinds.length === 0) return <span className="text-ink-muted">none declared</span>;

  return (
    <ul className="flex flex-wrap gap-1">
      {kinds.map((kind) => {
        const wasExpected = expected.includes(kind);
        const didFire = fired.includes(kind);
        const label = didFire
          ? wasExpected
            ? "expected and fired"
            : "fired but never declared"
          : "expected but silent";
        return (
          <li
            key={kind}
            title={`${kind} — ${label}`}
            className={`rounded-sheet border px-2 py-0.5 font-mono text-kicker ${
              didFire
                ? wasExpected
                  ? "border-p45 bg-p45 text-p45-on"
                  : "border-p44 bg-p44 text-p44-on"
                : "border-dashed border-rule text-ink-muted"
            }`}
          >
            {kind}
            <span className="sr-only"> {label}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * What happened to one case, as a verdict rather than a sentence.
 *
 * A case that was never scored shows no accuracy at all rather than zero: the repair was
 * not attempted, which is a different result from a repair that scored nothing. What the
 * verdicts mean is stated once above the table, not repeated on every row.
 */
function Outcome({ benchCase }: { benchCase: BenchCase }) {
  if (!benchCase.caught_by) return <span className="text-ink-muted">not detected</span>;
  if (!benchCase.healed) return <span className="text-ink-muted">detected, not repaired</span>;

  return (
    <span className="font-mono">
      repaired
      {benchCase.field_accuracy !== null && ` · accuracy ${benchCase.field_accuracy}`}
      {benchCase.non_regression_passed === null
        ? " · non-regression unchecked"
        : benchCase.non_regression_passed
          ? " · non-regression passed"
          : " · non-regression failed"}
    </span>
  );
}

/**
 * A timestamp a person can read. The API sends ISO because that is unambiguous to a
 * machine; microseconds and a UTC offset are noise on a status screen.
 */
function observed(iso: string) {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function HealHistory({ heals }: { heals: Heal[] }) {
  if (heals.length === 0) {
    return <p className="text-meta text-ink-muted">No drift detected since baseline.</p>;
  }
  return (
    <ol className="space-y-2">
      {heals.map((heal) => (
        <li
          key={`${heal.created_at}-${heal.status}`}
          className="flex flex-wrap items-baseline gap-x-3 text-meta"
        >
          <span
            className={`rounded-sheet border px-2 py-0.5 font-mono text-kicker uppercase ${
              heal.promoted ? "border-p45 bg-p45 text-p45-on" : "border-rule text-ink-muted"
            }`}
          >
            {heal.status}
          </span>
          <time className="text-ink-muted">{observed(heal.created_at)}</time>
          {heal.failure_class && (
            <span className="text-ink-muted">
              diagnosed {heal.failure_class.replace(/_/g, " ")}
            </span>
          )}
          {heal.attempts > 1 && <span className="text-ink-muted">{heal.attempts} attempts</span>}
          {heal.error && <span className="text-accent">{heal.error}</span>}
        </li>
      ))}
    </ol>
  );
}
