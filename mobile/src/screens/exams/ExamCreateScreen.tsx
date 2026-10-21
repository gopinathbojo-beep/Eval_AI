import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api } from "../../api/client";
import type { ClassRow, Subject, Exam } from "../../types";
import { Card } from "../../components/Card";
import { Input } from "../../components/Input";
import { Button } from "../../components/Button";
import { Loading } from "../../components/Loading";
import { CalendarPickerModal } from "../../components/CalendarPickerModal";
import { SearchablePickerModal, PickerItem } from "../../components/SearchablePickerModal";

interface ExamCreateScreenProps {
  navigation: any;
}

const DEFAULT_EXAM_TYPES = [
  "Midterm",
  "Final",
  "Unit Test",
  "Quiz",
  "Practice",
  "Internal Assessment",
  "Semester Exam",
  "Model Exam",
  "Assignment",
  "Practical Exam",
  "Diagnostic Test",
  "Weekly Test",
];

export const ExamCreateScreen: React.FC<ExamCreateScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [examTypes, setExamTypes] = useState<string[]>(DEFAULT_EXAM_TYPES);
  const [loadingData, setLoadingData] = useState(true);

  // Form State
  const [name, setName] = useState("");
  const [academicYear, setAcademicYear] = useState("2024-25");
  const [classId, setClassId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [examType, setExamType] = useState("Midterm");
  const [totalMarks, setTotalMarks] = useState("100");
  const [durationMinutes, setDurationMinutes] = useState("90");
  const [examDate, setExamDate] = useState(new Date().toISOString().split("T")[0]);
  const [instructions, setInstructions] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Picker Modals
  const [subjectModalVisible, setSubjectModalVisible] = useState(false);
  const [examTypeModalVisible, setExamTypeModalVisible] = useState(false);
  const [calendarModalVisible, setCalendarModalVisible] = useState(false);

  useEffect(() => {
    async function loadOptions() {
      try {
        const [c, s] = await Promise.all([
          api<ClassRow[]>("/classes"),
          api<Subject[]>("/subjects"),
        ]);
        setClasses(c);
        setSubjects(s);
        if (c.length > 0) setClassId(c[0].id);
        if (s.length > 0) setSubjectId(s[0].id);
      } catch (err: any) {
        Alert.alert("Error", "Failed to load classes or subjects");
      } finally {
        setLoadingData(false);
      }
    }
    loadOptions();
  }, []);

  const handleCreateNewSubject = async (subjectName: string, subjectCode?: string) => {
    const newSub = await api<Subject>("/subjects", {
      method: "POST",
      json: {
        name: subjectName,
        code: subjectCode || null,
      },
    });
    setSubjects((prev) => [...prev, newSub]);
    setSubjectId(newSub.id);
  };

  const handleCreateNewExamType = async (typeName: string) => {
    if (!examTypes.includes(typeName)) {
      setExamTypes((prev) => [typeName, ...prev]);
    }
    setExamType(typeName);
  };

  const selectedSubject = subjects.find((s) => s.id === subjectId);

  const subjectPickerItems: PickerItem[] = subjects.map((s) => ({
    id: s.id,
    label: s.name,
    subLabel: s.code ? `Course Code: ${s.code}` : undefined,
  }));

  const examTypePickerItems: PickerItem[] = examTypes.map((t) => ({
    id: t,
    label: t,
  }));

  const handleCreate = async () => {
    if (!name.trim()) {
      Alert.alert("Validation", "Please enter an examination title.");
      return;
    }
    if (!classId || !subjectId) {
      Alert.alert("Validation", "Please select a class and subject.");
      return;
    }
    const marksNum = parseFloat(totalMarks);
    if (isNaN(marksNum) || marksNum <= 0) {
      Alert.alert("Validation", "Total marks must be a positive number.");
      return;
    }

    try {
      setSubmitting(true);
      const res = await api<Exam>("/exams", {
        method: "POST",
        json: {
          name: name.trim(),
          academic_year: academicYear.trim(),
          class_id: classId,
          subject_id: subjectId,
          exam_type: examType,
          total_marks: marksNum,
          duration_minutes: durationMinutes ? parseInt(durationMinutes, 10) : null,
          exam_date: examDate.trim() || null,
          instructions: instructions.trim() || null,
        },
      });

      // Automatically move directly to the Question Upload module without any alerts
      navigation.replace("ExamWorkspace", {
        examId: res.id,
        initialTab: "paper",
      });
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to create examination");
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingData) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading configuration options..." />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.background }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <Card style={styles.card}>
          <View style={styles.headerRow}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.title, { color: colors.text }]}>New Examination</Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                Configure examination settings and link syllabus
              </Text>
            </View>
            <View style={[styles.badgeIcon, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
              <Ionicons name="school-outline" size={24} color={colors.primary} />
            </View>
          </View>

          <Input
            label="Examination Name *"
            placeholder="e.g. Mid-Term Mathematics 2024"
            value={name}
            onChangeText={setName}
            leftIcon={<Ionicons name="create-outline" size={18} color={colors.textSecondary} />}
          />

          <Input
            label="Academic Year"
            placeholder="2024-25"
            value={academicYear}
            onChangeText={setAcademicYear}
          />

          {/* Target Class Selector */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary }]}>
            Target Class *
          </Text>
          <View style={styles.chipsWrap}>
            {classes.map((c) => {
              const selected = classId === c.id;
              return (
                <TouchableOpacity
                  key={c.id}
                  onPress={() => setClassId(c.id)}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: selected ? "rgba(7, 159, 189, 0.18)" : colors.surface,
                      borderColor: selected ? colors.primary : colors.border,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      { color: selected ? colors.primary : colors.text },
                    ]}
                  >
                    {c.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Subject / Course (Dropdown with Search & Create New) */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary, marginTop: 14 }]}>
            Subject / Course * (Searchable Dropdown)
          </Text>
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={() => setSubjectModalVisible(true)}
            style={[
              styles.dropdownTrigger,
              {
                backgroundColor: colors.surfaceElevated,
                borderColor: selectedSubject ? colors.brandGreen : colors.border,
              },
            ]}
          >
            <View style={styles.dropdownLeft}>
              <View style={[styles.dropdownIconCircle, { backgroundColor: "rgba(81, 188, 117, 0.15)" }]}>
                <Ionicons name="book-outline" size={18} color={colors.brandGreen} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={[styles.dropdownValueText, { color: colors.text }]}>
                  {selectedSubject ? selectedSubject.name : "Select Subject or Course"}
                </Text>
                {selectedSubject?.code ? (
                  <Text style={[styles.dropdownSubText, { color: colors.textSecondary }]}>
                    Code: {selectedSubject.code}
                  </Text>
                ) : (
                  <Text style={[styles.dropdownSubText, { color: colors.textSecondary }]}>
                    Tap to search or create new subject
                  </Text>
                )}
              </View>
            </View>
            <Ionicons name="chevron-down" size={20} color={colors.textSecondary} />
          </TouchableOpacity>

          {/* Exam Type (Dropdown with Search & Create New) */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary, marginTop: 14 }]}>
            Exam Type * (Searchable Dropdown)
          </Text>
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={() => setExamTypeModalVisible(true)}
            style={[
              styles.dropdownTrigger,
              {
                backgroundColor: colors.surfaceElevated,
                borderColor: colors.primary,
              },
            ]}
          >
            <View style={styles.dropdownLeft}>
              <View style={[styles.dropdownIconCircle, { backgroundColor: "rgba(7, 159, 189, 0.15)" }]}>
                <Ionicons name="ribbon-outline" size={18} color={colors.primary} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={[styles.dropdownValueText, { color: colors.text }]}>
                  {examType}
                </Text>
                <Text style={[styles.dropdownSubText, { color: colors.textSecondary }]}>
                  Tap to search or add custom exam type
                </Text>
              </View>
            </View>
            <Ionicons name="chevron-down" size={20} color={colors.textSecondary} />
          </TouchableOpacity>

          {/* Total Marks & Duration */}
          <View style={styles.row}>
            <View style={{ flex: 1, marginRight: 8 }}>
              <Input
                label="Total Marks *"
                placeholder="100"
                value={totalMarks}
                onChangeText={setTotalMarks}
                keyboardType="numeric"
              />
            </View>
            <View style={{ flex: 1, marginLeft: 8 }}>
              <Input
                label="Duration (Mins)"
                placeholder="90"
                value={durationMinutes}
                onChangeText={setDurationMinutes}
                keyboardType="numeric"
              />
            </View>
          </View>
          <Text style={[styles.helperNote, { color: colors.primary }]}>
            Total marks are also checked against the question paper.
          </Text>

          {/* Examination Date (Calendar Picker Type) */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary, marginTop: 14 }]}>
            Examination Date * (Calendar Picker)
          </Text>
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={() => setCalendarModalVisible(true)}
            style={[
              styles.dropdownTrigger,
              {
                backgroundColor: colors.surfaceElevated,
                borderColor: colors.border,
                marginBottom: 14,
              },
            ]}
          >
            <View style={styles.dropdownLeft}>
              <View style={[styles.dropdownIconCircle, { backgroundColor: "rgba(240, 182, 90, 0.15)" }]}>
                <Ionicons name="calendar-outline" size={18} color={colors.warning} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={[styles.dropdownValueText, { color: colors.text }]}>
                  {examDate || "Pick Date from Calendar"}
                </Text>
                <Text style={[styles.dropdownSubText, { color: colors.textSecondary }]}>
                  Interactive Calendar Picker
                </Text>
              </View>
            </View>
            <View style={[styles.dateActionPill, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
              <Ionicons name="calendar" size={14} color={colors.primary} />
              <Text style={{ fontSize: 12, fontWeight: "700", color: colors.primary }}>
                Open Calendar
              </Text>
            </View>
          </TouchableOpacity>

          <Input
            label="Instructions for Students (Optional)"
            placeholder="Answer all questions in Section A..."
            value={instructions}
            onChangeText={setInstructions}
            multiline
            numberOfLines={3}
            style={{ minHeight: 70 }}
          />

          <Button
            title="Create & Move to Question Upload"
            icon={<Ionicons name="arrow-forward" size={18} color="#FFFFFF" />}
            onPress={handleCreate}
            variant="gradient"
            loading={submitting}
            fullWidth
            style={{ marginTop: 16 }}
          />
        </Card>
      </ScrollView>

      {/* Subject Searchable Picker Modal with Create New */}
      <SearchablePickerModal
        visible={subjectModalVisible}
        onClose={() => setSubjectModalVisible(false)}
        title="Select Subject / Course"
        subtitle="Search syllabus subjects or add a new subject"
        searchPlaceholder="Search subjects by name or code..."
        items={subjectPickerItems}
        selectedId={subjectId}
        onSelect={(item) => setSubjectId(item.id)}
        createConfig={{
          buttonLabel: "+ Create New Subject",
          inputLabel: "Subject / Course Name *",
          inputPlaceholder: "e.g. Physics, Data Structures, History",
          extraInputLabel: "Subject Code (Optional)",
          extraInputPlaceholder: "e.g. PHY101, CS204",
          onCreate: handleCreateNewSubject,
        }}
      />

      {/* Exam Type Searchable Picker Modal with Create New */}
      <SearchablePickerModal
        visible={examTypeModalVisible}
        onClose={() => setExamTypeModalVisible(false)}
        title="Select Exam Type"
        subtitle="Choose standard examination type or define a custom type"
        searchPlaceholder="Search exam types..."
        items={examTypePickerItems}
        selectedId={examType}
        onSelect={(item) => setExamType(item.label)}
        createConfig={{
          buttonLabel: "+ Add Custom Exam Type",
          inputLabel: "Custom Exam Type *",
          inputPlaceholder: "e.g. Monthly Test 1, Revision Exam",
          onCreate: handleCreateNewExamType,
        }}
      />

      {/* Calendar Date Picker Modal */}
      <CalendarPickerModal
        visible={calendarModalVisible}
        onClose={() => setCalendarModalVisible(false)}
        selectedDate={examDate}
        onSelectDate={setExamDate}
        title="Examination Date"
      />
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  card: {
    padding: 20,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  badgeIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
  },
  subtitle: {
    fontSize: 13,
    marginTop: 2,
  },
  pickerLabel: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  chipsWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 8,
  },
  chip: {
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 13,
    fontWeight: "600",
  },
  dropdownTrigger: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: 1.5,
    marginBottom: 6,
  },
  dropdownLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
  },
  dropdownIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  dropdownValueText: {
    fontSize: 15,
    fontWeight: "700",
  },
  dropdownSubText: {
    fontSize: 12,
    marginTop: 2,
  },
  dateActionPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
  },
  row: {
    flexDirection: "row",
    marginTop: 10,
  },
  helperNote: {
    fontSize: 12,
    fontWeight: "500",
    marginTop: 2,
    marginBottom: 8,
  },
});
