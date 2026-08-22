import { Bar, Loading } from "@/lib/skeleton";

/**
 * One label, before it arrives. Shaped against `page.tsx`: a back link, the bordered
 * identity card, then the concepts as a two-column ruled list.
 *
 * The card's border is drawn here rather than left to a plain block — it is the strongest
 * shape on the screen, and a placeholder that omits it collapses into loose bars and then
 * snaps into a frame when the data lands.
 */
export default function ProductLoading() {
  return (
    <Loading className="space-y-12">
      <Bar className="h-3 w-52" />

      <header className="grid gap-8 border border-rule p-6 lg:grid-cols-[minmax(0,22rem)_1fr] lg:p-8">
        <div className="space-y-4">
          <div className="space-y-2">
            <Bar className="h-3 w-28" />
            <Bar className="h-10 w-full" />
            <Bar className="h-10 w-4/5" />
            <Bar className="h-3 w-44" />
          </div>
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="contents">
                <Bar className="h-3 w-28" />
                <Bar className="h-3 w-32" />
              </div>
            ))}
          </div>
          <Bar className="h-3 w-32" />
        </div>
        <div className="space-y-3">
          <Bar className="h-5 w-32" />
          <Bar className="h-4 w-3/4" />
        </div>
      </header>

      <section className="space-y-4">
        <Bar className="h-5 w-40" />
        <ul className="grid border-t border-rule lg:grid-cols-2">
          {Array.from({ length: 8 }, (_, i) => (
            <li
              key={i}
              className="flex items-center justify-between gap-4 border-b border-rule py-4 lg:odd:border-r lg:odd:pr-8 lg:even:pl-8"
            >
              <Bar className="h-4 w-40" />
              <Bar className="h-6 w-28 shrink-0" />
            </li>
          ))}
        </ul>
      </section>
    </Loading>
  );
}
