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

/** The choices, in the order the control offers them. `system` is the absence of a cookie. */
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

export async function ThemeToggle() {
  const active = await currentTheme();

  return (
    <form action={chooseTheme} className="flex items-center gap-px">
      <span className="sr-only">Colour theme</span>
      {THEMES.map((theme) => (
        <button
          key={theme}
          type="submit"
          name={THEME_COOKIE}
          value={theme}
          aria-pressed={theme === active}
          className={`rounded-sheet border px-2 py-1 font-mono text-kicker tracking-widest uppercase ${
            theme === active
              ? "border-rule bg-rule/50 text-ink"
              : "border-transparent text-ink-muted hover:text-ink"
          }`}
        >
          {theme}
        </button>
      ))}
    </form>
  );
}
