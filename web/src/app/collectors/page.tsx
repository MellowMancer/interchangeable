import type { Metadata } from "next";
import { Section } from "@/lib/heading";
import { getBenchmark, type BenchCase, type BenchRun } from "@/lib/api";

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
  const runs = await getBenchmark();

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
        <Section>Controlled benchmark</Section>
        <p className="max-w-prose text-ink-muted">
          <span className="font-mono text-meta text-ink">medicines.org.uk</span> cannot be
          broken on cue, so the repair loop is measured against a fixture site we control,
          whose layout can be mutated to order. Its results are kept in a store of their
          own, deliberately: a benchmark must not be able to disturb the collectors that
          serve the corpus.
        </p>

        <BenchmarkSummary runs={runs} />

        {runs.length === 0 ? (
          <p className="text-meta text-ink-muted">
            No benchmark run recorded. Nothing has been measured, which is not the same as
            nothing having failed.
          </p>
        ) : (
          <Run runs={runs} />
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
  const attempts = runs.flatMap((run) => run.cases);
  if (attempts.length === 0) return null;

  /*
   * Counted per mutation, not per attempt.
   *
   * Every run is the same benchmark — `--run-id` exists so an interrupted one can be
   * resumed — so a mutation tried in two runs was one thing measured twice. Summing the
   * attempts read as broader coverage than the fixture site actually has: `table_to_div`
   * alone accounted for two of "6 cases".
   *
   * A mutation counts as detected or repaired if it ever was. That is the honest reading
   * of a repeated attempt: the loop is capable of it, and the per-run tables below still
   * show every attempt including the ones that failed.
   */
  const mutations = [...new Set(attempts.map((benchCase) => benchCase.mutation))];
  const ever = (mutation: string, held: (c: (typeof attempts)[number]) => boolean) =>
    attempts.some((benchCase) => benchCase.mutation === mutation && held(benchCase));

  const detected = mutations.filter((m) => ever(m, (c) => c.caught_by !== null)).length;
  const repaired = mutations.filter((m) => ever(m, (c) => c.healed)).length;
  const verified = mutations.filter((m) => ever(m, (c) => c.non_regression_passed === true)).length;

  return (
    <p className="max-w-prose border-l-2 border-rule pl-4 text-meta text-ink-muted">
      <span className="text-ink">
        {mutations.length} {mutations.length === 1 ? "mutation" : "mutations"} over{" "}
        {attempts.length} {attempts.length === 1 ? "attempt" : "attempts"}: {detected}{" "}
        detected, {repaired} repaired, {verified} verified against the old layout.
      </span>{" "}
      Every attempt is listed below, including the ones nothing caught. A signal chip is filled when
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
function Run({ runs }: { runs: BenchRun[] }) {
  /*
   * One table, because there is only one benchmark.
   *
   * `--run-id` exists so an interrupted run can be resumed; it names an occasion, not an
   * instrument. A table per run put the same mutation in two places and invited the
   * reader to compare them as though they measured different things. Sorted by mutation
   * so a repeated attempt sits beside the one it repeats, with the run that produced it
   * named in its own column.
   */
  const attempts = runs.flatMap((run) => run.cases);

  /*
   * One row per mutation, showing how far the loop ever got with it.
   *
   * Dropping the run column made two attempts at the same mutation two identical rows,
   * which reads as two mutations. Collapsing them to the furthest outcome matches the
   * count above it: a mutation the loop repaired once is a mutation it can repair, and a
   * second attempt that stalled is not a separate finding about the fixture site.
   */
  const reached = (benchCase: (typeof attempts)[number]) =>
    (benchCase.healed ? 2 : 0) + (benchCase.caught_by !== null ? 1 : 0);

  const cases = [...new Set(attempts.map((benchCase) => benchCase.mutation))]
    .map((mutation) =>
      attempts
        .filter((benchCase) => benchCase.mutation === mutation)
        .reduce((best, benchCase) => (reached(benchCase) > reached(best) ? benchCase : best)),
    )
    .sort((a, b) => a.mutation.localeCompare(b.mutation));

  return (
    <article className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full table-fixed border-collapse text-meta">
          <thead>
            <tr className="border-b border-rule text-left text-ink-muted">
              <th className="w-52 py-2 pr-4 font-normal">Mutation</th>
              <th className="w-60 py-2 pr-4 font-normal">Signals</th>
              <th className="py-2 text-right font-normal">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((benchCase) => (
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
                <td className="py-3 text-right">
                  <Outcome benchCase={benchCase} />
                </td>
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


