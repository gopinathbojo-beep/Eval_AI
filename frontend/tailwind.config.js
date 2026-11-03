const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
/** @type {import('tailwindcss').Config} */
export default {
  // `dark:` variants follow <html data-theme="dark"> (set by context/Theme.tsx and the boot script in index.html)
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: v("paper"), surface: v("surface"), sunken: v("sunken"), line: v("line"),
        ink: v("ink"), mute: v("mute"), pen: v("pen"), "pen-soft": v("pen-soft"),
        mark: v("mark"), "mark-soft": v("mark-soft"), ok: v("ok"), "ok-soft": v("ok-soft"),
        warn: v("warn"), "warn-soft": v("warn-soft"),
        // Modern sidebar and accent
        cover: v("cover"), "cover-ink": v("cover-ink"), "cover-line": v("cover-line"), "cover-brown": v("cover-brown"), hl: v("hl"),
        hover: v("hover"), brown: v("brown"), "on-pen": v("on-pen"),
      },
      // Solid teal behind text uses its own fill token: #0f766e in dark (white text) while
      // text-pen / border-pen / ring-pen stay the bright #2dd4bf / #0d9488 highlight.
      backgroundColor: { pen: v("pen-fill") },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '"Noto Sans Tamil"', '"Nirmala UI"', "system-ui", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "Roboto", "sans-serif"],
        doc: ['"Plus Jakarta Sans"', '"Noto Sans Tamil"', '"Nirmala UI"', "system-ui", "sans-serif"],
        display: ['"Plus Jakarta Sans"', '"Noto Sans Tamil"', "system-ui", "sans-serif"],
        brand: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        card: "0 1px 3px 0 rgb(0 0 0 / 0.05), 0 1px 2px -1px rgb(0 0 0 / 0.05)",
        pop: "0 10px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideIn: { from: { transform: "translateX(100%)" }, to: { transform: "none" } },
        rise: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        fadeIn: "fadeIn .15s ease-out",
        rise: "rise .2s cubic-bezier(.2,.7,.2,1) both",
      },
    },
  },
  plugins: [],
};
