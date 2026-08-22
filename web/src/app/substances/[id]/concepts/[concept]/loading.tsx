import { Bar, Loading } from "@/lib/skeleton";

/**
 * One concept, before the evidence arrives.
 *
 * `Evidence` leads with `PlacementSpectrum` — a real table of manufacturer columns
 * against placement rows — and only then the wording blocks. The placeholder is built on
 * the same table so the columns do not resize when the labels land, which is the one
 * thing a wide scrolling grid must not do under a reader.
 */
export default function ConceptLoading() {
  return (
    <Loading className="space-y-10">
      <header className="space-y-4">
        <Bar className="h-3 w-32" />
        <Bar className="h-11 w-2/3 max-w-lg" />
        <Bar className="h-4 w-80 max-w-full" />
      </header>

      <figure className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <tbody>
              <tr>
                <td className="w-44 p-2" />
                {Array.from({ length: 6 }, (_, c) => (
                  <td key={c} className="space-y-1 p-2 align-top">
                    <Bar className="h-3 w-24" />
                    <Bar className="h-3 w-16" />
                  </td>
                ))}
              </tr>
              {Array.from({ length: 5 }, (_, r) => (
                <tr key={r} className="border-t border-rule">
                  <td className="w-44 space-y-1.5 p-2 align-top">
                    <Bar className="h-4 w-28" />
                    <Bar className="h-3 w-36" />
                  </td>
                  {Array.from({ length: 6 }, (_, c) => (
                    <td key={c} className="p-2 align-middle">
                      {(r + c) % 3 === 0 ? <Bar className="h-6 w-full" /> : null}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </figure>

      <ul className="section-break grid border-t border-rule lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <li
            key={i}
            className="space-y-3 border-b border-rule py-8 lg:odd:border-r lg:odd:pr-10 lg:even:pl-10"
          >
            <Bar className="h-6 w-32" />
            <Bar className="h-3 w-48" />
            <div className="max-w-prose space-y-2 border-l-2 border-rule pl-6">
              <Bar className="h-4" />
              <Bar className="h-4 w-11/12" />
              <Bar className="h-4 w-2/3" />
            </div>
          </li>
        ))}
      </ul>
    </Loading>
  );
}
