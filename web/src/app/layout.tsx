import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <header className="border-b border-slate-200 dark:border-slate-800">
          <nav className="mx-auto flex max-w-7xl items-baseline gap-6 px-6 py-4">
            <Link href="/" className="font-semibold tracking-tight">
              Interchangeable<span className="text-red-600">?</span>
            </Link>
            <Link
              href="/collectors"
              className="text-sm text-slate-600 hover:underline dark:text-slate-400"
            >
              Collector health
            </Link>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">{children}</main>
        <footer className="border-t border-slate-200 px-6 py-4 text-xs text-slate-500 dark:border-slate-800">
          Not medical advice. Every quote is sliced from the stored section text at the
          character offsets shown, so any claim here can be checked against its source.
        </footer>
      </body>
    </html>
  );
}
