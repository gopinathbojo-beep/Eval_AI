import React from "react";
import { View, StyleSheet, ViewStyle, StyleProp, Platform } from "react-native";
import { useTheme } from "../theme/ThemeContext";

interface CardProps {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  elevated?: boolean;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  style,
  elevated = false,
  noPadding = false,
}) => {
  const { colors, isDark } = useTheme();

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: elevated ? colors.surfaceElevated : colors.surface,
          borderColor: isDark ? colors.border : "rgba(226, 232, 240, 0.9)",
          shadowColor: isDark ? "#000" : "#0F172A",
          shadowOpacity: isDark ? 0.3 : 0.04,
        },
        noPadding && { padding: 0 },
        style,
      ]}
    >
      {children}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 16,
    marginBottom: 12,
    ...Platform.select({
      ios: {
        shadowOffset: { width: 0, height: 2 },
        shadowRadius: 6,
      },
      android: {
        elevation: 1.5,
      },
    }),
  },
});
