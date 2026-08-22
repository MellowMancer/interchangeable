/**
 * The shapes a screen shows while its data is still in flight.
 *
 * Every other animation in this application is choreography over finished content, and
 * `globals.css` is emphatic that none of it may imply waiting. This is the exception that
 * proves it: the corpus is served from a free instance with a tenth of a CPU, so a
 * navigation is a genuine wait. Acknowledging it honestly is the opposite of dressing a
 * finished page up as a loading one — without this, a click changed nothing on screen
 * until the whole response arrived, which read as a broken link rather than a slow one.
 *
 * The pulse is confined to this file so no ordinary screen can borrow it.
 */

const SHAPE = "block rounded-sheet bg-rule animate-pulse motion-reduce:animate-none";

/** One placeholder block. Sized by the caller, because only it knows what is coming. */
export function Bar({ className = "" }: { className?: string }) {
  return <span className={`${SHAPE} ${className}`} />;
}

/**
 * The masthead every screen opens with: a title, and the marks that qualify it.
 *
 * Shared rather than repeated per route so the shapes cannot drift apart from each other
 * while the real headers stay in step.
 */
export function HeaderSkeleton({ back = false }: { back?: boolean }) {
  return (
    <header className="space-y-4">
      {back ? <Bar className="h-3 w-32" /> : null}
      <Bar className="h-11 w-2/3 max-w-md" />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <Bar className="h-3 w-28" />
        <Bar className="h-3 w-32" />
        <Bar className="h-3 w-40" />
      </div>
    </header>
  );
}

/**
 * A screen's worth of placeholder, with the announcement screen readers need.
 *
 * `role="status"` rather than a live region per shape: one polite announcement per
 * navigation, not one per bar.
 */
export function Loading({
  children,
  className = "space-y-12",
}: {
  children: React.ReactNode;
  /** The page's own wrapper spacing, so the placeholder does not reflow into it. */
  className?: string;
}) {
  return (
    <div className={className} role="status" aria-live="polite">
      <span className="sr-only">Loading</span>
      {children}
    </div>
  );
}
