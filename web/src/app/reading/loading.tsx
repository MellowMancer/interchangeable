import { Bar, Loading } from "@/lib/skeleton";

/** How to read the comparison: an explainer, so the placeholder is prose and a key. */
export default function ReadingLoading() {
  return (
    <Loading className="space-y-16">
      <header className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="space-y-4">
          <Bar className="h-11 w-72" />
          <div className="max-w-prose space-y-2">
            <Bar className="h-4" />
            <Bar className="h-4" />
            <Bar className="h-4 w-5/6" />
          </div>
        </div>
        <Bar className="h-44" />
      </header>

      {Array.from({ length: 3 }, (_, i) => (
        <section key={i} className="space-y-4">
          <Bar className="h-5 w-48" />
          <div className="max-w-prose space-y-2">
            <Bar className="h-4" />
            <Bar className="h-4" />
            <Bar className="h-4 w-3/4" />
          </div>
        </section>
      ))}
    </Loading>
  );
}
