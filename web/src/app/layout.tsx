import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import { PLACEMENT_LEGEND } from "@/lib/placement";
import { Primer } from "@/lib/primer";
import { ScrollMemory } from "@/lib/scroll";
import { currentTheme, ThemeToggle } from "@/lib/theme";
import "./globals.css";

/**
 * Three faces, and which one is used says where the words came from.
 *
 * Serif is the label's own text, sans is what this application says about it, and mono
 * is anything a reader can check for themselves — a section code, a character range, a
 * collector id. The rule is worth keeping because it makes the page self-describing: a
 * quote can never be mistaken for our summary of a quote.
 */
const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
});

/**
 * No screen in this app may be prerendered: every one reads live pipeline state, and a
 * build-time snapshot of it would be a stale page rather than an error. Declared once
 * here because route segment config is inherited by every segment beneath it — asserting
 * it per page means the next page added silently freezes.
 */
export const dynamic = "force-dynamic";

const DESCRIPTION =
  "Where the manufacturers of the same active substance disagree about its label — with the quoted text behind every claim.";

export const metadata: Metadata = {
  title: {
    default: "Interchangeable?",
    template: "%s · Interchangeable?",
  },
  description: DESCRIPTION,
  openGraph: {
    title: "Interchangeable?",
    description: DESCRIPTION,
    siteName: "Interchangeable?",
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "Interchangeable?", description: DESCRIPTION },
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const theme = await currentTheme();

  return (
    <html
      lang="en"
      data-theme={theme === "system" ? undefined : theme}
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-paper font-sans text-body text-ink">
        <header className="border-b border-rule">
          <nav className="mx-auto flex max-w-7xl flex-wrap items-baseline justify-between gap-x-6 gap-y-3 px-6 py-5">
            <Link href="/" className="text-lg font-medium tracking-tight">
              Interchangeable<span className="text-accent">?</span>
            </Link>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-3">
              <Link
                href="/"
                className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
              >
                Home
              </Link>
              <Link
                href="/collectors"
                className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
              >
                Reliability
              </Link>
              <Link
                href="/reading"
                className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
              >
                How to read this
              </Link>
              <ThemeToggle />
            </div>
          </nav>
        </header>

        {/* Clipped, not hidden: the matrix has its own scroller, and `clip` leaves the
            sticky concept column inside it working. Without this a phone scrolls the whole
            page sideways instead of just the table. */}
        <main className="mx-auto w-full max-w-7xl flex-1 overflow-x-clip px-6 py-12">{children}</main>

        {/* The guide belongs to the whole site, not to one screen: the same five marks
            are drawn on the roster, the comparison, a label and the evidence. */}
        <footer className="mt-16 border-t border-rule">
          <div className="mx-auto max-w-7xl px-6 py-8">
            <dl className="flex flex-wrap gap-x-6 gap-y-3 text-meta text-ink-muted">
              {PLACEMENT_LEGEND.map((style) => (
                <div key={style.label} className="flex items-center gap-2">
                  <dt>
                    <span
                      className={`inline-flex min-w-16 items-baseline justify-center rounded-sheet border px-2 py-1 text-kicker tracking-wide uppercase ${style.className}`}
                    >
                      {style.section ? (
                        style.label
                      ) : (
                        <>
                          <span aria-hidden>&mdash;</span>
                          <span className="sr-only">{style.label}</span>
                        </>
                      )}
                    </span>
                  </dt>
                  <dd className="text-kicker text-ink-muted">{style.detail}</dd>
                </div>
              ))}
            </dl>
          </div>
        </footer>

        <ScrollMemory />
        <Primer />
      </body>
    </html>
  );
}
