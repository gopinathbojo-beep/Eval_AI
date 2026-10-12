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
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Noto Sans Tamil"', '"Nirmala UI"', "Latha", "system-ui", "sans-serif"],
        doc: ['"Source Serif 4"', '"Noto Serif Tamil"', '"Nirmala UI"', "Latha", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
