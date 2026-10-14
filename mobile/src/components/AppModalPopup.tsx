import React from "react";
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { Button } from "./Button";

export type PopupType = "info" | "success" | "warning" | "error";

export interface AppPopupConfig {
  visible: boolean;
  title: string;
  message?: string;
  type?: PopupType;
  confirmText?: string;
  cancelText?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  isDestructive?: boolean;
}

interface AppModalPopupProps {
  config: AppPopupConfig;
  onClose: () => void;
}

export const AppModalPopup: React.FC<AppModalPopupProps> = ({ config, onClose }) => {
  const { colors } = useTheme();

  if (!config.visible) return null;

  const type = config.type || "info";

  const getIconConfig = () => {
    switch (type) {
      case "success":
        return {
          name: "checkmark-circle" as const,
          color: colors.brandGreen || "#22C55E",
          bg: "rgba(34, 197, 94, 0.12)",
        };
      case "error":
        return {
          name: "alert-circle" as const,
          color: colors.error || "#EF4444",
          bg: "rgba(239, 68, 68, 0.12)",
        };
      case "warning":
        return {
          name: "warning" as const,
          color: colors.warning || "#F59E0B",
          bg: "rgba(245, 158, 11, 0.12)",
        };
      case "info":
      default:
        return {
          name: "information-circle" as const,
          color: colors.primary || "#0EA5E9",
          bg: "rgba(14, 165, 233, 0.12)",
        };
    }
  };

  const iconInfo = getIconConfig();
  const hasCancel = Boolean(config.cancelText || config.onCancel);

  const handleConfirm = () => {
    const cb = config.onConfirm;
    onClose();
    if (cb) {
      setTimeout(() => cb(), 30);
    }
  };

  const handleCancel = () => {
    const cb = config.onCancel;
    onClose();
    if (cb) {
      setTimeout(() => cb(), 30);
    }
  };

  return (
    <Modal visible={config.visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={styles.overlay}>
          <TouchableWithoutFeedback>
            <View
              style={[
                styles.dialogContainer,
                { backgroundColor: colors.surface, borderColor: colors.border },
              ]}
            >
              {/* Icon circle */}
              <View style={[styles.iconCircle, { backgroundColor: iconInfo.bg }]}>
                <Ionicons name={iconInfo.name} size={30} color={iconInfo.color} />
              </View>

              {/* Title */}
              <Text style={[styles.title, { color: colors.text }]}>{config.title}</Text>

              {/* Message */}
              {config.message ? (
                <ScrollView style={styles.messageScroll} showsVerticalScrollIndicator={false}>
                  <Text style={[styles.message, { color: colors.textSecondary }]}>
                    {config.message}
                  </Text>
                </ScrollView>
              ) : null}

              {/* Action Buttons */}
              <View style={styles.buttonRow}>
                {hasCancel && (
                  <Button
                    title={config.cancelText || "Cancel"}
                    variant="secondary"
                    size="medium"
                    onPress={handleCancel}
                    style={{ flex: 1 }}
                  />
                )}
                <Button
                  title={config.confirmText || (hasCancel ? "Confirm" : "OK")}
                  variant={config.isDestructive ? "secondary" : "gradient"}
                  size="medium"
                  onPress={handleConfirm}
                  style={[
                    { flex: 1 },
                    config.isDestructive && {
                      backgroundColor: "rgba(239, 68, 68, 0.15)",
                      borderColor: colors.error,
                      borderWidth: 1,
                    },
                  ]}
                />
              </View>
            </View>
          </TouchableWithoutFeedback>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  dialogContainer: {
    width: "100%",
    maxWidth: 360,
    borderRadius: 20,
    borderWidth: 1,
    padding: 22,
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.3,
    shadowRadius: 16,
    elevation: 10,
  },
  iconCircle: {
    width: 58,
    height: 58,
    borderRadius: 29,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
  },
  title: {
    fontSize: 17,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 8,
  },
  messageScroll: {
    maxHeight: 180,
    width: "100%",
    marginBottom: 18,
  },
  message: {
    fontSize: 13,
    lineHeight: 19,
    textAlign: "center",
  },
  buttonRow: {
    flexDirection: "row",
    gap: 10,
    width: "100%",
    marginTop: 4,
  },
});
