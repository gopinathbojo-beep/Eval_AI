import React from "react";
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "../theme/ThemeContext";

interface ButtonProps {
  title?: string;
  onPress?: () => void;
  variant?: "primary" | "gradient" | "secondary" | "danger" | "outline" | "ghost";
  size?: "small" | "medium" | "large";
  icon?: React.ReactNode;
  iconPosition?: "left" | "right";
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  style?: ViewStyle;
  textStyle?: TextStyle;
}

export const Button: React.FC<ButtonProps> = ({
  title,
  onPress,
  variant = "primary",
  size = "medium",
  icon,
  iconPosition = "left",
  loading = false,
  disabled = false,
  fullWidth = false,
  style,
  textStyle,
}) => {
  const { colors } = useTheme();

  const getPadding = () => {
    switch (size) {
      case "small":
        return { paddingVertical: 6, paddingHorizontal: 12 };
      case "large":
        return { paddingVertical: 14, paddingHorizontal: 22 };
      default:
        return { paddingVertical: 10, paddingHorizontal: 16 };
    }
  };

  const getFontSize = () => {
    switch (size) {
      case "small":
        return 13;
      case "large":
        return 16;
      default:
        return 14;
    }
  };

  const isDisabled = disabled || loading;

  const content = (
    <View style={styles.innerContent}>
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === "secondary" || variant === "outline" || variant === "ghost" ? colors.primary : "#FFFFFF"}
          style={{ marginRight: 8 }}
        />
      ) : (
        icon && iconPosition === "left" && <View style={styles.iconLeft}>{icon}</View>
      )}
      {title ? (
        <Text
          style={[
            styles.text,
            {
              fontSize: getFontSize(),
              color:
                variant === "secondary"
                  ? colors.text
                  : variant === "outline"
                  ? colors.primary
                  : variant === "ghost"
                  ? colors.textSecondary
                  : "#FFFFFF",
            },
            isDisabled && { opacity: 0.7 },
            textStyle,
          ]}
        >
          {title}
        </Text>
      ) : null}
      {!loading && icon && iconPosition === "right" && (
        <View style={styles.iconRight}>{icon}</View>
      )}
    </View>
  );

  if (variant === "gradient" && !isDisabled) {
    return (
      <TouchableOpacity
        onPress={onPress}
        disabled={isDisabled}
        activeOpacity={0.85}
        style={[fullWidth && styles.fullWidth, style]}
      >
        <LinearGradient
          colors={[colors.gradientStart, colors.gradientEnd]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[styles.baseButton, getPadding(), fullWidth && styles.fullWidth]}
        >
          {content}
        </LinearGradient>
      </TouchableOpacity>
    );
  }

  const getBackgroundColor = () => {
    if (isDisabled) return colors.surfaceElevated;
    switch (variant) {
      case "primary":
      case "gradient": // fallback when disabled
        return colors.primary;
      case "secondary":
        return colors.surface;
      case "danger":
        return colors.error;
      case "outline":
      case "ghost":
        return "transparent";
      default:
        return colors.primary;
    }
  };

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={isDisabled}
      activeOpacity={0.8}
      style={[
        styles.baseButton,
        getPadding(),
        {
          backgroundColor: getBackgroundColor(),
          borderColor:
            variant === "outline"
              ? colors.primary
              : variant === "secondary"
              ? colors.border
              : "transparent",
          borderWidth: variant === "outline" || variant === "secondary" ? 1 : 0,
        },
        fullWidth && styles.fullWidth,
        isDisabled && { opacity: 0.6 },
        style,
      ]}
    >
      {content}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  baseButton: {
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
  },
  innerContent: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  fullWidth: {
    width: "100%",
  },
  text: {
    fontWeight: "600",
    letterSpacing: 0.2,
  },
  iconLeft: {
    marginRight: 8,
  },
  iconRight: {
    marginLeft: 8,
  },
});
