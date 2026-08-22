import { Bar, Loading } from "@/lib/skeleton";

/**
 * The landing page, before the roster arrives.
 *
 * Shaped against `page.tsx` and `roster.tsx` rather than drawn generically: the hero is a
 * two-column grid whose right half only exists from `lg`, and the roster is a two-column
 * bordered list, not a card grid. A placeholder that reflows into a different layout is
 * worse than no placeholder, because the page moves under the reader twice.
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
        <Bar className="h-3 w-44" />
        <div className="flex gap-3">
          <Bar className="h-14 w-full" />
          <Bar className="h-14 w-28 shrink-0" />
        </div>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <Bar className="h-6 w-44" />
      </div>

      <section className="space-y-6">
        <Bar className="h-5 w-48" />
        <ul className="grid border-t border-rule md:grid-cols-2">
          {Array.from({ length: 6 }, (_, i) => (
            <li
              key={i}
              className="space-y-4 border-b border-rule p-6 md:odd:border-r md:odd:last:border-r-0"
            >
              <Bar className="h-5 w-40" />
              <div className="flex gap-4">
                <Bar className="h-3 w-20" />
                <Bar className="h-3 w-24" />
              </div>
              <div className="space-y-1.5">
                <Bar className="h-3" />
                <Bar className="h-3 w-5/6" />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </Loading>
  );
}
