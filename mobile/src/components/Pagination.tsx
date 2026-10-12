import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems?: number;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  totalItems,
}) => {
  const { colors } = useTheme();

  if (totalPages <= 1) return null;

  return (
    <View style={styles.container}>
      <TouchableOpacity
        disabled={currentPage <= 1}
        onPress={() => onPageChange(currentPage - 1)}
        style={[
          styles.pageButton,
          {
            backgroundColor: colors.surface,
            borderColor: colors.border,
            opacity: currentPage <= 1 ? 0.4 : 1,
          },
        ]}
      >
        <Ionicons name="chevron-back" size={18} color={colors.text} />
      </TouchableOpacity>

      <View style={styles.infoContainer}>
        <Text style={[styles.pageText, { color: colors.text }]}>
          Page {currentPage} of {totalPages}
        </Text>
        {totalItems !== undefined && (
          <Text style={[styles.subText, { color: colors.textSecondary }]}>
            ({totalItems} total)
          </Text>
        )}
      </View>

      <TouchableOpacity
        disabled={currentPage >= totalPages}
        onPress={() => onPageChange(currentPage + 1)}
        style={[
          styles.pageButton,
          {
            backgroundColor: colors.surface,
            borderColor: colors.border,
            opacity: currentPage >= totalPages ? 0.4 : 1,
          },
        ]}
      >
        <Ionicons name="chevron-forward" size={18} color={colors.text} />
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
    marginTop: 8,
  },
  pageButton: {
    width: 38,
    height: 38,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  infoContainer: {
    alignItems: "center",
  },
  pageText: {
    fontSize: 13,
    fontWeight: "600",
  },
  subText: {
    fontSize: 11,
    marginTop: 2,
  },
});
