"use client";

/**
 * A quiet offer of the vocabulary, once.
 *
 * The screens are full of words that carry a specific meaning here — contraindication,
 * excipient, concept, placement — and a reader who guesses at them will most likely guess
 * that an unmarked cell means the label omits something, which is the one reading this
 * project exists to prevent. The home page links to the guide, but most people arrive on a
 * substance from a search and never see it.
 *
 * Unintrusive is the whole specification: it takes a corner rather than the screen, it
 * never covers what it interrupts, and dismissing it is remembered for good. It also does
 * not appear where it would be noise — on the guide itself, or on the home page, which
 * already offers the same link in its own words.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** Remembered across visits, not just this one: being told twice is being nagged. */
const DISMISSED = "primer-dismissed";

export function Primer() {
  const path = usePathname();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (path === "/" || path === "/reading") return;
    try {
      if (window.localStorage.getItem(DISMISSED)) return;
    } catch {
      // Storage unavailable: offering the guide is still the right default.
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setShow(true);
  }, [path]);

  if (!show) return null;

  const dismiss = () => {
    setShow(false);
    try {
      window.localStorage.setItem(DISMISSED, "1");
    } catch {
      // Not being able to remember is not a reason to keep showing it this session.
    }
  };

  return (
    <aside className="fixed right-6 bottom-6 z-30 w-[22rem] max-w-[calc(100vw-3rem)] rounded-sheet border border-rule bg-paper p-5 shadow-[0_22px_48px_-24px_rgba(0,0,0,0.6)]">
      <p className="text-body text-ink-muted">
        Words like <span className="text-ink">contraindication</span>,{" "}
        <span className="text-ink">excipient</span> and{" "}
        <span className="text-ink">placement</span> mean something specific here.
      </p>
      <div className="mt-3 flex items-baseline justify-between gap-4">
        <Link
          href="/reading"
          onClick={dismiss}
          className="text-meta text-accent underline underline-offset-4 hover:text-ink"
        >
          How to read this →
        </Link>
        <button
          type="button"
          onClick={dismiss}
          className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
        >
          Dismiss
        </button>
      </div>
    </aside>
  );
}
