import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api, downloadAndShareFile } from "../../api/client";
import type { EvaluationDetail, EvalItem, EvalQuestion, StudentAnswer } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { StatusBadge, Badge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Input } from "../../components/Input";
import { ModalDialog } from "../../components/ModalDialog";
import { AuthImage } from "../../components/AuthImage";

interface EvaluationDetailScreenProps {
  route: any;
  navigation: any;
}

export const EvaluationDetailScreen: React.FC<EvaluationDetailScreenProps> = ({
  route,
  navigation,
}) => {
  const { colors } = useTheme();
  const evaluationId = route.params.evaluationId;

  const [data, setData] = useState<EvaluationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Override Modal state
  const [overrideModal, setOverrideModal] = useState(false);
  const [activeItem, setActiveItem] = useState<EvalItem | null>(null);
  const [activeQuestion, setActiveQuestion] = useState<EvalQuestion | null>(null);
  const [newMark, setNewMark] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [feedback, setFeedback] = useState("");

  const fetchDetail = useCallback(async () => {
    try {
      const res = await api<EvaluationDetail>(`/evaluations/${evaluationId}`);
      setData(res);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load evaluation details");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [evaluationId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchDetail();
  };

  const handleOpenOverride = (item: EvalItem, question: EvalQuestion) => {
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation is finalized and can no longer be changed. Marks cannot be overridden."
      );
      return;
    }
    setActiveItem(item);
    setActiveQuestion(question);
    setNewMark(item.final_marks !== null ? String(item.final_marks) : item.ai_marks !== null ? String(item.ai_marks) : "0");
    setOverrideReason("");
    setFeedback(item.teacher_feedback || "");
    setOverrideModal(true);
  };

  const handleSaveOverride = async () => {
    if (!activeItem) return;
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation is finalized and can no longer be changed. Marks cannot be overridden."
      );
      setOverrideModal(false);
      return;
    }
    const markNum = parseFloat(newMark);
    if (isNaN(markNum) || markNum < 0) {
      Alert.alert("Validation", "Please enter a valid numeric mark.");
      return;
    }
    if (activeQuestion?.max_marks && markNum > activeQuestion.max_marks) {
      Alert.alert("Validation", `Mark cannot exceed maximum marks (${activeQuestion.max_marks}).`);
      return;
    }
    if (!overrideReason.trim()) {
      Alert.alert("Validation", "Please provide a reason for overriding marks.");
      return;
    }

    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/items/${activeItem.id}`, {
        method: "PATCH",
        json: {
          final_marks: markNum,
          reason: overrideReason.trim(),
          teacher_feedback: feedback.trim() || null,
        },
      });
      setOverrideModal(false);
      fetchDetail();
    } catch (err: any) {
      if (err.code === "EVALUATION_FINALIZED" || err.status === 409) {
        Alert.alert(
          "Evaluation Finalized (Read-Only)",
          "This evaluation is finalized and can no longer be changed."
        );
        setOverrideModal(false);
        fetchDetail();
      } else {
        Alert.alert("Error", err.message || "Failed to save mark override");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveAll = async () => {
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation is finalized and can no longer be changed."
      );
      return;
    }
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/items/approve-all`, {
        method: "POST",
      });
      Alert.alert("Approved", "All evaluation items have been approved!");
      fetchDetail();
    } catch (err: any) {
      if (err.code === "EVALUATION_FINALIZED" || err.status === 409) {
        Alert.alert(
          "Evaluation Finalized (Read-Only)",
          "This evaluation is finalized and can no longer be changed."
        );
        fetchDetail();
      } else {
        Alert.alert("Error", err.message || "Failed to approve all items");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleFinalize = async () => {
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert("Already Finalized", "This evaluation has already been finalized.");
      return;
    }
    Alert.alert(
      "Finalize Evaluation",
      "Are you sure you want to finalize this student's result? Once finalized, marks will be locked.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Finalize Result",
          style: "default",
          onPress: async () => {
            try {
              setActionLoading(true);
              await api(`/evaluations/${evaluationId}/finalize`, {
                method: "POST",
              });
              Alert.alert("Success", "Evaluation finalized successfully!");
              fetchDetail();
            } catch (err: any) {
              Alert.alert("Error", err.message || "Failed to finalize evaluation");
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  const handleDownloadReport = async () => {
    try {
      setActionLoading(true);
      const studentName = data?.evaluation.student?.name || "Student";
      const filename = `${studentName.replace(/\s+/g, "_")}_Result_Report.pdf`;
      await downloadAndShareFile(`/evaluations/${evaluationId}/report.pdf`, filename);
    } catch (err: any) {
      Alert.alert("Download Failed", err.message || "Failed to generate report");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading student evaluation details..." />
      </View>
    );
  }

  if (!data) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Empty title="Evaluation Not Found" description="The requested evaluation could not be loaded." />
      </View>
    );
  }

  const { evaluation, exam, questions, items, answers, issues } = data;
  const isFinalized = evaluation.status === "FINALIZED";

  // Index items and answers by exam_question_id
  const itemMap = new Map<string, EvalItem>();
  items.forEach((it) => itemMap.set(it.exam_question_id, it));

  const answerMap = new Map<string, StudentAnswer>();
  answers.forEach((ans) => {
    if (ans.exam_question_id) answerMap.set(ans.exam_question_id, ans);
  });

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
        {/* Student & Score Header Card */}
        <Card style={styles.summaryCard}>
          <View style={styles.summaryHeader}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.studentName, { color: colors.text }]}>
                {evaluation.student?.name}
              </Text>
              <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                Roll No: {evaluation.student?.roll_number} • {exam.name}
              </Text>
            </View>
            <StatusBadge status={evaluation.status} />
          </View>

          <View style={[styles.scoreRow, { borderColor: colors.border }]}>
            <View style={styles.scoreCol}>
              <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Final Marks</Text>
              <PenScore
                score={evaluation.total_marks}
                maxScore={evaluation.maximum_marks}
                size="large"
              />
            </View>

            {evaluation.percentage !== null && evaluation.percentage !== undefined && (
              <View style={styles.scoreCol}>
                <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Percentage</Text>
                <Text style={[styles.percentageValue, { color: colors.brandGreen }]}>
                  {evaluation.percentage.toFixed(1)}%
                </Text>
              </View>
            )}
          </View>

          {/* Action Buttons Row */}
          <View style={styles.actionRow}>
            <Button
              title="Download Report"
              icon={<Ionicons name="download-outline" size={16} color="#FFFFFF" />}
              variant="gradient"
              size="small"
              onPress={handleDownloadReport}
              loading={actionLoading}
              style={{ flex: 1 }}
            />
            {!isFinalized ? (
              <>
                <Button
                  title="Approve All"
                  icon={<Ionicons name="checkmark-done" size={16} color={colors.text} />}
                  variant="secondary"
                  size="small"
                  onPress={handleApproveAll}
                  loading={actionLoading}
                  style={{ flex: 1 }}
                />
                <Button
                  title="Finalize"
                  icon={<Ionicons name="lock-closed-outline" size={16} color="#FFFFFF" />}
                  variant="primary"
                  size="small"
                  onPress={handleFinalize}
                  loading={actionLoading}
                />
              </>
            ) : (
              <Button
                title="View Result Sheet"
                icon={<Ionicons name="ribbon-outline" size={16} color={colors.text} />}
                variant="secondary"
                size="small"
                onPress={() => navigation.navigate("ResultDetail", { evaluationId })}
                style={{ flex: 1 }}
              />
            )}
          </View>
        </Card>

        {/* Finalized Read-Only Notice Banner */}
        {isFinalized && (
          <View
            style={[
              styles.finalizedNoticeCard,
              { backgroundColor: "rgba(37, 200, 120, 0.08)", borderColor: colors.brandGreen },
            ]}
          >
            <View style={[styles.finalizedIconBox, { backgroundColor: "rgba(37, 200, 120, 0.16)" }]}>
              <Ionicons name="lock-closed" size={20} color={colors.brandGreen} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.finalizedNoticeTitle, { color: colors.text }]}>
                Evaluation Finalized (Read-Only)
              </Text>
              <Text style={[styles.finalizedNoticeDesc, { color: colors.textSecondary }]}>
                This evaluation is approved and finalized. All marks, feedback, and student responses are locked and cannot be edited.
              </Text>
            </View>
          </View>
        )}

        {/* Issues Warning Banner */}
        {issues && issues.length > 0 && (
          <View style={[styles.issuesBanner, { backgroundColor: "rgba(240, 182, 90, 0.12)", borderColor: colors.warning }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <Ionicons name="warning" size={18} color={colors.warning} />
              <Text style={[styles.issuesTitle, { color: colors.warning }]}>
                Issues Require Teacher Review ({issues.length})
              </Text>
            </View>
            {issues.map((iss, idx) => (
              <Text key={idx} style={[styles.issueItem, { color: colors.text }]}>
                • Q{iss.question}: {iss.reason}
              </Text>
            ))}
          </View>
        )}

        <Text style={[styles.sectionHeading, { color: colors.text }]}>Question-Wise Evaluation</Text>

        {/* Questions List */}
        {questions.map((q) => {
          const item = itemMap.get(q.id);
          const studentAns = answerMap.get(q.id);

          return (
            <Card key={q.id} style={styles.questionCard}>
              <View style={styles.qHeader}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Badge label={`Q${q.display_number}`} variant="teal" />
                  <Text style={[styles.maxMarksText, { color: colors.textSecondary }]}>
                    (Max: {q.max_marks ?? "?"} Marks)
                  </Text>
                </View>
                {item && (
                  <PenScore
                    score={item.final_marks ?? item.ai_marks}
                    maxScore={q.max_marks}
                    overridden={item.teacher_overridden}
                  />
                )}
              </View>

              <Text style={[styles.questionBody, { color: colors.text }]}>
                {q.question_text || q.raw_ocr_text}
              </Text>

              {/* Official Answer */}
              {q.official_answer && (
                <View style={[styles.block, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                  <Text style={[styles.blockTitle, { color: colors.primary }]}>Official Solution & Criteria:</Text>
                  <Text style={[styles.blockText, { color: colors.text }]}>{q.official_answer}</Text>
                  {q.criteria && q.criteria.length > 0 && (
                    <View style={{ marginTop: 6 }}>
                      {q.criteria.map((c, i) => (
                        <Text key={i} style={[styles.bullet, { color: colors.textSecondary }]}>• {c}</Text>
                      ))}
                    </View>
                  )}
                </View>
              )}

              {/* Student's Answer */}
              <View style={[styles.block, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.blockTitle, { color: colors.brandGreen }]}>Student's Handwritten Answer:</Text>
                <Text style={[styles.blockText, { color: colors.text }]}>
                  {studentAns?.answer_text || studentAns?.raw_ocr_text || "No handwritten response detected"}
                </Text>
                {studentAns?.has_crop && (
                  <View style={{ marginTop: 8 }}>
                    <Text style={{ fontSize: 11, fontWeight: "600", color: colors.textSecondary, marginBottom: 4 }}>
                      Handwritten Page Crop:
                    </Text>
                    <AuthImage
                      path={`/crops/student-answer/${studentAns.id}`}
                      style={{ minHeight: 120, maxHeight: 220, width: "100%", borderRadius: 6 }}
                    />
                  </View>
                )}
              </View>

              {/* AI Evaluation */}
              {item && (
                <View style={[styles.aiBlock, { borderColor: colors.border }]}>
                  <View style={styles.aiHeader}>
                    <Text style={[styles.aiTitle, { color: colors.primary }]}>
                      AI Marking Feedback (InternVL3.5)
                    </Text>
                    <Badge
                      label={item.ai_decision || item.status}
                      variant={item.ai_decision === "CORRECT" ? "success" : item.ai_decision === "PARTIAL" ? "warning" : "muted"}
                    />
                  </View>

                  {item.ai_feedback && (
                    <Text style={[styles.feedbackText, { color: colors.text }]}>
                      {item.ai_feedback}
                    </Text>
                  )}

                  {item.matched_points && item.matched_points.length > 0 && (
                    <View style={{ marginTop: 6 }}>
                      <Text style={[styles.pointsLabel, { color: colors.brandGreen }]}>Matched Points:</Text>
                      {item.matched_points.map((p, i) => (
                        <Text key={i} style={[styles.bullet, { color: colors.textSecondary }]}>✓ {p}</Text>
                      ))}
                    </View>
                  )}

                  {item.missing_points && item.missing_points.length > 0 && (
                    <View style={{ marginTop: 6 }}>
                      <Text style={[styles.pointsLabel, { color: colors.warning }]}>Missing Points:</Text>
                      {item.missing_points.map((p, i) => (
                        <Text key={i} style={[styles.bullet, { color: colors.textSecondary }]}>✗ {p}</Text>
                      ))}
                    </View>
                  )}

                  {item.teacher_overridden && (
                    <View style={[styles.overriddenBadge, { backgroundColor: "rgba(239, 100, 100, 0.1)" }]}>
                      <Ionicons name="pencil" size={14} color={colors.error} />
                      <Text style={[styles.overriddenText, { color: colors.error }]}>
                        Teacher Override Recorded
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* Teacher Override Button */}
              {!isFinalized && item && (
                <View style={styles.overrideBtnWrapper}>
                  <Button
                    title={item.teacher_overridden ? "Edit Teacher Override" : "Override Marks"}
                    icon={<Ionicons name="create-outline" size={14} color={colors.primary} />}
                    variant="outline"
                    size="small"
                    onPress={() => handleOpenOverride(item, q)}
                  />
                </View>
              )}
            </Card>
          );
        })}
      </ScrollView>

      {/* Override Modal */}
      <ModalDialog
        visible={overrideModal}
        onClose={() => setOverrideModal(false)}
        title={`Override Marks (Q${activeQuestion?.display_number})`}
        subtitle={`Max Marks: ${activeQuestion?.max_marks ?? "?"}`}
      >
        <Input
          label="Awarded Mark *"
          value={newMark}
          onChangeText={setNewMark}
          keyboardType="numeric"
          autoFocus
        />
        <Input
          label="Reason for Override *"
          placeholder="e.g. Valid alternative method, partial credit for step 2"
          value={overrideReason}
          onChangeText={setOverrideReason}
        />
        <Input
          label="Teacher Feedback (Optional)"
          placeholder="Comments visible on report..."
          value={feedback}
          onChangeText={setFeedback}
          multiline
        />
        <Button
          title="Save Override & Mark"
          onPress={handleSaveOverride}
          variant="gradient"
          loading={actionLoading}
          fullWidth
          style={{ marginTop: 12 }}
        />
      </ModalDialog>
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
  summaryCard: {
    padding: 18,
    marginBottom: 16,
  },
  summaryHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  studentName: {
    fontSize: 20,
    fontWeight: "800",
  },
  metaText: {
    fontSize: 12,
    marginTop: 4,
  },
  scoreRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    marginTop: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  scoreCol: {
    alignItems: "center",
  },
  scoreLabel: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
  },
  percentageValue: {
    fontSize: 28,
    fontWeight: "800",
  },
  actionRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 16,
  },
  issuesBanner: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  issuesTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  issueItem: {
    fontSize: 12,
    marginTop: 2,
    lineHeight: 18,
  },
  sectionHeading: {
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 12,
  },
  questionCard: {
    padding: 16,
    marginBottom: 14,
  },
  qHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  maxMarksText: {
    fontSize: 12,
    fontWeight: "500",
  },
  questionBody: {
    fontSize: 15,
    fontWeight: "600",
    lineHeight: 22,
    marginBottom: 12,
  },
  block: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
  },
  blockTitle: {
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 4,
  },
  blockText: {
    fontSize: 13,
    lineHeight: 18,
  },
  bullet: {
    fontSize: 12,
    lineHeight: 16,
  },
  aiBlock: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: "rgba(7, 159, 189, 0.05)",
    marginBottom: 10,
  },
  aiHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  aiTitle: {
    fontSize: 12,
    fontWeight: "700",
  },
  feedbackText: {
    fontSize: 13,
    lineHeight: 18,
  },
  pointsLabel: {
    fontSize: 11,
    fontWeight: "700",
    marginTop: 4,
    marginBottom: 2,
  },
  overriddenBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    padding: 6,
    borderRadius: 6,
    marginTop: 8,
  },
  overriddenText: {
    fontSize: 11,
    fontWeight: "700",
  },
  overrideBtnWrapper: {
    alignItems: "flex-end",
    marginTop: 4,
  },
  finalizedNoticeCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  finalizedIconBox: {
    width: 38,
    height: 38,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  finalizedNoticeTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  finalizedNoticeDesc: {
    fontSize: 12,
    lineHeight: 17,
    marginTop: 2,
  },
});
