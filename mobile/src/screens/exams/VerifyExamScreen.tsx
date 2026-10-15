import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api } from "../../api/client";
import type { ExamDetail, QuestionsResponse, KeysResponse } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Badge, StatusBadge } from "../../components/Badge";
import { Loading } from "../../components/Loading";

interface VerifyExamScreenProps {
  route: any;
  navigation: any;
}

interface IssueItem {
  id: string;
  category: "question_paper" | "questions" | "answer_key" | "marks";
  title: string;
  description: string;
  severity: "critical" | "warning" | "info";
  resolved: boolean;
  actionTitle?: string;
  onAction?: () => void;
}

export const VerifyExamScreen: React.FC<VerifyExamScreenProps> = ({
  route,
  navigation,
}) => {
  const { colors } = useTheme();
  const examId = route.params?.examId;

  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [questionsData, setQuestionsData] = useState<QuestionsResponse | null>(null);
  const [keysData, setKeysData] = useState<KeysResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<"VERIFIED" | "NEEDS_REVIEW" | "FAILED">("NEEDS_REVIEW");

  const fetchData = useCallback(async () => {
    try {
      const [e, q, k] = await Promise.all([
        api<ExamDetail>(`/exams/${examId}`),
        api<QuestionsResponse>(`/exams/${examId}/questions`),
        api<KeysResponse>(`/exams/${examId}/answer-keys`),
      ]);
      setExam(e);
      setQuestionsData(q);
      setKeysData(k);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load examination verification data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [examId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Compile deterministic issues list
  const issues: IssueItem[] = [];

  if (exam && questionsData && keysData) {
    const qList = questionsData.questions || [];
    const kList = keysData.keys || [];

    // 1. Question Paper Document
    if (!exam.question_paper) {
      issues.push({
        id: "qp_missing",
        category: "question_paper",
        title: "Question Paper Missing",
        description: "Upload the official question paper document to begin automated extraction.",
        severity: "critical",
        resolved: false,
        actionTitle: "Upload Paper",
        onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "paper" }),
      });
    } else if (exam.question_paper.status === "NEEDS_ATTENTION" || exam.question_paper.status === "FAILED") {
      issues.push({
        id: "qp_ocr_failed",
        category: "question_paper",
        title: "Question Paper OCR Incomplete",
        description: "One or more pages failed OCR processing with InternVL3.5. Retry failed pages.",
        severity: "critical",
        resolved: false,
        actionTitle: "Retry OCR",
        onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "paper" }),
      });
    }

    // 2. Questions Extraction & Validation
    if (qList.length === 0) {
      issues.push({
        id: "q_empty",
        category: "questions",
        title: "No Questions Extracted",
        description: "No canonical questions have been extracted or added to this examination.",
        severity: "critical",
        resolved: false,
        actionTitle: "Review Questions",
        onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "questions" }),
      });
    } else {
      const unverifiedCount = qList.filter((q) => q.verification_status !== "VERIFIED").length;
      if (unverifiedCount > 0) {
        issues.push({
          id: "q_unverified",
          category: "questions",
          title: `${unverifiedCount} Questions Pending Teacher Approval`,
          description: "All extracted questions must be inspected and approved before the exam can be locked.",
          severity: "critical",
          resolved: false,
          actionTitle: "Accept / Review",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "questions" }),
        });
      }

      // Check duplicates
      const seenLabels = new Set<string>();
      const dups: string[] = [];
      qList.forEach((q) => {
        const norm = q.normalized_number || q.display_number;
        if (seenLabels.has(norm)) dups.push(norm);
        else seenLabels.add(norm);
      });
      if (dups.length > 0) {
        issues.push({
          id: "q_duplicates",
          category: "questions",
          title: `Duplicate Question Labels: ${dups.join(", ")}`,
          description: "Multiple questions share the same question number. Rename or resequence them.",
          severity: "critical",
          resolved: false,
          actionTitle: "Edit Numbers",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "questions" }),
        });
      }

      // Check marks summation
      const sumMarks = questionsData.sum_of_marks || 0;
      if (Math.abs(sumMarks - exam.total_marks) > 0.01) {
        issues.push({
          id: "marks_sum_mismatch",
          category: "marks",
          title: `Total Marks Discrepancy (${sumMarks} vs ${exam.total_marks})`,
          description: `Sum of question marks (${sumMarks}) does not equal the declared exam total (${exam.total_marks}).`,
          severity: "warning",
          resolved: false,
          actionTitle: "Adjust Marks",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "questions" }),
        });
      }
    }

    // 3. Answer Key Validation
    if (kList.length === 0) {
      issues.push({
        id: "ak_missing",
        category: "answer_key",
        title: "Answer Key Missing",
        description: "Upload an official answer key or generate candidate answers using AI.",
        severity: "critical",
        resolved: false,
        actionTitle: "Upload / Generate",
        onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "answerKey" }),
      });
    } else {
      const unmapped = kList.filter((k) => k.mapping_status !== "MAPPED");
      if (unmapped.length > 0) {
        issues.push({
          id: "ak_unmapped",
          category: "answer_key",
          title: `${unmapped.length} Unmapped Answer Key Entries`,
          description: "All answers must be mapped deterministically to a canonical exam question.",
          severity: "critical",
          resolved: false,
          actionTitle: "Map Answers",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "answerKey" }),
        });
      }

      const mismatches = kList.filter((k) => k.mark_mismatch);
      if (mismatches.length > 0) {
        issues.push({
          id: "ak_mismatch",
          category: "answer_key",
          title: `${mismatches.length} MARK MISMATCH Detected`,
          description: "Answer key marks disagree with the authoritative question maximum marks.",
          severity: "critical",
          resolved: false,
          actionTitle: "Resolve Mismatch",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "answerKey" }),
        });
      }

      if (keysData.missing_question_ids && keysData.missing_question_ids.length > 0) {
        issues.push({
          id: "ak_coverage",
          category: "answer_key",
          title: `${keysData.missing_question_ids.length} Questions Lack Answer Keys`,
          description: "Every canonical question requires an approved answer key row.",
          severity: "critical",
          resolved: false,
          actionTitle: "Add Missing Keys",
          onAction: () => navigation.navigate("ExamWorkspace", { examId, initialTab: "answerKey" }),
        });
      }
    }
  }

  const criticalCount = issues.filter((i) => i.severity === "critical").length;
  const warningCount = issues.filter((i) => i.severity === "warning").length;

  const handleVerifyExam = async (confirmMarksMismatch = false) => {
    if (criticalCount > 0) {
      Alert.alert(
        "Verification Blocked",
        `There are ${criticalCount} critical issue(s) that must be resolved before this examination can be marked ready for evaluation.`
      );
      return;
    }

    try {
      setVerifying(true);
      // Run backend question verification
      if (exam?.status === "QUESTIONS_EXTRACTED") {
        await api(`/exams/${examId}/questions/verify`, {
          method: "POST",
          json: confirmMarksMismatch ? { confirm_marks_mismatch: true } : undefined,
        });
      }
      // Run backend answer key verification
      if (exam?.status === "ANSWER_KEY_UPLOADED") {
        await api(`/exams/${examId}/answer-keys/verify`, { method: "POST" });
      }

      Alert.alert(
        "Verification Succeeded",
        "The examination questions and answer keys have been verified and locked. The exam is ready for student evaluation!",
        [
          {
            text: "Open Workspace",
            onPress: () => navigation.navigate("ExamWorkspace", { examId }),
          },
        ]
      );
      fetchData();
    } catch (err: any) {
      if (err?.code === "MARKS_TOTAL_MISMATCH" && !confirmMarksMismatch) {
        Alert.alert("Marks Do Not Add Up", err.message, [
          { text: "Cancel", style: "cancel" },
          { text: "Verify Anyway", onPress: () => handleVerifyExam(true) },
        ]);
        return;
      }
      Alert.alert("Verification Failed", err.message || "Backend verification checks rejected the exam.");
    } finally {
      setVerifying(false);
    }
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Running deterministic exam verification..." />
      </View>
    );
  }

  const overallStatus =
    criticalCount > 0
      ? "FAILED"
      : warningCount > 0
      ? "NEEDS_REVIEW"
      : "VERIFIED";

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        {/* Status Hero Card */}
        <Card style={styles.heroCard}>
          <View style={styles.heroTop}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.examTitle, { color: colors.text }]}>{exam?.name}</Text>
              <Text style={[styles.examMeta, { color: colors.textSecondary }]}>
                {exam?.class_name} • {exam?.subject_name} • {exam?.total_marks} Marks
              </Text>
            </View>
            <View
              style={[
                styles.statusPill,
                {
                  backgroundColor:
                    overallStatus === "VERIFIED"
                      ? colors.successSoft
                      : overallStatus === "NEEDS_REVIEW"
                      ? colors.warningSoft
                      : colors.errorSoft,
                  borderColor:
                    overallStatus === "VERIFIED"
                      ? colors.success
                      : overallStatus === "NEEDS_REVIEW"
                      ? colors.warning
                      : colors.error,
                },
              ]}
            >
              <Ionicons
                name={
                  overallStatus === "VERIFIED"
                    ? "checkmark-circle"
                    : overallStatus === "NEEDS_REVIEW"
                    ? "alert-circle"
                    : "close-circle"
                }
                size={16}
                color={
                  overallStatus === "VERIFIED"
                    ? colors.success
                    : overallStatus === "NEEDS_REVIEW"
                    ? colors.warning
                    : colors.error
                }
              />
              <Text
                style={[
                  styles.statusPillText,
                  {
                    color:
                      overallStatus === "VERIFIED"
                        ? colors.success
                        : overallStatus === "NEEDS_REVIEW"
                        ? colors.warning
                        : colors.error,
                  },
                ]}
              >
                {overallStatus}
              </Text>
            </View>
          </View>

          <View style={[styles.heroSummary, { borderTopColor: colors.border }]}>
            <Text style={[styles.heroSummaryText, { color: colors.textSecondary }]}>
              {overallStatus === "VERIFIED"
                ? "All questions, answer keys, marks, and mappings satisfy deterministic criteria."
                : overallStatus === "NEEDS_REVIEW"
                ? `${warningCount} warning(s) detected. Review before proceeding.`
                : `${criticalCount} critical blocker(s) must be resolved to unlock evaluation.`}
            </Text>
          </View>
        </Card>

        {/* Verification Checklist Section */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          Deterministic Verification Checklist
        </Text>

        {issues.length === 0 ? (
          <Card style={styles.emptyCard}>
            <Ionicons name="checkmark-done-circle" size={48} color={colors.brandGreen} />
            <Text style={[styles.emptyTitle, { color: colors.text }]}>Exam Ready for Evaluation</Text>
            <Text style={[styles.emptySubtitle, { color: colors.textSecondary }]}>
              Zero blockers detected. All questions are mapped and verified against authoritative keys.
            </Text>
          </Card>
        ) : (
          issues.map((issue) => (
            <Card key={issue.id} style={styles.issueCard}>
              <View style={styles.issueRow}>
                <View
                  style={[
                    styles.issueIconCircle,
                    {
                      backgroundColor:
                        issue.severity === "critical"
                          ? colors.errorSoft
                          : issue.severity === "warning"
                          ? colors.warningSoft
                          : colors.surfaceElevated,
                    },
                  ]}
                >
                  <Ionicons
                    name={
                      issue.severity === "critical"
                        ? "close"
                        : issue.severity === "warning"
                        ? "warning-outline"
                        : "information-outline"
                    }
                    size={20}
                    color={
                      issue.severity === "critical"
                        ? colors.error
                        : issue.severity === "warning"
                        ? colors.warning
                        : colors.primary
                    }
                  />
                </View>

                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={[styles.issueTitle, { color: colors.text }]}>
                    {issue.title}
                  </Text>
                  <Text style={[styles.issueDesc, { color: colors.textSecondary }]}>
                    {issue.description}
                  </Text>

                  {issue.actionTitle && issue.onAction && (
                    <TouchableOpacity
                      onPress={issue.onAction}
                      style={[styles.issueActionBtn, { borderColor: colors.primary }]}
                    >
                      <Text style={[styles.issueActionText, { color: colors.primary }]}>
                        {issue.actionTitle}
                      </Text>
                      <Ionicons name="arrow-forward" size={14} color={colors.primary} />
                    </TouchableOpacity>
                  )}
                </View>
              </View>
            </Card>
          ))
        )}

        {/* Bottom Verification Button */}
        <View style={styles.footerActions}>
          <Button
            title={verifying ? "Verifying with Backend..." : "Lock & Confirm Verification"}
            icon={<Ionicons name="shield-checkmark" size={18} color="#FFFFFF" />}
            variant="gradient"
            disabled={criticalCount > 0 || verifying}
            onPress={() => handleVerifyExam()}
          />
          {criticalCount > 0 && (
            <Text style={[styles.blockedHint, { color: colors.error }]}>
              Fix the {criticalCount} critical issue(s) above to enable verification.
            </Text>
          )}
        </View>
      </ScrollView>
    </View>
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
  heroCard: {
    padding: 16,
    marginBottom: 20,
  },
  heroTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  examTitle: {
    fontSize: 18,
    fontWeight: "800",
  },
  examMeta: {
    fontSize: 13,
    marginTop: 4,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 16,
    borderWidth: 1,
    gap: 4,
  },
  statusPillText: {
    fontSize: 12,
    fontWeight: "800",
  },
  heroSummary: {
    borderTopWidth: 1,
    marginTop: 14,
    paddingTop: 10,
  },
  heroSummaryText: {
    fontSize: 13,
    lineHeight: 18,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 12,
  },
  issueCard: {
    padding: 14,
    marginBottom: 10,
  },
  issueRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  issueIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: "center",
    alignItems: "center",
  },
  issueTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  issueDesc: {
    fontSize: 13,
    marginTop: 3,
    lineHeight: 18,
  },
  issueActionBtn: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    marginTop: 10,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    gap: 4,
  },
  issueActionText: {
    fontSize: 12,
    fontWeight: "700",
  },
  emptyCard: {
    alignItems: "center",
    padding: 28,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: "700",
    marginTop: 12,
  },
  emptySubtitle: {
    fontSize: 13,
    textAlign: "center",
    marginTop: 4,
  },
  footerActions: {
    marginTop: 20,
  },
  blockedHint: {
    fontSize: 12,
    fontWeight: "600",
    textAlign: "center",
    marginTop: 8,
  },
});
