"use client";

/**
 * The vocabulary, taught once, before it is needed.
 *
 * The roster asks a newcomer to hold four ideas at once — substance, product,
 * manufacturer, and the five places a concept can be filed — and none of them are
 * inferable from a grid of coloured badges. `/reading` explains all of it and `Primer`
 * offers that page, but both are opt-in, and the reader who most needs them is the one
 * least likely to click.
 *
 * So this takes the screen, which `Primer` deliberately does not. That is defensible only
 * on the terms it is offered on: it appears once, on the front door, it can be skipped
 * from the first frame, and it is never shown again unasked. Finishing or skipping also
 * dismisses `Primer`, because being taught the same words twice is being nagged.
 *
 * Motion here is load-bearing, which contradicts the rule the rest of the application is
 * built on — see the note in `globals.css`. Text lifting off a drawn box *is* the
 * explanation of what is printed on a box. The exception is paid for twice: nothing
 * advances on its own, so no reader is carried past something unread, and every beat
 * states its lesson in words that stand without the movement.
 *
 * Nothing here replays on a timer. A beat plays once when it is stepped into and then
 * holds still: a loop running behind a reader who is still reading the first sentence
 * competes with them for the same attention, and the reader loses.
 */

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  type Placement,
  PlacementBadge,
  PlacementPip,
  placementStyle,
  SECTION_PLACEMENTS,
} from "@/lib/placement";
import { Pack } from "@/lib/pack";
import { PRIMER_DISMISSED } from "@/lib/primer";
import { QuotePosition } from "@/lib/scope";
import {
  CLAUSES,
  COLLECTED_LABELS,
  CORPUS,
  DIVERGENT_CONCEPT,
  EVIDENCE,
  HERO,
  LABEL,
  MATRIX,
  type MatrixRow,
  PARTS,
  SIBLINGS,
} from "@/lib/walkthrough-script";

/** Remembered across visits: an invitation repeated is an interruption. */
const SEEN = "walkthrough-seen";

/** The query parameter both entry points use, so a Server Component can open this. */
const PARAM = "tour";

/** One part arriving beside the box, and the gap before the next one follows it. */
const STEP_MS = 620;

/** The shelf of siblings deals faster: six cards, and no single one is being read yet. */
const CARD_STEP_MS = 150;

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Walkthrough() {
  return (
    // `useSearchParams` suspends, and this sits in the root layout above every route.
    <Suspense fallback={null}>
      <Tour />
    </Suspense>
  );
}

function Tour() {
  const path = usePathname();
  const params = useSearchParams();
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  /**
   * Dismissed, whatever storage thinks.
   *
   * Writing `walkthrough-seen` is how the decision outlives the session, but a browser
   * that refuses storage — private mode, blocked cookies, a partitioned webview — throws
   * on both the write and the read. Trusting storage alone meant Skip cleared `?tour=1`,
   * the effect re-ran, the read threw, and the overlay reopened over a page it had just
   * released. Held here as well so a reader can always get out.
   */
  const dismissed = useRef(false);

  const invited = params.get(PARAM) !== null;

  useEffect(() => {
    // An invitation outranks a dismissal. `?tour=1` is someone asking for this on purpose
    // — from the hero, or from the guide's replay link — and a reader who skipped it once
    // and then went looking for it must not be told no by their own earlier decision.
    if (invited) {
      dismissed.current = false;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      return setOpen(true);
    }
    if (dismissed.current) return setOpen(false);
    // Not just "do nothing off the landing page": the overlay traps focus and locks the
    // body, so leaving it open through a client-side navigation carries both onto a page
    // that never asked for them.
    if (path !== "/") return setOpen(false);
    try {
      if (window.localStorage.getItem(SEEN)) return setOpen(false);
    } catch {
      // Storage unavailable: showing it is still the right default for a first arrival.
    }
    setOpen(true);
  }, [invited, path]);

  /**
   * Step, and let the browser move what both beats have in common.
   *
   * The pack, the label and the matrix are the same objects from one beat to the next, so
   * they must *travel* between their two positions rather than vanish from one and appear
   * in the other. A hand-written slide cannot do that — it can only guess at where the
   * element was — so the positions come from the browser, which measured both.
   *
   * `flushSync` because the transition needs the new DOM inside the callback; React would
   * otherwise batch the state change until after the snapshot was taken. Unsupported
   * browsers fall through to a plain step, which is the current behaviour, not a broken one.
   */
  const go = useCallback((next: number) => {
    if (!document.startViewTransition) {
      setStep(next);
      return;
    }
    document.startViewTransition(() => flushSync(() => setStep(next)));
  }, []);

  const close = useCallback(() => {
    dismissed.current = true;
    setOpen(false);
    setStep(0);
    try {
      window.localStorage.setItem(SEEN, "1");
      // The guide has just been given in full; the nudge offering it would be noise.
      window.localStorage.setItem(PRIMER_DISMISSED, "1");
    } catch {
      // Not being able to remember is not a reason to refuse to close.
    }
    if (!invited) return;
    const rest = new URLSearchParams(params.toString());
    rest.delete(PARAM);
    const query = rest.toString();
    router.replace(query ? `${path}?${query}` : path, { scroll: false });
  }, [invited, params, path, router]);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    // The first control, not the panel: the panel carries `tabIndex={-1}` and so is not
    // in `FOCUSABLE`, which left the very first Shift+Tab matching neither end of the
    // cycle and stepping straight out of a dialog that claims to be modal.
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    const body = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      // Restored to whatever was inline before, so the stylesheet's own `overflow-x`
      // rule — which keeps the viewport the scroll container every sticky column
      // measures against — comes back untouched.
      document.body.style.overflow = body;
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        return;
      }
      if (event.key !== "Tab") return;
      const stops = panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!stops?.length) return;
      const first = stops[0];
      const last = stops[stops.length - 1];
      const on = document.activeElement;
      if (event.shiftKey && on === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && on === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  if (!open) return null;

  const beat = BEATS[step];
  const last = step === BEATS.length - 1;

  return (
    <div
      className="tour fixed inset-0 z-40 flex items-center justify-center bg-paper/85 p-4 backdrop-blur-sm sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-title"
    >
      <div
        ref={panel}
        tabIndex={-1}
        className="tour-in flex h-[47rem] max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-sheet border border-rule bg-paper shadow-[0_32px_64px_-28px_rgba(0,0,0,0.65)] outline-none"
      >
        <div className="flex items-center justify-between border-b border-rule px-5 py-3">
          <p className="font-mono text-kicker text-ink-muted">
            {step + 1} of {BEATS.length}
          </p>
          <button
            type="button"
            onClick={close}
            className="font-mono text-kicker text-ink-muted hover:text-ink"
          >
            Skip
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-8">
          {/* One height for every beat, and the content centred inside it. `min-h-full`
              with centred children rather than a centred scroll container: a short beat
              sits in the middle, and a tall one grows past the box and scrolls from its
              own top instead of having its top clipped.

              No crossfade between beats. Fading a whole screen out and a whole screen in
              breaks the one thing this sequence is built on — that the pack, the label and
              the matrix are the *same* objects being rearranged. Continuity is carried by
              the things that stay put, and a fade over the top of them reads as a slide
              change, which is exactly what they are not. */}
          <div className="flex min-h-full flex-col justify-center">
            {/* The left slot is rendered *outside* the keyed column on purpose. Beats two
                to four are one continuous scene: the pack holds still while what sits
                beside it becomes the list and then the label, and then the pack gives way
                and the label itself slides across into that slot. Keying it with the rest
                would remount on every step and turn one scene into three slides. */}
            <div className={beat.aside ? BESIDE : undefined}>
              {beat.aside}
              {/* `min-w-0` because a grid child defaults to `min-width: auto`, and the
                  label's table would otherwise push the column wider than the panel. */}
              <div key={step} data-beat={step + 1} className="min-w-0">
                {beat.stage}
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-rule px-5 py-4 sm:px-8">
          {/* The region is stable and only its children change. Keying the element that
              carries `aria-live` replaces it on every beat, and a live region inserted
              already-populated announces nothing — which would have left the one promise
              this overlay makes to a screen reader unkept. */}
          <div className="min-h-24" aria-live="polite">
            <h2 id="tour-title" className="font-serif text-quote font-normal text-ink">
              {beat.title}
            </h2>
            <p className="mt-1 max-w-prose text-meta text-ink-muted">{beat.caption}</p>
          </div>
          <div className="mt-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-1.5" aria-hidden>
              {BEATS.map((_, index) => (
                <span
                  key={index}
                  className={`h-1.5 w-1.5 rounded-sheet ${index === step ? "bg-accent" : "bg-rule"}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => go(Math.max(0, step - 1))}
                disabled={step === 0}
                className="font-mono text-kicker text-ink-muted hover:text-ink disabled:opacity-40"
              >
                ← Back
              </button>
              {last ? (
                <Link
                  href="/"
                  onClick={close}
                  className="rounded-sheet border border-accent px-3 py-1.5 font-mono text-kicker text-accent hover:bg-accent hover:text-paper"
                >
                  Browse all products →
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => go(step + 1)}
                  className="rounded-sheet border border-accent px-3 py-1.5 font-mono text-kicker text-accent hover:bg-accent hover:text-paper"
                >
                  Next →
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Whatever the scene is measured against, and what is being taken out of it. */
const BESIDE = "grid items-start gap-6 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]";

/**
 * The one pack this whole scene is about.
 *
 * It does not fade as its text is named beside it: the pack is the fixed point the whole
 * scene is measured against, and dimming it would say the box stopped being the subject.
 *
 * Named for the view transition: this pack is one object across beats one to three, and
 * the browser moves it from the centre of the opening card into the left slot.
 *
 * The drawing itself is shared with the product index, which stands six hundred of them in
 * a grid. One drawn object, taught here and met again on the front door, is what makes the
 * index read as the thing this beat explained rather than a new kind of picture.
 */
/**
 * One manufacturer, one name, whichever shape it currently has.
 *
 * On the shelf it is a pack; in the matrix it is a column. Giving both the same name is
 * what makes the browser fly each pack into its own column rather than dissolve six boxes
 * and draw a table — which is the claim the beat is making: the table *is* those six
 * labels, seen at once.
 */
const makerName = (maker: string) => `tour-maker-${maker.toLowerCase()}`;

const HeroPack = () => (
  <Pack
    product={HERO.product}
    substance={HERO.substance}
    form={HERO.form}
    holder={HERO.holder}
    name="tour-pack"
  />
);

/** The three printed strings, arriving one at a time as the box lets go of each. */
function Parts() {
  return (
    <dl className="space-y-3">
      {PARTS.map((part, index) => (
        <div
          key={part.term}
          className="tour-lift rounded-sheet border border-rule p-3"
          style={{ animationDelay: `${index * STEP_MS}ms` }}
        >
          <dt className="font-mono text-kicker tracking-wide text-accent">{part.term}</dt>
          <dd className="mt-1 font-serif text-body text-ink">{part.value}</dd>
          <dd className="mt-1 text-meta text-ink-muted">{part.gloss}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A placeholder line. Not the loading pulse — this depicts a document, it does not wait. */
const Line = ({ width }: { width: string }) => (
  <span className="block h-2 rounded-sheet bg-rule" style={{ width }} />
);

const WIDTHS = ["94%", "88%", "97%", "72%", "91%", "83%"];

/**
 * The label as the long document it is.
 *
 * `quoted` draws the real clauses inside it; the ghost copy on the next beat leaves them
 * out, because that is where those same clauses have moved to.
 */
function Sections({ quoted }: { quoted: boolean }) {
  return (
    <div className="space-y-5">
      {LABEL.map((section) => (
        <div key={section.code} className="space-y-2">
          {/* The heading as the label prints it, without its number. The code is
              provenance for someone checking a claim; a reader meeting the word
              "contraindications" for the first time is not helped by "§4.3". */}
          <p className="font-mono text-kicker text-ink-muted">{section.heading}</p>
          {Array.from({ length: section.bars }).map((_, index) => (
            <Line key={index} width={WIDTHS[index % WIDTHS.length]} />
          ))}
          {quoted ? (
            <p className="border-l-2 border-accent pl-3 font-serif text-meta text-ink">
              {section.quote}
            </p>
          ) : (
            <Line width="64%" />
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * The document, scrolling, because its length is the point.
 *
 * `aside` is the same document after the pack has gone: shifted into the slot the pack
 * held and squeezed to its width, so the placements arriving beside it are visibly what
 * was taken out of *this*, not a new screen that happens to follow it.
 */
function Document({ aside = false }: { aside?: boolean }) {
  return (
    <div
      // One name across both forms, so the browser carries the label from the column the
      // list vacated into the slot the pack has just left, resizing it on the way.
      style={{ viewTransitionName: "tour-label" }}
      className={`tour-window relative overflow-hidden rounded-sheet border border-rule px-4 ${
        aside ? "h-[22rem] opacity-45" : "h-[19rem]"
      }`}
    >
      <div className="tour-scroll space-y-5 py-4">
        <Sections quoted />
        <Sections quoted />
      </div>
    </div>
  );
}

/**
 * What the label was carrying, sorted by where it was filed.
 *
 * These are the same six quotes the document was scrolling a beat ago, in the same column
 * of the same scene — that is what makes this a reorganisation of the label rather than a
 * fresh screen of coloured badges.
 */
function Sorted() {
  return (
    <ul className="space-y-2">
      {CLAUSES.map((clause, index) => {
        const style = placementStyle(clause.placement);
        return (
          <li
            key={clause.placement}
            className="tour-lift grid grid-cols-[6.5rem_minmax(0,1fr)] items-start gap-3 rounded-sheet border border-rule p-3"
            style={{ animationDelay: `${index * CARD_STEP_MS}ms` }}
          >
            {/* A fixed column, so five badges of five widths still leave the quotes
                starting on one line down the page. */}
            <span>
              <PlacementBadge placement={clause.placement} />
            </span>
            <span>
              <span className="block font-serif text-meta text-ink">{clause.quote}</span>
              <span className="mt-1 block text-kicker text-ink-muted">
                <span className="font-mono text-accent">{clause.concept}</span> —{" "}
                {style.detail}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Six labels of one substance, each drawn as the pack the walkthrough opened with.
 *
 * No placement and no concept here on purpose: this beat makes one claim only — that a
 * substance is many products by many companies. What they disagree about comes next, and
 * putting it here would answer the question before it has been asked.
 */
function Shelf() {
  /*
   * Read off the matrix the next beat draws, so the two agree by construction.
   *
   * A card on the index carries every section its label files something in; here the set
   * is what these six concepts show, which is what a reader can check against the table
   * two screens later. Absence is not a mark — it is the one thing a bar must never claim.
   */
  const worn = (column: number) => [
    ...new Set(
      MATRIX.map((row) => row.placements[column]).filter((placement) => placement !== "absent"),
    ),
  ].sort();

  return (
    <div className="space-y-3">
      <p className="font-mono text-kicker text-ink-muted">
        Ibuprofen · {SIBLINGS.length} of {COLLECTED_LABELS} labels
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {SIBLINGS.map((sibling, column) => (
          <Pack
            key={sibling.name}
            product={sibling.short}
            substance={HERO.substance}
            form={sibling.form}
            holder={sibling.holder}
            placements={worn(column)}
            name={makerName(sibling.maker)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * The comparison, at the size it fits in a paragraph.
 *
 * The real thing on a substance page, shrunk: one row per concept, one column per
 * manufacturer, one mark per cell. `PlacementPip` is the right primitive at this size —
 * it is the mark the roster already uses where a grid is scanned rather than read, and it
 * keeps its accessible name, so the colours are never the only channel.
 *
 * A row whose marks differ is a finding, and its concept is set in the accent to say so.
 *
 * Nothing in here has an entrance animation. An element cannot both play its own arrival
 * and be carried by a view transition: the browser snapshots the new state at the moment
 * the DOM changes, which is the moment an entrance is at opacity zero, so it would morph
 * towards a picture of something invisible. The movement between beats is the transition's
 * job, and this table is one of the things it moves.
 *
 * It takes its rows so the beat after this one can show the very same table cut down to
 * the single row it is about. Rebuilding that row as its own thing would let the two drift,
 * and the whole point of the second one is that it *is* a row of the first.
 */
function Grid({ rows, legend = false }: { rows: MatrixRow[]; legend?: boolean }) {
  return (
    <div className="space-y-4">
      <table className="w-full border-collapse text-left" style={{ viewTransitionName: "tour-grid" }}>
      <thead>
        <tr>
          <th scope="col" className="pb-2 pr-3 font-mono text-kicker font-normal text-ink-muted">
            Concept
          </th>
          {SIBLINGS.map((sibling) => (
            <th
              key={sibling.holder}
              scope="col"
              style={{ viewTransitionName: makerName(sibling.maker) }}
              className="px-1 pb-2 font-mono text-kicker font-normal text-ink-muted"
            >
              {sibling.maker}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const diverges = new Set(row.placements).size > 1;
          return (
            <tr key={row.concept} className="border-t border-rule">
              <th
                scope="row"
                className={`py-2.5 pr-3 font-mono text-kicker font-normal ${
                  diverges ? "text-accent" : "text-ink-muted"
                }`}
              >
                {row.concept}
              </th>
              {row.placements.map((placement, column) => (
                <td key={SIBLINGS[column].holder} className="px-1 py-2.5">
                  <PlacementPip placement={placement} />
                </td>
              ))}
            </tr>
          );
        })}
        </tbody>
      </table>

      {/* The key to the marks above, read from `placement.tsx` rather than restated, so a
          section added there appears here without this file being remembered. Absence is
          in it: a legend listing only the five colours would leave the dashed cell the one
          mark on screen with nothing explaining it, and a reader guessing at that will
          guess it means the label omits something. */}
      <dl
        hidden={!legend}
        className="grid gap-x-5 gap-y-2 border-t border-rule pt-3 sm:grid-cols-2"
      >
        {[...SECTION_PLACEMENTS, "absent" as Placement].map((placement) => {
          const style = placementStyle(placement);
          return (
            <div key={placement} className="flex items-baseline gap-2">
              <dt className="shrink-0 translate-y-px">
                <PlacementPip placement={placement} />
              </dt>
              {/* The word and what it means, without the section code: the code is
                  provenance for someone checking a claim, and this legend is for someone
                  still learning which colour is which. The grid it explains does not
                  print codes either. */}
              <dd className="text-kicker text-ink-muted">
                <span className="text-ink">{style.label}</span> — {style.detail}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

/**
 * One row of that grid, read out.
 *
 * Grouped by where each label filed it rather than listed per manufacturer: the finding is
 * that there are *three answers*, and three groups say that at a glance where six rows
 * make a reader count.
 *
 * `expand` quiets two of them and opens the third onto the sentence that earned it. Same
 * component, same three cards in the same places — the beat is one of them being opened,
 * not a new screen of one card, and with no crossfade between beats that only reads if the
 * other two stay where they were.
 */
function Disagreement({ expand }: { expand?: Placement }) {
  const row = MATRIX.find((entry) => entry.concept === DIVERGENT_CONCEPT);
  if (!row) return null;

  const groups: { placement: Placement; makers: string[] }[] = [];
  row.placements.forEach((placement, index) => {
    const group = groups.find((entry) => entry.placement === placement);
    if (group) group.makers.push(SIBLINGS[index].maker);
    else groups.push({ placement, makers: [SIBLINGS[index].maker] });
  });

  return (
    <div className="space-y-4">
      {/* The same table, cut to the row it is about. */}
      <Grid rows={[row]} />
      <p className="font-mono text-kicker text-ink-muted">
        {expand
          ? "one of them, in the label's own words"
          : `${groups.length} different answers to one question`}
      </p>
      <ul className="space-y-2">
        {groups.map((group) => {
          const style = placementStyle(group.placement);
          return (
            <li
              key={group.placement}
              className={`grid grid-cols-[7.5rem_minmax(0,1fr)] items-start gap-3 rounded-sheet border border-rule p-3 ${
                expand && expand !== group.placement ? "opacity-25" : ""
              }`}
              // Each answer keeps its identity while one of them opens onto its evidence.
              style={{ viewTransitionName: `tour-answer-${group.placement.replace(".", "")}` }}
            >
              <span>
                <PlacementBadge placement={group.placement} />
              </span>
              <span>
                <span className="block text-meta text-ink">{style.detail}</span>
                <span className="mt-1 block font-mono text-kicker text-ink-muted">
                  {group.makers.join(" · ")}
                </span>
                {expand === group.placement ? (
                  <span className="mt-3 block space-y-2 border-t border-rule pt-3">
                    {/* Serif, because these are the label's own words and every quotation
                        on this site is set in the label's voice. */}
                    <span className="block border-l-2 border-accent pl-3 font-serif text-meta text-ink">
                      {EVIDENCE.quote}
                    </span>
                    <QuotePosition
                      charStart={EVIDENCE.charStart}
                      charEnd={EVIDENCE.charEnd}
                      sectionLength={EVIDENCE.sectionLength}
                      sectionCode={EVIDENCE.placement}
                    />
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * What the walkthrough was for, and the size of what it opens onto.
 *
 * The numbers are the argument. A reader who has just been shown one disagreement could
 * reasonably assume they were shown the interesting one — that most labels agree and this
 * was the exception. They were not: every substance collected has at least one.
 */
function Conclusion() {
  const totals = [
    { value: CORPUS.substances, label: "substances" },
    { value: CORPUS.products, label: "products" },
    { value: CORPUS.findings, label: "disagreements" },
  ];
  return (
    <div className="space-y-6">
      <dl className="grid gap-4 sm:grid-cols-3">
        {totals.map((total) => (
          <div key={total.label} className="rounded-sheet border border-rule p-4">
            {/* Mono, because every one of these is a count a reader could take from the
                corpus themselves. */}
            <dt className="font-mono text-title text-ink">{total.value}</dt>
            <dd className="mt-1 font-mono text-kicker text-ink-muted">{total.label}</dd>
          </div>
        ))}
      </dl>

      <p className="max-w-prose text-body text-ink-muted">
        Not one substance in the corpus is free of them.{" "}
        <span className="text-ink">
          Every drug collected so far has at least one thing its manufacturers file
          differently.
        </span>
      </p>

      <p className="max-w-prose text-meta text-ink-muted">
        You now have the five words the rest of the site is written in —{" "}
        <span className="font-mono text-accent">substance</span>,{" "}
        <span className="font-mono text-accent">product</span>,{" "}
        <span className="font-mono text-accent">manufacturer</span>,{" "}
        <span className="font-mono text-accent">concept</span> and{" "}
        <span className="font-mono text-accent">placement</span>.
      </p>
    </div>
  );
}

type Beat = {
  title: string;
  caption: string;
  /** What stands in the left slot — the pack, then the label itself. Null on its own. */
  aside: React.ReactNode | null;
  stage: React.ReactNode;
};

const BEATS: Beat[] = [
  {
    title: "This is a box of painkillers",
    caption:
      "Three different things are printed on it, and telling them apart is the whole trick to reading this site.",
    aside: null,
    stage: (
      <div className="mx-auto flex max-w-xs items-center justify-center py-4">
        <HeroPack />
      </div>
    ),
  },
  {
    title: "Substance, product, manufacturer",
    caption:
      "The substance is the drug. The product is one company's version of it. The manufacturer is the company. A brand name is never the drug itself.",
    aside: <HeroPack />,
    stage: <Parts />,
  },
  {
    title: "Every product has a label",
    caption:
      "Behind that box is a long legal document: what it is for, who must not take it, how to take it carefully, what else changes it, and what is in it.",
    aside: <HeroPack />,
    stage: <Document />,
  },
  {
    title: "The label files each concept into 5 sections",
    caption:
      "A concept is a thing a label talks about. A placement is the section it was filed in. 20-30 concepts -> 5 sections",
    aside: <Document aside />,
    stage: <Sorted />,
  },
  {
    title: "One substance, many products",
    caption:
      "Every one of these is ibuprofen, and every one is made by a different company. A pharmacy hands over whichever is on the shelf.",
    aside: null,
    stage: <Shelf />,
  },
  {
    title: "Are they the same?",
    caption:
      "Despite being derived from the same substance, the labels between them often disagree. We show you these disagreements per concept.",
    aside: null,
    stage: <Grid rows={MATRIX} legend />,
  },
  {
    title: "What do they disagree on?",
    caption:
      "Find out and analyse exactly where each product stands.", 
    aside: null,
    stage: <Disagreement />,
  },
  {
    title: "See why they disagree",
    caption:
      "Every verdict on this site opens onto the words that earned it. One product says ibuprofen must not be given to a child under six, while the other five products file it under a warning instead.",
    aside: null,
    stage: <Disagreement expand={EVIDENCE.placement} />,
  },
  {
    title: "You are ready to go!",
    caption:
      "Select any product to get started. And remember to be well informed before replacing one generic for another!",
    aside: null,
    stage: <Conclusion />,
  },
];
