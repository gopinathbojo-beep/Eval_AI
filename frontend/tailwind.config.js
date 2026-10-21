const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: v("paper"), surface: v("surface"), sunken: v("sunken"), line: v("line"),
        ink: v("ink"), mute: v("mute"), pen: v("pen"), "pen-soft": v("pen-soft"),
        mark: v("mark"), "mark-soft": v("mark-soft"), ok: v("ok"), "ok-soft": v("ok-soft"),
        warn: v("warn"), "warn-soft": v("warn-soft"),
        // Notebook-cover sidebar and highlighter accent
        cover: v("cover"), "cover-ink": v("cover-ink"), "cover-line": v("cover-line"), "cover-brown": v("cover-brown"), hl: v("hl"),
        hover: v("hover"), brown: v("brown"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Noto Sans Tamil"', '"Nirmala UI"', "Latha", "system-ui", "sans-serif"],
        doc: ['"Source Serif 4"', '"Noto Serif Tamil"', '"Nirmala UI"', "Latha", "Georgia", "serif"],
        display: ['"Source Serif 4"', '"Noto Serif Tamil"', "Georgia", "serif"],
        brand: ['"Fraunces"', '"Source Serif 4"', "Georgia", "serif"],
      },
      boxShadow: {
        xs: "0 1px 0 0 rgb(var(--line))",
        // Index card: hairline plus a hard offset "sheet underneath"
        card: "0 1px 0 0 rgb(var(--line)), 3px 3px 0 0 rgb(var(--line) / 0.7)",
        pop: "0 18px 40px -12px rgb(var(--ink) / 0.28), 0 2px 6px -2px rgb(var(--ink) / 0.12)",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        rise: { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        stamp: {
          "0%": { opacity: "0", transform: "scale(1.25) rotate(-6deg)" },
          "60%": { opacity: "1", transform: "scale(0.96) rotate(-2deg)" },
          "100%": { transform: "scale(1) rotate(-2deg)" },
        },
      },
      animation: {
        fadeIn: "fadeIn .2s ease-out",
        rise: "rise .35s cubic-bezier(.2,.7,.2,1) both",
        stamp: "stamp .45s cubic-bezier(.2,.7,.2,1) both",
      },
    },
  },
  plugins: [],
};
