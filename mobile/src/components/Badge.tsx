import React from "react";
import { View, Text, StyleSheet, ViewStyle } from "react-native";
import { useTheme } from "../theme/ThemeContext";

interface BadgeProps {
  label: string;
  variant?: "default" | "success" | "warning" | "danger" | "teal" | "muted";
  size?: "small" | "medium";
  style?: ViewStyle;
}

export const Badge: React.FC<BadgeProps> = ({
  label,
  variant = "default",
  size = "medium",
  style,
}) => {
  const { colors } = useTheme();

  const getColors = () => {
    switch (variant) {
      case "success":
        return { bg: "rgba(81, 188, 117, 0.15)", text: colors.brandGreen, border: "rgba(81, 188, 117, 0.35)" };
      case "warning":
        return { bg: "rgba(240, 182, 90, 0.15)", text: colors.warning, border: "rgba(240, 182, 90, 0.35)" };
      case "danger":
        return { bg: "rgba(239, 100, 100, 0.15)", text: colors.error, border: "rgba(239, 100, 100, 0.35)" };
      case "teal":
        return { bg: "rgba(7, 159, 189, 0.15)", text: colors.primary, border: "rgba(7, 159, 189, 0.35)" };
      case "muted":
        return { bg: colors.surfaceElevated, text: colors.textSecondary, border: colors.border };
      default:
        return { bg: colors.surfaceElevated, text: colors.text, border: colors.border };
    }
  };

  const c = getColors();

  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: c.bg,
          borderColor: c.border,
          paddingVertical: size === "small" ? 2 : 4,
          paddingHorizontal: size === "small" ? 6 : 8,
        },
        style,
      ]}
    >
      <Text
        style={[
          styles.text,
          {
            color: c.text,
            fontSize: size === "small" ? 11 : 12,
          },
        ]}
      >
        {label}
      </Text>
    </View>
  );
};

export const StatusBadge: React.FC<{ status: string; style?: ViewStyle }> = ({ status, style }) => {
  let variant: "default" | "success" | "warning" | "danger" | "teal" | "muted" = "default";
  let label = status === "OCR_PROCESSING" ? "READING PAGES" : status.replace(/_/g, " ").replace(/\bOCR\b/g, "READING");

  switch (status) {
    case "FINALIZED":
    case "COMPLETED":
    case "VERIFIED":
    case "SUCCESS":
      variant = "success";
      break;
    case "REVIEW_REQUIRED":
    case "NEEDS_REVIEW":
    case "EVALUATING":
    case "PENDING":
      variant = "warning";
      break;
    case "AI_ERROR":
    case "ERROR":
    case "FAILED":
      variant = "danger";
      break;
    case "READY_FOR_EVALUATION":
    case "RUNNING":
      variant = "teal";
      break;
    case "DRAFT":
    case "UNVERIFIED":
    case "MISSING":
    case "UNANSWERED":
    case "CANCELLING":
    case "CANCELLED":
      variant = "muted";
      if (status === "MISSING") label = "Unanswered";
      break;
    default:
      variant = "teal";
  }

  return <Badge label={label} variant={variant} style={style} />;
};

const styles = StyleSheet.create({
  badge: {
    borderRadius: 6,
    borderWidth: 1,
    alignSelf: "flex-start",
  },
  text: {
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
});
