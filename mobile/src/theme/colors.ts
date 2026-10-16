export interface ThemeColors {
  primary: string;
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
  card: string;
  tabBar: string;
  tabBarActive: string;
  tabBarInactive: string;
  inputBackground: string;
  penScore: string;
}

export const lightColors: ThemeColors = {
  primary: "#18447E",        // Academic Deep Navy
  primaryDeep: "#0F294A",    // Deep Navy Shade
  secondary: "#2B6CB0",      // Slate Blue
  brandGreen: "#16A34A",     // Verified Emerald Green
  lightGreen: "#22C55E",     // Light Green
  gradient: ["#18447E", "#2B6CB0"],
  gradientStart: "#18447E",
  gradientEnd: "#2B6CB0",
  background: "#F8FAFC",     // Neutral Academic Canvas
  surface: "#FFFFFF",        // Pure Surface
  surfaceElevated: "#F1F5F9",// Soft Slate Surface
  text: "#0F172A",           // High-contrast Slate 900
  textSecondary: "#475569",  // Readable Secondary Text
  mutedText: "#94A3B8",      // Subtitle / Placeholder Muted
  border: "#E2E8F0",         // Subtle Thin Border
  success: "#16A34A",
  successSoft: "rgba(22, 163, 74, 0.12)",
  error: "#DC2626",          // Error / Mark Red
  errorSoft: "rgba(220, 38, 38, 0.12)",
  danger: "#DC2626",
  warning: "#D97706",        // Amber Warning
  warningSoft: "rgba(217, 119, 6, 0.12)",
  card: "#FFFFFF",
  tabBar: "#FFFFFF",
  tabBarActive: "#18447E",
  tabBarInactive: "#64748B",
  inputBackground: "#F8FAFC",
  penScore: "#C23B2E",       // Teacher Pen Red
};

export const darkColors: ThemeColors = {
  primary: "#60A5FA",        // Light Academic Blue
  primaryDeep: "#0F172A",
  secondary: "#38BDF8",      // Sky Accent
  brandGreen: "#22C55E",     // Emerald
  lightGreen: "#4ADE80",
  gradient: ["#1E3A8A", "#2563EB"],
  gradientStart: "#1E3A8A",
  gradientEnd: "#2563EB",
  background: "#0B132B",     // Deep Slate Navy Background
  surface: "#132238",        // Dark Card Surface
  surfaceElevated: "#1C304A",// Elevated Dark Surface
  text: "#F8FAFC",           // Light Crisp Text
  textSecondary: "#94A3B8",  // Slate Muted
  mutedText: "#64748B",
  border: "#233852",
  success: "#22C55E",
  successSoft: "rgba(34, 197, 94, 0.16)",
  error: "#F87171",
  errorSoft: "rgba(248, 113, 113, 0.16)",
  danger: "#F87171",
  warning: "#FBBF24",
  warningSoft: "rgba(251, 191, 36, 0.16)",
  card: "#132238",
  tabBar: "#0B132B",
  tabBarActive: "#60A5FA",
  tabBarInactive: "#64748B",
  inputBackground: "#0E1B2E",
  penScore: "#F87171",
};
