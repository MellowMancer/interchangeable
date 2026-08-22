/**
 * What a section is called.
 *
 * One component because every screen had its own copy of the same muted mono line, and a
 * page of eight of them read as one texture — nothing on it looked more important than
 * anything else, least of all the finding.
 *
 * A heading has to out-weigh what it introduces and sit closer to it than to what came
 * before. Size and weight do the first; `section-break` does the second, by putting most
 * of the space above the heading rather than around it. Before that, a 13px lettered label
 * sat equidistant between two blocks of 16px text and belonged to neither.
 *
 * Sentence case in the serif, matching the substance and product names it sits under, so
 * a page reads as one document rather than a stack of panels. Mono stays for what a reader
 * can check — a section code, an offset, a date.
 */
export const Section = ({ children }: { children: React.ReactNode }) => (
  <h2 className="flex items-center gap-3 font-serif text-quote font-normal tracking-tight text-ink">
    <span aria-hidden className="h-6 w-1.5 shrink-0 rounded-sheet bg-accent" />
    {children}
  </h2>
);

