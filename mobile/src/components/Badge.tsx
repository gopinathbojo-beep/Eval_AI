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
  const { colors } = useTheme();

  // Rubber-stamp colours as on the web: soft tint fill, ink text, the same ink at ~45% for the rule
  const tone = (ink: string, bg: string, dot = ink) => ({ bg, text: ink, border: `${ink}73`, dot });
  const getColors = () => {
    switch (variant) {
      case "success":
        return tone(colors.success, colors.successSoft);
      case "warning":
        return tone(colors.warning, colors.warningSoft);
      case "danger":
        return tone(colors.error, colors.errorSoft);
      case "navy":
      case "teal":
        return tone(colors.primary, colors.primarySoft);
      case "muted":
        return { ...tone(colors.textSecondary, colors.surfaceElevated, colors.mutedText), border: colors.border };
      default:
        return { ...tone(colors.text, colors.surfaceElevated, colors.primary), border: colors.border };
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
    borderRadius: 4,
    borderWidth: 1.5,
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
    letterSpacing: 0.8,
  },
});
