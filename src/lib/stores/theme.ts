import { get, writable } from "svelte/store";
export type ThemePreference = "light" | "dark" | "system";
export const themePreference = writable<ThemePreference>("system");
export const effectiveTheme = writable<"light" | "dark">("light");
let users = 0;
let media: MediaQueryList | undefined;
let cleanup: (() => void) | undefined;
const valid = (value: unknown): value is ThemePreference => value === "light" || value === "dark" || value === "system";

function apply() {
  if (typeof document === "undefined") return;
  const choice = get(themePreference);
  const dark = choice === "dark" || (choice === "system" && Boolean(media?.matches));
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  document.documentElement.classList.toggle("dark", dark);
  effectiveTheme.set(dark ? "dark" : "light");
}
export function setTheme(value: ThemePreference) {
  if (!valid(value)) return;
  themePreference.set(value);
  try { window.localStorage.setItem("theme", value); } catch { /* Current session remains usable. */ }
  apply();
}
export function toggleTheme() { setTheme(get(effectiveTheme) === "dark" ? "light" : "dark"); }
export function initializeTheme(): () => void {
  if (typeof window === "undefined") return () => {};
  if (users++ === 0) {
    let stored: string | null = null;
    try { stored = window.localStorage.getItem("theme"); } catch { /* Use the system preference. */ }
    themePreference.set(valid(stored) ? stored : "system");
    media = window.matchMedia("(prefers-color-scheme: dark)");
    const changed = () => apply();
    const synced = (event: StorageEvent) => {
      if (event.key === "theme") { themePreference.set(valid(event.newValue) ? event.newValue : "system"); apply(); }
    };
    media.addEventListener("change", changed);
    window.addEventListener("storage", synced);
    cleanup = () => { media?.removeEventListener("change", changed); window.removeEventListener("storage", synced); media = undefined; };
    apply();
  }
  let released = false;
  return () => { if (!released) { released = true; if (--users === 0) { cleanup?.(); cleanup = undefined; } } };
}
