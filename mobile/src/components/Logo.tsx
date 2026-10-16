import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";

interface LogoProps {
  size?: "small" | "medium" | "large";
  showSubtitle?: boolean;
}

export const Logo: React.FC<LogoProps> = ({ size = "medium", showSubtitle = true }) => {
  const { colors, isDark } = useTheme();

  const iconSize = size === "small" ? 20 : size === "medium" ? 30 : 42;
  const containerSize = size === "small" ? 36 : size === "medium" ? 52 : 68;
  const fontSize = size === "small" ? 18 : size === "medium" ? 24 : 32;

  return (
    <View style={styles.wrapper}>
      <View style={styles.row}>
        <LinearGradient
          colors={colors.gradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[
            styles.iconContainer,
            {
              width: containerSize,
              height: containerSize,
              borderRadius: containerSize * 0.28,
              shadowColor: colors.primary,
              shadowOpacity: isDark ? 0.4 : 0.2,
            },
          ]}
        >
          <Ionicons name="school" size={iconSize} color="#FFFFFF" />
        </LinearGradient>
        <View style={styles.textContainer}>
          <Text style={[styles.title, { color: colors.text, fontSize }]}>Eval AI</Text>
          {showSubtitle && (
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
              Academic Evaluation Platform
            </Text>
          )}
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    alignItems: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
  },
  iconContainer: {
    justifyContent: "center",
    alignItems: "center",
    shadowOffset: { width: 0, height: 3 },
    shadowRadius: 6,
    elevation: 4,
  },
  textContainer: {
    marginLeft: 12,
  },
  title: {
    fontWeight: "800",
    letterSpacing: 0.8,
  },
  subtitle: {
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 0.3,
    marginTop: 1,
  },
});
