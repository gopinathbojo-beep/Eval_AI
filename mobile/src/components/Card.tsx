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
          borderColor: colors.border,
          // Index card: a hard offset "sheet underneath" in the rule colour, as on the web
          shadowColor: isDark ? "#000" : colors.border,
          shadowOpacity: isDark ? 0.35 : 0.9,
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
    borderRadius: 10,
    borderWidth: 1,
    padding: 16,
    marginBottom: 12,
    ...Platform.select({
      ios: {
        shadowOffset: { width: 3, height: 3 },
        shadowRadius: 0,
      },
      android: {
        elevation: 1.5,
      },
    }),
  },
});
