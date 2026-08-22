"use client";

/**
 * A horizontal shelf that advances itself, with arrows for a reader who would rather not
 * wait.
 *
 * Client only for the scroll mechanics — a timer and two buttons. The cards are passed in
 * as children, so whatever is on the shelf is still rendered on the server and this ships
 * no markup of its own.
 *
 * It stops the moment a reader engages with it. These cards carry clinical sentences, and
 * text that slides away mid-sentence is worse than text that never moved; hover, focus or
 * a manual scroll all hold it, and `prefers-reduced-motion` means it never starts.
 *
 * The shelf is as tall as its tallest card and stays that height. Sizing it to whatever is
 * in view was tried and is worse: the page reflows under the reader every few seconds,
 * which is more distracting than the white it saves.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** How long a card holds before the shelf advances. Long enough to read a short one. */
const DWELL_MS = 7000;

/** Matches the `gap-6` between cards, so a step lands one card along rather than near it. */
const GAP_PX = 24;

export function Carousel({
  children,
  label,
  heading,
  count,
}: {
  children: ReactNode;
  label: string;
  /** Rendered on the control row, so the arrows sit beside what they move. */
  heading?: ReactNode;
  count?: number;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [held, setHeld] = useState(false);

  const step = useCallback((direction: 1 | -1) => {
    const node = track.current;
    if (!node) return;
    const card = node.firstElementChild as HTMLElement | null;
    const stride = card ? card.offsetWidth + GAP_PX : node.clientWidth;
    const last = node.scrollWidth - node.clientWidth;
    // Wrapping rather than stopping: a shelf that silently dead-ends at its last card
    // looks broken, and there is no order here worth preserving an end to.
    const wrapped =
      direction === 1 && node.scrollLeft >= last - 1
        ? 0
        : direction === -1 && node.scrollLeft <= 1
          ? last
          : node.scrollLeft + direction * stride;
    node.scrollTo({ left: wrapped, behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (held) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => step(1), DWELL_MS);
    return () => window.clearInterval(timer);
  }, [held, step]);

  return (
    <div
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocusCapture={() => setHeld(true)}
      onBlurCapture={() => setHeld(false)}
      className="min-w-0 space-y-2"
    >
      {heading}

      <div
        ref={track}
        onScroll={() => setHeld(true)}
        aria-label={label}
        className="no-scrollbar flex snap-x items-stretch gap-6 overflow-x-auto scroll-smooth"
      >
        {children}
      </div>

      {/* Centred beneath the shelf, where a reader looks for them. Left-aligned under a
          tall track they read as leftover page furniture rather than as the control that
          moves the cards. */}
      <div className="flex items-center justify-center gap-3 pt-1">
        <Arrow onClick={() => step(-1)} label="Previous">
          ←
        </Arrow>
        {count !== undefined && (
          <span className="font-mono text-kicker text-ink-muted">
            {count} in all
          </span>
        )}
        <Arrow onClick={() => step(1)} label="Next">
          →
        </Arrow>
      </div>
    </div>
  );
}

const Arrow = ({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex size-8 items-center justify-center rounded-full border border-rule bg-paper text-ink-muted transition-colors hover:border-accent hover:bg-accent hover:text-paper"
  >
    <span aria-hidden>{children}</span>
    <span className="sr-only">{label}</span>
  </button>
);
