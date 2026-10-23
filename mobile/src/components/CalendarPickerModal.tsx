import React, { useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { Button } from "./Button";
import { fonts } from "../theme/colors";

interface CalendarPickerModalProps {
  visible: boolean;
  onClose: () => void;
  selectedDate: string; // YYYY-MM-DD format
  onSelectDate: (dateStr: string) => void;
  title?: string;
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const WEEK_DAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

export const CalendarPickerModal: React.FC<CalendarPickerModalProps> = ({
  visible,
  onClose,
  selectedDate,
  onSelectDate,
  title = "Select Examination Date",
}) => {
  const { colors } = useTheme();

  // Parse initial selected date or default to today
  const initial = useMemo(() => {
    if (selectedDate && /^\d{4}-\d{2}-\d{2}$/.test(selectedDate)) {
      const [y, m, d] = selectedDate.split("-").map(Number);
      return { year: y, month: m - 1, day: d };
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth(), day: now.getDate() };
  }, [selectedDate]);

  const [currentYear, setCurrentYear] = useState<number>(initial.year);
  const [currentMonth, setCurrentMonth] = useState<number>(initial.month);
  const [tempSelectedDate, setTempSelectedDate] = useState<string>(selectedDate || "");

  // Synchronize when modal opens
  React.useEffect(() => {
    if (visible) {
      setCurrentYear(initial.year);
      setCurrentMonth(initial.month);
      setTempSelectedDate(selectedDate || "");
    }
  }, [visible, initial, selectedDate]);

  const handlePrevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else {
      setCurrentMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else {
      setCurrentMonth((m) => m + 1);
    }
  };

  const handlePrevYear = () => {
    setCurrentYear((y) => y - 1);
  };

  const handleNextYear = () => {
    setCurrentYear((y) => y + 1);
  };

  const handleJumpToday = () => {
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
      now.getDate()
    ).padStart(2, "0")}`;
    setCurrentYear(now.getFullYear());
    setCurrentMonth(now.getMonth());
    setTempSelectedDate(todayStr);
  };

  // Calendar days grid calculation
  const calendarDays = useMemo(() => {
    const firstDayIndex = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

    const cells: Array<{ day: number | null; dateStr: string | null }> = [];

    // Empty lead cells
    for (let i = 0; i < firstDayIndex; i++) {
      cells.push({ day: null, dateStr: null });
    }

    // Days in current month
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(
        d
      ).padStart(2, "0")}`;
      cells.push({ day: d, dateStr });
    }

    return cells;
  }, [currentYear, currentMonth]);

  const todayStr = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
      now.getDate()
    ).padStart(2, "0")}`;
  }, []);

  const handleConfirm = () => {
    if (tempSelectedDate) {
      onSelectDate(tempSelectedDate);
    }
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <SafeAreaView style={styles.safeArea}>
          <View style={[styles.dialogContainer, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {/* Header */}
            <View style={styles.header}>
              <View style={{ flex: 1 }}>
                <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
                <Text style={[styles.subtitle, { color: colors.primary, fontWeight: "600" }]}>
                  {tempSelectedDate ? tempSelectedDate : "No date selected"}
                </Text>
              </View>
              <TouchableOpacity
                onPress={onClose}
                style={[styles.closeBtn, { backgroundColor: colors.surfaceElevated }]}
              >
                <Ionicons name="close" size={20} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>

            {/* Navigation Bar (Month & Year) */}
            <View style={[styles.navBar, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
              <View style={styles.navGroup}>
                <TouchableOpacity onPress={handlePrevYear} style={styles.navArrow}>
                  <Ionicons name="chevron-back-outline" size={16} color={colors.textSecondary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={handlePrevMonth} style={styles.navArrow}>
                  <Ionicons name="chevron-back" size={18} color={colors.primary} />
                </TouchableOpacity>
              </View>

              <Text style={[styles.monthYearText, { color: colors.text }]}>
                {MONTH_NAMES[currentMonth]} {currentYear}
              </Text>

              <View style={styles.navGroup}>
                <TouchableOpacity onPress={handleNextMonth} style={styles.navArrow}>
                  <Ionicons name="chevron-forward" size={18} color={colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={handleNextYear} style={styles.navArrow}>
                  <Ionicons name="chevron-forward-outline" size={16} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>
            </View>

            {/* Weekday headers */}
            <View style={styles.weekdayRow}>
              {WEEK_DAYS.map((wd, index) => (
                <Text
                  key={wd}
                  style={[
                    styles.weekdayText,
                    {
                      color: index === 0 || index === 6 ? colors.textSecondary : colors.text,
                    },
                  ]}
                >
                  {wd}
                </Text>
              ))}
            </View>

            {/* Calendar Grid */}
            <View style={styles.grid}>
              {calendarDays.map((cell, index) => {
                if (!cell.day || !cell.dateStr) {
                  return <View key={`empty-${index}`} style={styles.dayCell} />;
                }

                const isSelected = tempSelectedDate === cell.dateStr;
                const isToday = todayStr === cell.dateStr;

                return (
                  <TouchableOpacity
                    key={cell.dateStr}
                    onPress={() => setTempSelectedDate(cell.dateStr!)}
                    activeOpacity={0.7}
                    style={[
                      styles.dayCell,
                      isSelected && { backgroundColor: colors.primaryFill, borderRadius: 20 },
                      isToday && !isSelected && {
                        borderColor: colors.primary,
                        borderWidth: 1.5,
                        borderRadius: 20,
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.dayText,
                        {
                          color: isSelected
                            ? "#FFFFFF"
                            : isToday
                            ? colors.primary
                            : colors.text,
                          fontWeight: isSelected || isToday ? "700" : "500",
                        },
                      ]}
                    >
                      {cell.day}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Bottom Actions */}
            <View style={[styles.footer, { borderTopColor: colors.border }]}>
              <TouchableOpacity
                onPress={handleJumpToday}
                style={[styles.todayBtn, { borderColor: colors.primary }]}
              >
                <Ionicons name="today-outline" size={15} color={colors.primary} />
                <Text style={[styles.todayText, { color: colors.primary }]}>Today</Text>
              </TouchableOpacity>

              <View style={{ flexDirection: "row", gap: 10, flex: 1, justifyContent: "flex-end" }}>
                <Button
                  title="Cancel"
                  variant="secondary"
                  size="small"
                  onPress={onClose}
                  style={{ minWidth: 80 }}
                />
                <Button
                  title="Select Date"
                  variant="gradient"
                  size="small"
                  icon={<Ionicons name="checkmark" size={16} color="#FFFFFF" />}
                  onPress={handleConfirm}
                  style={{ minWidth: 100 }}
                />
              </View>
            </View>
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    justifyContent: "center",
    alignItems: "center",
    padding: 16,
  },
  safeArea: {
    width: "100%",
    maxWidth: 380,
  },
  dialogContainer: {
    width: "100%",
    borderRadius: 16,
    borderWidth: 1,
    padding: 18,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 8,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 12,
  },
  title: {
    fontSize: 16,
    fontFamily: fonts.display,
    fontWeight: "700",
  },
  subtitle: {
    fontSize: 13,
    marginTop: 2,
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  navBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 12,
  },
  navGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  navArrow: {
    padding: 6,
    borderRadius: 6,
  },
  monthYearText: {
    fontSize: 15,
    fontWeight: "700",
  },
  weekdayRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  weekdayText: {
    width: 36,
    textAlign: "center",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-around",
    paddingHorizontal: 4,
    marginBottom: 12,
  },
  dayCell: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    marginVertical: 3,
  },
  dayText: {
    fontSize: 14,
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 12,
    borderTopWidth: 1,
  },
  todayBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  todayText: {
    fontSize: 12,
    fontWeight: "700",
  },
});
