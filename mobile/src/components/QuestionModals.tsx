import React, { useState } from "react";
import {
  Modal,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { Question } from "../types";
import { api } from "../api/client";

// ==========================================
// 1. EDIT / ADD QUESTION MODAL
// ==========================================
interface EditQuestionModalProps {
  visible: boolean;
  question?: Question | null;
  examId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export const EditQuestionModal: React.FC<EditQuestionModalProps> = ({
  visible,
  question,
  examId,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();
  const [num, setNum] = useState(question?.display_number ?? "");
  const [marks, setMarks] = useState(question?.max_marks != null ? String(question.max_marks) : "");
  const [section, setSection] = useState(question?.section ?? "");
  const [text, setText] = useState(question?.question_text ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  // Sync state when question prop changes
  React.useEffect(() => {
    if (visible) {
      setNum(question?.display_number ?? "");
      setMarks(question?.max_marks != null ? String(question.max_marks) : "");
      setSection(question?.section ?? "");
      setText(question?.question_text ?? "");
      setReason("");
    }
  }, [visible, question]);

  const handleSave = async () => {
    if (!num.trim()) {
      Alert.alert("Validation", "Question number is required (e.g. 1, 3(a), 4(i)).");
      return;
    }

    try {
      setSaving(true);
      if (question) {
        // Edit existing
        await api(`/exam-questions/${question.id}`, {
          method: "PATCH",
          json: {
            display_number: num.trim(),
            question_text: text,
            max_marks: marks ? Number(marks) : undefined,
            section: section.trim() || undefined,
            reason: reason.trim() || undefined,
          },
        });
      } else {
        // Add new
        await api(`/exams/${examId}/questions`, {
          method: "POST",
          json: {
            display_number: num.trim(),
            question_text: text,
            max_marks: marks ? Number(marks) : null,
            section: section.trim() || null,
          },
        });
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      Alert.alert("Save Error", err.message || "Failed to save question.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          {/* Header */}
          <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
            <Text style={[modalStyles.title, { color: colors.text }]}>
              {question ? `Edit Question ${question.display_number}` : "Add Question"}
            </Text>
            <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
              <Ionicons name="close" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={modalStyles.body} keyboardShouldPersistTaps="handled">
            <View style={modalStyles.row}>
              <View style={[modalStyles.field, { flex: 1 }]}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Number *</Text>
                <TextInput
                  style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  value={num}
                  onChangeText={setNum}
                  placeholder="e.g. 1, 2(a)"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>

              <View style={[modalStyles.field, { flex: 1 }]}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Max Marks</Text>
                <TextInput
                  style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  value={marks}
                  onChangeText={setMarks}
                  keyboardType="numeric"
                  placeholder="e.g. 5"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
            </View>

            <View style={modalStyles.field}>
              <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Section (Optional)</Text>
              <TextInput
                style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                value={section}
                onChangeText={setSection}
                placeholder="e.g. Section A"
                placeholderTextColor={colors.textSecondary}
              />
            </View>

            <View style={modalStyles.field}>
              <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Question Text</Text>
              <TextInput
                style={[modalStyles.textArea, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                value={text}
                onChangeText={setText}
                multiline
                numberOfLines={6}
                textAlignVertical="top"
                placeholder="Enter complete question statement..."
                placeholderTextColor={colors.textSecondary}
              />
            </View>

            {question && (
              <View style={modalStyles.field}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Reason for change (Optional)</Text>
                <TextInput
                  style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  value={reason}
                  onChangeText={setReason}
                  placeholder="e.g. Fixed transcription typo in formula"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
            )}
          </ScrollView>

          {/* Footer */}
          <View style={[modalStyles.footer, { borderTopColor: colors.border }]}>
            <TouchableOpacity onPress={onClose} style={[modalStyles.btn, modalStyles.btnCancel, { borderColor: colors.border }]}>
              <Text style={[modalStyles.btnCancelText, { color: colors.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={handleSave} disabled={saving} style={[modalStyles.btn, modalStyles.btnPrimary, { backgroundColor: colors.primary }]}>
              {saving ? (
                <ActivityIndicator size="small" color="#FFFFFF" />
              ) : (
                <Text style={modalStyles.btnPrimaryText}>Save Question</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

// ==========================================
// 2. SPLIT QUESTION MODAL
// ==========================================
interface SplitQuestionModalProps {
  visible: boolean;
  question: Question | null;
  onClose: () => void;
  onSuccess: () => void;
}

export const SplitQuestionModal: React.FC<SplitQuestionModalProps> = ({
  visible,
  question,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();
  const [splitPos, setSplitPos] = useState<number>(0);
  const [newNum, setNewNum] = useState("");
  const [newMarks, setNewMarks] = useState("");
  const [saving, setSaving] = useState(false);

  React.useEffect(() => {
    if (visible && question) {
      setSplitPos(Math.floor(question.question_text.length / 2));
      setNewNum("");
      setNewMarks("");
    }
  }, [visible, question]);

  if (!question) return null;

  const handleSplit = async () => {
    if (!newNum.trim()) {
      Alert.alert("Validation", "Please provide a number for the new question.");
      return;
    }
    if (splitPos <= 0 || splitPos >= question.question_text.length) {
      Alert.alert("Validation", "Invalid split position.");
      return;
    }

    try {
      setSaving(true);
      await api(`/exam-questions/${question.id}/split`, {
        method: "POST",
        json: {
          at_char: splitPos,
          new_number: newNum.trim(),
          new_marks: newMarks ? Number(newMarks) : null,
        },
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      Alert.alert("Split Error", err.message || "Failed to split question.");
    } finally {
      setSaving(false);
    }
  };

  const headPreview = question.question_text.slice(0, splitPos);
  const tailPreview = question.question_text.slice(splitPos);

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
            <Text style={[modalStyles.title, { color: colors.text }]}>
              Split Question {question.display_number}
            </Text>
            <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
              <Ionicons name="close" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={modalStyles.body} keyboardShouldPersistTaps="handled">
            <Text style={[modalStyles.hint, { color: colors.textSecondary }]}>
              Split the question into two separate items where the second part begins.
            </Text>

            <View style={modalStyles.field}>
              <Text style={[modalStyles.label, { color: colors.textSecondary }]}>
                Split Character Position: {splitPos} of {question.question_text.length}
              </Text>
              <TextInput
                style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                value={String(splitPos)}
                keyboardType="numeric"
                onChangeText={(v) => {
                  const n = parseInt(v, 10);
                  if (!isNaN(n)) setSplitPos(Math.min(Math.max(1, n), question.question_text.length - 1));
                }}
              />
            </View>

            {/* Split Preview Boxes */}
            <View style={modalStyles.previewBox}>
              <Text style={[modalStyles.previewTitle, { color: colors.primary }]}>Part 1 (Remains Q{question.display_number}):</Text>
              <Text style={[modalStyles.previewText, { color: colors.text }]}>{headPreview || "(empty)"}</Text>
            </View>

            <View style={modalStyles.previewBox}>
              <Text style={[modalStyles.previewTitle, { color: colors.brandGreen }]}>Part 2 (New Question):</Text>
              <Text style={[modalStyles.previewText, { color: colors.text }]}>{tailPreview || "(empty)"}</Text>
            </View>

            <View style={modalStyles.row}>
              <View style={[modalStyles.field, { flex: 1 }]}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>New Question Number *</Text>
                <TextInput
                  style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  value={newNum}
                  onChangeText={setNewNum}
                  placeholder="e.g. 1(b)"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>

              <View style={[modalStyles.field, { flex: 1 }]}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Marks for New Question</Text>
                <TextInput
                  style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  value={newMarks}
                  onChangeText={setNewMarks}
                  keyboardType="numeric"
                  placeholder="e.g. 2.5"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
            </View>
          </ScrollView>

          <View style={[modalStyles.footer, { borderTopColor: colors.border }]}>
            <TouchableOpacity onPress={onClose} style={[modalStyles.btn, modalStyles.btnCancel, { borderColor: colors.border }]}>
              <Text style={[modalStyles.btnCancelText, { color: colors.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleSplit} disabled={saving} style={[modalStyles.btn, modalStyles.btnPrimary, { backgroundColor: colors.primary }]}>
              {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={modalStyles.btnPrimaryText}>Execute Split</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

// ==========================================
// 3. MERGE QUESTION MODAL
// ==========================================
interface MergeQuestionModalProps {
  visible: boolean;
  question: Question | null;
  allQuestions: Question[];
  onClose: () => void;
  onSuccess: () => void;
}

export const MergeQuestionModal: React.FC<MergeQuestionModalProps> = ({
  visible,
  question,
  allQuestions,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();
  const [targetId, setTargetId] = useState<string>("");
  const [saving, setSaving] = useState(false);

  if (!question) return null;

  const candidateQuestions = allQuestions.filter((q) => q.id !== question.id);

  const handleMerge = async () => {
    if (!targetId) {
      Alert.alert("Validation", "Please select a question to absorb.");
      return;
    }

    try {
      setSaving(true);
      await api(`/exam-questions/${question.id}/merge`, {
        method: "POST",
        json: { other_id: targetId },
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      Alert.alert("Merge Error", err.message || "Failed to merge questions.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
            <Text style={[modalStyles.title, { color: colors.text }]}>
              Merge into Question {question.display_number}
            </Text>
            <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
              <Ionicons name="close" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={modalStyles.body}>
            <Text style={[modalStyles.hint, { color: colors.textSecondary }]}>
              The selected question's text will be appended to Question {question.display_number}, and the selected question will then be removed. Use this when a question continued onto the next page.
            </Text>

            <Text style={[modalStyles.label, { color: colors.textSecondary, marginTop: 10, marginBottom: 8 }]}>
              Select question to absorb:
            </Text>

            {candidateQuestions.map((cand) => {
              const isSelected = targetId === cand.id;
              return (
                <TouchableOpacity
                  key={cand.id}
                  onPress={() => setTargetId(cand.id)}
                  style={[
                    modalStyles.selectOption,
                    {
                      borderColor: isSelected ? colors.primary : colors.border,
                      backgroundColor: isSelected ? "rgba(7, 159, 189, 0.12)" : colors.background,
                    },
                  ]}
                >
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <Text style={[modalStyles.selectOptionTitle, { color: colors.text }]}>
                      Question {cand.display_number} ({cand.max_marks ?? "?"} marks)
                    </Text>
                    <Ionicons
                      name={isSelected ? "radio-button-on" : "radio-button-off"}
                      size={18}
                      color={isSelected ? colors.primary : colors.textSecondary}
                    />
                  </View>
                  <Text numberOfLines={2} style={[modalStyles.selectOptionDesc, { color: colors.textSecondary }]}>
                    {cand.question_text || "(empty)"}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <View style={[modalStyles.footer, { borderTopColor: colors.border }]}>
            <TouchableOpacity onPress={onClose} style={[modalStyles.btn, modalStyles.btnCancel, { borderColor: colors.border }]}>
              <Text style={[modalStyles.btnCancelText, { color: colors.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleMerge} disabled={saving || !targetId} style={[modalStyles.btn, modalStyles.btnPrimary, { backgroundColor: colors.primary, opacity: targetId ? 1 : 0.6 }]}>
              {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={modalStyles.btnPrimaryText}>Merge Questions</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

// ==========================================
// 4. REVIEW FLAG MODAL
// ==========================================
interface ReviewQuestionModalProps {
  visible: boolean;
  question: Question | null;
  onClose: () => void;
  onSuccess: () => void;
}

export const ReviewQuestionModal: React.FC<ReviewQuestionModalProps> = ({
  visible,
  question,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  if (!question) return null;

  const handleFlag = async () => {
    try {
      setSaving(true);
      await api(`/exam-questions/${question.id}`, {
        method: "PATCH",
        json: {
          verification_status: "NEEDS_REVIEW",
          reason: reason.trim() || "Flagged for teacher review",
        },
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to flag question.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
            <Text style={[modalStyles.title, { color: colors.text }]}>
              Flag Question {question.display_number} for Review
            </Text>
            <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
              <Ionicons name="close" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <View style={modalStyles.body}>
            <View style={modalStyles.field}>
              <Text style={[modalStyles.label, { color: colors.textSecondary }]}>What looks wrong?</Text>
              <TextInput
                style={[modalStyles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                value={reason}
                onChangeText={setReason}
                placeholder="e.g. Incomplete question statement or unclear diagram"
                placeholderTextColor={colors.textSecondary}
              />
            </View>
          </View>

          <View style={[modalStyles.footer, { borderTopColor: colors.border }]}>
            <TouchableOpacity onPress={onClose} style={[modalStyles.btn, modalStyles.btnCancel, { borderColor: colors.border }]}>
              <Text style={[modalStyles.btnCancelText, { color: colors.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleFlag} disabled={saving} style={[modalStyles.btn, modalStyles.btnPrimary, { backgroundColor: colors.warning }]}>
              {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={modalStyles.btnPrimaryText}>Flag for Review</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const modalStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    justifyContent: "center",
    padding: 16,
  },
  dialog: {
    borderRadius: 14,
    borderWidth: 1,
    maxHeight: "85%",
    overflow: "hidden",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  title: {
    fontSize: 17,
    fontWeight: "700",
  },
  closeBtn: {
    padding: 4,
  },
  body: {
    padding: 16,
  },
  hint: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 12,
  },
  row: {
    flexDirection: "row",
    gap: 12,
  },
  field: {
    marginBottom: 14,
  },
  label: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  input: {
    height: 42,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 14,
  },
  textArea: {
    minHeight: 110,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    lineHeight: 20,
  },
  previewBox: {
    padding: 10,
    borderRadius: 8,
    backgroundColor: "rgba(0,0,0,0.04)",
    marginBottom: 10,
  },
  previewTitle: {
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 4,
  },
  previewText: {
    fontSize: 13,
  },
  selectOption: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  selectOptionTitle: {
    fontSize: 14,
    fontWeight: "600",
  },
  selectOptionDesc: {
    fontSize: 12,
    marginTop: 4,
  },
  footer: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
  },
  btn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  btnCancel: {
    borderWidth: 1,
  },
  btnCancelText: {
    fontSize: 14,
    fontWeight: "600",
  },
  btnPrimary: {},
  btnPrimaryText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
});
