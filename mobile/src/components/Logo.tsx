import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";

interface LogoProps {
  size?: "small" | "medium" | "large";
  showSubtitle?: boolean;
}

export const Logo: React.FC<LogoProps> = ({ size = "medium", showSubtitle = true }) => {
  const { colors } = useTheme();

  const iconSize = size === "small" ? 22 : size === "medium" ? 34 : 48;
  const containerSize = size === "small" ? 36 : size === "medium" ? 52 : 72;
  const fontSize = size === "small" ? 18 : size === "medium" ? 26 : 34;

  return (
    <View style={styles.wrapper}>
      <View style={styles.row}>
        <LinearGradient
          colors={colors.gradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[
            styles.iconContainer,
            { width: containerSize, height: containerSize, borderRadius: containerSize * 0.28 },
          ]}
        >
          <MaterialCommunityIcons name="file-document-edit" size={iconSize} color="#FFFFFF" />
        </LinearGradient>
        <View style={styles.textContainer}>
          <Text style={[styles.title, { color: colors.text, fontSize }]}>ADEM</Text>
          {showSubtitle && (
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
              Smart Evaluation. Brighter Future.
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
    shadowColor: "#079FBD",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 8,
    elevation: 6,
  },
  textContainer: {
    marginLeft: 12,
  },
  title: {
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  subtitle: {
    fontSize: 11,
    fontWeight: "500",
    letterSpacing: 0.3,
    marginTop: 1,
  },
});
