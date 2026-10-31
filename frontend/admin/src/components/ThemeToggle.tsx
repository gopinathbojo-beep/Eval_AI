import { useId, type MouseEvent } from "react";
import { useTheme } from "../context/Theme";

const EASE = "cubic-bezier(.4,0,.2,1)";
const RAYS = Array.from({ length: 8 }, (_, i) => (i * Math.PI) / 4);

/**
 * Sun / moon button. Light: amber sun with rays. Click: rays spin away, the core grows and a shadow
 * slides in to carve a crescent moon, and the page switches theme with a reveal from the button.
 */
export function ThemeToggle({ className = "", menuItem = false }: { className?: string; menuItem?: boolean }) {
  const { resolved, toggle } = useTheme();
  const dark = resolved === "dark";
  const maskId = `moon-cut-${useId().replace(/:/g, "")}`;
  const t = (props: string) => `${props} 0.5s ${EASE}`;

  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    toggle({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
  };

  return (
    <button
      type="button"
      role={menuItem ? "menuitem" : undefined}
      onClick={onClick}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className={
        menuItem
          ? `flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-ink transition-ui hover:bg-hover hover:text-brown ${className}`
          : `flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface transition-colors hover:bg-hover ${
              dark ? "text-ink" : "text-warn"
            } ${className}`
      }
    >
      <svg
        viewBox="0 0 24 24"
        className={menuItem ? `h-4 w-4 shrink-0 ${dark ? "text-ink" : "text-warn"}` : "h-5 w-5"}
        aria-hidden
        style={{ transform: dark ? "rotate(40deg)" : "rotate(0deg)", transition: t("transform") }}
      >
        <mask id={maskId}>
          <rect width="24" height="24" fill="white" />
          {/* The shadow that turns the sun into a crescent; parked off-canvas in light mode */}
          <circle
            cx="17"
            cy="7"
            r="7"
            fill="black"
            style={{ transform: dark ? "translate(0px, 0px)" : "translate(10px, -10px)", transition: t("transform") }}
          />
        </mask>
        <circle
          cx="12"
          cy="12"
          r="8"
          fill="currentColor"
          mask={`url(#${maskId})`}
          style={{ transformOrigin: "12px 12px", transform: dark ? "scale(1)" : "scale(0.55)", transition: t("transform") }}
        />
        <g
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          style={{
            transformOrigin: "12px 12px",
            transform: dark ? "rotate(-90deg) scale(0.4)" : "rotate(0deg) scale(1)",
            opacity: dark ? 0 : 1,
            transition: `${t("transform")}, ${t("opacity")}`,
          }}
        >
          {RAYS.map((a) => (
            <line
              key={a}
              x1={12 + 7.2 * Math.cos(a)}
              y1={12 + 7.2 * Math.sin(a)}
              x2={12 + 9.8 * Math.cos(a)}
              y2={12 + 9.8 * Math.sin(a)}
            />
          ))}
        </g>
      </svg>
      {menuItem && (dark ? "Light mode" : "Dark mode")}
    </button>
  );
}
