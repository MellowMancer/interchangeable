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
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** How long a card holds before the shelf advances. Long enough to read a short one. */
const DWELL_MS = 7000;

export function Carousel({ children, label }: { children: ReactNode; label: string }) {
  const track = useRef<HTMLDivElement>(null);
  const [held, setHeld] = useState(false);
  const [height, setHeight] = useState<number>();

  /**
   * Size the shelf to what is on it, not to its tallest card.
   *
   * A flex row is as tall as its largest child, so one label listing nine indications
   * left a screenful of white under two one-line cards — the fatigue this shelf was
   * built to remove, reintroduced by its own layout.
   */
  const measure = useCallback(() => {
    const node = track.current;
    if (!node) return;
    const cards = [...node.children] as HTMLElement[];
    const visible = cards.filter(
      (card) =>
        card.offsetLeft + card.offsetWidth > node.scrollLeft + 1 &&
        card.offsetLeft < node.scrollLeft + node.clientWidth - 1,
    );
    const shown = visible.length ? visible : cards;
    setHeight(Math.max(...shown.map((card) => card.scrollHeight)));
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const step = useCallback((direction: 1 | -1) => {
    const node = track.current;
    if (!node) return;
    const card = node.firstElementChild as HTMLElement | null;
    const stride = card ? card.offsetWidth + 24 : node.clientWidth;
    const last = node.scrollWidth - node.clientWidth;
    // Wrapping rather than stopping: a shelf that silently dead-ends at the last card
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
      className="space-y-2"
    >
      <div
        ref={track}
        onScroll={() => {
          setHeld(true);
          measure();
        }}
        style={height ? { height } : undefined}
        aria-label={label}
        className="no-scrollbar flex snap-x items-start gap-6 overflow-x-auto scroll-smooth transition-[height] duration-300"
      >
        {children}
      </div>
      <div className="flex gap-2">
        <Arrow onClick={() => step(-1)} label="Previous">
          ←
        </Arrow>
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
    className="rounded-sheet border border-rule px-3 py-1 font-mono text-kicker text-ink-muted hover:border-accent hover:text-accent"
  >
    <span aria-hidden>{children}</span>
    <span className="sr-only">{label}</span>
  </button>
);
