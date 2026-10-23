import React from "react";
import { View, Text, StyleSheet, ViewStyle } from "react-native";
import { useTheme } from "../theme/ThemeContext";

interface PenScoreProps {
  score: number | null | undefined;
  maxScore?: number | null;
  size?: "small" | "medium" | "large";
  overridden?: boolean;
  style?: ViewStyle;
}

export const PenScore: React.FC<PenScoreProps> = ({
  score,
  maxScore,
  size = "medium",
  overridden = false,
  style,
}) => {
  const { colors } = useTheme();

  const getDims = () => {
    switch (size) {
      case "small":
        return { fontSize: 13, maxFontSize: 10, padding: 4 };
      case "large":
        return { fontSize: 24, maxFontSize: 16, padding: 8 };
      default:
        return { fontSize: 16, maxFontSize: 12, padding: 6 };
    }
  };

  const dims = getDims();
  const penColor = colors.error; // Traditional teacher red pen

  if (score === null || score === undefined) {
    return (
      <View style={[styles.container, { borderColor: colors.border }, style]}>
        <Text style={[styles.scoreText, { fontSize: dims.fontSize, color: colors.textSecondary }]}>
          --
        </Text>
      </View>
    );
  }

  return (
    <View
      style={[
        styles.container,
        {
          borderColor: penColor,
          backgroundColor: "rgba(196, 58, 40, 0.08)",
          paddingHorizontal: dims.padding + 4,
          paddingVertical: dims.padding,
        },
        overridden && { borderWidth: 2 },
        style,
      ]}
    >
      <Text style={[styles.scoreText, { fontSize: dims.fontSize, color: penColor }]}>
        {score}
      </Text>
      {maxScore !== undefined && maxScore !== null && (
        <Text style={[styles.maxText, { fontSize: dims.maxFontSize, color: colors.textSecondary }]}>
          /{maxScore}
        </Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "baseline",
    borderRadius: 8,
    borderWidth: 1.5,
    alignSelf: "flex-start",
  },
  scoreText: {
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  maxText: {
    fontWeight: "500",
    marginLeft: 1,
  },
});
