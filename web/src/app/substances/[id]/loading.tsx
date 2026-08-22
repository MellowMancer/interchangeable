import { Bar, Loading } from "@/lib/skeleton";

/**
 * The comparison, before it arrives.
 *
 * The matrix block is deliberately tall: collapsing to a short placeholder and then
 * expanding moves everything below it, which is a worse flicker than waiting on a block
 * of roughly the right size.
 */
export default function SubstanceLoading() {
  return (
    <Loading className="space-y-12">
      <header className="space-y-4">
        <Bar className="h-3 w-36" />
        <Bar className="h-11 w-2/3 max-w-md" />
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <Bar className="h-3 w-32" />
          <Bar className="h-3 w-36" />
          <Bar className="h-3 w-52" />
        </div>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
          <div className="min-w-0 space-y-5">
            <Bar className="h-16" />
            <Bar className="h-28" />
          </div>
          <Bar className="h-52" />
        </div>
      </header>

      <Bar className="h-96" />

      <section className="section-break space-y-4">
        <Bar className="h-5 w-56" />
        <ul className="-mx-6 flex gap-4 overflow-hidden px-6 pb-2">
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className="w-64 shrink-0">
              <Bar className="h-44" />
            </li>
          ))}
        </ul>
      </section>
    </Loading>
  );
}
