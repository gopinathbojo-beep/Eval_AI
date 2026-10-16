import React from "react";
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
  StyleProp,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "../theme/ThemeContext";

interface ButtonProps {
  title?: string;
  onPress?: () => void;
  variant?: "primary" | "gradient" | "secondary" | "soft" | "danger" | "outline" | "ghost";
  size?: "small" | "medium" | "large";
  icon?: React.ReactNode;
  iconPosition?: "left" | "right";
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
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
  const { colors, isDark } = useTheme();

  const getDimensions = () => {
    switch (size) {
      case "small":
        return { minHeight: 36, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8 };
      case "large":
        return { minHeight: 52, paddingVertical: 14, paddingHorizontal: 22, borderRadius: 12 };
      default:
        return { minHeight: 44, paddingVertical: 10, paddingHorizontal: 16, borderRadius: 10 };
    }
  };

  const getFontSize = () => {
    switch (size) {
      case "small":
        return 12.5;
      case "large":
        return 16;
      default:
        return 14;
    }
  };

  const isDisabled = disabled || loading;
  const dims = getDimensions();

  const getTextColor = () => {
    if (variant === "secondary") return colors.text;
    if (variant === "soft") return colors.primary;
    if (variant === "outline") return colors.primary;
    if (variant === "ghost") return colors.textSecondary;
    return "#FFFFFF";
  };

  const content = (
    <View style={styles.innerContent}>
      {loading ? (
        <ActivityIndicator
          size="small"
          color={getTextColor()}
          style={title ? { marginRight: 8 } : undefined}
        />
      ) : (
        icon && iconPosition === "left" && <View style={title ? styles.iconLeft : undefined}>{icon}</View>
      )}
      {Boolean(title) && (
        <Text
          style={[
            styles.text,
            {
              fontSize: getFontSize(),
              color: getTextColor(),
            },
            isDisabled && { opacity: 0.65 },
            textStyle,
          ]}
        >
          {title}
        </Text>
      )}
      {!loading && icon && iconPosition === "right" && (
        <View style={title ? styles.iconRight : undefined}>{icon}</View>
      )}
    </View>
  );

  if (variant === "gradient" && !isDisabled) {
    return (
      <TouchableOpacity
        onPress={onPress || (() => {})}
        disabled={isDisabled}
        activeOpacity={0.82}
        style={[fullWidth && styles.fullWidth, style]}
      >
        <LinearGradient
          colors={[colors.gradientStart, colors.gradientEnd]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[
            styles.baseButton,
            {
              minHeight: dims.minHeight,
              paddingVertical: dims.paddingVertical,
              paddingHorizontal: dims.paddingHorizontal,
              borderRadius: dims.borderRadius,
            },
            fullWidth && styles.fullWidth,
          ]}
        >
          {content}
        </LinearGradient>
      </TouchableOpacity>
    );
  }

  const getBackgroundColor = () => {
    if (isDisabled) return isDark ? colors.surfaceElevated : "#E2E8F0";
    switch (variant) {
      case "primary":
      case "gradient":
        return colors.primary;
      case "secondary":
        return colors.surface;
      case "soft":
        return isDark ? "rgba(96, 165, 250, 0.14)" : "rgba(24, 68, 126, 0.08)";
      case "danger":
        return colors.error;
      case "outline":
      case "ghost":
        return "transparent";
      default:
        return colors.primary;
    }
  };

  const getBorderColor = () => {
    if (variant === "outline") return colors.primary;
    if (variant === "secondary") return colors.border;
    if (variant === "soft") return isDark ? "rgba(96, 165, 250, 0.25)" : "rgba(24, 68, 126, 0.15)";
    return "transparent";
  };

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={isDisabled}
      activeOpacity={0.78}
      style={[
        styles.baseButton,
        {
          minHeight: dims.minHeight,
          paddingVertical: dims.paddingVertical,
          paddingHorizontal: dims.paddingHorizontal,
          borderRadius: dims.borderRadius,
          backgroundColor: getBackgroundColor(),
          borderColor: getBorderColor(),
          borderWidth: variant === "outline" || variant === "secondary" || variant === "soft" ? 1 : 0,
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
    fontWeight: "700",
    letterSpacing: 0.15,
  },
  iconLeft: {
    marginRight: 7,
  },
  iconRight: {
    marginLeft: 7,
  },
});
