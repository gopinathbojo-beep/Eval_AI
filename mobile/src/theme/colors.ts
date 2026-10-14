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

export const darkColors: ThemeColors = {
  primary: "#00A8E8",        // ADEM Blue
  primaryDeep: "#071B2B",    // ADEM Navy
  secondary: "#22C7F2",      // ADEM Cyan
  brandGreen: "#25C878",     // ADEM Green
  lightGreen: "#55D98B",     // ADEM Light Green
  gradient: ["#00A8E8", "#25C878"],
  gradientStart: "#00A8E8",
  gradientEnd: "#25C878",
  background: "#071B2B",     // ADEM Navy Background
  surface: "#0B2638",        // ADEM Secondary Navy
  surfaceElevated: "#11344D",
  text: "#FFFFFF",
  textSecondary: "#94A3B8",  // ADEM Muted Text
  mutedText: "#66788A",
  border: "#173E5B",
  success: "#25C878",
  successSoft: "rgba(37, 200, 120, 0.16)",
  error: "#EF6262",          // ADEM Error
  errorSoft: "rgba(239, 98, 98, 0.16)",
  danger: "#EF6262",
  warning: "#F5A623",        // ADEM Warning
  warningSoft: "rgba(245, 166, 35, 0.16)",
  card: "#0B2638",
  tabBar: "#071B2B",
  tabBarActive: "#00A8E8",
  tabBarInactive: "#66788A",
  inputBackground: "#092233",
  penScore: "#EF6262",
};

export const lightColors: ThemeColors = {
  primary: "#00A8E8",        // ADEM Blue
  primaryDeep: "#071B2B",    // ADEM Navy
  secondary: "#22C7F2",      // ADEM Cyan
  brandGreen: "#25C878",     // ADEM Green
  lightGreen: "#55D98B",     // ADEM Light Green
  gradient: ["#00A8E8", "#22C7F2"],
  gradientStart: "#00A8E8",
  gradientEnd: "#22C7F2",
  background: "#F7FAFC",     // ADEM Background
  surface: "#FFFFFF",        // ADEM White
  surfaceElevated: "#F4F9FC",// ADEM Light Blue
  text: "#172B3A",           // ADEM Primary Text
  textSecondary: "#66788A",  // ADEM Secondary Text
  mutedText: "#94A3B8",      // ADEM Muted Text
  border: "#E2EAF0",         // ADEM Border
  success: "#25C878",
  successSoft: "rgba(37, 200, 120, 0.12)",
  error: "#EF6262",
  errorSoft: "rgba(239, 98, 98, 0.12)",
  danger: "#EF6262",
  warning: "#F5A623",
  warningSoft: "rgba(245, 166, 35, 0.12)",
  card: "#FFFFFF",
  tabBar: "#FFFFFF",
  tabBarActive: "#00A8E8",
  tabBarInactive: "#66788A",
  inputBackground: "#F4F9FC",
  penScore: "#C23B2E",
};
