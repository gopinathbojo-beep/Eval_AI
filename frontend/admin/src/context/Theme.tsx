import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";

/** Light / Dark / follow the OS. Stored under the same key the boot script in index.html reads. */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "adem_theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

interface ThemeCtx {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference(p: ThemePreference): void;
  /** Switch light <-> dark with an animated reveal spreading from `origin` (e.g. the clicked button). */
  toggle(origin?: { x: number; y: number }): void;
}
const Ctx = createContext<ThemeCtx>(null!);
export const useTheme = () => useContext(Ctx);

function readPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* storage blocked: fall through to the default */
  }
  return "system";
}

const systemTheme = (): ResolvedTheme =>
  typeof window !== "undefined" && window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";

function applyTheme(theme: ResolvedTheme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPref] = useState<ThemePreference>(readPreference);
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme);
  const resolved: ResolvedTheme = preference === "system" ? system : preference;

  // Track OS changes live so "System" switches without a reload
  useEffect(() => {
    const mq = window.matchMedia?.(DARK_QUERY);
    if (!mq) return;
    const onChange = () => setSystem(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => applyTheme(resolved), [resolved]);

  const setPreference = useCallback((p: ThemePreference) => {
    setPref(p);
    try {
      localStorage.setItem(STORAGE_KEY, p);
    } catch {
      /* preference still applies for this session */
    }
  }, []);

  const toggle = useCallback(
    (origin?: { x: number; y: number }) => {
      const next: ResolvedTheme = resolved === "dark" ? "light" : "dark";
      const commit = () => {
        flushSync(() => setPreference(next));
        applyTheme(next); // DOM must change inside the transition callback, not after React's effect
      };
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) return commit();

      if (!document.startViewTransition) {
        // Fallback: brief cross-fade of colours (see .theme-fade in index.css)
        const root = document.documentElement;
        root.classList.add("theme-fade");
        commit();
        window.setTimeout(() => root.classList.remove("theme-fade"), 450);
        return;
      }

      // Circular reveal of the new theme, growing from the toggle to the farthest corner
      const x = origin?.x ?? window.innerWidth - 40;
      const y = origin?.y ?? 28;
      const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
      const transition = document.startViewTransition(commit);
      transition.ready
        .then(() =>
          document.documentElement.animate(
            { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
            { duration: 550, easing: "cubic-bezier(.4,0,.2,1)", pseudoElement: "::view-transition-new(root)" },
          ),
        )
        .catch(() => {
          /* transition skipped (e.g. tab hidden): theme is already applied */
        });
    },
    [resolved, setPreference],
  );

  return <Ctx.Provider value={{ preference, resolved, setPreference, toggle }}>{children}</Ctx.Provider>;
}
