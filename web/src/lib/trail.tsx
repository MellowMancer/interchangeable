"use client";

/**
 * Where the reader came from, as a stack rather than a single breadcrumb.
 *
 * A comparison is reached *from* a box someone is holding, and a box is often reached from
 * another comparison. Remembering only the last product answered the wrong question: after
 * a browser Back the stored value described the page the reader had just retreated *from*,
 * so the way back pointed forward.
 *
 * So this keeps the path, not the last step. Arriving at a page already on the trail
 * truncates to it rather than pushing — which is exactly what a Back is — and arriving
 * anywhere else pushes. That keeps the trail in step with the browser's own history
 * without trying to observe it, and makes the offered way back the page actually behind
 * this one, whether that is a product, a comparison, or the index.
 *
 * Session storage for the same reason the column filter uses it (`chosen:{id}`): a path
 * through the site is a fact about what someone is doing now, not a preference worth
 * keeping next week.
 *
 * Read after mount rather than during render, because the server has no session storage
 * and a differing first paint would be a hydration mismatch. Until it is read — and
 * whenever the trail is empty — the link is the index, which is a true statement about
 * where back leads rather than a name nobody supplied.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

const TRAIL = "trail";

/** Deep enough for any real path through the site, bounded so a long session cannot grow it forever. */
const DEPTH = 20;

type Step = { href: string; label: string };

const INDEX: Step = { href: "/", label: "All products" };

/** Parsed defensively: anything stored under this key is untrusted by the time it is read. */
function stored(): Step[] {
  try {
    const raw = window.sessionStorage.getItem(TRAIL);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (step): step is Step =>
        typeof step === "object" &&
        step !== null &&
        typeof (step as Step).href === "string" &&
        typeof (step as Step).label === "string",
    );
  } catch {
    return [];
  }
}

/**
 * Records this page on the trail and offers the way back off it.
 *
 * One component rather than two, because the answer depends on the write: what is behind
 * this page is only known once this page has been placed on the trail.
 */
export function Back({ href, label }: { href: string; label: string }) {
  const [previous, setPrevious] = useState<Step | null>(null);

  useEffect(() => {
    const trail = stored();
    const seen = trail.findIndex((step) => step.href === href);
    // Already on the trail means the reader came back to it; anything else is a step out.
    const next =
      seen >= 0 ? trail.slice(0, seen + 1) : [...trail, { href, label }].slice(-DEPTH);
    try {
      window.sessionStorage.setItem(TRAIL, JSON.stringify(next));
    } catch {
      // Not being able to remember the path costs the name on the link, nothing else.
    }
    // The trail is external state read after mount, which is what this effect is for;
    // the same suppression sits on `Primer` for the same reason.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPrevious(next.length > 1 ? next[next.length - 2] : null);
  }, [href, label]);

  const target = previous ?? INDEX;
  return (
    <Link href={target.href} className="font-mono text-kicker text-ink-muted hover:text-ink">
      ← {target.label}
    </Link>
  );
}
