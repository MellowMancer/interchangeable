import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
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

export const metadata: Metadata = {
  title: "Interchangeable?",
  description:
    "Where the manufacturers of the same active substance disagree about its label.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-paper font-sans text-body text-ink">
        <header className="border-b border-rule">
          <nav className="mx-auto flex max-w-6xl items-baseline justify-between gap-6 px-6 py-5">
            <Link href="/" className="text-lg font-medium tracking-tight">
              Interchangeable<span className="text-accent">?</span>
            </Link>
            <div className="flex items-baseline gap-6">
              <Link
                href="/substances"
                className="font-mono text-kicker tracking-widest text-ink-muted uppercase hover:text-ink"
              >
                Substances
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
                Reading
              </Link>
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-12">{children}</main>

        <footer className="mt-16 border-t border-rule">
          <p className="mx-auto max-w-6xl px-6 py-6 text-meta text-ink-muted">
            Not medical advice. Every quote is sliced from the stored section text at the
            character offsets shown, so any claim here can be checked against its source.
          </p>
        </footer>
      </body>
    </html>
  );
}
