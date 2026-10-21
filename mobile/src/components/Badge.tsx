import React from "react";
import { View, Text, StyleSheet, ViewStyle } from "react-native";
import { useTheme } from "../theme/ThemeContext";

interface BadgeProps {
  label: string;
  variant?: "default" | "success" | "warning" | "danger" | "teal" | "muted" | "navy";
  size?: "small" | "medium";
  style?: ViewStyle;
  withDot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  label,
  variant = "default",
  size = "medium",
  style,
  withDot = false,
}) => {
  const { colors, isDark } = useTheme();

  const getColors = () => {
    switch (variant) {
      case "success":
        return {
          bg: isDark ? "rgba(34, 197, 94, 0.16)" : "rgba(22, 163, 74, 0.10)",
          text: colors.brandGreen,
          border: isDark ? "rgba(34, 197, 94, 0.3)" : "rgba(22, 163, 74, 0.22)",
          dot: colors.brandGreen,
        };
      case "warning":
        return {
          bg: isDark ? "rgba(251, 191, 36, 0.16)" : "rgba(217, 119, 6, 0.10)",
          text: colors.warning,
          border: isDark ? "rgba(251, 191, 36, 0.3)" : "rgba(217, 119, 6, 0.22)",
          dot: colors.warning,
        };
      case "danger":
        return {
          bg: isDark ? "rgba(248, 113, 113, 0.16)" : "rgba(220, 38, 38, 0.10)",
          text: colors.error,
          border: isDark ? "rgba(248, 113, 113, 0.3)" : "rgba(220, 38, 38, 0.22)",
          dot: colors.error,
        };
      case "navy":
      case "teal":
        return {
          bg: isDark ? "rgba(96, 165, 250, 0.16)" : "rgba(24, 68, 126, 0.08)",
          text: colors.primary,
          border: isDark ? "rgba(96, 165, 250, 0.3)" : "rgba(24, 68, 126, 0.2)",
          dot: colors.primary,
        };
      case "muted":
        return {
          bg: isDark ? colors.surfaceElevated : "#F1F5F9",
          text: colors.textSecondary,
          border: colors.border,
          dot: colors.mutedText,
        };
      default:
        return {
          bg: isDark ? colors.surfaceElevated : "#F8FAFC",
          text: colors.text,
          border: colors.border,
          dot: colors.primary,
        };
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
          paddingVertical: size === "small" ? 2.5 : 4,
          paddingHorizontal: size === "small" ? 7 : 10,
        },
        style,
      ]}
    >
      {withDot && (
        <View
          style={[
            styles.dot,
            {
              backgroundColor: c.dot,
              width: size === "small" ? 5 : 6,
              height: size === "small" ? 5 : 6,
            },
          ]}
        />
      )}
      <Text
        style={[
          styles.text,
          {
            color: c.text,
            fontSize: size === "small" ? 10.5 : 11.5,
          },
        ]}
      >
        {label}
      </Text>
    </View>
  );
};

// status codes keep their names; only the words shown to teachers change
const STATUS_LABELS: Record<string, string> = {
  OCR_PROCESSING: "READING PAGES", OCR_REVIEW: "TRANSCRIPTION REVIEW", WAITING: "WAITING FOR VERIFIED QUESTIONS",
  IDENTIFYING: "IDENTIFYING STUDENT", NEEDS_STUDENT: "NEEDS STUDENT", AI_EVALUATED: "EVALUATED",
};

export const StatusBadge: React.FC<{
  status?: string | null;
  style?: ViewStyle;
  size?: "small" | "medium";
}> = ({ status = "DRAFT", style, size = "medium" }) => {
  const rawStatus = (status || "").toUpperCase();
  let variant: "default" | "success" | "warning" | "danger" | "teal" | "muted" | "navy" = "default";
  let label = (STATUS_LABELS[rawStatus] || status || "").replace(/_/g, " ");

  switch (rawStatus) {
    case "FINALIZED":
    case "COMPLETED":
    case "VERIFIED":
    case "SUCCESS":
    case "READY":
    case "APPROVED":
    case "MAPPED":
      variant = "success";
      break;
    case "REVIEW_REQUIRED":
    case "NEEDS_REVIEW":
    case "NEEDS_ATTENTION":
    case "EVALUATING":
    case "PENDING":
    case "MAPPING_REVIEW":
    case "OCR_REVIEW":
    case "NEEDS_STUDENT":
      variant = "warning";
      break;
    case "AI_ERROR":
    case "ERROR":
    case "FAILED":
    case "FAILED_PARSE":
    case "UNMAPPED":
      variant = "danger";
      break;
    case "READY_FOR_EVALUATION":
    case "RUNNING":
    case "EXTRACTING":
    case "RENDERING":
    case "OCR_PROCESSING":
    case "IDENTIFYING":
      variant = "navy";
      break;
    case "DRAFT":
    case "UNVERIFIED":
    case "UPLOADED":
    case "IDLE":
    case "IGNORED":
    case "WAITING":
      variant = "muted";
      break;
    default:
      variant = "navy";
  }

  return <Badge label={label} variant={variant} size={size} style={style} />;
};

const styles = StyleSheet.create({
  badge: {
    borderRadius: 20,
    borderWidth: 1,
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
  },
  dot: {
    borderRadius: 3,
    marginRight: 5,
  },
  text: {
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.3,
  },
});
