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

interface ExamCreateScreenProps {
  navigation: any;
}

export const ExamCreateScreen: React.FC<ExamCreateScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
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

      Alert.alert("Success", "Examination created successfully!", [
        {
          text: "Open Workspace",
          onPress: () => {
            navigation.replace("ExamWorkspace", { examId: res.id });
          },
        },
      ]);
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

  const examTypes = ["Midterm", "Final", "Unit Test", "Quiz", "Practice"];

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.background }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <Card style={styles.card}>
          <Text style={[styles.title, { color: colors.text }]}>New Examination</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Configure examination settings and link syllabus
          </Text>

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

          {/* Class Picker */}
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

          {/* Subject Picker */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary, marginTop: 12 }]}>
            Subject / Course *
          </Text>
          <View style={styles.chipsWrap}>
            {subjects.map((s) => {
              const selected = subjectId === s.id;
              return (
                <TouchableOpacity
                  key={s.id}
                  onPress={() => setSubjectId(s.id)}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: selected ? "rgba(81, 188, 117, 0.18)" : colors.surface,
                      borderColor: selected ? colors.brandGreen : colors.border,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      { color: selected ? colors.brandGreen : colors.text },
                    ]}
                  >
                    {s.name} {s.code ? `(${s.code})` : ""}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Exam Type Picker */}
          <Text style={[styles.pickerLabel, { color: colors.textSecondary, marginTop: 12 }]}>
            Exam Type
          </Text>
          <View style={styles.chipsWrap}>
            {examTypes.map((t) => {
              const selected = examType === t;
              return (
                <TouchableOpacity
                  key={t}
                  onPress={() => setExamType(t)}
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
                    {t}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

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

          <Input
            label="Examination Date (YYYY-MM-DD)"
            placeholder="2024-10-15"
            value={examDate}
            onChangeText={setExamDate}
          />

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
            title="Create and Configure Exam"
            onPress={handleCreate}
            variant="gradient"
            loading={submitting}
            fullWidth
            style={{ marginTop: 12 }}
          />
        </Card>
      </ScrollView>
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
  title: {
    fontSize: 20,
    fontWeight: "700",
  },
  subtitle: {
    fontSize: 13,
    marginTop: 2,
    marginBottom: 16,
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
  row: {
    flexDirection: "row",
  },
});
