import { Platform } from "react-native";

/*
 * "Examiner's Desk" palette, shared with the web app (frontend/src/index.css): cream exam paper,
 * teal fountain ink, a coral marking pen and a yellow highlighter. Dark mode is "Midnight Slate & Teal".
 */
export interface ThemeColors {
  primary: string;
  /** Solid fill behind white text (buttons, active tabs); `primary` itself is for text and icons */
  primaryFill: string;
  /** Pale tint of the primary ink, for selected rows, soft buttons and icon wells */
  primarySoft: string;
  primaryDeep: string;
  secondary: string;
  brandGreen: string;
  lightGreen: string;
  gradient: [string, string];
  gradientStart: string;
  gradientEnd: string;
  background: string;
  surface: string;
  surfaceElevated: string;
  text: string;
  textSecondary: string;
  mutedText: string;
  border: string;
  success: string;
  successSoft: string;
  error: string;
  errorSoft: string;
  danger: string;
  warning: string;
  warningSoft: string;
  /** Highlighter yellow, for emphasis behind numbers that need the teacher's attention */
  highlight: string;
  card: string;
  tabBar: string;
  tabBarActive: string;
  tabBarInactive: string;
  inputBackground: string;
  penScore: string;
}

export const lightColors: ThemeColors = {
  primary: "#0E5E70",        // Teal fountain ink
  primaryFill: "#0F766E",    // Solid teal behind white text
  primarySoft: "#DEEEF0",
  primaryDeep: "#0A4552",
  secondary: "#0F766E",
  brandGreen: "#17734D",     // Green tick
  lightGreen: "#2E9E6B",
  gradient: ["#0F766E", "#0E5E70"],
  gradientStart: "#0F766E",
  gradientEnd: "#0E5E70",
  background: "#FAF5E6",     // Cream desk paper
  surface: "#FFFCF3",        // Fresh answer sheet
  surfaceElevated: "#F3ECDA",// Folded margin
  text: "#18211D",           // Green-black ink
  textSecondary: "#5A655F",  // Graphite
  mutedText: "#8A918C",
  border: "#E5DBC3",         // Pencil rule
  success: "#17734D",
  successSoft: "#E2F1E7",
  error: "#C43A28",          // Coral marking pen
  errorSoft: "#FBE7E1",
  danger: "#C43A28",
  warning: "#A86200",        // Amber query
  warningSoft: "#F9ECCD",
  highlight: "#FFD666",
  card: "#FFFCF3",
  tabBar: "#FFFCF3",
  tabBarActive: "#0E5E70",
  tabBarInactive: "#5A655F",
  inputBackground: "#FAF5E6",
  penScore: "#C43A28",
};

export const darkColors: ThemeColors = {
  primary: "#5EEAD4",        // Teal highlight
  primaryFill: "#0F766E",
  primarySoft: "#133A3F",
  primaryDeep: "#0B171B",
  secondary: "#2DD4BF",
  brandGreen: "#34D399",
  lightGreen: "#6EE7B7",
  gradient: ["#0F766E", "#115E59"],
  gradientStart: "#0F766E",
  gradientEnd: "#115E59",
  background: "#111827",     // Midnight slate
  surface: "#1F2937",
  surfaceElevated: "#283344",
  text: "#E5E7EB",
  textSecondary: "#9CA3AF",
  mutedText: "#6B7280",
  border: "#374151",
  success: "#34D399",
  successSoft: "#133A32",
  error: "#F87171",
  errorSoft: "#452026",
  danger: "#F87171",
  warning: "#FBBF24",
  warningSoft: "#423416",
  highlight: "#FBBF24",
  card: "#1F2937",
  tabBar: "#0B171B",         // Chalkboard cover
  tabBarActive: "#5EEAD4",
  tabBarInactive: "#9CA3AF",
  inputBackground: "#182130",
  penScore: "#F87171",
};

/** Serif for page titles and headings, like the web app's Source Serif; body text stays the system sans. */
export const fonts = {
  display: Platform.select({ ios: "Georgia", android: "serif", default: "Georgia" }) as string,
};
