import { Bar, Loading } from "@/lib/skeleton";

/** The reliability screen: prose, the benchmark summary, then the cases. */
export default function CollectorsLoading() {
  return (
    <Loading className="space-y-12">
      <header className="space-y-4">
        <Bar className="h-11 w-64" />
        <div className="max-w-prose space-y-2">
          <Bar className="h-4" />
          <Bar className="h-4" />
          <Bar className="h-4 w-3/4" />
        </div>
      </header>

      <section className="space-y-6">
        <Bar className="h-5 w-56" />
        <div className="max-w-prose space-y-2">
          <Bar className="h-4" />
          <Bar className="h-4" />
          <Bar className="h-4 w-2/3" />
        </div>
        <Bar className="h-24" />
        <ul className="grid border-t border-rule">
          {Array.from({ length: 4 }, (_, i) => (
            <li key={i} className="flex items-center justify-between gap-4 border-b border-rule py-4">
              <Bar className="h-4 w-56" />
              <Bar className="h-6 w-24 shrink-0" />
            </li>
          ))}
        </ul>
      </section>
    </Loading>
  );
}
