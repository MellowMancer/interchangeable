import { Bar, Loading } from "@/lib/skeleton";

/**
 * The landing page, before the roster arrives.
 *
 * Shaped against `page.tsx` and `roster.tsx` rather than drawn generically: the hero is a
 * two-column grid whose right half only exists from `lg`, and the roster is a grid of
 * packs that widens with the viewport. A placeholder that reflows into a different layout
 * is worse than no placeholder, because the page moves under the reader twice.
 */
export default function RootLoading() {
  return (
    <Loading>
      <header className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)]">
        <div className="space-y-5">
          {/* The strapline sets in display size and lands on three lines. */}
          <div className="max-w-3xl space-y-2">
            <Bar className="h-11 w-full" />
            <Bar className="h-11 w-11/12" />
            <Bar className="h-11 w-3/5" />
          </div>
          <div className="max-w-prose space-y-2.5">
            <Bar className="h-4" />
            <Bar className="h-4" />
            <Bar className="h-4" />
            <Bar className="h-4 w-4/5" />
          </div>
          <Bar className="h-3 w-72" />
        </div>
        {/* The staged pair is `hidden lg:flex`, so its placeholder appears no earlier. */}
        <Bar className="hidden h-52 lg:block" />
      </header>

      <div className="space-y-3">
        <Bar className="h-3 w-48" />
        <div className="flex gap-3">
          <Bar className="h-14 w-full" />
          <Bar className="h-14 w-28 shrink-0" />
        </div>
      </div>

      <section className="space-y-6">
        <Bar className="h-5 w-48" />
        {/* One block per pack rather than the rules inside it: a pack is a bordered card
            of a settled height, and drawing its six blister cells in the pulse would be
            a picture of a box rather than a placeholder for one. */}
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <li key={i}>
              <Bar className="h-48" />
            </li>
          ))}
        </ul>
      </section>
    </Loading>
  );
}
