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
  Modal,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
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

  // Edit Student Answer Modal state
  const [transcriptionModal, setTranscriptionModal] = useState(false);
  const [activeAnswer, setActiveAnswer] = useState<StudentAnswer | null>(null);
  const [transcriptionText, setTranscriptionText] = useState("");
  const [transcriptionReason, setTranscriptionReason] = useState("");

  // Tab State: Mapping Review vs Marks & Finalize
  const [activeTab, setActiveTab] = useState<"mapping" | "marks">("mapping");
  const [mappingFilter, setMappingFilter] = useState<
    "All" | "Mapped" | "Suggested" | "Needs review" | "Unmapped" | "Missing" | "OCR error"
  >("All");
  const [activeSheetPage, setActiveSheetPage] = useState(1);

  // Change Mapping Modal state
  const [mapModalVisible, setMapModalVisible] = useState(false);
  const [targetMapAnswer, setTargetMapAnswer] = useState<StudentAnswer | null>(null);
  const [mapQuestionId, setMapQuestionId] = useState("");
  const [mapRawLabel, setMapRawLabel] = useState("");
  const [mapAnswerText, setMapAnswerText] = useState("");
  const [mapReason, setMapReason] = useState("");

  // Split Answer Modal state
  const [splitModalVisible, setSplitModalVisible] = useState(false);
  const [splitTargetAnswer, setSplitTargetAnswer] = useState<StudentAnswer | null>(null);
  const [splitPos, setSplitPos] = useState(1);
  const [splitNewLabel, setSplitNewLabel] = useState("");

  // Merge Answer Modal state
  const [mergeModalVisible, setMergeModalVisible] = useState(false);
  const [mergeTargetAnswer, setMergeTargetAnswer] = useState<StudentAnswer | null>(null);
  const [mergeOtherAnswerId, setMergeOtherAnswerId] = useState("");

  // Original Handwriting Page / Crop Viewer Modal state
  const [imageViewerModal, setImageViewerModal] = useState(false);
  const [imageViewerPath, setImageViewerPath] = useState<string | null>(null);
  const [imageViewerTitle, setImageViewerTitle] = useState("");
  const [imageViewerAnswer, setImageViewerAnswer] = useState<StudentAnswer | null>(null);
  const [imageViewerQuestion, setImageViewerQuestion] = useState<EvalQuestion | null>(null);

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

  // Reactive polling while AI evaluation is running in background
  useEffect(() => {
    if (data?.evaluation.run_status === "RUNNING") {
      const timer = setInterval(() => {
        fetchDetail();
      }, 1500);
      return () => clearInterval(timer);
    }
  }, [data?.evaluation.run_status, fetchDetail]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchDetail();
  };

  // --- Handlers ---

  const handleStartEvaluation = async () => {
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation is finalized and cannot be re-evaluated."
      );
      return;
    }
    if (data?.evaluation.run_status === "RUNNING") {
      Alert.alert("Already Running", "AI evaluation is already in progress.");
      return;
    }

    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/run`, { method: "POST" });
      Alert.alert(
        "Evaluation Started",
        "InternVL3.5 4B is now evaluating each student response against official solutions and scoring rubrics. Results will stream in automatically."
      );
      fetchDetail();
    } catch (err: any) {
      if (err.code === "MAPPING_INCOMPLETE") {
        const issuesSummary = err.issues
          ? err.issues.map((i: any) => `• ${i.question}: ${i.reason}`).join("\n")
          : err.message;
        Alert.alert("Mapping Incomplete", `${err.message}\n\n${issuesSummary}`);
      } else if (err.code === "EXAM_NOT_READY") {
        Alert.alert(
          "Exam Not Ready",
          "The question paper and answer key must be verified in the Exam Workspace before starting evaluation."
        );
      } else {
        Alert.alert("Evaluation Error", err.message || "Failed to start evaluation");
      }
    } finally {
      setActionLoading(false);
    }
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
    setNewMark(
      item.final_marks !== null
        ? String(item.final_marks)
        : item.ai_marks !== null
        ? String(item.ai_marks)
        : "0"
    );
    setOverrideReason("");
    setFeedback(item.teacher_feedback || "");
    setOverrideModal(true);
  };

  const handleSaveOverride = async () => {
    if (!activeItem) return;
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation is finalized and can no longer be changed."
      );
      setOverrideModal(false);
      return;
    }
    const markNum = parseFloat(newMark);
    if (isNaN(markNum) || markNum < 0) {
      Alert.alert("Validation", "Please enter a valid numeric mark.");
      return;
    }
    if (activeQuestion?.max_marks !== null && activeQuestion?.max_marks !== undefined && markNum > activeQuestion.max_marks) {
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

  const handleApproveItem = async (item: EvalItem, question: EvalQuestion) => {
    if (data?.evaluation.status === "FINALIZED") return;
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/items/${item.id}`, {
        method: "PATCH",
        json: { approve: true },
      });
      fetchDetail();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to approve question marks");
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmNotAttempted = async (item: EvalItem, question: EvalQuestion) => {
    if (data?.evaluation.status === "FINALIZED") return;
    Alert.alert(
      `Confirm Q${question.display_number} Not Attempted`,
      "Confirm that the student did not attempt this question? Final mark will be recorded as 0.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Confirm (0 Marks)",
          style: "default",
          onPress: async () => {
            try {
              setActionLoading(true);
              await api(`/evaluations/${evaluationId}/items/${item.id}`, {
                method: "PATCH",
                json: { confirm_not_attempted: true, approve: true },
              });
              fetchDetail();
            } catch (err: any) {
              Alert.alert("Error", err.message || "Failed to confirm question status");
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  const handleRerunItem = async (item: EvalItem) => {
    if (data?.evaluation.status === "FINALIZED") return;
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/items/${item.id}/rerun`, {
        method: "POST",
      });
      fetchDetail();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to re-evaluate question");
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

    const eligible = (data?.items || []).filter(
      (it) => it.status === "EVALUATED" && it.final_marks !== null
    );

    if (eligible.length === 0) {
      Alert.alert(
        "No Eligible Items",
        "There are no evaluated items awaiting approval. Run AI evaluation first or resolve question errors."
      );
      return;
    }

    const summaryStr = eligible
      .map((it) => {
        const q = data?.questions.find((x) => x.id === it.exam_question_id);
        return `• Q${q?.display_number || "?"}: ${it.final_marks} marks`;
      })
      .join("\n");

    Alert.alert(
      "Approve Evaluated Items",
      `Approve ${eligible.length} cleanly evaluated question(s)?\n\n${summaryStr}\n\nUnevaluated, errored, or missing items will remain unapproved.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: `Approve (${eligible.length})`,
          style: "default",
          onPress: async () => {
            try {
              setActionLoading(true);
              const res: any = await api(`/evaluations/${evaluationId}/items/approve-all`, {
                method: "POST",
              });
              Alert.alert(
                "Approved",
                `${res.approved ?? eligible.length} evaluation item(s) approved successfully!`
              );
              fetchDetail();
            } catch (err: any) {
              Alert.alert("Error", err.message || "Failed to approve items");
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  const handleFinalize = async () => {
    if (data?.evaluation.status === "FINALIZED") {
      Alert.alert("Already Finalized", "This evaluation has already been finalized.");
      return;
    }

    if (!isFinalizable) {
      Alert.alert(
        "Finalization Blocked",
        `All evaluation items must be evaluated and approved before finalization. ${issues.length} issue(s) remaining.`
      );
      return;
    }

    Alert.alert(
      "Finalize Evaluation",
      `Are you sure you want to finalize this student's result?\n\nTotal Marks: ${totalProvisionalMarks} / ${totalMaxMarks}\n\nOnce finalized, marks will be officially locked and cannot be edited.`,
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
              Alert.alert("Success", "Evaluation finalized successfully! Marks are now locked.");
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
    if (!isFinalized) {
      Alert.alert(
        "Report Not Ready",
        "Official PDF reports can only be downloaded after the evaluation is finalized."
      );
      return;
    }
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

  const handleOpenEditTranscription = (ans: StudentAnswer, q?: EvalQuestion | null, it?: EvalItem | null) => {
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked. Editing is only permitted through an authorized correction/reopening workflow."
      );
      return;
    }
    setActiveAnswer(ans);
    setActiveQuestion(q || null);
    setActiveItem(it || (q ? itemMap.get(q.id) ?? null : null));
    setTranscriptionText(ans.answer_text || "");
    setTranscriptionReason("");
    setTranscriptionModal(true);
  };

  const handleSaveTranscription = async () => {
    if (!activeAnswer) return;
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked. Editing is only permitted through an authorized correction/reopening workflow."
      );
      setTranscriptionModal(false);
      return;
    }
    if (!transcriptionReason.trim()) {
      Alert.alert(
        "Reason Required",
        "Please enter a reason for the transcription correction (e.g. OCR misread handwriting, Tamil script, or missing mathematical steps)."
      );
      return;
    }

    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/mapping/${activeAnswer.id}`, {
        method: "PATCH",
        json: {
          answer_text: transcriptionText,
          reason: transcriptionReason.trim(),
        },
      });

      setTranscriptionModal(false);
      await fetchDetail();

      const currentItem = activeItem || (activeQuestion ? itemMap.get(activeQuestion.id) : null);

      Alert.alert(
        "Transcription Saved",
        "The corrected student answer has been saved and audited. Previous evaluation marks have been reset so they do not show as stale.",
        [
          { text: "Review on Screen", style: "cancel" },
          ...(currentItem
            ? [
                {
                  text: "Re-evaluate Now (InternVL)",
                  onPress: () => handleRerunItem(currentItem),
                },
              ]
            : []),
        ]
      );
    } catch (err: any) {
      if (err.code === "EVALUATION_FINALIZED" || err.status === 409) {
        Alert.alert(
          "Evaluation Finalized (Read-Only)",
          "This evaluation has been finalized and locked. Editing is only permitted through an authorized correction/reopening workflow."
        );
        setTranscriptionModal(false);
        fetchDetail();
      } else {
        Alert.alert("Error", err.message || "Failed to save corrected answer transcription");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleViewOriginalPage = (ans: StudentAnswer, q: EvalQuestion) => {
    const pageNum = ans.page_number || 1;
    const docId = data?.document?.id || "";
    setImageViewerPath(`/documents/answer-sheet/${docId}/pages/${pageNum}/image`);
    setImageViewerTitle(`Answer Sheet • Page ${pageNum} (Q${q.display_number})`);
    setImageViewerAnswer(ans);
    setImageViewerQuestion(q);
    setImageViewerModal(true);
  };

  const handleViewCrop = (ans: StudentAnswer, q?: EvalQuestion | null) => {
    setImageViewerPath(`/crops/student-answer/${ans.id}`);
    setImageViewerTitle(
      q
        ? `Handwritten Response Crop • Q${q.display_number}`
        : `Handwritten Crop (${ans.raw_question_number ?? "no number"})`
    );
    setImageViewerAnswer(ans);
    setImageViewerQuestion(q || null);
    setImageViewerModal(true);
  };

  const handleOpenChangeMapping = (ans: StudentAnswer) => {
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked. Editing is only permitted through an authorized correction/reopening workflow."
      );
      return;
    }
    setTargetMapAnswer(ans);
    setMapQuestionId(ans.exam_question_id || "");
    setMapRawLabel(ans.raw_question_number || "");
    setMapAnswerText(ans.answer_text || "");
    setMapReason("");
    setMapModalVisible(true);
  };

  const handleSaveMapping = async () => {
    if (!targetMapAnswer) return;
    try {
      setActionLoading(true);
      const json: Record<string, any> = {};
      if (mapReason.trim()) json.reason = mapReason.trim();
      if (mapAnswerText !== targetMapAnswer.answer_text) json.answer_text = mapAnswerText;
      if (mapQuestionId !== (targetMapAnswer.exam_question_id || "")) {
        json.exam_question_id = mapQuestionId || null;
      }
      if (mapRawLabel !== (targetMapAnswer.raw_question_number || "")) {
        json.raw_question_number = mapRawLabel.trim();
      }

      await api(`/evaluations/${evaluationId}/mapping/${targetMapAnswer.id}`, {
        method: "PATCH",
        json,
      });
      setMapModalVisible(false);
      setTargetMapAnswer(null);
      await fetchDetail();
      Alert.alert("Mapping Updated", "Student answer mapping has been updated successfully.");
    } catch (err: any) {
      Alert.alert("Mapping Error", err.message || "Failed to update answer mapping.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenSplitAnswer = (ans: StudentAnswer) => {
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked."
      );
      return;
    }
    const mid = Math.max(1, Math.floor(ans.answer_text.length / 2));
    setSplitTargetAnswer(ans);
    setSplitPos(mid);
    setSplitNewLabel("");
    setSplitModalVisible(true);
  };

  const handleSplitAnswer = async () => {
    if (!splitTargetAnswer || !splitNewLabel.trim()) {
      Alert.alert("Question Number Required", "Please enter a question number for the second answer.");
      return;
    }
    if (splitPos <= 0 || splitPos >= splitTargetAnswer.answer_text.length) {
      Alert.alert("Invalid Position", "Split position must be within the answer text.");
      return;
    }
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/answers/${splitTargetAnswer.id}/split`, {
        method: "POST",
        json: {
          at_char: splitPos,
          new_label: splitNewLabel.trim(),
        },
      });
      setSplitModalVisible(false);
      setSplitTargetAnswer(null);
      await fetchDetail();
      Alert.alert("Answer Split", "Answer block has been split into two separate responses.");
    } catch (err: any) {
      Alert.alert("Split Error", err.message || "Failed to split answer.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenMergeAnswer = (ans: StudentAnswer) => {
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked."
      );
      return;
    }
    setMergeTargetAnswer(ans);
    setMergeOtherAnswerId("");
    setMergeModalVisible(true);
  };

  const handleMergeAnswer = async () => {
    if (!mergeTargetAnswer || !mergeOtherAnswerId) {
      Alert.alert("Selection Required", "Please choose an answer to merge.");
      return;
    }
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/answers/${mergeTargetAnswer.id}/merge`, {
        method: "POST",
        json: {
          other_id: mergeOtherAnswerId,
        },
      });
      setMergeModalVisible(false);
      setMergeTargetAnswer(null);
      await fetchDetail();
      Alert.alert("Answers Merged", "The selected responses have been merged into one.");
    } catch (err: any) {
      Alert.alert("Merge Error", err.message || "Failed to merge answers.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleMappingAction = async (
    ans: StudentAnswer,
    payload: Record<string, any>,
    label: string
  ) => {
    if (isFinalized) {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        "This evaluation has been finalized and locked."
      );
      return;
    }
    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/mapping/${ans.id}`, {
        method: "PATCH",
        json: payload,
      });
      await fetchDetail();
    } catch (err: any) {
      Alert.alert("Action Error", err.message || `Failed to ${label}`);
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

  const { evaluation, exam, questions, items, answers, issues, summary, document } = data;
  const isFinalized = evaluation.status === "FINALIZED";
  const isRunning = evaluation.run_status === "RUNNING";
  const isRunError = evaluation.run_status === "ERROR";

  // Index items and answers by exam_question_id
  const itemMap = new Map<string, EvalItem>();
  items.forEach((it) => itemMap.set(it.exam_question_id, it));

  const answerMap = new Map<string, StudentAnswer>();
  answers.forEach((ans) => {
    if (ans.exam_question_id) answerMap.set(ans.exam_question_id, ans);
  });

  // Derived evaluation states
  const hasAnyEvaluated = items.some(
    (it) => it.status === "EVALUATED" || it.status === "APPROVED" || it.teacher_overridden
  );
  const eligibleForApproval = items.filter(
    (it) => it.status === "EVALUATED" && it.final_marks !== null
  );

  const totalProvisionalMarks = questions.reduce((sum, q) => {
    const it = itemMap.get(q.id);
    return sum + (it?.final_marks ?? it?.ai_marks ?? 0);
  }, 0);
  const totalMaxMarks = questions.reduce((sum, q) => sum + (q.max_marks || 0), 0);

  // Check prerequisites for evaluation run
  const mappingIssuesCount = (summary?.unmapped || 0) + (summary?.needs_review || 0);
  const ocrFailedCount =
    document?.pages?.filter((p) => p.ocr_status && p.ocr_status !== "OK").length || 0;
  const isExamReady =
    exam.status === "ANSWER_KEY_VERIFIED" ||
    exam.status === "READY_FOR_EVALUATION" ||
    exam.status === "EVALUATING" ||
    exam.status === "REVIEW_REQUIRED";

  let isEvalBlocked = false;
  let evalBlockReason = "";
  if (document?.status !== "READY" && document?.status !== "NEEDS_ATTENTION") {
    isEvalBlocked = true;
    evalBlockReason = "Answer sheet is still undergoing OCR reading. Please wait for OCR to complete.";
  } else if (!isExamReady) {
    isEvalBlocked = true;
    evalBlockReason = "Question paper and answer key must be verified in Exam Workspace before evaluation.";
  } else if (mappingIssuesCount > 0) {
    isEvalBlocked = true;
    evalBlockReason = `${mappingIssuesCount} student answer(s) are unmapped or need mapping review before running evaluation.`;
  } else if (ocrFailedCount > 0) {
    isEvalBlocked = true;
    evalBlockReason = `${ocrFailedCount} answer sheet page(s) failed OCR. Retry page reading before evaluating.`;
  }

  // Mapping review data derived
  const qmap = new Map(questions.map((q) => [q.id, q]));
  // Same buckets as the summary counts: questions with neither a mapped answer nor a suggestion.
  const missingQuestionIds = new Set(summary?.missing_question_ids ?? []);
  const missingQuestions = questions.filter((q) => missingQuestionIds.has(q.id));
  const ocrErrorPages =
    document?.pages?.filter((p) => p.ocr_status && p.ocr_status !== "OK") || [];

  const mappingRows = answers.filter((a) => {
    switch (mappingFilter) {
      case "Mapped":
        return ["MAPPED", "EVALUATING", "EVALUATED", "APPROVED"].includes(a.status);
      case "Suggested":
        return (
          a.status === "NEEDS_REVIEW" &&
          a.mapping_candidates &&
          a.mapping_candidates.length > 0
        );
      case "Unmapped":
        return a.status === "UNMAPPED";
      case "Needs review":
        return a.status === "NEEDS_REVIEW";
      case "Missing":
      case "OCR error":
        return false;
      default:
        return true;
    }
  });

  // Finalization readiness check
  const isFinalizable =
    !isFinalized &&
    !isRunning &&
    issues.length === 0 &&
    items.length > 0 &&
    items.every(
      (it) =>
        it.status === "APPROVED" ||
        (it.status === "MISSING" && it.not_attempted_confirmed)
    );

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
            <View style={styles.studentInfoContainer}>
              <View
                style={[
                  styles.avatarCircle,
                  { backgroundColor: "rgba(7, 159, 189, 0.15)", borderColor: colors.primary },
                ]}
              >
                <Text style={[styles.avatarText, { color: colors.primary }]}>
                  {evaluation.student?.name ? evaluation.student.name.charAt(0).toUpperCase() : "S"}
                </Text>
              </View>
              <View style={styles.studentTextWrapper}>
                <Text
                  style={[styles.studentName, { color: colors.text }]}
                  numberOfLines={1}
                  ellipsizeMode="tail"
                >
                  {evaluation.student?.name || "Student Submission"}
                </Text>
                <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                  Roll No: <Text style={{ color: colors.text, fontWeight: "700" }}>{evaluation.student?.roll_number}</Text> • {exam.name}
                </Text>
              </View>
            </View>
            <StatusBadge
              status={isRunning ? "EVALUATING" : evaluation.status}
              style={{ alignSelf: "flex-start" }}
            />
          </View>

          {/* Scores Row */}
          <View style={[styles.scoreRow, { borderColor: colors.border }]}>
            <View style={styles.scoreCol}>
              <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Final Marks</Text>
              <PenScore
                score={isFinalized ? evaluation.total_marks : null}
                maxScore={evaluation.maximum_marks}
                size="large"
              />
              {!isFinalized && (
                <Text style={[styles.scoreSubHint, { color: colors.textSecondary }]}>
                  {hasAnyEvaluated
                    ? `Provisional: ${totalProvisionalMarks} / ${totalMaxMarks}`
                    : "Not finalized yet"}
                </Text>
              )}
            </View>

            <View style={styles.scoreCol}>
              <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Percentage</Text>
              {isFinalized && evaluation.percentage !== null && evaluation.percentage !== undefined ? (
                <Text style={[styles.percentageValue, { color: colors.brandGreen }]}>
                  {evaluation.percentage.toFixed(1)}%
                </Text>
              ) : (
                <Text style={[styles.percentageValue, { color: colors.textSecondary }]}>
                  --
                </Text>
              )}
              {!isFinalized && hasAnyEvaluated && totalMaxMarks > 0 && (
                <Text style={[styles.scoreSubHint, { color: colors.textSecondary }]}>
                  Provisional: {((totalProvisionalMarks / totalMaxMarks) * 100).toFixed(1)}%
                </Text>
              )}
            </View>
          </View>

          {/* Action Buttons Row */}
          <View style={styles.actionRow}>
            {!isFinalized ? (
              <>
                <Button
                  title={hasAnyEvaluated ? "Re-run Evaluation" : "Start Evaluation"}
                  icon={<Ionicons name="sparkles" size={16} color="#FFFFFF" />}
                  variant="gradient"
                  size="small"
                  onPress={handleStartEvaluation}
                  loading={isRunning || actionLoading}
                  disabled={isEvalBlocked || isRunning}
                  style={{ flex: 1.3 }}
                />
                <Button
                  title={`Approve All${eligibleForApproval.length > 0 ? ` (${eligibleForApproval.length})` : ""}`}
                  icon={
                    <Ionicons
                      name="checkmark-done"
                      size={16}
                      color={eligibleForApproval.length > 0 ? colors.text : colors.textSecondary}
                    />
                  }
                  variant="secondary"
                  size="small"
                  onPress={handleApproveAll}
                  loading={actionLoading}
                  disabled={eligibleForApproval.length === 0 || isRunning}
                  style={{ flex: 1 }}
                />
                <Button
                  title="Finalize"
                  icon={
                    <Ionicons
                      name="lock-closed-outline"
                      size={16}
                      color={isFinalizable ? "#FFFFFF" : colors.textSecondary}
                    />
                  }
                  variant={isFinalizable ? "primary" : "outline"}
                  size="small"
                  onPress={handleFinalize}
                  loading={actionLoading}
                  disabled={!isFinalizable || isRunning}
                  style={{ flex: 1 }}
                />
              </>
            ) : (
              <>
                <Button
                  title="Download Report"
                  icon={<Ionicons name="download-outline" size={16} color="#FFFFFF" />}
                  variant="gradient"
                  size="small"
                  onPress={handleDownloadReport}
                  loading={actionLoading}
                  style={{ flex: 1 }}
                />
                <Button
                  title="View Result Sheet"
                  icon={<Ionicons name="ribbon-outline" size={16} color={colors.text} />}
                  variant="secondary"
                  size="small"
                  onPress={() => navigation.navigate("ResultDetail", { evaluationId })}
                  style={{ flex: 1 }}
                />
              </>
            )}
          </View>

          {/* Finalization Helper Notice when blocked */}
          {!isFinalized && !isFinalizable && (
            <View style={[styles.finalizeNoticeRow, { borderColor: colors.border, backgroundColor: colors.surfaceElevated }]}>
              <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
              <Text style={[styles.finalizeNoticeText, { color: colors.textSecondary }]}>
                {isRunning
                  ? "AI evaluation is currently processing."
                  : !hasAnyEvaluated
                  ? "Tap 'Start Evaluation' to run AI evaluation against rubrics."
                  : eligibleForApproval.length > 0
                  ? `Approve ${eligibleForApproval.length} evaluated question${eligibleForApproval.length === 1 ? '' : 's'} before finalization.`
                  : issues.length > 0
                  ? `${issues.length} issue(s) require attention before marks can be finalized.`
                  : "Complete teacher review and mark approvals to finalize."}
              </Text>
            </View>
          )}
        </Card>

        {/* Module Tab Selector: Mapping Review vs Marks & Finalize */}
        <View style={[styles.tabBarContainer, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
          <TouchableOpacity
            style={[styles.tabButton, activeTab === "mapping" && { backgroundColor: colors.primary }]}
            onPress={() => setActiveTab("mapping")}
          >
            <Ionicons
              name="git-network-outline"
              size={15}
              color={activeTab === "mapping" ? "#FFFFFF" : colors.textSecondary}
            />
            <Text
              style={[
                styles.tabButtonText,
                { color: activeTab === "mapping" ? "#FFFFFF" : colors.textSecondary },
              ]}
            >
              Mapping Review
            </Text>
            {mappingIssuesCount > 0 && (
              <Badge label={String(mappingIssuesCount)} variant="warning" size="small" />
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.tabButton, activeTab === "marks" && { backgroundColor: colors.primary }]}
            onPress={() => setActiveTab("marks")}
          >
            <Ionicons
              name="ribbon-outline"
              size={15}
              color={activeTab === "marks" ? "#FFFFFF" : colors.textSecondary}
            />
            <Text
              style={[
                styles.tabButtonText,
                { color: activeTab === "marks" ? "#FFFFFF" : colors.textSecondary },
              ]}
            >
              Marks & Finalize
            </Text>
            {hasAnyEvaluated && (
              <Badge
                label={`${totalProvisionalMarks}/${totalMaxMarks}`}
                variant="teal"
                size="small"
              />
            )}
          </TouchableOpacity>
        </View>

        {/* Tab 1: Mapping Review */}
        {activeTab === "mapping" ? (
          <View style={{ gap: 14 }}>
            {/* Summary Stat Grid */}
            <View style={styles.mappingStatsGrid}>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: colors.text }]}>{summary?.total_questions || questions.length}</Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>Total Questions</Text>
              </View>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: colors.brandGreen }]}>{summary?.mapped || 0}</Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>Mapped</Text>
              </View>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: colors.primary }]}>{summary?.suggested || 0}</Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>Suggested</Text>
              </View>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: colors.warning }]}>{summary?.needs_review || 0}</Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>Needs Review</Text>
              </View>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: colors.error }]}>{summary?.missing || 0}</Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>Missing</Text>
              </View>
              <View style={[styles.statBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.statBoxNumber, { color: ocrErrorPages.length > 0 ? colors.error : colors.textSecondary }]}>
                  {ocrErrorPages.length}
                </Text>
                <Text style={[styles.statBoxLabel, { color: colors.textSecondary }]}>OCR Errors</Text>
              </View>
            </View>

            {/* Filter Pills */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterPillsRow}>
              {(["All", "Mapped", "Suggested", "Needs review", "Unmapped", "Missing", "OCR error"] as const).map((f) => (
                <TouchableOpacity
                  key={f}
                  onPress={() => setMappingFilter(f)}
                  style={[
                    styles.filterPill,
                    {
                      backgroundColor: mappingFilter === f ? colors.primary : colors.surfaceElevated,
                      borderColor: mappingFilter === f ? colors.primary : colors.border,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.filterPillText,
                      { color: mappingFilter === f ? "#FFFFFF" : colors.text },
                    ]}
                  >
                    {f}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Answer Sheet Page Quick Selector */}
            {document?.pages && document.pages.length > 0 && (
              <View style={[styles.pageStripCard, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Ionicons name="document-text" size={16} color={colors.primary} />
                    <Text style={[styles.pageStripTitle, { color: colors.text }]}>
                      Answer Sheet Page {activeSheetPage} of {document.pages.length}
                    </Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => {
                      const docId = data?.document?.id || "";
                      setImageViewerPath(`/documents/answer-sheet/${docId}/pages/${activeSheetPage}/image`);
                      setImageViewerTitle(`Answer Sheet • Page ${activeSheetPage}`);
                      setImageViewerModal(true);
                    }}
                    style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
                  >
                    <Ionicons name="scan-outline" size={13} color={colors.primary} />
                    <Text style={{ fontSize: 12, fontWeight: "600", color: colors.primary }}>
                      View Full Page
                    </Text>
                  </TouchableOpacity>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 8 }}>
                  <View style={{ flexDirection: "row", gap: 8 }}>
                    {document.pages.map((p) => (
                      <TouchableOpacity
                        key={p.page_number}
                        onPress={() => setActiveSheetPage(p.page_number)}
                        style={[
                          styles.pageThumbButton,
                          {
                            borderColor: activeSheetPage === p.page_number ? colors.primary : colors.border,
                            backgroundColor: activeSheetPage === p.page_number ? "rgba(7, 159, 189, 0.15)" : colors.surface,
                          },
                        ]}
                      >
                        <Text
                          style={[
                            styles.pageThumbText,
                            { color: activeSheetPage === p.page_number ? colors.primary : colors.text },
                          ]}
                        >
                          P{p.page_number}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </ScrollView>
              </View>
            )}

            {/* Content per filter */}
            {mappingFilter === "Missing" ? (
              missingQuestions.length > 0 ? (
                missingQuestions.map((q) => (
                  <Card key={q.id} style={[styles.mappingCard, { borderColor: "rgba(240, 182, 90, 0.4)" }]}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                      <Text style={[styles.mappingCardTitle, { color: colors.text }]}>
                        Question Q{q.display_number}: No Answer Detected
                      </Text>
                      <Badge label={`${q.max_marks ?? "?"} marks`} variant="warning" size="small" />
                    </View>
                    <Text style={[styles.mappingCardSub, { color: colors.textSecondary }]}>
                      {q.question_text}
                    </Text>
                  </Card>
                ))
              ) : (
                <Empty title="No Missing Questions" description="Every exam question has at least one mapped student answer." />
              )
            ) : mappingFilter === "OCR error" ? (
              ocrErrorPages.length > 0 ? (
                ocrErrorPages.map((p) => (
                  <Card key={p.page_number} style={[styles.mappingCard, { borderColor: colors.error }]}>
                    <Text style={[styles.mappingCardTitle, { color: colors.error }]}>
                      Page {p.page_number}: {p.ocr_status}
                    </Text>
                    <Text style={[styles.mappingCardSub, { color: colors.textSecondary }]}>
                      {p.ocr_error || "OCR failed on this page."}
                    </Text>
                  </Card>
                ))
              ) : (
                <Empty title="No OCR Errors" description="All pages were processed cleanly." />
              )
            ) : mappingRows.length === 0 ? (
              <Empty title="No Answers Found" description="No student responses match the current filter." />
            ) : (
              mappingRows.map((a) => {
                const q = a.exam_question_id ? qmap.get(a.exam_question_id) : undefined;
                const topCandId = a.mapping_candidates?.[0];
                const topCand = topCandId ? qmap.get(topCandId) : undefined;
                const topDetail = a.mapping_candidate_details?.find((c) => c.id === topCandId);
                const needs = a.status === "UNMAPPED" || a.status === "NEEDS_REVIEW";
                return (
                  <Card
                    key={a.id}
                    style={[
                      styles.mappingCard,
                      needs && { borderColor: "rgba(240, 182, 90, 0.5)" },
                      a.status === "IGNORED" && { opacity: 0.6 },
                    ]}
                  >
                    <View style={styles.mappingCardHeader}>
                      <Text style={[styles.mappingCardTitle, { color: colors.text }]}>
                        Student wrote “{a.raw_question_number ?? "no number"}”
                      </Text>
                      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
                        {topCand && a.status === "NEEDS_REVIEW" && (
                          <Badge
                            label={`Suggested: Q${topCand.display_number}${topDetail ? ` (${Math.round(topDetail.score * 100)}%)` : ""}`}
                            variant="teal"
                            size="small"
                          />
                        )}
                        <Badge label={`Page ${a.page_number || 1}`} variant="muted" size="small" />
                        {a.ocr_confidence !== null && (
                          <Badge label={`${Math.round(a.ocr_confidence * 100)}%`} variant="muted" size="small" />
                        )}
                        <StatusBadge status={a.status} />
                      </View>
                    </View>

                    <View style={{ marginTop: 4 }}>
                      {q ? (
                        <Text style={{ fontSize: 13, color: colors.text }}>
                          Mapped to <Text style={{ fontWeight: "700" }}>Question {q.display_number}</Text> •{" "}
                          <Text style={{ color: colors.textSecondary }}>{q.question_text.slice(0, 60)}</Text>
                        </Text>
                      ) : (
                        <Text style={{ fontSize: 13, fontWeight: "600", color: colors.error }}>
                          Not mapped to an exam question
                        </Text>
                      )}
                    </View>

                    {a.mapping_note && needs && (
                      <View style={[styles.mappingNoteBox, { backgroundColor: "rgba(240, 182, 90, 0.1)" }]}>
                        <Ionicons name="information-circle-outline" size={14} color={colors.warning} />
                        <Text style={[styles.mappingNoteText, { color: colors.warning }]}>
                          {a.mapping_note}
                          {topDetail && a.status === "NEEDS_REVIEW" ? `
Why Q${topCand?.display_number}: ${topDetail.reason}` : ""}
                        </Text>
                      </View>
                    )}

                    <Text style={[styles.mappingAnswerText, { color: colors.text }]} numberOfLines={4}>
                      {a.answer_text || "(empty response text)"}
                    </Text>

                    {a.edited && (
                      <Text style={{ fontSize: 11, fontStyle: "italic", color: colors.brandGreen, marginTop: 2 }}>
                        ✓ Edited by teacher. Original OCR preserved in audit.
                      </Text>
                    )}

                    {a.has_crop && (
                      <TouchableOpacity
                        onPress={() => handleViewCrop(a, q || null)}
                        style={{ marginTop: 8 }}
                      >
                        <AuthImage
                          path={`/crops/student-answer/${a.id}`}
                          style={{ minHeight: 90, maxHeight: 160, width: "100%", borderRadius: 6 }}
                        />
                      </TouchableOpacity>
                    )}

                    {!isFinalized && (
                      <View style={styles.mappingActionsRow}>
                        {a.status === "IGNORED" ? (
                          <Button
                            title="Restore"
                            variant="secondary"
                            size="small"
                            onPress={() => handleMappingAction(a, { restore: true }, "restore answer")}
                            loading={actionLoading}
                          />
                        ) : (
                          <>
                            {topCand && a.status === "NEEDS_REVIEW" && (
                              <Button
                                title={`Accept Q${topCand.display_number}`}
                                variant="gradient"
                                size="small"
                                onPress={() => handleMappingAction(a, { accept_suggestion: true }, "accept suggestion")}
                                loading={actionLoading}
                              />
                            )}
                            <Button
                              title="Change Mapping"
                              variant="outline"
                              size="small"
                              onPress={() => handleOpenChangeMapping(a)}
                            />
                            <Button
                              title="Edit OCR"
                              variant="outline"
                              size="small"
                              onPress={() => handleOpenEditTranscription(a, q || null)}
                            />
                            <Button
                              title="Split"
                              variant="secondary"
                              size="small"
                              onPress={() => handleOpenSplitAnswer(a)}
                            />
                            <Button
                              title="Merge"
                              variant="secondary"
                              size="small"
                              onPress={() => handleOpenMergeAnswer(a)}
                            />
                            {a.exam_question_id && (
                              <Button
                                title="Unmap"
                                variant="secondary"
                                size="small"
                                onPress={() => handleMappingAction(a, { unmap: true }, "unmap answer")}
                                loading={actionLoading}
                              />
                            )}
                            <Button
                              title="Ignore"
                              variant="secondary"
                              size="small"
                              onPress={() => handleMappingAction(a, { ignore: true }, "ignore answer")}
                              loading={actionLoading}
                            />
                          </>
                        )}
                      </View>
                    )}
                  </Card>
                );
              })
            )}
          </View>
        ) : (
          /* Tab 2: Marks & Finalize */
          <View style={{ gap: 14 }}>
            {/* Live Evaluation Running Banner */}
            {isRunning && (
              <Card style={[styles.runningCard, { borderColor: colors.primary, backgroundColor: "rgba(7, 159, 189, 0.08)" }]}>
                <View style={styles.runningHeader}>
                  <ActivityIndicator size="small" color={colors.primary} />
                  <Text style={[styles.runningTitle, { color: colors.primary }]}>
                    AI Evaluation in Progress (InternVL3.5 4B)
                  </Text>
                </View>
                <Text style={[styles.runningDesc, { color: colors.textSecondary }]}>
                  Evaluating handwritten responses with Ollama vision model.
                  {evaluation.run_total > 0
                    ? ` Progress: Question ${evaluation.run_progress} of ${evaluation.run_total}...`
                    : " Starting vision model inference..."}
                </Text>
                {evaluation.run_total > 0 && (
                  <View style={[styles.progressBarTrack, { backgroundColor: colors.border }]}>
                    <View
                      style={[
                        styles.progressBarFill,
                        {
                          backgroundColor: colors.primary,
                          width: `${Math.min(100, Math.round((evaluation.run_progress / evaluation.run_total) * 100))}%`,
                        },
                      ]}
                    />
                  </View>
                )}
              </Card>
            )}

            {/* AI Error Banner */}
            {isRunError && (
              <View style={[styles.errorCard, { backgroundColor: "rgba(239, 100, 100, 0.1)", borderColor: colors.error }]}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Ionicons name="alert-circle" size={18} color={colors.error} />
                  <Text style={[styles.errorTitle, { color: colors.error }]}>
                    Evaluation Error / AI Model Offline
                  </Text>
                </View>
                <Text style={[styles.errorDesc, { color: colors.text }]}>
                  InternVL3.5 4B was unavailable or returned an error. Ensure Ollama is running with blaifa/InternVL3_5:4B, then retry evaluation.
                </Text>
                <Button
                  title="Retry Evaluation"
                  variant="outline"
                  size="small"
                  icon={<Ionicons name="refresh" size={14} color={colors.error} />}
                  onPress={handleStartEvaluation}
                  style={{ alignSelf: "flex-start", marginTop: 8 }}
                />
              </View>
            )}

            {/* Prerequisites Block Banner */}
            {isEvalBlocked && !isFinalized && !isRunning && (
              <View style={[styles.blockingBanner, { backgroundColor: "rgba(240, 182, 90, 0.12)", borderColor: colors.warning }]}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <Ionicons name="warning" size={18} color={colors.warning} />
                  <Text style={[styles.blockingTitle, { color: colors.warning }]}>
                    Evaluation Prerequisites Incomplete
                  </Text>
                </View>
                <Text style={[styles.blockingDesc, { color: colors.text }]}>
                  {evalBlockReason}
                </Text>
              </View>
            )}

            {/* Finalized Read-Only Banner */}
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

            {/* Issues Warning Panel */}
            {!isFinalized && issues && issues.length > 0 && (
              <View style={[styles.issuesBanner, { backgroundColor: "rgba(240, 182, 90, 0.12)", borderColor: colors.warning }]}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <Ionicons name="warning" size={18} color={colors.warning} />
                  <Text style={[styles.issuesTitle, { color: colors.warning }]}>
                    Requirements for Finalization ({issues.length})
                  </Text>
                </View>
                {issues.map((iss, idx) => (
                  <Text key={idx} style={[styles.issueItem, { color: colors.text }]}>
                    • Q{iss.question}: {iss.reason}
                  </Text>
                ))}
              </View>
            )}

            {/* Question-Wise Evaluation Section Heading */}
            <Text style={[styles.sectionHeading, { color: colors.text }]}>
              Question-Wise Evaluation ({questions.length})
            </Text>

        {questions.map((q) => {
          const item = itemMap.get(q.id);
          const studentAns = answerMap.get(q.id);
          const isItemPending = !item || item.status === "PENDING";
          const isItemEvaluated = item?.status === "EVALUATED";
          const isItemApproved = item?.status === "APPROVED";
          const isItemError = item?.status === "EVALUATION_ERROR";
          const isItemMissing = item?.status === "MISSING";

          return (
            <Card key={q.id} style={styles.questionCard}>
              <View style={styles.qHeader}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1, flexWrap: "wrap" }}>
                  <Badge label={`Q${q.display_number}`} variant="teal" />
                  <Text style={[styles.maxMarksText, { color: colors.textSecondary }]}>
                    (Max: {q.max_marks ?? "?"} Marks)
                  </Text>
                  {isItemPending && (
                    <Badge label="Not Evaluated" variant="muted" size="small" />
                  )}
                  {isItemEvaluated && (
                    <Badge label="Awaiting Approval" variant="warning" size="small" />
                  )}
                  {isItemApproved && (
                    <Badge label="Approved" variant="success" size="small" />
                  )}
                  {isItemError && (
                    <Badge label="Evaluation Error" variant="danger" size="small" />
                  )}
                  {isItemMissing && (
                    <Badge
                      label="Unanswered"
                      variant="muted"
                      size="small"
                    />
                  )}
                </View>
                <PenScore
                  score={item ? (item.final_marks ?? item.ai_marks) : null}
                  maxScore={q.max_marks}
                  overridden={item?.teacher_overridden}
                />
              </View>

              <Text style={[styles.questionBody, { color: colors.text }]}>
                {q.question_text || q.raw_ocr_text}
              </Text>

              {/* Official Answer & Criteria */}
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
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={[styles.blockTitle, { color: colors.brandGreen }]}>Student's Handwritten Answer:</Text>
                    {studentAns?.page_number && (
                      <Badge label={`Page ${studentAns.page_number}`} variant="teal" size="small" />
                    )}
                  </View>
                  {!isFinalized && studentAns && (
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      <TouchableOpacity
                        onPress={() => handleViewOriginalPage(studentAns, q)}
                        style={[styles.smallActionBtn, { backgroundColor: "rgba(7, 159, 189, 0.1)", borderRadius: 6 }]}
                      >
                        <Ionicons name="document-text-outline" size={13} color={colors.primary} />
                        <Text style={[styles.smallActionBtnText, { color: colors.primary }]}>View Page</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => handleOpenEditTranscription(studentAns, q, item)}
                        style={[styles.smallActionBtn, { backgroundColor: "rgba(7, 159, 189, 0.1)", borderRadius: 6 }]}
                      >
                        <Ionicons name="create-outline" size={13} color={colors.primary} />
                        <Text style={[styles.smallActionBtnText, { color: colors.primary }]}>Edit Answer</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>

                <Text style={[styles.blockText, { color: colors.text }]}>
                  {studentAns?.answer_text || studentAns?.raw_ocr_text || "No handwritten response detected"}
                </Text>

                {studentAns?.edited && (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 }}>
                    <Ionicons name="create" size={12} color={colors.brandGreen} />
                    <Text style={{ fontSize: 11, fontStyle: "italic", color: colors.brandGreen }}>
                      Corrected by teacher (OCR audit record preserved)
                    </Text>
                  </View>
                )}

                {studentAns?.has_crop && (
                  <TouchableOpacity
                    onPress={() => handleViewCrop(studentAns, q)}
                    activeOpacity={0.85}
                    style={{ marginTop: 8 }}
                  >
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <Text style={{ fontSize: 11, fontWeight: "600", color: colors.textSecondary }}>
                        Handwritten Response (Page {studentAns.page_number || 1}):
                      </Text>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
                        <Ionicons name="scan-outline" size={12} color={colors.primary} />
                        <Text style={{ fontSize: 11, color: colors.primary, fontWeight: "600" }}>Tap to Zoom</Text>
                      </View>
                    </View>
                    <AuthImage
                      path={`/crops/student-answer/${studentAns.id}`}
                      style={{ minHeight: 120, maxHeight: 220, width: "100%", borderRadius: 6 }}
                    />
                  </TouchableOpacity>
                )}
              </View>

              {/* AI Evaluation */}
              {item && !isItemPending && (
                <View style={[styles.aiBlock, { borderColor: colors.border }]}>
                  <View style={styles.aiHeader}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Ionicons name="sparkles" size={14} color={colors.primary} />
                      <Text style={[styles.aiTitle, { color: colors.primary }]}>
                        AI Marking Feedback (InternVL3.5 4B)
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      {item.ai_confidence !== null && item.ai_confidence !== undefined && (
                        <Text style={{ fontSize: 11, color: colors.textSecondary }}>
                          {Math.round(item.ai_confidence * 100)}% conf.
                        </Text>
                      )}
                      {item.ai_decision && (
                        <Badge
                          label={item.ai_decision.replace(/_/g, " ")}
                          variant={
                            item.ai_decision === "CORRECT"
                              ? "success"
                              : item.ai_decision === "PARTIALLY_CORRECT" || item.ai_decision === "PARTIAL"
                              ? "warning"
                              : "danger"
                          }
                          size="small"
                        />
                      )}
                    </View>
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

                  {item.error && (
                    <View style={[styles.itemErrorBox, { backgroundColor: "rgba(239, 100, 100, 0.08)", borderColor: colors.error }]}>
                      <Ionicons name="alert-circle-outline" size={14} color={colors.error} />
                      <Text style={[styles.itemErrorText, { color: colors.error }]}>
                        {item.error}
                      </Text>
                    </View>
                  )}

                  {item.teacher_overridden && (
                    <View style={[styles.overriddenBadge, { backgroundColor: "rgba(239, 100, 100, 0.1)" }]}>
                      <Ionicons name="pencil" size={14} color={colors.error} />
                      <Text style={[styles.overriddenText, { color: colors.error }]}>
                        Teacher Override Recorded: {item.final_marks} marks
                        {item.teacher_feedback ? ` (${item.teacher_feedback})` : ""}
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* Individual Question Actions */}
              {!isFinalized ? (
                <View style={styles.itemActionRow}>
                  {/* View Original Page button */}
                  {studentAns && (
                    <Button
                      title="View Page"
                      icon={<Ionicons name="document-text-outline" size={13} color={colors.text} />}
                      variant="secondary"
                      size="small"
                      onPress={() => handleViewOriginalPage(studentAns, q)}
                    />
                  )}

                  {/* Edit Answer button */}
                  {studentAns && (
                    <Button
                      title="Edit Answer"
                      icon={<Ionicons name="pencil" size={13} color={colors.primary} />}
                      variant="outline"
                      size="small"
                      onPress={() => handleOpenEditTranscription(studentAns, q, item)}
                    />
                  )}

                  {/* Re-evaluate button (InternVL) */}
                  {item && (isItemPending || isItemEvaluated || isItemError || studentAns?.edited) && (
                    <Button
                      title="Re-evaluate"
                      icon={<Ionicons name="sparkles" size={13} color="#FFFFFF" />}
                      variant="gradient"
                      size="small"
                      onPress={() => handleRerunItem(item)}
                      loading={actionLoading}
                    />
                  )}

                  {/* Approve Mark button */}
                  {isItemEvaluated && item.final_marks !== null && (
                    <Button
                      title="Approve"
                      icon={<Ionicons name="checkmark-circle-outline" size={14} color="#FFFFFF" />}
                      variant="primary"
                      size="small"
                      onPress={() => handleApproveItem(item, q)}
                      loading={actionLoading}
                    />
                  )}

                  {/* Override Marks button */}
                  {item && !isItemPending && (
                    <Button
                      title={item.teacher_overridden ? "Edit Override" : "Override"}
                      icon={<Ionicons name="create-outline" size={13} color={colors.primary} />}
                      variant="outline"
                      size="small"
                      onPress={() => handleOpenOverride(item, q)}
                    />
                  )}

                  {isItemMissing && !item?.not_attempted_confirmed && (
                    <Button
                      title="Not Attempted"
                      icon={<Ionicons name="checkbox-outline" size={13} color={colors.textSecondary} />}
                      variant="secondary"
                      size="small"
                      onPress={() => handleConfirmNotAttempted(item, q)}
                      loading={actionLoading}
                    />
                  )}
                </View>
              ) : (
                <View style={[styles.finalizedItemNotice, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                  <Ionicons name="lock-closed" size={14} color={colors.textSecondary} />
                  <Text style={[styles.finalizedItemText, { color: colors.textSecondary }]}>
                    Finalized • Marks locked ({item?.final_marks ?? 0}/{q.max_marks}) • Editing requires authorized reopening
                  </Text>
                </View>
              )}
            </Card>
          );
        })}
          </View>
        )}
      </ScrollView>

      {/* Change Mapping Modal */}
      <ModalDialog
        visible={mapModalVisible}
        onClose={() => setMapModalVisible(false)}
        title="Change Question Mapping"
        subtitle={targetMapAnswer ? `Student wrote “${targetMapAnswer.raw_question_number ?? "no number"}” (Page ${targetMapAnswer.page_number || 1})` : ""}
      >
        <Text style={{ fontSize: 12, fontWeight: "700", color: colors.textSecondary, marginBottom: 6, textTransform: "uppercase" }}>
          Map to Exam Question
        </Text>
        <ScrollView style={{ maxHeight: 180, marginBottom: 12, borderWidth: 1, borderColor: colors.border, borderRadius: 8 }}>
          <TouchableOpacity
            style={[
              styles.questionPickItem,
              { backgroundColor: mapQuestionId === "" ? "rgba(7, 159, 189, 0.12)" : colors.surface },
              mapQuestionId === "" && { borderColor: colors.primary, borderWidth: 1 },
            ]}
            onPress={() => setMapQuestionId("")}
          >
            <Text style={{ fontSize: 13, fontWeight: "600", color: mapQuestionId === "" ? colors.primary : colors.text }}>
              None (Unmapped / Extra Answer)
            </Text>
          </TouchableOpacity>
          {questions.map((q) => (
            <TouchableOpacity
              key={q.id}
              style={[
                styles.questionPickItem,
                { backgroundColor: mapQuestionId === q.id ? "rgba(7, 159, 189, 0.12)" : colors.surface },
                mapQuestionId === q.id && { borderColor: colors.primary, borderWidth: 1 },
              ]}
              onPress={() => setMapQuestionId(q.id)}
            >
              <Text style={{ fontSize: 13, fontWeight: "700", color: mapQuestionId === q.id ? colors.primary : colors.text }}>
                Question {q.display_number} ({q.max_marks} marks)
              </Text>
              <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 2 }} numberOfLines={1}>
                {q.question_text}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <Input
          label="Student's Written Question Number *"
          placeholder="e.g. 1a, 2, Q3"
          value={mapRawLabel}
          onChangeText={setMapRawLabel}
        />

        <Input
          label="Answer Text"
          placeholder="Student's handwritten response..."
          value={mapAnswerText}
          onChangeText={setMapAnswerText}
          multiline
          style={{ minHeight: 90, textAlignVertical: "top" }}
        />

        <Input
          label="Reason for Change (Audit)"
          placeholder="e.g. Student mislabeled 1b as 2, confirmed by teacher"
          value={mapReason}
          onChangeText={setMapReason}
        />

        <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
          <Button
            title="Cancel"
            onPress={() => setMapModalVisible(false)}
            variant="secondary"
            style={{ flex: 1 }}
          />
          <Button
            title="Save Mapping"
            icon={<Ionicons name="save-outline" size={16} color="#FFFFFF" />}
            onPress={handleSaveMapping}
            variant="gradient"
            loading={actionLoading}
            style={{ flex: 1 }}
          />
        </View>
      </ModalDialog>

      {/* Split Answer Modal */}
      <ModalDialog
        visible={splitModalVisible}
        onClose={() => setSplitModalVisible(false)}
        title="Split Answer Block"
        subtitle="Divide this answer into two distinct question responses."
      >
        <Input
          label="New Question Number (for second part) *"
          placeholder="e.g. 2, 1b"
          value={splitNewLabel}
          onChangeText={setSplitNewLabel}
        />

        <Text style={{ fontSize: 12, fontWeight: "700", color: colors.textSecondary, marginBottom: 4 }}>
          Split Position: character {splitPos} of {splitTargetAnswer?.answer_text?.length || 0}
        </Text>
        <View style={{ flexDirection: "row", gap: 6, marginBottom: 12 }}>
          {[-20, -5, +5, +20].map((delta) => (
            <TouchableOpacity
              key={delta}
              onPress={() => {
                const total = splitTargetAnswer?.answer_text?.length || 0;
                setSplitPos((prev) => Math.min(Math.max(1, prev + delta), total - 1));
              }}
              style={[styles.splitStepBtn, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}
            >
              <Text style={[styles.splitStepBtnText, { color: colors.text }]}>
                {delta > 0 ? `+${delta}` : delta}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={{ fontSize: 11, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase" }}>
          Part 1 ({splitTargetAnswer?.raw_question_number ?? "orig"}):
        </Text>
        <View style={[styles.splitPreviewBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
          <Text style={{ fontSize: 12, color: colors.text }} numberOfLines={4}>
            {splitTargetAnswer?.answer_text?.slice(0, splitPos) || "(empty)"}
          </Text>
        </View>

        <Text style={{ fontSize: 11, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase", marginTop: 8 }}>
          Part 2 ({splitNewLabel || "new"}):
        </Text>
        <View style={[styles.splitPreviewBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
          <Text style={{ fontSize: 12, color: colors.text }} numberOfLines={4}>
            {splitTargetAnswer?.answer_text?.slice(splitPos) || "(empty)"}
          </Text>
        </View>

        <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
          <Button
            title="Cancel"
            onPress={() => setSplitModalVisible(false)}
            variant="secondary"
            style={{ flex: 1 }}
          />
          <Button
            title="Split Answer"
            icon={<Ionicons name="cut-outline" size={16} color="#FFFFFF" />}
            onPress={handleSplitAnswer}
            variant="gradient"
            loading={actionLoading}
            style={{ flex: 1 }}
          />
        </View>
      </ModalDialog>

      {/* Merge Answer Modal */}
      <ModalDialog
        visible={mergeModalVisible}
        onClose={() => setMergeModalVisible(false)}
        title="Merge With Another Answer"
        subtitle={`Merge response for “${mergeTargetAnswer?.raw_question_number ?? "no number"}” with another block.`}
      >
        <Text style={{ fontSize: 12, fontWeight: "700", color: colors.textSecondary, marginBottom: 8, textTransform: "uppercase" }}>
          Select Answer to Merge Into This:
        </Text>
        <ScrollView style={{ maxHeight: 240, marginBottom: 14, borderWidth: 1, borderColor: colors.border, borderRadius: 8 }}>
          {(answers || [])
            .filter((a) => a.id !== mergeTargetAnswer?.id)
            .map((a) => {
              const selected = mergeOtherAnswerId === a.id;
              return (
                <TouchableOpacity
                  key={a.id}
                  style={[
                    styles.questionPickItem,
                    { backgroundColor: selected ? "rgba(7, 159, 189, 0.12)" : colors.surface },
                    selected && { borderColor: colors.primary, borderWidth: 1 },
                  ]}
                  onPress={() => setMergeOtherAnswerId(a.id)}
                >
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: selected ? colors.primary : colors.text }}>
                      Student wrote “{a.raw_question_number ?? "no number"}”
                    </Text>
                    <Badge label={`P${a.page_number || 1}`} variant="muted" size="small" />
                  </View>
                  <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 2 }} numberOfLines={2}>
                    {a.answer_text}
                  </Text>
                </TouchableOpacity>
              );
            })}
        </ScrollView>

        <View style={{ flexDirection: "row", gap: 10 }}>
          <Button
            title="Cancel"
            onPress={() => setMergeModalVisible(false)}
            variant="secondary"
            style={{ flex: 1 }}
          />
          <Button
            title="Merge Answers"
            icon={<Ionicons name="git-merge-outline" size={16} color="#FFFFFF" />}
            onPress={handleMergeAnswer}
            variant="gradient"
            loading={actionLoading}
            style={{ flex: 1 }}
          />
        </View>
      </ModalDialog>

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

      {/* Edit Student Answer Modal */}
      <ModalDialog
        visible={transcriptionModal}
        onClose={() => setTranscriptionModal(false)}
        title={`Edit Student Answer (Q${activeQuestion?.display_number || "?"})`}
        subtitle={`Authoritative Max Marks: ${activeQuestion?.max_marks ?? "?"}`}
      >
        {/* Question prompt summary */}
        {activeQuestion?.question_text && (
          <View
            style={{
              padding: 10,
              borderRadius: 8,
              backgroundColor: "rgba(7, 159, 189, 0.08)",
              borderWidth: 1,
              borderColor: colors.border,
              marginBottom: 12,
            }}
          >
            <Text style={{ fontSize: 11, fontWeight: "700", color: colors.primary, marginBottom: 2 }}>
              Question Prompt:
            </Text>
            <Text style={{ fontSize: 12, color: colors.text, lineHeight: 17 }} numberOfLines={3}>
              {activeQuestion.question_text}
            </Text>
          </View>
        )}

        {/* Original handwritten crop for immediate visual inspection */}
        {activeAnswer?.has_crop && (
          <View style={{ marginBottom: 12 }}>
            <View
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 4,
              }}
            >
              <Text style={{ fontSize: 11, fontWeight: "700", color: colors.textSecondary }}>
                Original Student Handwriting (Page {activeAnswer.page_number || 1}):
              </Text>
              {activeQuestion && (
                <TouchableOpacity
                  onPress={() => handleViewCrop(activeAnswer, activeQuestion)}
                  style={{ flexDirection: "row", alignItems: "center", gap: 3 }}
                >
                  <Ionicons name="scan-outline" size={12} color={colors.primary} />
                  <Text style={{ fontSize: 11, color: colors.primary, fontWeight: "600" }}>
                    Zoom In
                  </Text>
                </TouchableOpacity>
              )}
            </View>
            <AuthImage
              path={`/crops/student-answer/${activeAnswer.id}`}
              style={{
                minHeight: 100,
                maxHeight: 180,
                width: "100%",
                borderRadius: 8,
                borderWidth: 1,
                borderColor: colors.border,
              }}
            />
          </View>
        )}

        {/* Audit: Original OCR Text */}
        {activeAnswer?.raw_ocr_text && (
          <View
            style={{
              padding: 10,
              borderRadius: 8,
              backgroundColor: colors.surfaceElevated,
              borderWidth: 1,
              borderColor: colors.border,
              marginBottom: 12,
            }}
          >
            <Text style={{ fontSize: 10, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase" }}>
              Original OCR Transcription (Audit Preserved):
            </Text>
            <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 3, fontStyle: "italic" }} numberOfLines={2}>
              "{activeAnswer.raw_ocr_text}"
            </Text>
          </View>
        )}

        {/* Multiline Editor for corrected answer text */}
        <Input
          label="Corrected Student Answer Text *"
          value={transcriptionText}
          onChangeText={setTranscriptionText}
          multiline
          style={{ minHeight: 140, textAlignVertical: "top" }}
          placeholder="Type the exact student handwriting, preserving line breaks, formulas, Tamil/English..."
        />

        {/* Mandatory correction reason */}
        <Input
          label="Correction Reason *"
          placeholder="e.g. OCR misread handwriting; corrected Tamil/math script"
          value={transcriptionReason}
          onChangeText={setTranscriptionReason}
        />

        {/* Action buttons: Cancel and Save */}
        <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
          <Button
            title="Cancel Editing"
            onPress={() => setTranscriptionModal(false)}
            variant="secondary"
            style={{ flex: 1 }}
          />
          <Button
            title="Save Correction"
            icon={<Ionicons name="save-outline" size={16} color="#FFFFFF" />}
            onPress={handleSaveTranscription}
            variant="gradient"
            loading={actionLoading}
            style={{ flex: 1 }}
          />
        </View>
      </ModalDialog>

      {/* View Original Page / Zoom Inspection Modal */}
      <Modal
        visible={imageViewerModal}
        transparent={false}
        animationType="fade"
        onRequestClose={() => setImageViewerModal(false)}
      >
        <SafeAreaView style={{ flex: 1, backgroundColor: "#000000" }}>
          {/* Header */}
          <View
            style={{
              flexDirection: "row",
              justifyContent: "space-between",
              alignItems: "center",
              paddingHorizontal: 16,
              paddingVertical: 12,
              backgroundColor: "rgba(20, 25, 30, 0.95)",
              borderBottomWidth: 1,
              borderColor: "rgba(255, 255, 255, 0.15)",
            }}
          >
            <View style={{ flex: 1, marginRight: 10 }}>
              <Text style={{ color: "#FFFFFF", fontSize: 16, fontWeight: "700" }}>
                {imageViewerTitle}
              </Text>
              <Text style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: 12, marginTop: 2 }}>
                Pinch or double-tap to zoom into handwriting
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => setImageViewerModal(false)}
              style={{
                width: 36,
                height: 36,
                borderRadius: 18,
                backgroundColor: "rgba(255, 255, 255, 0.2)",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Ionicons name="close" size={22} color="#FFFFFF" />
            </TouchableOpacity>
          </View>

          {/* Zoomable Image View */}
          <ScrollView
            style={{ flex: 1 }}
            contentContainerStyle={{
              flexGrow: 1,
              justifyContent: "center",
              alignItems: "center",
              padding: 10,
            }}
            maximumZoomScale={4.0}
            minimumZoomScale={1.0}
            showsHorizontalScrollIndicator={false}
            showsVerticalScrollIndicator={false}
          >
            {imageViewerPath && (
              <AuthImage
                path={imageViewerPath}
                style={{
                  width: "100%",
                  height: "100%",
                  minHeight: 400,
                }}
                resizeMode="contain"
              />
            )}
          </ScrollView>

          {/* Bottom Action Footer */}
          {!isFinalized && imageViewerAnswer && imageViewerQuestion && (
            <View
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
                paddingHorizontal: 20,
                paddingVertical: 14,
                backgroundColor: "rgba(20, 25, 30, 0.95)",
                borderTopWidth: 1,
                borderColor: "rgba(255, 255, 255, 0.15)",
              }}
            >
              <TouchableOpacity
                onPress={() => setImageViewerModal(false)}
                style={{
                  paddingVertical: 10,
                  paddingHorizontal: 16,
                  borderRadius: 8,
                  backgroundColor: "rgba(255, 255, 255, 0.15)",
                }}
              >
                <Text style={{ color: "#FFFFFF", fontSize: 14, fontWeight: "600" }}>Close</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => {
                  setImageViewerModal(false);
                  handleOpenEditTranscription(imageViewerAnswer, imageViewerQuestion);
                }}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: 6,
                  paddingVertical: 10,
                  paddingHorizontal: 18,
                  borderRadius: 8,
                  backgroundColor: colors.primary,
                }}
              >
                <Ionicons name="pencil" size={16} color="#FFFFFF" />
                <Text style={{ color: "#FFFFFF", fontSize: 14, fontWeight: "700" }}>
                  Edit This Answer
                </Text>
              </TouchableOpacity>
            </View>
          )}
        </SafeAreaView>
      </Modal>
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
    alignItems: "center",
  },
  studentInfoContainer: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    marginRight: 10,
  },
  avatarCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontSize: 18,
    fontWeight: "800",
  },
  studentTextWrapper: {
    flex: 1,
    marginLeft: 12,
  },
  studentName: {
    fontSize: 18,
    fontWeight: "800",
  },
  metaText: {
    fontSize: 12,
    marginTop: 3,
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
  scoreSubHint: {
    fontSize: 11,
    marginTop: 4,
    fontWeight: "500",
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
  finalizeNoticeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  finalizeNoticeText: {
    fontSize: 12,
    lineHeight: 16,
    flex: 1,
  },
  runningCard: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  runningHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 6,
  },
  runningTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  runningDesc: {
    fontSize: 12,
    lineHeight: 18,
  },
  progressBarTrack: {
    height: 6,
    borderRadius: 3,
    marginTop: 10,
    overflow: "hidden",
  },
  progressBarFill: {
    height: "100%",
    borderRadius: 3,
  },
  errorCard: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  errorTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  errorDesc: {
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4,
  },
  blockingBanner: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
  },
  blockingTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  blockingDesc: {
    fontSize: 12,
    lineHeight: 18,
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
  smallActionBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 2,
    paddingHorizontal: 6,
  },
  smallActionBtnText: {
    fontSize: 11,
    fontWeight: "600",
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
  itemErrorBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    padding: 8,
    borderRadius: 6,
    borderWidth: 1,
    marginTop: 8,
  },
  itemErrorText: {
    fontSize: 12,
    fontWeight: "500",
    flex: 1,
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
  itemActionRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 8,
    marginTop: 6,
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
  finalizedItemNotice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 6,
  },
  finalizedItemText: {
    fontSize: 12,
    fontWeight: "500",
    flex: 1,
  },
  tabBarContainer: {
    flexDirection: "row",
    borderRadius: 12,
    borderWidth: 1,
    padding: 4,
    marginBottom: 16,
    gap: 6,
  },
  tabButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    gap: 6,
  },
  tabButtonText: {
    fontSize: 13,
    fontWeight: "700",
  },
  mappingStatsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 12,
  },
  statBox: {
    flex: 1,
    minWidth: "30%",
    padding: 10,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: "center",
  },
  statBoxNumber: {
    fontSize: 18,
    fontWeight: "800",
  },
  statBoxLabel: {
    fontSize: 10,
    fontWeight: "600",
    marginTop: 2,
    textTransform: "uppercase",
  },
  filterPillsRow: {
    flexDirection: "row",
    gap: 8,
    paddingVertical: 4,
    marginBottom: 12,
  },
  filterPill: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 20,
    borderWidth: 1,
  },
  filterPillText: {
    fontSize: 12,
    fontWeight: "700",
  },
  pageStripCard: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 12,
  },
  pageStripTitle: {
    fontSize: 13,
    fontWeight: "700",
  },
  pageThumbButton: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  pageThumbText: {
    fontSize: 12,
    fontWeight: "700",
  },
  mappingCard: {
    padding: 14,
    marginBottom: 12,
  },
  mappingCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  mappingCardTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  mappingCardSub: {
    fontSize: 12,
    lineHeight: 17,
    marginTop: 4,
  },
  mappingNoteBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    padding: 8,
    borderRadius: 6,
    marginTop: 6,
    marginBottom: 4,
  },
  mappingNoteText: {
    fontSize: 11,
    fontWeight: "600",
    flex: 1,
  },
  mappingAnswerText: {
    fontSize: 13,
    lineHeight: 18,
    marginTop: 6,
    fontStyle: "italic",
  },
  mappingActionsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 10,
  },
  questionPickItem: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(128, 128, 128, 0.15)",
  },
  splitStepBtn: {
    flex: 1,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    alignItems: "center",
  },
  splitStepBtnText: {
    fontSize: 12,
    fontWeight: "700",
  },
  splitPreviewBox: {
    padding: 8,
    borderRadius: 6,
    borderWidth: 1,
    marginTop: 4,
    marginBottom: 8,
    minHeight: 50,
  },
});
