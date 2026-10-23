import React from "react";
import { View, Text, ActivityIndicator, StyleSheet, ViewStyle } from "react-native";
import { useTheme } from "../theme/ThemeContext";

interface LoadingProps {
  message?: string;
  style?: ViewStyle;
}

export const Loading: React.FC<LoadingProps> = ({ message = "Loading...", style }) => {
  const { colors } = useTheme();

  return (
    <View
      style={[styles.container, style]}
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={message || "Loading"}
      accessibilityLiveRegion="polite"
    >
      <ActivityIndicator size="large" color={colors.primary} />
      {message ? (
        <Text style={[styles.message, { color: colors.textSecondary }]}>
          {message}
        </Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    padding: 32,
    alignItems: "center",
    justifyContent: "center",
  },
  message: {
    marginTop: 12,
    fontSize: 14,
  },
});
