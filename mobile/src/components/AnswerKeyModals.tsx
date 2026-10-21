import React, { useState, useEffect } from "react";
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
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import {
  AnswerKeyRow,
  AnswerKeyValidationResponse,
  AnswerKeyValidationIssue,
} from "../types";
import { api } from "../api/client";
import { Button } from "./Button";
import { Badge } from "./Badge";

interface QuestionOption {
  id: string;
  display_number: string;
  max_marks: number | null;
  question_text: string;
}

// ==========================================
// 1. EDIT ANSWER KEY MODAL
// ==========================================
interface EditAnswerKeyModalProps {
  visible: boolean;
  row: AnswerKeyRow | null;
  questions: QuestionOption[];
  onClose: () => void;
  onSuccess: (updated: AnswerKeyRow) => void;
}

export const EditAnswerKeyModal: React.FC<EditAnswerKeyModalProps> = ({
  visible,
  row,
  questions,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();

  const [questionId, setQuestionId] = useState(row?.exam_question_id ?? "");
  const [solutionText, setSolutionText] = useState(row?.answer_text ?? "");
  const [marks, setMarks] = useState(row?.marks != null ? String(row.marks) : "");
  const [criteriaList, setCriteriaList] = useState<string[]>(row?.criteria ?? []);
  const [keywords, setKeywords] = useState((row?.keywords ?? []).join("\n"));
  const [acceptedAnswers, setAcceptedAnswers] = useState((row?.accepted_answers ?? []).join("\n"));
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible && row) {
      setQuestionId(row.exam_question_id ?? "");
      setSolutionText(row.answer_text ?? "");
      setMarks(row.marks != null ? String(row.marks) : "");
      setCriteriaList(row.criteria ? [...row.criteria] : []);
      setKeywords((row.keywords ?? []).join("\n"));
      setAcceptedAnswers((row.accepted_answers ?? []).join("\n"));
      setReason("");
    }
  }, [visible, row]);

  const targetQuestion = questions.find((q) => q.id === questionId);

  const handleAddCriterion = () => {
    setCriteriaList([...criteriaList, ""]);
  };

  const handleCriterionChange = (index: number, text: string) => {
    const updated = [...criteriaList];
    updated[index] = text;
    setCriteriaList(updated);
  };

  const handleRemoveCriterion = (index: number) => {
    setCriteriaList(criteriaList.filter((_, idx) => idx !== index));
  };

  const handleSave = async () => {
    if (!row) return;

    if (!questionId) {
      Alert.alert("Validation", "Please select a question this answer maps to.");
      return;
    }

    if (!solutionText.trim()) {
      Alert.alert("Validation", "Official solution text cannot be empty.");
      return;
    }

    const cleanedCriteria = criteriaList.map((c) => c.trim()).filter(Boolean);
    const cleanedKeywords = keywords
      .split("\n")
      .map((k) => k.trim())
      .filter(Boolean);
    const cleanedAccepted = acceptedAnswers
      .split("\n")
      .map((a) => a.trim())
      .filter(Boolean);

    try {
      setSaving(true);
      const payload: any = {
        answer_text: solutionText.trim(),
        marks: marks ? Number(marks) : null,
        criteria: cleanedCriteria,
        keywords: cleanedKeywords,
        accepted_answers: cleanedAccepted,
        reason: reason.trim() || undefined,
      };

      if (questionId !== row.exam_question_id) {
        payload.exam_question_id = questionId;
      }

      const res = await api<AnswerKeyRow>(`/answer-keys/${row.id}`, {
        method: "PATCH",
        json: payload,
      });

      Alert.alert("Success", "Answer key changes saved successfully.");
      onSuccess(res);
      onClose();
    } catch (err: any) {
      Alert.alert("Save Error", err.message || "Failed to update answer key.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={modalStyles.keyboardView}
        >
          <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {/* Header */}
            <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
              <View style={{ flex: 1 }}>
                <Text style={[modalStyles.title, { color: colors.text }]}>
                  Edit Answer: Q{row?.raw_question_number || row?.normalized_number || "?"}
                </Text>
                <Text style={[modalStyles.subtitle, { color: colors.textSecondary }]}>
                  Update official solution, criteria and question mapping
                </Text>
              </View>
              <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
                <Ionicons name="close" size={22} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>

            {/* Scrollable Form Body */}
            <ScrollView style={modalStyles.body} keyboardShouldPersistTaps="handled">
              {/* Question Mapping Dropdown / List */}
              <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Maps to Exam Question *</Text>
              <ScrollView
                style={[modalStyles.selectScrollBox, { borderColor: colors.border, backgroundColor: colors.inputBackground }]}
                nestedScrollEnabled
              >
                {questions.map((q) => {
                  const isSelected = q.id === questionId;
                  return (
                    <TouchableOpacity
                      key={q.id}
                      onPress={() => setQuestionId(q.id)}
                      style={[
                        modalStyles.questionOptionRow,
                        {
                          backgroundColor: isSelected ? "rgba(0, 168, 232, 0.16)" : "transparent",
                          borderColor: isSelected ? colors.primary : colors.border,
                        },
                      ]}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[modalStyles.questionOptionTitle, { color: isSelected ? colors.primary : colors.text }]}>
                          Question {q.display_number} {q.max_marks != null ? `(${q.max_marks} Marks)` : ""}
                        </Text>
                        <Text style={[modalStyles.questionOptionSub, { color: colors.textSecondary }]} numberOfLines={1}>
                          {q.question_text || "(No question text)"}
                        </Text>
                      </View>
                      {isSelected && <Ionicons name="checkmark-circle" size={18} color={colors.primary} />}
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Solution Text */}
              <Text style={[modalStyles.label, { color: colors.textSecondary, marginTop: 12 }]}>Official Solution Text *</Text>
              <TextInput
                style={[
                  modalStyles.textArea,
                  {
                    backgroundColor: colors.inputBackground,
                    borderColor: colors.border,
                    color: colors.text,
                  },
                ]}
                value={solutionText}
                onChangeText={setSolutionText}
                multiline
                numberOfLines={4}
                placeholder="Enter authoritative model answer..."
                placeholderTextColor={colors.mutedText}
              />

              {/* Marks */}
              <View style={{ marginTop: 12 }}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Key Marks</Text>
                <TextInput
                  style={[
                    modalStyles.input,
                    {
                      backgroundColor: colors.inputBackground,
                      borderColor: colors.border,
                      color: colors.text,
                    },
                  ]}
                  value={marks}
                  onChangeText={setMarks}
                  keyboardType="numeric"
                  placeholder="e.g. 5"
                  placeholderTextColor={colors.mutedText}
                />
                {targetQuestion && targetQuestion.max_marks != null && marks !== String(targetQuestion.max_marks) && (
                  <Text style={[modalStyles.hintText, { color: colors.warning }]}>
                    Note: Question max marks is {targetQuestion.max_marks}. If marks differ, a marks mismatch will be flagged.
                  </Text>
                )}
              </View>

              {/* Evaluation Criteria */}
              <View style={{ marginTop: 14 }}>
                <View style={modalStyles.sectionHeaderRow}>
                  <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Evaluation Criteria (Mark Breakdown)</Text>
                  <TouchableOpacity onPress={handleAddCriterion} style={modalStyles.addCriteriaBtn}>
                    <Ionicons name="add-circle" size={16} color={colors.primary} />
                    <Text style={[modalStyles.addCriteriaText, { color: colors.primary }]}>Add Point</Text>
                  </TouchableOpacity>
                </View>

                {criteriaList.map((crit, idx) => (
                  <View key={idx} style={modalStyles.criterionRow}>
                    <Badge label={`Point ${idx + 1}`} variant="teal" />
                    <TextInput
                      style={[
                        modalStyles.criterionInput,
                        {
                          backgroundColor: colors.inputBackground,
                          borderColor: colors.border,
                          color: colors.text,
                        },
                      ]}
                      value={crit}
                      onChangeText={(val) => handleCriterionChange(idx, val)}
                      placeholder="e.g. 1 mark for correct definition and formula"
                      placeholderTextColor={colors.mutedText}
                    />
                    <TouchableOpacity
                      onPress={() => handleRemoveCriterion(idx)}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                      style={modalStyles.removeCriterionBtn}
                    >
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </TouchableOpacity>
                  </View>
                ))}
              </View>

              {/* Keywords */}
              <View style={{ marginTop: 12 }}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Essential Keywords (one per line)</Text>
                <TextInput
                  style={[
                    modalStyles.textArea,
                    {
                      backgroundColor: colors.inputBackground,
                      borderColor: colors.border,
                      color: colors.text,
                      minHeight: 60,
                    },
                  ]}
                  value={keywords}
                  onChangeText={setKeywords}
                  multiline
                  placeholder="Terms student answers must include..."
                  placeholderTextColor={colors.mutedText}
                />
              </View>

              {/* Reason for Audit */}
              <View style={{ marginTop: 12, marginBottom: 16 }}>
                <Text style={[modalStyles.label, { color: colors.textSecondary }]}>Reason for changes (Audit record)</Text>
                <TextInput
                  style={[
                    modalStyles.input,
                    {
                      backgroundColor: colors.inputBackground,
                      borderColor: colors.border,
                      color: colors.text,
                    },
                  ]}
                  value={reason}
                  onChangeText={setReason}
                  placeholder="e.g. Corrected typo / aligned marks with scheme"
                  placeholderTextColor={colors.mutedText}
                />
              </View>
            </ScrollView>

            {/* Footer */}
            <View style={[modalStyles.footer, { borderTopColor: colors.border, backgroundColor: colors.surface }]}>
              <View style={modalStyles.footerActions}>
                <Button
                  title="Cancel"
                  variant="secondary"
                  size="medium"
                  onPress={onClose}
                  disabled={saving}
                  style={{ flex: 1 }}
                />
                <Button
                  title="Save Changes"
                  variant="gradient"
                  size="medium"
                  onPress={handleSave}
                  loading={saving}
                  style={{ flex: 1.4 }}
                />
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
};

// ==========================================
// 2. RESOLVE ISSUE MODAL
// ==========================================
interface ResolveAnswerKeyModalProps {
  visible: boolean;
  row: AnswerKeyRow | null;
  questions: QuestionOption[];
  onClose: () => void;
  onSuccess: (updated: AnswerKeyRow) => void;
}

export const ResolveAnswerKeyModal: React.FC<ResolveAnswerKeyModalProps> = ({
  visible,
  row,
  questions,
  onClose,
  onSuccess,
}) => {
  const { colors } = useTheme();

  const [questionId, setQuestionId] = useState(row?.exam_question_id ?? "");
  const [solutionText, setSolutionText] = useState(row?.answer_text ?? "");
  const [reason, setReason] = useState("");
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    if (visible && row) {
      setQuestionId(row.exam_question_id ?? "");
      setSolutionText(row.answer_text ?? "");
      setReason("");
    }
  }, [visible, row]);

  if (!row) return null;

  const targetQuestion = questions.find((q) => q.id === (questionId || row.exam_question_id));
  const candidateQuestion =
    row.mapping_candidates && row.mapping_candidates.length > 0
      ? questions.find((q) => q.id === row.mapping_candidates[0])
      : null;

  const hasMismatch = row.mark_mismatch && targetQuestion;
  const isNeedsReview = row.mapping_status !== "MAPPED" || !row.exam_question_id;
  const isEmptyText = !(row.answer_text || "").trim();

  // 1. Resolve Marks Mismatch
  const handleResolveMismatch = async (choice: "keep_question_marks" | "use_key_marks") => {
    if (choice === "use_key_marks" && !reason.trim()) {
      Alert.alert("Reason Required", "Please provide a reason for changing the question's maximum marks.");
      return;
    }

    try {
      setResolving(true);
      const res = await api<AnswerKeyRow>(`/answer-keys/${row.id}`, {
        method: "PATCH",
        json: {
          mismatch_resolution: choice,
          reason: reason.trim() || undefined,
        },
      });

      Alert.alert(
        "Mismatch Resolved",
        choice === "keep_question_marks"
          ? `Answer key marks aligned to Question's ${targetQuestion?.max_marks} marks.`
          : `Question maximum marks updated to ${row.marks} marks.`
      );
      onSuccess(res);
      onClose();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to resolve marks mismatch.");
    } finally {
      setResolving(false);
    }
  };

  // 2. Accept Candidate Mapping
  const handleAcceptCandidateMapping = async () => {
    if (!candidateQuestion) return;

    try {
      setResolving(true);
      const res = await api<AnswerKeyRow>(`/answer-keys/${row.id}`, {
        method: "PATCH",
        json: {
          exam_question_id: candidateQuestion.id,
          reason: "Accepted candidate question mapping",
        },
      });

      Alert.alert("Mapping Confirmed", `Answer mapped to Question ${candidateQuestion.display_number}.`);
      onSuccess(res);
      onClose();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to update mapping.");
    } finally {
      setResolving(false);
    }
  };

  // 3. Save Custom Mapping & Solution Text
  const handleSaveResolution = async () => {
    if (isNeedsReview && !questionId) {
      Alert.alert("Mapping Required", "Please choose the exam question this answer belongs to.");
      return;
    }

    if (!solutionText.trim()) {
      Alert.alert("Solution Required", "Please provide the official solution text.");
      return;
    }

    try {
      setResolving(true);
      const payload: any = {
        answer_text: solutionText.trim(),
        reason: reason.trim() || undefined,
      };

      if (questionId && questionId !== row.exam_question_id) {
        payload.exam_question_id = questionId;
      }

      const res = await api<AnswerKeyRow>(`/answer-keys/${row.id}`, {
        method: "PATCH",
        json: payload,
      });

      Alert.alert("Issue Resolved", "Answer key issue resolved successfully.");
      onSuccess(res);
      onClose();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to save resolution.");
    } finally {
      setResolving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={modalStyles.keyboardView}
        >
          <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {/* Header */}
            <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
              <View style={{ flex: 1 }}>
                <Text style={[modalStyles.title, { color: colors.text }]}>
                  Resolve Issue: Q{row.raw_question_number || row.normalized_number || "?"}
                </Text>
                <Text style={[modalStyles.subtitle, { color: colors.textSecondary }]}>
                  Resolve mapping ambiguity, marks mismatch or missing solution
                </Text>
              </View>
              <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
                <Ionicons name="close" size={22} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>

            <ScrollView style={modalStyles.body} keyboardShouldPersistTaps="handled">
              {/* ISSUE 1: MARKS MISMATCH */}
              {hasMismatch && (
                <View style={[modalStyles.issueCard, { backgroundColor: "rgba(245, 166, 35, 0.12)", borderColor: colors.warning }]}>
                  <View style={modalStyles.issueHeaderRow}>
                    <Ionicons name="alert-circle" size={18} color={colors.warning} />
                    <Text style={[modalStyles.issueTitle, { color: colors.warning }]}>Marks Discrepancy Detected</Text>
                  </View>
                  <Text style={[modalStyles.issueDesc, { color: colors.text }]}>
                    Answer key says <Text style={{ fontWeight: "700" }}>{row.marks} Marks</Text>, but Question {targetQuestion.display_number} is worth <Text style={{ fontWeight: "700" }}>{targetQuestion.max_marks} Marks</Text>.
                  </Text>

                  <View style={{ gap: 8, marginTop: 10 }}>
                    <Button
                      title={`Keep Question's ${targetQuestion.max_marks} Marks`}
                      variant="primary"
                      size="small"
                      onPress={() => handleResolveMismatch("keep_question_marks")}
                      loading={resolving}
                    />
                    <Button
                      title={`Change Question to ${row.marks} Marks`}
                      variant="secondary"
                      size="small"
                      onPress={() => handleResolveMismatch("use_key_marks")}
                      loading={resolving}
                    />
                  </View>

                  <TextInput
                    style={[
                      modalStyles.input,
                      {
                        backgroundColor: colors.surface,
                        borderColor: colors.border,
                        color: colors.text,
                        marginTop: 10,
                      },
                    ]}
                    value={reason}
                    onChangeText={setReason}
                    placeholder="Reason required if changing question marks..."
                    placeholderTextColor={colors.mutedText}
                  />
                </View>
              )}

              {/* ISSUE 2: MAPPING / NEEDS REVIEW */}
              {isNeedsReview && (
                <View style={[modalStyles.issueCard, { backgroundColor: "rgba(239, 98, 98, 0.12)", borderColor: colors.error }]}>
                  <View style={modalStyles.issueHeaderRow}>
                    <Ionicons name="git-branch-outline" size={18} color={colors.error} />
                    <Text style={[modalStyles.issueTitle, { color: colors.error }]}>
                      Question Mapping Ambiguity ({row.mapping_status})
                    </Text>
                  </View>
                  <Text style={[modalStyles.issueDesc, { color: colors.text }]}>
                    {row.mapping_note || "This answer is not deterministically mapped to any question."}
                  </Text>

                  {candidateQuestion && (
                    <View style={{ marginTop: 10 }}>
                      <Button
                        title={`Accept Suggestion: Question ${candidateQuestion.display_number}`}
                        icon={<Ionicons name="checkmark-circle" size={16} color="#FFFFFF" />}
                        variant="gradient"
                        size="small"
                        onPress={handleAcceptCandidateMapping}
                        loading={resolving}
                        fullWidth
                      />
                    </View>
                  )}

                  <Text style={[modalStyles.label, { color: colors.textSecondary, marginTop: 12 }]}>Or Manually Select Exam Question *</Text>
                  <ScrollView
                    style={[modalStyles.selectScrollBox, { borderColor: colors.border, backgroundColor: colors.surface, maxHeight: 120 }]}
                    nestedScrollEnabled
                  >
                    {questions.map((q) => {
                      const isSelected = q.id === questionId;
                      return (
                        <TouchableOpacity
                          key={q.id}
                          onPress={() => setQuestionId(q.id)}
                          style={[
                            modalStyles.questionOptionRow,
                            {
                              backgroundColor: isSelected ? "rgba(0, 168, 232, 0.16)" : "transparent",
                              borderColor: isSelected ? colors.primary : colors.border,
                            },
                          ]}
                        >
                          <Text style={[{ fontSize: 13, fontWeight: "600" }, { color: isSelected ? colors.primary : colors.text }]}>
                            Question {q.display_number} {q.max_marks != null ? `(${q.max_marks}M)` : ""} — {q.question_text.slice(0, 45)}
                          </Text>
                          {isSelected && <Ionicons name="checkmark-circle" size={16} color={colors.primary} />}
                        </TouchableOpacity>
                      );
                    })}
                  </ScrollView>
                </View>
              )}

              {/* ISSUE 3: EMPTY SOLUTION TEXT */}
              {isEmptyText && (
                <View style={[modalStyles.issueCard, { backgroundColor: "rgba(239, 98, 98, 0.08)", borderColor: colors.error }]}>
                  <View style={modalStyles.issueHeaderRow}>
                    <Ionicons name="document-text-outline" size={18} color={colors.error} />
                    <Text style={[modalStyles.issueTitle, { color: colors.error }]}>Missing Solution Text</Text>
                  </View>
                  <Text style={[modalStyles.issueDesc, { color: colors.text }]}>
                    Enter the model answer below.
                  </Text>

                  <TextInput
                    style={[
                      modalStyles.textArea,
                      {
                        backgroundColor: colors.surface,
                        borderColor: colors.border,
                        color: colors.text,
                        marginTop: 10,
                      },
                    ]}
                    value={solutionText}
                    onChangeText={setSolutionText}
                    multiline
                    numberOfLines={4}
                    placeholder="Enter official model answer here..."
                    placeholderTextColor={colors.mutedText}
                  />
                </View>
              )}

              {/* Common Save Button for Non-Mismatch Resolvers */}
              {(isNeedsReview || isEmptyText) && (
                <View style={{ marginTop: 8, marginBottom: 16 }}>
                  <Button
                    title="Confirm & Resolve Issue"
                    variant="gradient"
                    size="medium"
                    onPress={handleSaveResolution}
                    loading={resolving}
                    fullWidth
                  />
                </View>
              )}
            </ScrollView>

            {/* Footer */}
            <View style={[modalStyles.footer, { borderTopColor: colors.border, backgroundColor: colors.surface }]}>
              <Button title="Close" variant="secondary" size="medium" onPress={onClose} fullWidth />
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
};

// ==========================================
// 3. VALIDATION SUMMARY MODAL
// ==========================================
interface ValidationSummaryModalProps {
  visible: boolean;
  validation: AnswerKeyValidationResponse | null;
  onClose: () => void;
  onReviewIssue: (keyId: string | null, issue: AnswerKeyValidationIssue) => void;
  onProceedToSubmissions?: () => void;
}

export const ValidationSummaryModal: React.FC<ValidationSummaryModalProps> = ({
  visible,
  validation,
  onClose,
  onReviewIssue,
  onProceedToSubmissions,
}) => {
  const { colors } = useTheme();

  if (!validation) return null;

  const { summary, blocking_issues } = validation;
  const isAllValid = validation.valid && summary.blocking_issues_count === 0;

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={modalStyles.overlay}>
        <View style={modalStyles.keyboardView}>
          <View style={[modalStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {/* Header */}
            <View style={[modalStyles.header, { borderBottomColor: colors.border }]}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={[modalStyles.title, { color: colors.text }]}>Validation Summary</Text>
                  <Badge
                    label={isAllValid ? "Ready" : `${summary.blocking_issues_count} Issues`}
                    variant={isAllValid ? "teal" : "danger"}
                  />
                </View>
                <Text style={[modalStyles.subtitle, { color: colors.textSecondary }]}>
                  {summary.total_keys} answer keys checked against backend verification rules
                </Text>
              </View>
              <TouchableOpacity onPress={onClose} style={modalStyles.closeBtn}>
                <Ionicons name="close" size={22} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>

            <ScrollView style={modalStyles.body} keyboardShouldPersistTaps="handled">
              {/* 4 Metrics Cards: Total, Verified, Needs Review, Failed */}
              <View style={summaryStyles.statsGrid}>
                {/* Total Processed */}
                <View
                  style={[
                    summaryStyles.statCard,
                    {
                      backgroundColor: "rgba(0, 168, 232, 0.12)",
                      borderColor: colors.primary,
                    },
                  ]}
                >
                  <Ionicons name="layers-outline" size={20} color={colors.primary} />
                  <Text style={[summaryStyles.statValue, { color: colors.primary }]}>
                    {summary.total_processed ?? summary.total_keys}
                  </Text>
                  <Text style={[summaryStyles.statLabel, { color: colors.textSecondary }]}>
                    Total Processed
                  </Text>
                </View>

                {/* Automatically Verified */}
                <View
                  style={[
                    summaryStyles.statCard,
                    {
                      backgroundColor: "rgba(37, 200, 120, 0.12)",
                      borderColor: colors.brandGreen,
                    },
                  ]}
                >
                  <Ionicons name="checkmark-circle" size={20} color={colors.brandGreen} />
                  <Text style={[summaryStyles.statValue, { color: colors.brandGreen }]}>
                    {summary.verified_count}
                  </Text>
                  <Text style={[summaryStyles.statLabel, { color: colors.textSecondary }]}>
                    Auto-Verified
                  </Text>
                </View>

                {/* Needs Review */}
                <View
                  style={[
                    summaryStyles.statCard,
                    {
                      backgroundColor: "rgba(245, 166, 35, 0.12)",
                      borderColor: colors.warning,
                    },
                  ]}
                >
                  <Ionicons name="time" size={20} color={colors.warning} />
                  <Text style={[summaryStyles.statValue, { color: colors.warning }]}>
                    {summary.needs_review_count}
                  </Text>
                  <Text style={[summaryStyles.statLabel, { color: colors.textSecondary }]}>
                    Needs Review
                  </Text>
                </View>

                {/* Failed Entries */}
                <View
                  style={[
                    summaryStyles.statCard,
                    {
                      backgroundColor: "rgba(239, 98, 98, 0.12)",
                      borderColor: colors.error,
                    },
                  ]}
                >
                  <Ionicons name="alert-circle" size={20} color={colors.error} />
                  <Text style={[summaryStyles.statValue, { color: colors.error }]}>
                    {summary.failed_count ?? 0}
                  </Text>
                  <Text style={[summaryStyles.statLabel, { color: colors.textSecondary }]}>
                    Failed Entries
                  </Text>
                </View>
              </View>

              {/* Status Note Banner */}
              <View
                style={[
                  summaryStyles.noteBanner,
                  {
                    backgroundColor: isAllValid ? "rgba(37, 200, 120, 0.12)" : "rgba(239, 98, 98, 0.1)",
                    borderColor: isAllValid ? colors.brandGreen : colors.error,
                  },
                ]}
              >
                <Ionicons
                  name={isAllValid ? "shield-checkmark" : "information-circle"}
                  size={18}
                  color={isAllValid ? colors.brandGreen : colors.error}
                />
                <Text style={[summaryStyles.noteText, { color: colors.text }]}>
                  {isAllValid
                    ? "All eligible answers verified and approved. Answer key is ready for whole-key validation."
                    : `${summary.verified_count} answer(s) verified automatically. ${summary.needs_review_count + (summary.failed_count || 0)} entry/entries require manual review. Tap Review below to correct.`}
                </Text>
              </View>

              {/* Issues List */}
              {blocking_issues.length > 0 && (
                <View style={{ marginTop: 14 }}>
                  <Text style={[modalStyles.label, { color: colors.textSecondary, marginBottom: 8 }]}>
                    Problematic Answers & Issues ({blocking_issues.length})
                  </Text>

                  {blocking_issues.map((issue, idx) => {
                    const badgeVariant =
                      issue.issue_type === "mark_mismatch"
                        ? "warning"
                        : issue.issue_type === "unapproved"
                        ? "muted"
                        : "danger";

                    const badgeLabel =
                      issue.issue_type === "mark_mismatch"
                        ? "Marks Mismatch"
                        : issue.issue_type === "unapproved"
                        ? "Pending Approval"
                        : issue.issue_type === "empty_solution"
                        ? "Empty Solution"
                        : issue.issue_type === "unmapped"
                        ? "Unmapped"
                        : issue.issue_type === "needs_review"
                        ? "Needs Review"
                        : issue.issue_type === "missing_key"
                        ? "Missing Key"
                        : issue.issue_type === "duplicate_mapping"
                        ? "Duplicate Mapping"
                        : "Issue";

                    return (
                      <View
                        key={idx}
                        style={[
                          summaryStyles.issueItemCard,
                          {
                            backgroundColor: colors.inputBackground,
                            borderColor: colors.border,
                          },
                        ]}
                      >
                        <View style={summaryStyles.issueItemHeader}>
                          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1, flexWrap: "wrap" }}>
                            <Text style={[summaryStyles.issueQuestionText, { color: colors.text }]}>
                              {issue.question}
                            </Text>
                            <Badge label={badgeLabel} variant={badgeVariant as any} />
                          </View>

                          {issue.key_id ? (
                            <Button
                              title="Review"
                              icon={<Ionicons name="arrow-forward" size={14} color="#FFFFFF" />}
                              iconPosition="right"
                              variant="gradient"
                              size="small"
                              onPress={() => onReviewIssue(issue.key_id, issue)}
                            />
                          ) : (
                            <Badge label="Exam Question" variant="muted" />
                          )}
                        </View>

                        <Text style={[summaryStyles.issueReasonText, { color: colors.textSecondary }]}>
                          {issue.reason}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              )}
            </ScrollView>

            {/* Footer */}
            <View style={[modalStyles.footer, { borderTopColor: colors.border, backgroundColor: colors.surface }]}>
              {isAllValid && onProceedToSubmissions ? (
                <View style={{ flexDirection: "row", gap: 10, width: "100%" }}>
                  <Button
                    title="Close"
                    variant="secondary"
                    size="medium"
                    onPress={onClose}
                    style={{ flex: 1 }}
                  />
                  <Button
                    title="Go to Submissions"
                    icon={<Ionicons name="arrow-forward" size={16} color="#FFFFFF" />}
                    variant="gradient"
                    size="medium"
                    onPress={() => {
                      onClose();
                      onProceedToSubmissions();
                    }}
                    style={{ flex: 1.5 }}
                  />
                </View>
              ) : (
                <Button title="Close Summary" variant="secondary" size="medium" onPress={onClose} fullWidth />
              )}
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const summaryStyles = StyleSheet.create({
  statsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 12,
  },
  statsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
  },
  statCard: {
    width: "48.5%",
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 10,
    paddingHorizontal: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  statValue: {
    fontSize: 18,
    fontWeight: "700",
    marginTop: 4,
    marginBottom: 2,
  },
  statLabel: {
    fontSize: 10,
    fontWeight: "600",
    textAlign: "center",
  },
  noteBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 4,
  },
  noteText: {
    fontSize: 12,
    lineHeight: 16,
    flex: 1,
  },
  issueItemCard: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    marginBottom: 10,
  },
  issueItemHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    marginBottom: 6,
  },
  issueQuestionText: {
    fontSize: 14,
    fontWeight: "700",
  },
  issueReasonText: {
    fontSize: 12,
    lineHeight: 16,
  },
});

// ==========================================
// STYLES
// ==========================================
const modalStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.72)",
    justifyContent: "center",
    alignItems: "center",
    padding: 16,
  },
  keyboardView: {
    width: "100%",
    maxWidth: 480,
  },
  dialog: {
    width: "100%",
    borderRadius: 16,
    borderWidth: 1,
    maxHeight: "92%",
    overflow: "hidden",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  title: {
    fontSize: 17,
    fontWeight: "700",
  },
  subtitle: {
    fontSize: 12,
    marginTop: 2,
  },
  closeBtn: {
    padding: 4,
    marginLeft: 8,
  },
  body: {
    paddingHorizontal: 18,
    paddingVertical: 14,
    maxHeight: 460,
  },
  label: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  hintText: {
    fontSize: 11,
    marginTop: 4,
  },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    fontSize: 14,
  },
  textArea: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    minHeight: 88,
    textAlignVertical: "top",
  },
  selectScrollBox: {
    borderWidth: 1,
    borderRadius: 8,
    maxHeight: 140,
    padding: 4,
  },
  questionOptionRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    marginBottom: 4,
  },
  questionOptionTitle: {
    fontSize: 13,
    fontWeight: "600",
  },
  questionOptionSub: {
    fontSize: 11,
    marginTop: 1,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  addCriteriaBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  addCriteriaText: {
    fontSize: 12,
    fontWeight: "600",
  },
  criterionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 8,
  },
  criterionInput: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 13,
  },
  removeCriterionBtn: {
    padding: 4,
  },
  issueCard: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
    marginBottom: 14,
  },
  issueHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 6,
  },
  issueTitle: {
    fontSize: 13,
    fontWeight: "700",
  },
  issueDesc: {
    fontSize: 12,
    lineHeight: 18,
  },
  footer: {
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderTopWidth: 1,
    width: "100%",
  },
  footerActions: {
    flexDirection: "row",
    gap: 10,
  },
});
