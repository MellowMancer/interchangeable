"use client";

/**
 * Where a reader was on each page, for as long as they are here.
 *
 * Moving between a substance, one of its concepts and a label is a loop, not a trip: the
 * comparison is the map and the other two are things looked up from it. Landing back at
 * the top of a matrix twenty rows after the one that was open makes the reader find their
 * place again every time, which is enough friction to stop them checking a second concept.
 *
 * The router already restores the browser's back and forward. This covers the rest —
 * arriving at a page by any route it has been read at before.
 *
 * Per path and per session. Where someone was in a table is a fact about what they are
 * doing now, and restoring it a week later would be a surprise rather than a courtesy.
 */

import { useEffect } from "react";
import { usePathname } from "next/navigation";

const key = (path: string) => `scroll:${path}`;

export function ScrollMemory() {
  const path = usePathname();

  useEffect(() => {
    let held = 0;
    try {
      held = Number(window.sessionStorage.getItem(key(path))) || 0;
    } catch {
      // Storage unavailable: the top of the page is a correct place to start.
    }

    // After paint, not during: the page is server-rendered but its height is not settled
    // until the browser has laid it out, and scrolling to 4000px of a 600px document does
    // nothing at all.
    const restore = requestAnimationFrame(() => {
      if (held > 0) window.scrollTo(0, held);
    });

    // Only a real position is worth keeping. The router scrolls to the top as it leaves a
    // page, and those events arrive before this effect is torn down — recording them
    // overwrote the place the reader had actually reached with a zero, every time.
    // A page at the top needs no restoring, so nothing is lost by ignoring it.
    const remember = () => {
      if (window.scrollY <= 0) return;
      try {
        window.sessionStorage.setItem(key(path), String(window.scrollY));
      } catch {
        // Not being able to remember is not a reason to interrupt scrolling.
      }
    };

    window.addEventListener("scroll", remember, { passive: true });
    return () => {
      cancelAnimationFrame(restore);
      window.removeEventListener("scroll", remember);
    };
  }, [path]);

  return null;
}
