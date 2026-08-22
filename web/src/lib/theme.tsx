import type { ReactNode } from "react";
import { cookies } from "next/headers";

/**
 * The reader's theme, chosen server-side.
 *
 * Held in a cookie rather than `localStorage` so the server renders the right theme on
 * the first byte. The `localStorage` approach needs a blocking inline script to read the
 * value before paint, and without one the reader sees a flash of the other theme — which
 * on a page whose whole palette inverts is the most visible defect it could have.
 *
 * It also keeps the toggle out of client JavaScript entirely: a form and a server action,
 * so nothing here hydrates and the application still ships no client components.
 */
export const THEME_COOKIE = "theme";

/** The choices, in the order the control cycles them. `system` is the absence of a cookie. */
export const THEMES = ["system", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

const isTheme = (value: string | undefined): value is Theme =>
  THEMES.includes(value as Theme);

/** The stored choice, or `system` when nothing was ever chosen or the value is unknown. */
export async function currentTheme(): Promise<Theme> {
  const stored = (await cookies()).get(THEME_COOKIE)?.value;
  return isTheme(stored) ? stored : "system";
}

/**
 * Records a theme, or clears the cookie when the reader returns to following the system.
 *
 * The value is validated against the same list the control renders, so a hand-written
 * form post cannot put an arbitrary string into the `data-theme` attribute.
 */
export async function chooseTheme(formData: FormData): Promise<void> {
  "use server";

  const wanted = formData.get(THEME_COOKIE);
  const theme = typeof wanted === "string" && isTheme(wanted) ? wanted : "system";
  const jar = await cookies();

  if (theme === "system") jar.delete(THEME_COOKIE);
  else jar.set(THEME_COOKIE, theme, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
}

/**
 * One mark per choice, drawn rather than named.
 *
 * The nav beside this is entirely links, so three words reading SYSTEM LIGHT DARK read as
 * three more destinations. An icon is unambiguously a control. Inline SVG on
 * `currentColor`, so it inherits the same hover the links use and needs no asset.
 */
const ICONS: Record<Theme, ReactNode> = {
  system: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none" />
    </>
  ),
  light: (
    <>
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M19.1 4.9l-1.5 1.5M6.4 17.6l-1.5 1.5" />
    </>
  ),
  dark: <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" />,
};

/**
 * A single button showing the theme in force and switching to the next one.
 *
 * Cycling rather than three buttons: the choice is small enough that a reader can reach
 * any of them in at most two presses, and one control takes the space of one nav item
 * instead of dominating the header.
 */
export async function ThemeToggle() {
  const active = await currentTheme();
  const next = THEMES[(THEMES.indexOf(active) + 1) % THEMES.length];
  const description = `Colour theme: ${active}. Switch to ${next}.`;

  return (
    <form action={chooseTheme} className="flex self-center">
      <button
        type="submit"
        name={THEME_COOKIE}
        value={next}
        title={description}
        className="rounded-sheet border border-transparent p-1.5 text-ink-muted hover:border-rule hover:text-ink"
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          aria-hidden
        >
          {ICONS[active]}
        </svg>
        <span className="sr-only">{description}</span>
      </button>
    </form>
  );
}
