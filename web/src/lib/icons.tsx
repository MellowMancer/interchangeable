/**
 * The marks that stand in for a word where a word would be noise.
 *
 * Shared rather than declared per screen: a manufacturer count means the same thing on the
 * roster, on a comparison and on a label, and three drawings of it would drift. Only the
 * three quantities this project actually repeats have one — the rest of the interface says
 * what it means in words, because an icon nobody can name is worse than a short label.
 *
 * Inline SVG on `currentColor`, so each inherits whatever the row around it is doing.
 */
/** Inline, on `currentColor`, so an icon inherits whatever the row around it is doing. */
export const Glyph = ({ children }: { children: React.ReactNode }) => (
  <svg
    viewBox="0 0 24 24"
    width="14"
    height="14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

export const Makers = () => (
  <Glyph>
    <path d="M3 21V9l6 3V9l6 3V9l6 3v9z" />
  </Glyph>
);

export const Concepts = () => (
  <Glyph>
    <path d="M4 6h16M4 12h16M4 18h10" />
  </Glyph>
);

export const Diverges = () => (
  <Glyph>
    <path d="M4 12h6M14 6l6 6-6 6M10 12l4-6M10 12l4 6" />
  </Glyph>
);
