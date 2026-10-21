import React, { useState, useEffect, useCallback, useRef } from "react";
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
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { printToFileAsync } from "expo-print";
import { useTheme } from "../../theme/ThemeContext";
import { api, downloadAndShareFile, uploadFileNative } from "../../api/client";
import type {
  ExamDetail,
  QuestionsResponse,
  Question,
  KeysResponse,
  AnswerKeyRow,
  AnswerKeyValidationResponse,
  AnswerKeyValidationIssue,
  VerifyAllResponse,
  Evaluation,
  Student,
  UnassignedSheet,
  Outcomes,
} from "../../types";
import { OutcomeTables } from "../../components/OutcomeTables";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { StatusBadge, Badge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Input } from "../../components/Input";
import { ModalDialog } from "../../components/ModalDialog";
import { DocumentScannerModal, DocumentScannerResult } from "../../components/DocumentScannerModal";
import { AuthImage } from "../../components/AuthImage";
import {
  EditQuestionModal,
  SplitQuestionModal,
  MergeQuestionModal,
  ReviewQuestionModal,
} from "../../components/QuestionModals";
import {
  EditAnswerKeyModal,
  ResolveAnswerKeyModal,
  ValidationSummaryModal,
} from "../../components/AnswerKeyModals";

/**
 * Compiles one or more picked document pages (images or PDF) into a unified multi-page PDF document.
 * Ensures that answer sheets with multiple pages are not truncated to only 1 page.
 */
async function compileAssetsToMultiPagePdf(
  assets: Array<{ uri: string; name?: string; mimeType?: string }>,
  title: string
): Promise<{ uri: string; name: string; mimeType: string; pageCount: number }> {
  if (assets.length === 1 && (assets[0].mimeType?.includes("pdf") || assets[0].name?.toLowerCase().endsWith(".pdf"))) {
    return {
      uri: assets[0].uri,
      name: assets[0].name || `${title}.pdf`,
      mimeType: "application/pdf",
      pageCount: 1,
    };
  }

  const processedPages: string[] = [];
  for (let i = 0; i < assets.length; i++) {
    const asset = assets[i];
    try {
      const manip = await manipulateAsync(
        asset.uri,
        [{ resize: { width: 1240 } }],
        { compress: 0.88, format: SaveFormat.JPEG, base64: true }
      );
      if (manip.base64) {
        processedPages.push(`data:image/jpeg;base64,${manip.base64}`);
      } else {
        processedPages.push(manip.uri);
      }
    } catch {
      processedPages.push(asset.uri);
    }
  }

  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          @page {
            size: 210mm 297mm;
            margin: 0;
          }
          * {
            box-sizing: border-box;
          }
          html, body {
            margin: 0;
            padding: 0;
            width: 210mm;
            background-color: #ffffff;
          }
          .page {
            width: 210mm;
            height: 297mm;
            max-height: 297mm;
            page-break-before: auto;
            page-break-after: always;
            break-after: page;
            page-break-inside: avoid;
            break-inside: avoid;
            display: block;
            position: relative;
            overflow: hidden;
            background-color: #ffffff;
          }
          .page:last-child {
            page-break-after: auto;
            break-after: auto;
          }
          .page img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
          }
        </style>
      </head>
      <body>
        ${processedPages
          .map(
            (src, i) => `
          <div class="page" id="page-${i + 1}">
            <img src="${src}" alt="Page ${i + 1}" />
          </div>
        `
          )
          .join("")}
      </body>
    </html>
  `;

  const pdf = await printToFileAsync({
    html,
    width: 595,
    height: 842,
    base64: true,
  });

  const cleanTitle = title.replace(/[^a-zA-Z0-9_-]/g, "_");
  const destDir = `${FileSystem.cacheDirectory}adem_uploads/`;
  try {
    const dirInfo = await FileSystem.getInfoAsync(destDir);
    if (!dirInfo.exists) {
      await FileSystem.makeDirectoryAsync(destDir, { intermediates: true });
    }
  } catch {}

  const safePdfUri = `${destDir}${cleanTitle}_${Date.now()}.pdf`;
  if (pdf.base64) {
    await FileSystem.writeAsStringAsync(safePdfUri, pdf.base64, {
      encoding: FileSystem.EncodingType.Base64,
    });
  } else {
    await FileSystem.copyAsync({ from: pdf.uri, to: safePdfUri });
  }

  return {
    uri: safePdfUri,
    name: `${cleanTitle}_${assets.length}_Pages.pdf`,
    mimeType: "application/pdf",
    pageCount: assets.length,
  };
}

interface ExamWorkspaceScreenProps {
  route: any;
  navigation: any;
}

const K_LEVEL_NAMES: Record<string, string> = {
  K1: "Remember", K2: "Understand", K3: "Apply", K4: "Analyse", K5: "Evaluate", K6: "Create",
};

type TabType = "overview" | "paper" | "questions" | "answerKey" | "students" | "submissions" | "evaluations" | "results";

export const ExamWorkspaceScreen: React.FC<ExamWorkspaceScreenProps> = ({
  route,
  navigation,
}) => {
  const { colors } = useTheme();
  const examId = route.params.examId;

  const [activeTab, setActiveTab] = useState<TabType>(route.params?.initialTab || "overview");
  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const tabScrollRef = useRef<ScrollView>(null);
  const tabLayouts = useRef<Record<string, { x: number; width: number }>>({});

  const scrollToActiveTab = useCallback((tabKey: TabType) => {
    const layout = tabLayouts.current[tabKey];
    if (layout && tabScrollRef.current) {
      tabScrollRef.current.scrollTo({
        x: Math.max(0, layout.x - 24),
        animated: true,
      });
    }
  }, []);

  // Tab data states
  const [questionsData, setQuestionsData] = useState<QuestionsResponse | null>(null);
  const [keysData, setKeysData] = useState<KeysResponse | null>(null);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [results, setResults] = useState<Evaluation[]>([]);
  const [students, setStudents] = useState<Student[]>([]);

  // Action states
  const [actionLoading, setActionLoading] = useState(false);
  const [finalizingExam, setFinalizingExam] = useState(false);

  // Question Management Modal States
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedQuestionForEdit, setSelectedQuestionForEdit] = useState<Question | null>(null);

  const [splitModalVisible, setSplitModalVisible] = useState(false);
  const [selectedQuestionForSplit, setSelectedQuestionForSplit] = useState<Question | null>(null);

  const [mergeModalVisible, setMergeModalVisible] = useState(false);
  const [selectedQuestionForMerge, setSelectedQuestionForMerge] = useState<Question | null>(null);

  const [reviewModalVisible, setReviewModalVisible] = useState(false);
  const [selectedQuestionForReview, setSelectedQuestionForReview] = useState<Question | null>(null);

  const [expandedCrops, setExpandedCrops] = useState<Record<string, boolean>>({});

  // Answer Key Modals & Verification States
  const [editKeyModalVisible, setEditKeyModalVisible] = useState(false);
  const [resolveKeyModalVisible, setResolveKeyModalVisible] = useState(false);
  const [selectedKeyForRow, setSelectedKeyForRow] = useState<AnswerKeyRow | null>(null);
  const [verifyingKeyId, setVerifyingKeyId] = useState<string | null>(null);
  const [validatingAll, setValidatingAll] = useState(false);
  const [validationModalVisible, setValidationModalVisible] = useState(false);
  const [validationResult, setValidationResult] = useState<AnswerKeyValidationResponse | null>(null);

  const [uploadSheetModal, setUploadSheetModal] = useState(false);
  const [unassigned, setUnassigned] = useState<UnassignedSheet[]>([]);
  const [assignTarget, setAssignTarget] = useState<UnassignedSheet | null>(null);
  const [outcomeTarget, setOutcomeTarget] = useState<Question | null>(null);
  const [moreTarget, setMoreTarget] = useState<Question | null>(null);
  const [classOutcomes, setClassOutcomes] = useState<(Outcomes & { finalized_students: number }) | null>(null);
  const [coInput, setCoInput] = useState("");
  const [bulkProgress, setBulkProgress] = useState<string | null>(null);
  const [uploadingSheet, setUploadingSheet] = useState(false);
  const [compilingPages, setCompilingPages] = useState(false);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [attachedPages, setAttachedPages] = useState<
    Array<{ uri: string; name?: string; mimeType?: string; base64?: string }>
  >([]);
  const [cameraScannerVisible, setCameraScannerVisible] = useState(false);
  const [scannerTarget, setScannerTarget] = useState<"question_paper" | "answer_key" | "student_sheet">("question_paper");

  // Failed uploads queue for offline / network resilience
  const [failedUploads, setFailedUploads] = useState<
    Array<{
      id: string;
      studentId: string;
      studentName: string;
      rollNumber: string;
      fileUri: string;
      fileName: string;
      error: string;
    }>
  >([]);

  // Total marks verification & popup modal state
  const [totalMarksModalVisible, setTotalMarksModalVisible] = useState(false);
  const [customTotalMarks, setCustomTotalMarks] = useState("");
  const hasAutoPromptedTotalMarks = useRef(false);

  const handleUpdateTotalMarks = async (marks: number) => {
    try {
      setActionLoading(true);
      await api(`/exams/${examId}`, {
        method: "PATCH",
        json: { total_marks: marks },
      });
      setTotalMarksModalVisible(false);
      await Promise.all([fetchExamDetail(), loadTabData("questions")]);
      Alert.alert("Total Marks Updated", `Examination total marks successfully set to ${marks}.`);
    } catch (err: any) {
      Alert.alert("Update Error", err.message || "Failed to update total marks.");
    } finally {
      setActionLoading(false);
    }
  };

  const selectedStudent = students.find((s) => s.id === selectedStudentId);

  const fetchExamDetail = useCallback(async () => {
    try {
      const e = await api<ExamDetail>(`/exams/${examId}`);
      setExam(e);

      // Also prefetch enrolled students for this class
      if (e.class_id) {
        const studs = await api<Student[]>(`/students?class_id=${e.class_id}`);
        setStudents(studs);
        if (studs.length > 0 && !selectedStudentId) {
          setSelectedStudentId(studs[0].id);
        }
      }
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load examination");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [examId, selectedStudentId]);

  const loadTabData = useCallback(async (tab: TabType) => {
    try {
      if (tab === "questions" || tab === "paper") {
        const q = await api<QuestionsResponse>(`/exams/${examId}/questions`);
        setQuestionsData(q);
      } else if (tab === "answerKey") {
        const k = await api<KeysResponse>(`/exams/${examId}/answer-keys`);
        setKeysData(k);
      } else if (tab === "submissions" || tab === "students") {
        const [sheets, held] = await Promise.all([
          api<Evaluation[]>(`/exams/${examId}/answer-sheets`),
          api<UnassignedSheet[]>(`/exams/${examId}/answer-sheets/unassigned`),
        ]);
        setEvaluations(sheets);
        setUnassigned(held);
        if (exam?.class_id) {
          const studs = await api<Student[]>(`/students?class_id=${exam.class_id}`);
          setStudents(studs);
        }
      } else if (tab === "evaluations") {
        const evs = await api<Evaluation[]>(`/exams/${examId}/answer-sheets`);
        setEvaluations(evs);
      } else if (tab === "results") {
        const [res, summary] = await Promise.all([
          api<Evaluation[]>(`/exams/${examId}/results`),
          api<Outcomes & { finalized_students: number }>(`/exams/${examId}/outcome-summary`),
        ]);
        setResults(res);
        setClassOutcomes(summary);
      }
    } catch (err: any) {
      console.warn("Tab load error:", err);
    }
  }, [examId, exam?.class_id]);

  useEffect(() => {
    fetchExamDetail();
  }, [fetchExamDetail]);

  useEffect(() => {
    loadTabData(activeTab);
    scrollToActiveTab(activeTab);
  }, [activeTab, loadTabData, scrollToActiveTab]);

  // When question paper extracts questions and computes total marks, show popup if discrepancy exists
  useEffect(() => {
    if (!questionsData || !exam) return;
    const paperSum = questionsData.sum_of_marks;
    if (
      paperSum > 0 &&
      !hasAutoPromptedTotalMarks.current &&
      Math.abs(paperSum - exam.total_marks) > 0.001
    ) {
      hasAutoPromptedTotalMarks.current = true;
      setCustomTotalMarks(String(paperSum));
      setTotalMarksModalVisible(true);
    }
  }, [questionsData, exam]);

  // Active polling while question paper, answer key, or any student sheet is running OCR or extraction
  const BUSY_DOC = ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING"];
  const isPaperBusy = !!(exam?.question_paper && BUSY_DOC.includes(exam.question_paper.status));
  const isKeyBusy = !!(exam?.answer_key_document && BUSY_DOC.includes(exam.answer_key_document.status));
  const hasBusySheet =
    evaluations.some((e) => (e.document && BUSY_DOC.includes(e.document.status)) || e.run_status === "RUNNING") ||
    unassigned.some((d) => BUSY_DOC.includes(d.status));

  useEffect(() => {
    if (!isPaperBusy && !isKeyBusy && !hasBusySheet && exam?.status !== "QUESTION_PAPER_UPLOADED") {
      return;
    }
    const timer = setInterval(() => {
      fetchExamDetail();
      if (activeTab === "questions" || activeTab === "paper") {
        loadTabData("questions");
      } else if (activeTab === "answerKey") {
        loadTabData("answerKey");
      } else if (activeTab === "submissions" || activeTab === "students") {
        loadTabData("submissions");
      } else if (activeTab === "evaluations") {
        loadTabData("evaluations");
      } else if (activeTab === "results") {
        loadTabData("results");
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [isPaperBusy, isKeyBusy, hasBusySheet, exam?.status, activeTab, fetchExamDetail, loadTabData]);

  // Accept a single question
  const handleAcceptQuestion = async (qId: string) => {
    try {
      setActionLoading(true);
      await api(`/exam-questions/${qId}`, {
        method: "PATCH",
        json: { verification_status: "VERIFIED" },
      });
      await Promise.all([loadTabData("questions"), fetchExamDetail()]);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to accept question");
    } finally {
      setActionLoading(false);
    }
  };

  // Bulk accept all complete questions
  const handleAcceptAllValid = async () => {
    try {
      setActionLoading(true);
      const res = await api<{ accepted: number }>(`/exams/${examId}/questions/accept-valid`, {
        method: "POST",
      });
      await Promise.all([loadTabData("questions"), fetchExamDetail()]);
      setActiveTab("answerKey");
      scrollToActiveTab("answerKey");
      loadTabData("answerKey");
      Alert.alert(
        "Questions Verified",
        `${res.accepted} complete question(s) verified! Moving to Answer Key module.`
      );
    } catch (err: any) {
      Alert.alert("Bulk Accept Error", err.message || "Failed to accept valid questions");
    } finally {
      setActionLoading(false);
    }
  };

  // Delete question
  const handleDeleteQuestion = (q: Question) => {
    Alert.alert(
      `Delete Question ${q.display_number}`,
      "This removes the question from the exam. The deletion is recorded in the audit log.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              setActionLoading(true);
              await api(`/exam-questions/${q.id}`, { method: "DELETE" });
              await Promise.all([loadTabData("questions"), fetchExamDetail()]);
            } catch (err: any) {
              Alert.alert("Delete Failed", err.message || "Could not delete question");
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  const onRefresh = () => {
    setRefreshing(true);
    fetchExamDetail();
    loadTabData(activeTab);
  };

  // Upload Question Paper
  const executeQuestionPaperUpload = async (file: { uri: string; name: string; mimeType?: string }) => {
    if (actionLoading) return;
    try {
      setActionLoading(true);

      await uploadFileNative(`/exams/${examId}/question-paper`, file.uri, {
        fileName: file.name,
        mimeType: file.mimeType,
      });

      Alert.alert("Success", "Question paper uploaded! Extraction started.");
      setActiveTab("questions");
      fetchExamDetail();
      loadTabData("questions");
    } catch (err: any) {
      Alert.alert(
        "Upload Failed",
        err.message || "Failed to upload question paper. You can retry with the same selected file.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Retry Upload", onPress: () => executeQuestionPaperUpload(file) },
        ]
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleUploadQuestionPaper = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf", "image/*"],
        multiple: true,
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) return;

      if (result.assets.length > 1) {
        setActionLoading(true);
        const compiled = await compileAssetsToMultiPagePdf(
          result.assets,
          `QuestionPaper_${exam?.name || "exam"}`
        );
        setActionLoading(false);
        await executeQuestionPaperUpload(compiled);
      } else {
        const file = result.assets[0];
        await executeQuestionPaperUpload({
          uri: file.uri,
          name: file.name,
          mimeType: file.mimeType,
        });
      }
    } catch (err: any) {
      setActionLoading(false);
      Alert.alert("File Selection Failed", err.message || "Failed to select question paper.");
    }
  };

  // Upload Multi-Page Scanned Question Paper
  const handleScannedPaperComplete = async (file: { uri: string; name: string; type: string }) => {
    await executeQuestionPaperUpload({
      uri: file.uri,
      name: file.name,
      mimeType: file.type || "application/pdf",
    });
  };

  // Upload Answer Key Document
  const executeAnswerKeyUpload = async (file: { uri: string; name: string; mimeType?: string }) => {
    if (actionLoading) return;
    try {
      setActionLoading(true);

      await uploadFileNative(`/exams/${examId}/answer-key`, file.uri, {
        fileName: file.name,
        mimeType: file.mimeType,
      });

      Alert.alert("Success", "Answer key uploaded! Extraction started.");
      fetchExamDetail();
      loadTabData("answerKey");
    } catch (err: any) {
      Alert.alert(
        "Upload Failed",
        err.message || "Failed to upload answer key. You can retry with the same selected file.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Retry Upload", onPress: () => executeAnswerKeyUpload(file) },
        ]
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleUploadAnswerKeyDoc = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf", "image/*"],
        multiple: true,
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) return;

      if (result.assets.length > 1) {
        setActionLoading(true);
        const compiled = await compileAssetsToMultiPagePdf(
          result.assets,
          `AnswerKey_${exam?.name || "exam"}`
        );
        setActionLoading(false);
        await executeAnswerKeyUpload(compiled);
      } else {
        const file = result.assets[0];
        await executeAnswerKeyUpload({
          uri: file.uri,
          name: file.name,
          mimeType: file.mimeType,
        });
      }
    } catch (err: any) {
      setActionLoading(false);
      Alert.alert("File Selection Failed", err.message || "Failed to select answer key.");
    }
  };

  // Upload Multi-Page Scanned Answer Key
  const handleScannedAnswerKeyComplete = async (file: { uri: string; name: string; type: string }) => {
    await executeAnswerKeyUpload({
      uri: file.uri,
      name: file.name,
      mimeType: file.type || "application/pdf",
    });
  };

  // Generate Answer Key with Ollama
  const handleGenerateAnswerKey = async () => {
    try {
      setActionLoading(true);
      const res = await api<{ answers: any[] }>(`/exams/${examId}/answer-keys/generate-ai`, {
        method: "POST",
        timeoutMs: 180000,
      });
      if (res.answers && res.answers.length > 0) {
        await api(`/exams/${examId}/answer-keys/save-ai`, {
          method: "POST",
          json: { answers: res.answers },
          timeoutMs: 60000,
        });
      }
      Alert.alert(
        "AI Generation Complete",
        `Ollama (blaifa/InternVL3_5:4B) generated solutions and criteria for ${res.answers?.length || 0} questions!`
      );
      await Promise.all([loadTabData("answerKey"), fetchExamDetail()]);
    } catch (err: any) {
      Alert.alert("Generation Failed", err.message || "Failed to generate answer key");
    } finally {
      setActionLoading(false);
    }
  };

  // Answer Key Item Actions
  const handleOpenEditKey = (k: AnswerKeyRow) => {
    setSelectedKeyForRow(k);
    setEditKeyModalVisible(true);
  };

  const handleOpenResolveKey = (k: AnswerKeyRow) => {
    setSelectedKeyForRow(k);
    setResolveKeyModalVisible(true);
  };

  const handleKeyUpdateSuccess = (updated: AnswerKeyRow) => {
    setKeysData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        keys: prev.keys.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
      };
    });
    fetchExamDetail();
    loadTabData("answerKey");
  };

  // Verify All Answers (Confirmation dialog + backend automated processing)
  const handleVerifyAllAnswers = () => {
    if (validatingAll) return;
    if (!keysData || !keysData.keys || keysData.keys.length === 0) {
      Alert.alert("No Answers", "Please upload or generate an answer key first.");
      return;
    }

    Alert.alert(
      "Verify All Answers",
      "All eligible answers that satisfy existing validation rules and have valid, unambiguous question mappings will be automatically verified and approved.\n\nAnswers with missing solutions, ambiguous or duplicate mappings, or mark mismatches will remain in Needs Review for manual inspection.\n\nDo you want to proceed?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Verify All Answers",
          style: "default",
          onPress: executeVerifyAllAnswers,
        },
      ]
    );
  };

  const executeVerifyAllAnswers = async () => {
    if (validatingAll) return;
    if (!keysData || !keysData.keys || keysData.keys.length === 0) return;

    try {
      setValidatingAll(true);
      const res = await api<VerifyAllResponse>(
        `/exams/${examId}/answer-keys/verify-all`,
        { method: "POST" }
      );

      // Refresh Answer Key page immediately using actual backend response
      if (res.keys) {
        setKeysData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            keys: res.keys,
            missing_question_ids: res.missing_question_ids ?? prev.missing_question_ids,
            locked: res.locked ?? prev.locked,
          };
        });
      }

      // Sync background tab and exam state
      loadTabData("answerKey");
      fetchExamDetail();

      if (res.valid) {
        setActiveTab("submissions");
        scrollToActiveTab("submissions");
        loadTabData("submissions");
        Alert.alert(
          "Answer Key Verified",
          `All ${res.summary?.verified_count ?? "official"} answers verified and locked! Moving to the Submissions module.`
        );
      } else {
        // Show summary containing total processed, verified, needs review, and failed entries
        setValidationResult({
          valid: res.valid,
          summary: res.summary,
          blocking_issues: res.blocking_issues || [],
          issues: res.issues || [],
        });
        setValidationModalVisible(true);
      }
    } catch (err: any) {
      if (err.issues && err.issues.length > 0) {
        setValidationResult({
          valid: false,
          summary: {
            total_processed: keysData?.keys.length || 0,
            total_keys: keysData?.keys.length || 0,
            total_questions: keysData?.questions.length || 0,
            verified_count: (keysData?.keys || []).filter((k) => k.verification_status === "VERIFIED").length,
            needs_review_count: err.issues.length,
            failed_count: 0,
            blocking_issues_count: err.issues.length,
          },
          blocking_issues: err.issues.map((i: any) => ({
            key_id: null,
            question: i.question,
            reason: i.reason,
            issue_type: i.reason.includes("MARK MISMATCH") ? "mark_mismatch" : "needs_review",
          })),
          issues: err.issues,
        });
        setValidationModalVisible(true);
      } else {
        Alert.alert(
          "Verification Error",
          err.message || "Failed to verify answers automatically. Please check connection and try again."
        );
      }
    } finally {
      setValidatingAll(false);
    }
  };

  const handleReviewValidationIssue = (
    keyId: string | null,
    issue: AnswerKeyValidationIssue
  ) => {
    setValidationModalVisible(false);
    if (!keysData?.keys) return;
    let targetKey = keyId ? keysData.keys.find((k) => k.id === keyId) : null;
    if (!targetKey && issue.question) {
      const cleanNum = issue.question.replace(/[^0-9a-zA-Z()]/g, "");
      targetKey = keysData.keys.find(
        (k) =>
          k.raw_question_number === issue.question ||
          k.raw_question_number === cleanNum ||
          `Q${k.raw_question_number}` === issue.question ||
          k.normalized_number === cleanNum
      );
    }
    if (targetKey) {
      setSelectedKeyForRow(targetKey);
      if (
        issue.issue_type === "mark_mismatch" ||
        issue.issue_type === "needs_review" ||
        issue.issue_type === "unmapped" ||
        issue.issue_type === "empty_solution" ||
        issue.issue_type === "duplicate_mapping"
      ) {
        setResolveKeyModalVisible(true);
      } else {
        setEditKeyModalVisible(true);
      }
    }
  };

  const handleVerifySingleKey = async (k: AnswerKeyRow) => {
    const issues: string[] = [];
    if (k.mapping_status !== "MAPPED" || !k.exam_question_id) {
      issues.push("Answer must be mapped to an exam question.");
    }
    if (!k.answer_text?.trim()) {
      issues.push("Official solution text is empty.");
    }
    if (k.mark_mismatch) {
      issues.push("Marks mismatch must be resolved.");
    }

    if (issues.length > 0) {
      Alert.alert(
        "Unresolved Issues",
        `This answer cannot be verified yet:\n\n• ${issues.join("\n• ")}\n\nPlease resolve the issues first.`,
        [
          { text: "Cancel", style: "cancel" },
          { text: "Resolve Issue", onPress: () => handleOpenResolveKey(k) },
        ]
      );
      return;
    }

    try {
      setVerifyingKeyId(k.id);
      const updated = await api<AnswerKeyRow>(`/answer-keys/${k.id}`, {
        method: "PATCH",
        json: { verification_status: "VERIFIED" },
      });
      handleKeyUpdateSuccess(updated);
      Alert.alert("Answer Verified", `Answer for Q${k.raw_question_number || k.normalized_number || "?"} has been verified.`);
    } catch (err: any) {
      Alert.alert("Verification Error", err.message || "Failed to verify answer.");
    } finally {
      setVerifyingKeyId(null);
    }
  };

  // Verify Answer Key (Final validation step)
  const handleVerifyAnswerKey = async () => {
    if (!keysData || !keysData.keys || keysData.keys.length === 0) {
      Alert.alert("No Answers", "Please upload or generate an answer key first.");
      return;
    }

    const unmappedKeys = keysData.keys.filter(
      (k) => k.mapping_status !== "MAPPED" || !k.exam_question_id
    );
    const emptyTextKeys = keysData.keys.filter((k) => !(k.answer_text || "").trim());
    const mismatchKeys = keysData.keys.filter((k) => k.mark_mismatch);

    const blockers: string[] = [];
    if (unmappedKeys.length > 0) {
      blockers.push(`${unmappedKeys.length} answer(s) need question mapping.`);
    }
    if (emptyTextKeys.length > 0) {
      blockers.push(`${emptyTextKeys.length} answer(s) have empty solution text.`);
    }
    if (mismatchKeys.length > 0) {
      blockers.push(`${mismatchKeys.length} answer(s) have marks mismatches.`);
    }
    if (keysData.missing_question_ids && keysData.missing_question_ids.length > 0) {
      blockers.push(`${keysData.missing_question_ids.length} question(s) lack answer keys.`);
    }

    if (blockers.length > 0) {
      Alert.alert(
        "Verification Incomplete",
        `Issues must be resolved before verifying and locking the answer key:\n\n• ${blockers.join(
          "\n• "
        )}\n\nPlease resolve these issues using 'Resolve Issue' or 'Verify All Answers'.`,
        [
          { text: "Cancel", style: "cancel" },
          { text: "Verify All Answers", onPress: handleVerifyAllAnswers },
        ]
      );
      return;
    }

    try {
      setActionLoading(true);
      const res = await api<{ verified: number }>(`/exams/${examId}/answer-keys/verify`, {
        method: "POST",
      });
      await Promise.all([loadTabData("answerKey"), fetchExamDetail()]);
      setActiveTab("submissions");
      scrollToActiveTab("submissions");
      loadTabData("submissions");
      Alert.alert(
        "Answer Key Verified",
        `All ${res.verified} official answers verified and locked! Moving to the Submissions module.`
      );
    } catch (err: any) {
      Alert.alert("Verification Failed", err.message || "Failed to verify answer key.");
    } finally {
      setActionLoading(false);
    }
  };

  // Verify Questions
  const handleVerifyQuestions = async () => {
    try {
      setActionLoading(true);
      await api(`/exams/${examId}/questions/verify`, {
        method: "POST",
      });
      await Promise.all([loadTabData("questions"), fetchExamDetail()]);
      setActiveTab("answerKey");
      scrollToActiveTab("answerKey");
      loadTabData("answerKey");
      Alert.alert(
        "Questions Verified",
        "All canonical questions have been verified! Moving to the Answer Key module."
      );
    } catch (err: any) {
      await Promise.all([loadTabData("questions"), fetchExamDetail()]);
      Alert.alert("Verification Notice", err.message || "Verification failed");
    } finally {
      setActionLoading(false);
    }
  };

  // Upload Student Answer Sheet (Supports single or multiple page images/PDF)
  const handlePickStudentFile = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf", "image/*"],
        multiple: true,
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets || res.assets.length === 0) return;

      setAttachedPages((prev) => [...prev, ...res.assets]);
    } catch (err: any) {
      Alert.alert("File Selection Failed", err.message || "Failed to select answer sheet file.");
    }
  };

  const handleScannedStudentSheetComplete = async (file: DocumentScannerResult) => {
    if (file.pages && file.pages.length > 0) {
      setAttachedPages((prev) => [
        ...prev,
        ...file.pages!.map((p) => ({
          uri: p.uri,
          name: p.name,
          mimeType: p.mimeType || "image/jpeg",
        })),
      ]);
    } else {
      setAttachedPages((prev) => [
        ...prev,
        {
          uri: file.uri,
          name: file.name,
          mimeType: file.type || "application/pdf",
        },
      ]);
    }
    setCameraScannerVisible(false);
    setUploadSheetModal(true);
  };

  /**
   * Continuous Classroom Batch Scanning:
   * Handles immediate background upload of Student A while the camera stays active for Student B
   */
  const handleScanNextStudentBatch = async (
    file: DocumentScannerResult,
    currentStudentId: string,
    nextStudentId?: string
  ) => {
    try {
      // Dispatch non-blocking background upload; the student is identified from the sheet itself
      uploadFileNative(`/exams/${examId}/answer-sheets`, file.uri, {
        fileName: file.name,
        mimeType: file.type || "application/pdf",
      })
        .then(() => {
          fetchExamDetail();
          loadTabData("submissions");
        })
        .catch((err: any) => {
          // If upload fails, retain in failedUploads queue so teacher can retry without re-scanning
          setFailedUploads((prev) => [
            ...prev,
            {
              id: `failed_${Date.now()}`,
              studentId: "",
              studentName: file.name || "Answer sheet",
              rollNumber: "",
              fileUri: file.uri,
              fileName: file.name,
              error: err.message || "Network upload error",
            },
          ]);
        });

      if (nextStudentId) {
        setSelectedStudentId(nextStudentId);
      }
    } catch (err: any) {
      console.warn("Batch student dispatch error", err);
    }
  };

  const handleRetryFailedUpload = async (item: typeof failedUploads[0]) => {
    try {
      await uploadFileNative(`/exams/${examId}/answer-sheets`, item.fileUri, {
        fileName: item.fileName,
        mimeType: "application/pdf",
        params: item.studentId ? { student_id: item.studentId } : undefined,
      });
      setFailedUploads((prev) => prev.filter((f) => f.id !== item.id));
      await Promise.all([fetchExamDetail(), loadTabData("submissions")]);
      Alert.alert("Upload Succeeded", `${item.studentName} uploaded successfully.`);
    } catch (err: any) {
      Alert.alert("Retry Failed", err.message || "Could not upload answer sheet. Please try again.");
    }
  };

  const handleSubmitStudentSheet = async () => {
    if (uploadingSheet || compilingPages) return;

    if (attachedPages.length === 0) {
      Alert.alert("Answer Sheet Required", "Please attach or scan at least one page for the student's answer sheet.");
      return;
    }

    try {
      let finalUpload: { uri: string; name: string; mimeType: string };

      if (
        attachedPages.length === 1 &&
        (attachedPages[0].mimeType?.includes("pdf") || attachedPages[0].name?.toLowerCase().endsWith(".pdf"))
      ) {
        finalUpload = {
          uri: attachedPages[0].uri,
          name: attachedPages[0].name || "student_answer_sheet.pdf",
          mimeType: "application/pdf",
        };
      } else {
        setCompilingPages(true);
        const compiled = await compileAssetsToMultiPagePdf(attachedPages, `AnswerSheet_${Date.now()}`);
        finalUpload = {
          uri: compiled.uri,
          name: compiled.name,
          mimeType: compiled.mimeType,
        };
        setCompilingPages(false);
      }

      setUploadingSheet(true);
      // no student is sent: it is identified from the details written on the sheet
      await uploadFileNative(`/exams/${examId}/answer-sheets`, finalUpload.uri, {
        fileName: finalUpload.name,
        mimeType: finalUpload.mimeType || "application/pdf",
      });
      const actualPageCount = attachedPages.length;

      // Only clear state and dismiss modal on verified upload success
      setUploadSheetModal(false);
      setAttachedPages([]);

      Alert.alert(
        "Upload Confirmed",
        `Answer sheet (${actualPageCount} page${actualPageCount === 1 ? "" : "s"}) uploaded. The student is identified from the sheet, then it is read.`
      );
      fetchExamDetail();
      loadTabData("submissions");
    } catch (err: any) {
      Alert.alert(
        "Submission Failed",
        err.message || "Failed to submit answer sheet. Your scanned pages are preserved so you can retry without re-scanning.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Retry Submission", onPress: handleSubmitStudentSheet },
        ]
      );
    } finally {
      setCompilingPages(false);
      setUploadingSheet(false);
    }
  };

  // Bloom's K level / course outcome tags; they never change marks, so they stay editable until finalized
  const saveOutcome = async (q: Question, json: { k_level?: string | null; course_outcome?: string | null }) => {
    try {
      const updated = await api<Question>(`/exam-questions/${q.id}/outcome`, { method: "PATCH", json });
      setOutcomeTarget((cur) => (cur && cur.id === q.id ? updated : cur));
      await loadTabData("questions");
    } catch (err: any) {
      Alert.alert("Could Not Save", err.message || "Failed to save the K level / course outcome.");
    }
  };

  // Many answer sheets at once: one file per student, matched to the student from the sheet itself
  const handleBulkUploadSheets = async () => {
    let assets: DocumentPicker.DocumentPickerAsset[] = [];
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: [
          "application/pdf",
          "image/*",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        multiple: true,
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.length) return;
      assets = res.assets;
    } catch (err: any) {
      Alert.alert("File Selection Failed", err.message || "Failed to select answer sheets.");
      return;
    }
    const failed: string[] = [];
    for (let i = 0; i < assets.length; i++) {
      setBulkProgress(`Uploading ${i + 1} of ${assets.length}…`);
      try {
        await uploadFileNative(`/exams/${examId}/answer-sheets`, assets[i].uri, {
          fileName: assets[i].name,
          mimeType: assets[i].mimeType,
        });
      } catch (err: any) {
        failed.push(`${assets[i].name}: ${err.message || "upload failed"}`);
      }
    }
    setBulkProgress(null);
    await Promise.all([fetchExamDetail(), loadTabData("submissions")]);
    Alert.alert(
      failed.length ? "Some Uploads Failed" : "Answer Sheets Uploaded",
      failed.length
        ? `${assets.length - failed.length} of ${assets.length} uploaded.\n\n${failed.join("\n")}`
        : `${assets.length} sheet(s) uploaded. Each is matched to its student, then read one after another.`
    );
  };

  const handleAssignSheet = async (doc: UnassignedSheet, studentId: string) => {
    try {
      setActionLoading(true);
      await api(`/answer-sheets/${doc.id}/assign`, { method: "POST", json: { student_id: studentId } });
      setAssignTarget(null);
      await Promise.all([fetchExamDetail(), loadTabData("submissions")]);
    } catch (err: any) {
      Alert.alert("Could Not Assign", err.message || "Failed to assign the student.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetryIdentify = async (doc: UnassignedSheet) => {
    try {
      await api(`/answer-sheets/${doc.id}/identify`, { method: "POST" });
      await loadTabData("submissions");
    } catch (err: any) {
      Alert.alert("Retry Failed", err.message || "Could not read the student details again.");
    }
  };

  const handleDeleteUnassigned = (doc: UnassignedSheet) => {
    Alert.alert("Delete Answer Sheet", `Remove ${doc.original_filename}? The original file is retained in storage.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api(`/answer-sheets/${doc.id}`, { method: "DELETE" });
            await loadTabData("submissions");
          } catch (err: any) {
            Alert.alert("Delete Failed", err.message || "Failed to delete the answer sheet.");
          }
        },
      },
    ]);
  };

  // Run AI Evaluation with precise status handling and guidance
  const handleRunEvaluation = async (evaluationId: string) => {
    const targetEv = evaluations.find((e) => e.id === evaluationId);
    if (targetEv?.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        `The evaluation for ${targetEv.student?.name || "this student"} is finalized and approved. Finalized evaluations are permanently locked and cannot be re-evaluated or modified.`
      );
      return;
    }

    if (exam && !["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED", "FINALIZED"].includes(exam.status)) {
      Alert.alert(
        "Answer Key Verification Required",
        "Before evaluating student answer sheets, the Answer Key must be verified.\n\nPlease go to the Answer Key tab to verify answers and lock the key.",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Go to Answer Key",
            style: "default",
            onPress: () => {
              setActiveTab("answerKey");
              scrollToActiveTab("answerKey");
            },
          },
        ]
      );
      return;
    }

    if (targetEv?.document && BUSY_DOC.includes(targetEv.document.status)) {
      Alert.alert(
        "Processing in Progress",
        `The student's answer sheet is currently ${targetEv.document.stage || "being read"}. Please wait until reading finishes.`
      );
      return;
    }

    try {
      setActionLoading(true);
      await api(`/evaluations/${evaluationId}/run`, {
        method: "POST",
      });
      Alert.alert("Evaluation Started", "AI evaluation run started using Ollama model.");
      await Promise.all([loadTabData("submissions"), loadTabData("evaluations")]);
    } catch (err: any) {
      if (err.code === "EVALUATION_FINALIZED") {
        Alert.alert(
          "Evaluation Finalized (Read-Only)",
          "This evaluation is finalized and can no longer be changed. Finalized marks and student answers are permanently locked."
        );
      } else if (err.code === "EXAM_NOT_READY" || err.message?.includes("verified question paper and answer key")) {
        Alert.alert(
          "Answer Key Verification Required",
          "Before evaluating student answer sheets, the Answer Key must be verified.\n\nPlease go to the Answer Key tab to verify answers and lock the key.",
          [
            { text: "Cancel", style: "cancel" },
            {
              text: "Go to Answer Key",
              style: "default",
              onPress: () => {
                setActiveTab("answerKey");
                scrollToActiveTab("answerKey");
              },
            },
          ]
        );
      } else if (err.code === "OCR_NOT_FINISHED") {
        Alert.alert(
          "Processing in Progress",
          "The answer sheet is still being read. Please wait a few seconds and try again."
        );
      } else if (err.code === "ALREADY_RUNNING") {
        Alert.alert("Already Running", "AI evaluation is already in progress for this student.");
      } else if (err.code === "MAPPING_INCOMPLETE") {
        Alert.alert(
          "Mapping Review Required",
          err.message || "Some student answers need mapping review before evaluation can run.",
          [
            { text: "Cancel", style: "cancel" },
            {
              text: "Review Answers",
              onPress: () => navigation.navigate("EvaluationDetail", { evaluationId }),
            },
          ]
        );
      } else {
        Alert.alert("Evaluation Error", err.message || "Failed to start evaluation.");
      }
      loadTabData("submissions");
    } finally {
      setActionLoading(false);
    }
  };

  // Finalize Whole Exam (Laptop parity)
  const handlePurgeFilesNow = () => {
    Alert.alert(
      "Delete Exam Files Now?",
      "This permanently removes the uploaded documents and page images for this exam. Marks, results and the saved PDF reports stay.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete Files",
          style: "destructive",
          onPress: async () => {
            try {
              await api(`/exams/${examId}/purge-files`, { method: "POST" });
              fetchExamDetail();
            } catch (err: any) {
              Alert.alert("Delete Failed", err.message || "Failed to delete the exam files.");
            }
          },
        },
      ]
    );
  };

  const handleFinalizeExam = () => {
    if (finalizingExam) return;
    const pending = evaluations.filter((e) => e.status !== "FINALIZED");
    if (evaluations.length === 0 || pending.length > 0) {
      Alert.alert(
        "Cannot Finalize Exam",
        `Every student's evaluation must be marked and finalized first. Currently ${pending.length} evaluation(s) are pending.`
      );
      return;
    }

    Alert.alert(
      "Finalize Exam",
      "This closes the exam and locks all student marks permanently. No more answer sheets can be uploaded or modified.\n\n" +
        "Each student's PDF report is saved. 24 hours later the uploaded files, page images and raw AI output are permanently deleted from the computer. Marks and results stay.\n\nDo you want to finalize this exam?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Finalize Exam",
          style: "destructive",
          onPress: async () => {
            try {
              setFinalizingExam(true);
              await api(`/exams/${examId}/finalize`, { method: "POST" });
              Alert.alert("Exam Finalized", "The exam is finalized and every student's report is saved. Uploaded files will be deleted in 24 hours.");
              fetchExamDetail();
              loadTabData("results");
            } catch (err: any) {
              Alert.alert("Finalize Failed", err.message || "Failed to finalize exam.");
            } finally {
              setFinalizingExam(false);
            }
          },
        },
      ]
    );
  };

  // Delete Answer Sheet (Matching laptop functionality)
  const handleDeleteAnswerSheet = (ev: Evaluation) => {
    Alert.alert(
      "Delete Answer Sheet",
      `Are you sure you want to remove ${ev.student?.name || "this student"}'s answer sheet and its evaluation? The original file stays on disk and the action will be logged.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              setActionLoading(true);
              await api(`/evaluations/${ev.id}`, { method: "DELETE" });
              Alert.alert("Deleted", "Answer sheet removed successfully.");
              await Promise.all([loadTabData("submissions"), fetchExamDetail()]);
            } catch (err: any) {
              Alert.alert("Delete Failed", err.message || "Failed to delete answer sheet.");
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading examination workspace..." />
      </View>
    );
  }

  if (!exam) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Empty title="Exam Not Found" description="The requested examination could not be loaded." />
      </View>
    );
  }

  const tabs: { key: TabType; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: "overview", label: "Overview", icon: "information-circle-outline" },
    { key: "paper", label: "Paper & Key", icon: "document-text-outline" },
    { key: "questions", label: "Questions", icon: "list-outline" },
    { key: "answerKey", label: "Answer Key", icon: "key-outline" },
    { key: "students", label: "Students", icon: "people-outline" },
    { key: "submissions", label: "Answer Sheets", icon: "cloud-upload-outline" },
    { key: "evaluations", label: "Evaluations", icon: "checkbox-outline" },
    { key: "results", label: "Results", icon: "trophy-outline" },
  ];

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      {/* Header Banner */}
      <View style={[styles.headerBanner, { borderBottomColor: colors.border }]}>
        <View style={styles.headerInfo}>
          <Text style={[styles.examTitle, { color: colors.text }]}>{exam.name}</Text>
          <Text style={[styles.examSub, { color: colors.textSecondary }]}>
            {exam.class_name} • {exam.subject_name} • Total: {exam.total_marks} Marks
          </Text>
        </View>
        <View style={{ alignItems: "flex-end", gap: 6 }}>
          <StatusBadge status={exam.status} />
          <TouchableOpacity
            onPress={() => navigation.navigate("VerifyExam", { examId })}
            style={[styles.verifyLinkPill, { borderColor: colors.primary }]}
          >
            <Ionicons name="shield-checkmark-outline" size={12} color={colors.primary} />
            <Text style={[styles.verifyLinkText, { color: colors.primary }]}>Verify Exam</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Segmented Horizontal Tabs */}
      <View style={[styles.tabBarWrapper, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
        <ScrollView
          ref={tabScrollRef}
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.tabScrollView}
          contentContainerStyle={styles.tabBar}
        >
          {tabs.map((t) => {
            const active = activeTab === t.key;
            return (
              <TouchableOpacity
                key={t.key}
                accessibilityRole="tab"
                accessibilityState={{ selected: active }}
                accessibilityLabel={t.label}
                activeOpacity={0.7}
                onLayout={(e) => {
                  tabLayouts.current[t.key] = e.nativeEvent.layout;
                  if (active) {
                    scrollToActiveTab(t.key);
                  }
                }}
                onPress={() => {
                  setActiveTab(t.key);
                  scrollToActiveTab(t.key);
                }}
                style={[
                  styles.tabItem,
                  {
                    borderBottomColor: active ? colors.primary : "transparent",
                    backgroundColor: active ? `${colors.primary}18` : "transparent",
                  },
                ]}
              >
                <Ionicons
                  name={t.icon}
                  size={16}
                  color={active ? colors.primary : colors.textSecondary}
                />
                <Text
                  numberOfLines={1}
                  style={[
                    styles.tabText,
                    {
                      color: active ? colors.primary : colors.textSecondary,
                      fontWeight: active ? "700" : "600",
                    },
                  ]}
                >
                  {t.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Tab Content Body */}
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        {/* OVERVIEW TAB */}
        {activeTab === "overview" && (
          <View>
            <Card style={styles.sectionCard}>
              <Text style={[styles.cardTitle, { color: colors.text }]}>Examination Summary</Text>
              <View style={styles.grid2}>
                <View style={styles.gridItem}>
                  <Text style={[styles.gridLabel, { color: colors.textSecondary }]}>Academic Year</Text>
                  <Text style={[styles.gridValue, { color: colors.text }]}>{exam.academic_year}</Text>
                </View>
                <View style={styles.gridItem}>
                  <Text style={[styles.gridLabel, { color: colors.textSecondary }]}>Exam Type</Text>
                  <Text style={[styles.gridValue, { color: colors.text }]}>{exam.exam_type}</Text>
                </View>
                <View style={styles.gridItem}>
                  <Text style={[styles.gridLabel, { color: colors.textSecondary }]}>Duration</Text>
                  <Text style={[styles.gridValue, { color: colors.text }]}>
                    {exam.duration_minutes ? `${exam.duration_minutes} Mins` : "Untimed"}
                  </Text>
                </View>
                <View style={styles.gridItem}>
                  <Text style={[styles.gridLabel, { color: colors.textSecondary }]}>Exam Date</Text>
                  <Text style={[styles.gridValue, { color: colors.text }]}>
                    {exam.exam_date || "Not set"}
                  </Text>
                </View>
              </View>

              {exam.instructions ? (
                <View style={[styles.instructionsBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                  <Text style={[styles.instructionsLabel, { color: colors.primary }]}>Instructions:</Text>
                  <Text style={[styles.instructionsText, { color: colors.text }]}>{exam.instructions}</Text>
                </View>
              ) : null}
            </Card>

            <Card style={styles.sectionCard}>
              <View style={styles.workflowRow}>
                <View style={styles.wfStep}>
                  <Ionicons
                    name={exam.question_paper ? "checkmark-circle" : "ellipse-outline"}
                    size={22}
                    color={exam.question_paper ? colors.brandGreen : colors.textSecondary}
                  />
                  <Text style={[styles.wfText, { color: colors.text }]}>1. Paper Upload</Text>
                </View>
                <View style={styles.wfStep}>
                  <Ionicons
                    name={exam.verified_question_count > 0 ? "checkmark-circle" : "ellipse-outline"}
                    size={22}
                    color={exam.verified_question_count > 0 ? colors.brandGreen : colors.textSecondary}
                  />
                  <Text style={[styles.wfText, { color: colors.text }]}>2. Questions ({exam.verified_question_count})</Text>
                </View>
                <View style={styles.wfStep}>
                  <Ionicons
                    name={exam.answer_key_document ? "checkmark-circle" : "ellipse-outline"}
                    size={22}
                    color={exam.answer_key_document ? colors.brandGreen : colors.textSecondary}
                  />
                  <Text style={[styles.wfText, { color: colors.text }]}>3. Answer Key</Text>
                </View>
                <View style={styles.wfStep}>
                  <Ionicons
                    name={exam.evaluation_count > 0 ? "checkmark-circle" : "ellipse-outline"}
                    size={22}
                    color={exam.evaluation_count > 0 ? colors.brandGreen : colors.textSecondary}
                  />
                  <Text style={[styles.wfText, { color: colors.text }]}>4. Evaluated ({exam.finalized_count}/{exam.evaluation_count})</Text>
                </View>
              </View>
            </Card>
          </View>
        )}

        {/* QUESTION PAPER TAB */}
        {activeTab === "paper" && (
          <View>
            <Card style={styles.sectionCard}>
              <Text style={[styles.cardTitle, { color: colors.text }]}>Question Paper Document</Text>
              {exam.question_paper ? (
                <View>
                  <View style={styles.docInfoRow}>
                    <Ionicons name="document-text" size={32} color={colors.primary} />
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={[styles.docName, { color: colors.text }]}>
                        {exam.question_paper.original_filename}
                      </Text>
                      <Text style={[styles.docMeta, { color: colors.textSecondary }]}>
                        Uploaded: {new Date(exam.question_paper.uploaded_at).toLocaleString()}
                        {exam.question_paper.pages?.length ? ` • ${exam.question_paper.pages.length} pages` : ""}
                      </Text>
                    </View>
                    <StatusBadge status={exam.question_paper.status} />
                  </View>

                  {/* Live OCR Progress Indicator inside Paper tab */}
                  {isPaperBusy && (
                    <View style={[styles.ocrProgressBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.primary }]}>
                      <View style={styles.ocrProgressHeader}>
                        <ActivityIndicator size="small" color={colors.primary} />
                        <Text style={[styles.ocrProgressTitle, { color: colors.text }]}>
                          Reading Document with InternVL AI...
                        </Text>
                      </View>
                      <Text style={[styles.ocrStageText, { color: colors.primary }]}>
                        {exam.question_paper.stage || "Processing pages..."}
                      </Text>
                      <View style={styles.progressBarTrack}>
                        <View
                          style={[
                            styles.progressBarFill,
                            {
                              backgroundColor: colors.primary,
                              width: `${Math.min(
                                100,
                                Math.max(
                                  15,
                                  ((exam.question_paper.progress_current || 1) /
                                    Math.max(exam.question_paper.progress_total || 1, 1)) *
                                    100
                                )
                              )}%`,
                            },
                          ]}
                        />
                      </View>
                      <Text style={[styles.ocrHintText, { color: colors.textSecondary }]}>
                        Page {exam.question_paper.progress_current || 0} of {exam.question_paper.progress_total || 1}
                      </Text>
                    </View>
                  )}

                  {/* Direct shortcut to review extracted questions once ready */}
                  {(exam.question_paper.status === "READY" || (questionsData?.questions?.length || 0) > 0) && (
                    <Button
                      title={`Review Extracted Questions (${questionsData?.questions?.length || exam.question_count || 0})`}
                      icon={<Ionicons name="list" size={16} color="#FFFFFF" />}
                      variant="gradient"
                      size="medium"
                      onPress={() => setActiveTab("questions")}
                      style={{ marginTop: 12 }}
                      fullWidth
                    />
                  )}

                  <View style={{ gap: 8, marginTop: 12 }}>
                    <Button
                      title="Download / Share PDF"
                      icon={<Ionicons name="share-outline" size={16} color="#FFFFFF" />}
                      variant="primary"
                      size="small"
                      onPress={() =>
                        downloadAndShareFile(
                          `/exams/${examId}/question-paper/pdf`,
                          exam.question_paper?.original_filename || `${exam.name}_QuestionPaper.pdf`
                        )
                      }
                      fullWidth
                    />
                    <View style={styles.btnRow}>
                      <Button
                        title="Scan to Replace"
                        icon={<Ionicons name="camera-outline" size={16} color="#FFFFFF" />}
                        variant="gradient"
                        size="small"
                        onPress={() => {
                          setScannerTarget("question_paper");
                          setCameraScannerVisible(true);
                        }}
                        loading={actionLoading}
                        style={{ flex: 1 }}
                      />
                      <Button
                        title="Upload File"
                        icon={<Ionicons name="cloud-upload-outline" size={16} color={colors.text} />}
                        variant="secondary"
                        size="small"
                        onPress={handleUploadQuestionPaper}
                        loading={actionLoading}
                        style={{ flex: 1 }}
                      />
                    </View>
                  </View>
                </View>
              ) : (
                <View style={styles.scannerPromptCard}>
                  <View style={[styles.scannerPromptIcon, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
                    <Ionicons name="scan-outline" size={44} color={colors.primary} />
                  </View>
                  <Text style={[styles.scannerPromptTitle, { color: colors.text }]}>
                    Capture Question Paper
                  </Text>
                  <Text style={[styles.scannerPromptDesc, { color: colors.textSecondary }]}>
                    Scan pages with the camera, or upload a file.
                  </Text>

                  <Button
                    title="Scan Question Paper (Camera)"
                    icon={<Ionicons name="camera-outline" size={18} color="#FFFFFF" />}
                    variant="gradient"
                    size="large"
                    onPress={() => {
                      setScannerTarget("question_paper");
                      setCameraScannerVisible(true);
                    }}
                    fullWidth
                    style={{ marginBottom: 10, marginTop: 6 }}
                  />

                  <Button
                    title="Upload Existing PDF / Image File"
                    icon={<Ionicons name="document-attach-outline" size={18} color={colors.text} />}
                    variant="secondary"
                    size="medium"
                    onPress={handleUploadQuestionPaper}
                    loading={actionLoading}
                    fullWidth
                  />
                </View>
              )}
            </Card>

            {/* Total Marks Verification Card in Question Paper Tab */}
            {questionsData && (
              <Card
                style={[
                  styles.totalMarksCard,
                  {
                    borderColor:
                      Math.abs((questionsData.sum_of_marks || 0) - exam.total_marks) > 0.01
                        ? colors.warning
                        : colors.brandGreen,
                  },
                ]}
              >
                <View style={styles.totalMarksHeader}>
                  <View
                    style={[
                      styles.totalMarksIconCircle,
                      {
                        backgroundColor:
                          Math.abs((questionsData.sum_of_marks || 0) - exam.total_marks) > 0.01
                            ? "rgba(240, 182, 90, 0.15)"
                            : "rgba(81, 188, 117, 0.15)",
                      },
                    ]}
                  >
                    <Ionicons
                      name={
                        Math.abs((questionsData.sum_of_marks || 0) - exam.total_marks) > 0.01
                          ? "alert-circle-outline"
                          : "checkmark-circle-outline"
                      }
                      size={20}
                      color={
                        Math.abs((questionsData.sum_of_marks || 0) - exam.total_marks) > 0.01
                          ? colors.warning
                          : colors.brandGreen
                      }
                    />
                  </View>
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={[styles.totalMarksCardTitle, { color: colors.text }]}>
                      Total Marks: {exam.total_marks} Marks
                    </Text>
                    <Text style={[styles.totalMarksCardSub, { color: colors.textSecondary }]}>
                      {questionsData.sum_of_marks > 0
                        ? `Extracted from Question Paper: ${questionsData.sum_of_marks} Marks (${questionsData.questions.length} questions)`
                        : "Upload question paper to automatically compute and verify total marks."}
                    </Text>
                  </View>
                </View>

                {questionsData.sum_of_marks > 0 && (
                  <View style={styles.totalMarksActionRow}>
                    <Button
                      title="Verify / Update Total Marks"
                      icon={<Ionicons name="calculator-outline" size={15} color="#FFFFFF" />}
                      variant={
                        Math.abs((questionsData.sum_of_marks || 0) - exam.total_marks) > 0.01
                          ? "gradient"
                          : "primary"
                      }
                      size="small"
                      onPress={() => {
                        setCustomTotalMarks(String(questionsData.sum_of_marks || exam.total_marks));
                        setTotalMarksModalVisible(true);
                      }}
                    />
                  </View>
                )}
              </Card>
            )}
            {/* Answer key can be uploaded together with the paper; it is read once questions are verified */}
            <Card style={styles.sectionCard}>
              <Text style={[styles.cardTitle, { color: colors.text }]}>Answer Key Document</Text>
              {exam.answer_key_document ? (
                <View style={styles.docInfoRow}>
                  <Ionicons name="key-outline" size={28} color={colors.primary} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={[styles.docName, { color: colors.text }]}>{exam.answer_key_document.original_filename}</Text>
                    <Text style={[styles.docMeta, { color: colors.textSecondary }]}>
                      {exam.answer_key_document.status === "WAITING"
                        ? "Reading starts automatically when you verify the questions."
                        : exam.answer_key_document.stage || `Uploaded: ${new Date(exam.answer_key_document.uploaded_at).toLocaleString()}`}
                    </Text>
                  </View>
                  <StatusBadge status={exam.answer_key_document.status} size="small" />
                </View>
              ) : (
                <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 10 }}>
                  Upload now or later. It is read once the questions are verified.
                </Text>
              )}
              {["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED"].includes(exam.status) &&
                !isKeyBusy && (
                  <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
                    <Button
                      title="Scan Key"
                      icon={<Ionicons name="camera-outline" size={15} color="#FFFFFF" />}
                      variant="gradient"
                      size="small"
                      onPress={() => {
                        setScannerTarget("answer_key");
                        setCameraScannerVisible(true);
                      }}
                      style={{ flex: 1 }}
                    />
                    <Button
                      title={exam.answer_key_document ? "Replace Key" : "Upload Key"}
                      icon={<Ionicons name="cloud-upload-outline" size={15} color={colors.text} />}
                      variant="secondary"
                      size="small"
                      onPress={handleUploadAnswerKeyDoc}
                      loading={actionLoading}
                      style={{ flex: 1 }}
                    />
                  </View>
                )}
            </Card>
          </View>
        )}

        {/* QUESTIONS TAB */}
        {activeTab === "questions" && (() => {
          const qs = questionsData?.questions || [];
          const counts = {
            ok: qs.filter((q) => q.verification_status === "VERIFIED").length,
            review: qs.filter((q) => q.verification_status === "NEEDS_REVIEW").length,
          };

          return (
            <View>
              {/* Live OCR Progress Card if paper is currently being processed */}
              {isPaperBusy && (
                <Card style={[styles.ocrProgressCard, { borderColor: colors.primary }]}>
                  <View style={styles.ocrProgressHeader}>
                    <ActivityIndicator size="small" color={colors.primary} />
                    <Text style={[styles.ocrProgressTitle, { color: colors.text }]}>
                      Extracting Questions with InternVL AI...
                    </Text>
                    <StatusBadge status={exam.question_paper?.status || "OCR_PROCESSING"} />
                  </View>
                  <Text style={[styles.ocrStageText, { color: colors.primary }]}>
                    {exam.question_paper?.stage || "Reading pages and extracting questions..."}
                  </Text>
                  <View style={styles.progressBarTrack}>
                    <View
                      style={[
                        styles.progressBarFill,
                        {
                          backgroundColor: colors.primary,
                          width: `${Math.min(
                            100,
                            Math.max(
                              15,
                              ((exam.question_paper?.progress_current || 1) /
                                Math.max(exam.question_paper?.progress_total || 1, 1)) *
                                100
                            )
                          )}%`,
                        },
                      ]}
                    />
                  </View>
                  <Text style={[styles.ocrHintText, { color: colors.textSecondary }]}>
                    Page {exam.question_paper?.progress_current || 0} of {exam.question_paper?.progress_total || 1}. Extracted questions will appear below in real-time.
                  </Text>
                </Card>
              )}

              {/* Summary Stats Header Bar (matching website) */}
              <View style={[styles.summaryBar, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <View style={styles.summaryStatsRow}>
                  <Text style={[styles.summaryStatsText, { color: colors.text }]}>
                    <Text style={{ fontWeight: "700" }}>{counts.ok}</Text> of {qs.length} accepted ·{" "}
                    <Text
                      style={{
                        color: counts.review ? colors.warning : colors.textSecondary,
                        fontWeight: counts.review ? "700" : "400",
                      }}
                    >
                      {counts.review} need review
                    </Text>{" "}
                    · marks add up to{" "}
                    <Text style={{ fontWeight: "700" }}>{questionsData?.sum_of_marks ?? 0}</Text> of{" "}
                    <Text style={{ fontWeight: "700" }}>
                      {questionsData?.exam_total_marks ?? exam.total_marks}
                    </Text>
                  </Text>
                  <TouchableOpacity
                    onPress={() => {
                      setCustomTotalMarks(String(questionsData?.sum_of_marks || exam.total_marks));
                      setTotalMarksModalVisible(true);
                    }}
                    style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 }}
                  >
                    <Ionicons name="calculator-outline" size={13} color={colors.primary} />
                    <Text style={{ fontSize: 12, fontWeight: "700", color: colors.primary }}>
                      Verify Total Marks ({questionsData?.sum_of_marks ?? 0} vs {exam.total_marks})
                    </Text>
                  </TouchableOpacity>
                </View>

                {!questionsData?.locked && (
                  <View style={styles.summaryActionsRow}>
                    <Button
                      title="+ Add Question"
                      variant="secondary"
                      size="small"
                      onPress={() => {
                        setSelectedQuestionForEdit(null);
                        setEditModalVisible(true);
                      }}
                    />
                    {qs.length > 0 && (
                      <Button
                        title="Accept All Complete"
                        variant="secondary"
                        size="small"
                        loading={actionLoading}
                        disabled={
                          actionLoading ||
                          (!!exam?.question_paper && ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"].includes(exam.question_paper.status)) ||
                          Boolean(questionsData && (questionsData as any).document_status && ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"].includes((questionsData as any).document_status))
                        }
                        onPress={handleAcceptAllValid}
                      />
                    )}
                    {qs.length > 0 && (
                      <Button
                        title="Verify Questions"
                        icon={<Ionicons name="checkmark-done" size={16} color="#FFFFFF" />}
                        variant="gradient"
                        size="small"
                        loading={actionLoading}
                        disabled={
                          actionLoading ||
                          (!!exam?.question_paper && ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"].includes(exam.question_paper.status)) ||
                          Boolean(questionsData && (questionsData as any).document_status && ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"].includes((questionsData as any).document_status))
                        }
                        onPress={handleVerifyQuestions}
                      />
                    )}
                  </View>
                )}
              </View>

              {/* Marks Warning Banner */}
              {questionsData?.marks_warning && (
                <TouchableOpacity
                  activeOpacity={0.8}
                  onPress={() => {
                    setCustomTotalMarks(String(questionsData.sum_of_marks));
                    setTotalMarksModalVisible(true);
                  }}
                  style={[styles.alertBanner, { backgroundColor: "rgba(234, 179, 8, 0.12)", borderColor: colors.warning }]}
                >
                  <Ionicons name="warning-outline" size={18} color={colors.warning} />
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.alertText, { color: colors.text }]}>
                      {questionsData.marks_warning}
                    </Text>
                    <Text style={{ fontSize: 11, fontWeight: "700", color: colors.warning, marginTop: 2 }}>
                      Tap to open confirmation popup and set exam total marks.
                    </Text>
                  </View>
                </TouchableOpacity>
              )}

              {/* Locked Banner */}
              {questionsData?.locked && (
                <View style={[styles.alertBanner, { backgroundColor: "rgba(81, 188, 117, 0.12)", borderColor: colors.brandGreen }]}>
                  <Ionicons name="shield-checkmark-outline" size={18} color={colors.brandGreen} />
                  <Text style={[styles.alertText, { color: colors.text }]}>
                    Questions are verified and locked.
                  </Text>
                </View>
              )}

              {/* Empty state when no questions extracted yet */}
              {qs.length === 0 && !isPaperBusy ? (
                <View>
                  {exam.question_paper?.error_message ? (
                    <View style={[styles.alertBanner, { backgroundColor: "rgba(239, 68, 68, 0.12)", borderColor: colors.error, marginBottom: 12 }]}>
                      <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
                      <Text style={[styles.alertText, { color: colors.text }]}>
                        {exam.question_paper.error_message}
                      </Text>
                    </View>
                  ) : null}
                  <Empty
                    icon="list-outline"
                    title="No Questions Extracted Yet"
                    description="Upload the question paper, or add questions by hand."
                    actionTitle="+ Add Question"
                    onAction={() => {
                      setSelectedQuestionForEdit(null);
                      setEditModalVisible(true);
                    }}
                  />
                  <View style={{ flexDirection: "row", gap: 10, marginTop: 12, justifyContent: "center" }}>
                    <Button
                      title="Scan Paper"
                      icon={<Ionicons name="camera-outline" size={16} color="#FFFFFF" />}
                      variant="gradient"
                      size="medium"
                      onPress={() => setCameraScannerVisible(true)}
                    />
                    <Button
                      title="Upload PDF / Image"
                      icon={<Ionicons name="cloud-upload-outline" size={16} color={colors.text} />}
                      variant="secondary"
                      size="medium"
                      onPress={handleUploadQuestionPaper}
                    />
                  </View>
                </View>
              ) : (
                qs.map((q: Question) => {
                  const isNeedsReview = q.verification_status === "NEEDS_REVIEW";
                  return (
                    <Card
                      key={q.id}
                      style={[
                        styles.questionCard,
                        isNeedsReview ? { borderColor: colors.warning, borderWidth: 1.5 } : {},
                      ]}
                    >
                      {/* Question Header */}
                      <View style={styles.qCardHeader}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                          <Text style={[styles.qNumberText, { color: colors.text }]}>
                            Question {q.display_number}
                          </Text>
                          {q.section ? (
                            <Badge label={q.section} variant="muted" />
                          ) : null}
                        </View>

                        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                          <Badge
                            label={`${q.max_marks !== null ? q.max_marks : "–"} Marks`}
                            variant="muted"
                          />
                          {q.ocr_confidence !== null && q.ocr_confidence < 0.6 && (
                            <Badge label={`Low confidence ${Math.round(q.ocr_confidence * 100)}%`} variant="warning" />
                          )}
                          <StatusBadge status={q.verification_status} />
                        </View>
                      </View>

                      <TouchableOpacity
                        disabled={exam.status === "FINALIZED"}
                        onPress={() => {
                          setCoInput(q.course_outcome || "");
                          setOutcomeTarget(q);
                        }}
                        style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 }}
                      >
                        <Badge
                          label={q.k_level ? `${q.k_level} ${K_LEVEL_NAMES[q.k_level] || ""}` : "K level –"}
                          variant={q.k_level_source === "SUGGESTED" ? "warning" : q.k_level ? "teal" : "muted"}
                          size="small"
                        />
                        {q.k_level_source === "SUGGESTED" && (
                          <Text style={{ fontSize: 11, color: colors.warning }}>Suggested</Text>
                        )}
                        <Badge label={q.course_outcome || "CO –"} variant={q.course_outcome ? "teal" : "muted"} size="small" />
                        {exam.status !== "FINALIZED" && <Ionicons name="pencil-outline" size={13} color={colors.primary} />}
                      </TouchableOpacity>

                      {/* Review Reason Highlight */}
                      {q.review_reason ? (
                        <View style={[styles.reviewReasonBanner, { backgroundColor: "rgba(234, 179, 8, 0.12)" }]}>
                          <Ionicons name="alert-circle-outline" size={16} color={colors.warning} />
                          <Text style={[styles.reviewReasonText, { color: colors.warning }]}>
                            {q.review_reason}
                          </Text>
                        </View>
                      ) : null}

                      {/* Question Text */}
                      <Text style={[styles.questionBodyText, { color: colors.text }]}>
                        {q.question_text || q.raw_ocr_text || "(empty question statement)"}
                      </Text>

                      {/* Model OCR Crop Snippet */}
                      {q.has_crop && (
                        <View style={[styles.cropBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                          <View style={styles.cropBoxHeader}>
                            <Ionicons name="scan-outline" size={14} color={colors.primary} />
                            <Text style={[styles.cropBoxLabel, { color: colors.textSecondary }]}>
                              Detected area
                            </Text>
                          </View>
                          <AuthImage
                            path={`/crops/question/${q.id}`}
                            style={styles.cropImage}
                          />
                        </View>
                      )}

                      {/* Action Buttons Toolbar */}
                      {!questionsData?.locked && (
                        <View style={[styles.qActionsBar, { borderTopColor: colors.border }]}>
                          <TouchableOpacity
                            disabled={q.verification_status === "VERIFIED" || actionLoading}
                            onPress={() => handleAcceptQuestion(q.id)}
                            style={[
                              styles.actionPill,
                              {
                                backgroundColor:
                                  q.verification_status === "VERIFIED"
                                    ? "rgba(255,255,255,0.06)"
                                    : colors.primary,
                                opacity: q.verification_status === "VERIFIED" ? 0.5 : 1,
                              },
                            ]}
                          >
                            <Ionicons name="checkmark" size={14} color="#FFFFFF" />
                            <Text style={styles.actionPillTextWhite}>
                              {q.verification_status === "VERIFIED" ? "Accepted" : "Accept"}
                            </Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            onPress={() => {
                              setSelectedQuestionForEdit(q);
                              setEditModalVisible(true);
                            }}
                            style={[styles.actionPillSec, { borderColor: colors.border }]}
                          >
                            <Ionicons name="pencil-outline" size={14} color={colors.text} />
                            <Text style={[styles.actionPillText, { color: colors.text }]}>Edit</Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            onPress={() => setMoreTarget(q)}
                            style={[styles.actionPillSec, { borderColor: colors.border }]}
                          >
                            <Ionicons name="ellipsis-horizontal" size={14} color={colors.text} />
                            <Text style={[styles.actionPillText, { color: colors.text }]}>More</Text>
                          </TouchableOpacity>
                        </View>
                      )}
                    </Card>
                  );
                })
              )}
            </View>
          );
        })()}

        {/* ANSWER KEY TAB */}
        {activeTab === "answerKey" && (
          <View>
            <View style={styles.tabActionHeader}>
              <Text style={[styles.tabHeading, { color: colors.text }]}>
                Official Solutions & Criteria ({keysData?.keys?.length || 0})
              </Text>
              <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {!keysData?.locked && (
                  <>
                    <Button
                      title="Scan (Camera)"
                      icon={<Ionicons name="camera-outline" size={14} color="#FFFFFF" />}
                      variant="gradient"
                      size="small"
                      onPress={() => {
                        setScannerTarget("answer_key");
                        setCameraScannerVisible(true);
                      }}
                      loading={actionLoading}
                    />
                    <Button
                      title="Upload File"
                      icon={<Ionicons name="cloud-upload-outline" size={14} color={colors.text} />}
                      variant="secondary"
                      size="small"
                      onPress={handleUploadAnswerKeyDoc}
                      loading={actionLoading}
                    />
                    <Button
                      title="Generate AI"
                      icon={<Ionicons name="sparkles" size={14} color={colors.primary} />}
                      variant="secondary"
                      size="small"
                      onPress={handleGenerateAnswerKey}
                      loading={actionLoading}
                    />
                  </>
                )}
                {keysData?.keys && keysData.keys.length > 0 && !keysData.locked && (
                  <>
                    <Button
                      title="Verify All Answers"
                      icon={<Ionicons name="shield-checkmark" size={14} color="#FFFFFF" />}
                      variant="gradient"
                      size="small"
                      onPress={handleVerifyAllAnswers}
                      loading={validatingAll}
                      disabled={validatingAll}
                    />
                    <Button
                      title="Verify Key"
                      icon={<Ionicons name="lock-closed-outline" size={14} color={colors.text} />}
                      variant="secondary"
                      size="small"
                      onPress={handleVerifyAnswerKey}
                      loading={actionLoading}
                      disabled={actionLoading || validatingAll}
                    />
                  </>
                )}
              </View>
            </View>

            {/* Prominent Verify All Answers Banner */}
            {keysData?.keys && keysData.keys.length > 0 && !keysData.locked && (
              <Card style={[styles.verifyAllBannerCard, { borderColor: colors.primary, backgroundColor: colors.surfaceElevated, marginBottom: 14 }]}>
                <View style={styles.verifyAllBannerContent}>
                  <View style={[styles.verifyAllIconBox, { backgroundColor: "rgba(0, 168, 232, 0.16)" }]}>
                    <Ionicons name="shield-checkmark" size={24} color={colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.verifyAllBannerTitle, { color: colors.text }]}>
                      Verify All Answers
                    </Text>
                    <Text style={[styles.verifyAllBannerDesc, { color: colors.textSecondary }]}>
                      Validates all {keysData.keys.length} answers against backend rules, automatically approves eligible solutions, and flags unresolved issues for review.
                    </Text>
                  </View>
                </View>
                <View style={{ marginTop: 12, flexDirection: "row", gap: 8 }}>
                  <Button
                    title={validatingAll ? "Verifying Answers..." : "Verify All Answers"}
                    icon={<Ionicons name="checkmark-done-circle" size={17} color="#FFFFFF" />}
                    variant="gradient"
                    size="medium"
                    onPress={handleVerifyAllAnswers}
                    loading={validatingAll}
                    disabled={validatingAll}
                    style={{ flex: 1.4 }}
                  />
                  <Button
                    title="Verify Key"
                    icon={<Ionicons name="lock-closed-outline" size={16} color={colors.text} />}
                    variant="secondary"
                    size="medium"
                    onPress={handleVerifyAnswerKey}
                    loading={actionLoading}
                    disabled={actionLoading || validatingAll}
                    style={{ flex: 1 }}
                  />
                </View>
              </Card>
            )}

            {keysData?.locked && (
              <View style={[styles.alertBanner, { backgroundColor: "rgba(81, 188, 117, 0.12)", borderColor: colors.brandGreen }]}>
                <Ionicons name="shield-checkmark-outline" size={18} color={colors.brandGreen} />
                <Text style={[styles.alertText, { color: colors.text }]}>
                  Answer Key is verified and locked. Ready for grading and evaluations.
                </Text>
              </View>
            )}

            {isKeyBusy && (
              <Card style={[styles.ocrProgressCard, { borderColor: colors.primary, marginBottom: 12 }]}>
                <View style={styles.ocrProgressHeader}>
                  <ActivityIndicator size="small" color={colors.primary} />
                  <Text style={[styles.ocrProgressTitle, { color: colors.text }]}>
                    Extracting Answer Key with InternVL AI...
                  </Text>
                  <StatusBadge status={exam.answer_key_document?.status || "OCR_PROCESSING"} />
                </View>
                <Text style={[styles.ocrStageText, { color: colors.primary }]}>
                  {exam.answer_key_document?.stage || "Reading pages and extracting official solutions..."}
                </Text>
                <View style={styles.progressBarTrack}>
                  <View
                    style={[
                      styles.progressBarFill,
                      {
                        backgroundColor: colors.primary,
                        width: `${Math.min(
                          100,
                          Math.max(
                            15,
                            ((exam.answer_key_document?.progress_current || 1) /
                              Math.max(exam.answer_key_document?.progress_total || 1, 1)) *
                              100
                          )
                        )}%`,
                      },
                    ]}
                  />
                </View>
                <Text style={[styles.ocrHintText, { color: colors.textSecondary }]}>
                  Status: {exam.answer_key_document?.status}. Ollama vision model is parsing solutions and criteria.
                </Text>
              </Card>
            )}

            {actionLoading && !isKeyBusy && (
              <Card style={[styles.ocrProgressCard, { borderColor: colors.primary, marginBottom: 12 }]}>
                <View style={styles.ocrProgressHeader}>
                  <ActivityIndicator size="small" color={colors.primary} />
                  <Text style={[styles.ocrProgressTitle, { color: colors.text }]}>
                    Ollama AI Generating Answer Key...
                  </Text>
                </View>
                <Text style={[styles.ocrHintText, { color: colors.textSecondary }]}>
                  Generating answers. This can take up to a minute.
                </Text>
              </Card>
            )}

            {(!keysData?.keys || keysData.keys.length === 0) && !isKeyBusy ? (
              <Card style={styles.scannerPromptCard}>
                <View style={[styles.scannerPromptIcon, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
                  <Ionicons name="key-outline" size={44} color={colors.primary} />
                </View>
                <Text style={[styles.scannerPromptTitle, { color: colors.text }]}>
                  Capture / Create Answer Key
                </Text>
                <Text style={[styles.scannerPromptDesc, { color: colors.textSecondary }]}>
                  Scan or upload the answer key, or generate it with AI.
                </Text>

                <Button
                  title="Scan Answer Key (Camera)"
                  icon={<Ionicons name="camera-outline" size={18} color="#FFFFFF" />}
                  variant="gradient"
                  size="large"
                  onPress={() => {
                    setScannerTarget("answer_key");
                    setCameraScannerVisible(true);
                  }}
                  fullWidth
                  style={{ marginBottom: 10, marginTop: 6 }}
                />

                <Button
                  title="Upload Existing PDF / Image File"
                  icon={<Ionicons name="cloud-upload-outline" size={18} color={colors.text} />}
                  variant="secondary"
                  size="medium"
                  onPress={handleUploadAnswerKeyDoc}
                  loading={actionLoading}
                  fullWidth
                  style={{ marginBottom: 10 }}
                />

                <Button
                  title="Draft Solutions with Ollama AI"
                  icon={<Ionicons name="sparkles" size={16} color={colors.primary} />}
                  variant="ghost"
                  size="medium"
                  onPress={handleGenerateAnswerKey}
                  loading={actionLoading}
                  fullWidth
                />
              </Card>
            ) : (
              (keysData?.keys || []).map((k) => {
                const mappedQ = (keysData?.questions || []).find((q) => q.id === k.exam_question_id);
                const hasIssue =
                  k.mapping_status !== "MAPPED" ||
                  k.mark_mismatch ||
                  !(k.answer_text || "").trim();
                const isNeedsReview = k.mapping_status === "NEEDS_REVIEW";
                const isUnmapped = k.mapping_status === "UNMAPPED";
                const isEmptySolution = !(k.answer_text || "").trim();
                const isVerified = k.verification_status === "VERIFIED";

                return (
                  <Card
                    key={k.id}
                    style={[
                      styles.itemCard,
                      hasIssue ? { borderColor: colors.warning, borderWidth: 1.5 } : null,
                      isVerified ? { borderColor: "rgba(37, 200, 120, 0.4)" } : null,
                    ]}
                  >
                    <View style={styles.itemHeader}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap", flex: 1 }}>
                        <Badge label={`Q${k.raw_question_number || k.normalized_number || "?"}`} variant="teal" />
                        {mappedQ && (
                          <Badge label={`→ Question ${mappedQ.display_number}`} variant="muted" />
                        )}
                        {k.marks !== null && (
                          <Text style={[styles.qMarksText, { color: colors.brandGreen }]}>
                            {k.marks} Marks
                          </Text>
                        )}
                      </View>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                        <Badge
                          label={k.mapping_status}
                          variant={k.mapping_status === "MAPPED" ? "teal" : k.mapping_status === "NEEDS_REVIEW" ? "warning" : "danger"}
                        />
                        <StatusBadge status={k.verification_status || "UNVERIFIED"} />
                      </View>
                    </View>

                    {/* Prominent Issue Banners */}
                    {k.mark_mismatch && (
                      <View style={[styles.reviewReasonBanner, { backgroundColor: "rgba(245, 166, 35, 0.14)", borderColor: colors.warning, borderWidth: 1 }]}>
                        <Ionicons name="alert-circle" size={16} color={colors.warning} />
                        <Text style={[styles.reviewReasonText, { color: colors.warning }]}>
                          Marks Mismatch: Key has {k.marks} marks, Question {mappedQ?.display_number || "?"} is worth {mappedQ?.max_marks || "?"} marks.
                        </Text>
                      </View>
                    )}

                    {isNeedsReview && (
                      <View style={[styles.reviewReasonBanner, { backgroundColor: "rgba(239, 98, 98, 0.12)", borderColor: colors.error, borderWidth: 1 }]}>
                        <Ionicons name="git-branch-outline" size={16} color={colors.error} />
                        <Text style={[styles.reviewReasonText, { color: colors.error }]}>
                          Needs Review: {k.mapping_note || "Ambiguous question mapping. Resolve to confirm question."}
                        </Text>
                      </View>
                    )}

                    {isUnmapped && (
                      <View style={[styles.reviewReasonBanner, { backgroundColor: "rgba(239, 98, 98, 0.12)", borderColor: colors.error, borderWidth: 1 }]}>
                        <Ionicons name="help-circle-outline" size={16} color={colors.error} />
                        <Text style={[styles.reviewReasonText, { color: colors.error }]}>
                          Unmapped: Not mapped to any exam question.
                        </Text>
                      </View>
                    )}

                    {isEmptySolution && (
                      <View style={[styles.reviewReasonBanner, { backgroundColor: "rgba(239, 98, 98, 0.12)", borderColor: colors.error, borderWidth: 1 }]}>
                        <Ionicons name="document-text-outline" size={16} color={colors.error} />
                        <Text style={[styles.reviewReasonText, { color: colors.error }]}>
                          Empty Solution Text: Must enter official solution before verifying.
                        </Text>
                      </View>
                    )}

                    <Text
                      style={[
                        styles.qText,
                        { color: isEmptySolution ? colors.error : colors.text, fontStyle: isEmptySolution ? "italic" : "normal" },
                      ]}
                    >
                      {k.answer_text || "(Empty solution text - tap Edit or Resolve to add)"}
                    </Text>

                    {k.has_crop && (
                      <View style={[styles.cropBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border, marginTop: 10 }]}>
                        <View style={styles.cropBoxHeader}>
                          <Ionicons name="scan-outline" size={14} color={colors.primary} />
                          <Text style={[styles.cropBoxLabel, { color: colors.textSecondary }]}>
                            What the model read (approximate crop):
                          </Text>
                        </View>
                        <AuthImage
                          path={`/crops/answer-key/${k.id}`}
                          style={styles.cropImage}
                        />
                      </View>
                    )}

                    {k.criteria && k.criteria.length > 0 && (
                      <View style={styles.criteriaBox}>
                        <Text style={[styles.criteriaTitle, { color: colors.primary }]}>Evaluation Criteria:</Text>
                        {k.criteria.map((c, idx) => (
                          <Text key={idx} style={[styles.criteriaItem, { color: colors.textSecondary }]}>
                            • {c}
                          </Text>
                        ))}
                      </View>
                    )}

                    {/* Card Action Controls: Edit, Resolve Issue, Verify Answer */}
                    {!keysData?.locked && (
                      <View
                        style={[
                          styles.cardActionsRow,
                          { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: 10, marginTop: 10 },
                        ]}
                      >
                        <Button
                          title="Edit"
                          icon={<Ionicons name="create-outline" size={14} color={colors.text} />}
                          variant="secondary"
                          size="small"
                          onPress={() => handleOpenEditKey(k)}
                        />

                        {hasIssue && (
                          <Button
                            title="Resolve Issue"
                            icon={<Ionicons name="alert-circle-outline" size={14} color="#FFFFFF" />}
                            variant="primary"
                            size="small"
                            onPress={() => handleOpenResolveKey(k)}
                          />
                        )}

                        {!isVerified ? (
                          <Button
                            title="Verify Answer"
                            icon={<Ionicons name="checkmark-circle-outline" size={14} color="#FFFFFF" />}
                            variant="gradient"
                            size="small"
                            onPress={() => handleVerifySingleKey(k)}
                            loading={verifyingKeyId === k.id}
                          />
                        ) : (
                          <View style={styles.verifiedTag}>
                            <Ionicons name="checkmark-done-circle" size={16} color={colors.brandGreen} />
                            <Text style={[styles.verifiedTagText, { color: colors.brandGreen }]}>Verified</Text>
                          </View>
                        )}
                      </View>
                    )}
                  </Card>
                );
              })
            )}

            {keysData?.keys && keysData.keys.length > 0 && !keysData.locked && (
              <Card style={{ borderColor: colors.border, backgroundColor: colors.surfaceElevated, marginTop: 14, marginBottom: 20, padding: 14 }}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                  <View style={{ flex: 1, minWidth: 200 }}>
                    <Text style={{ fontSize: 14, fontWeight: "700", color: colors.text }}>
                      Answer Key Verification
                    </Text>
                    <Text style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>
                      {(keysData.keys || []).filter((k) => k.verification_status === "VERIFIED").length} of {keysData.keys.length} answers verified. When all answers are resolved, finalize the key for grading.
                    </Text>
                  </View>
                  <View style={{ flexDirection: "row", gap: 8 }}>
                    <Button
                      title="Verify All Answers"
                      icon={<Ionicons name="shield-checkmark" size={14} color="#FFFFFF" />}
                      variant="gradient"
                      size="small"
                      onPress={handleVerifyAllAnswers}
                      loading={validatingAll}
                      disabled={validatingAll}
                    />
                    <Button
                      title="Verify Key"
                      icon={<Ionicons name="lock-closed-outline" size={14} color={colors.text} />}
                      variant="secondary"
                      size="small"
                      onPress={handleVerifyAnswerKey}
                      loading={actionLoading}
                      disabled={actionLoading || validatingAll}
                    />
                  </View>
                </View>
              </Card>
            )}
          </View>
        )}

        {/* STUDENTS TAB (Class Roster with submission & marks status - Laptop Parity) */}
        {activeTab === "students" && (
          <View>
            <View style={styles.tabActionHeader}>
              <View>
                <Text style={[styles.tabHeading, { color: colors.text }]}>
                  Class Roster ({students.length})
                </Text>
                <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                  {evaluations.length} of {students.length} student answer sheets submitted
                </Text>
              </View>
              <Button
                title="+ Upload Sheet"
                icon={<Ionicons name="cloud-upload-outline" size={14} color="#FFFFFF" />}
                variant="gradient"
                size="small"
                onPress={() => {
                  setAttachedPages([]);
                  setUploadSheetModal(true);
                }}
              />
            </View>

            {students.length === 0 ? (
              <Empty
                icon="people-outline"
                title="No Students Enrolled"
                description="Add or import students in the Students section."
              />
            ) : (
              students.map((st) => {
                const sheet = evaluations.find((ev) => ev.student?.id === st.id);
                return (
                  <Card key={st.id} style={styles.itemCard}>
                    <View style={styles.itemHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.studentItemName, { color: colors.text }]}>
                          {st.name}
                        </Text>
                        <Text style={[styles.studentItemRoll, { color: colors.textSecondary }]}>
                          Roll No: {st.roll_number}
                        </Text>
                      </View>
                      {sheet ? (
                        sheet.status === "FINALIZED" ? (
                          <PenScore score={sheet.total_marks} maxScore={sheet.maximum_marks} />
                        ) : (
                          <StatusBadge status={sheet.status} />
                        )
                      ) : (
                        <View style={[styles.unsubmittedPill, { borderColor: colors.border }]}>
                          <Text style={[styles.unsubmittedText, { color: colors.textSecondary }]}>Not Uploaded</Text>
                        </View>
                      )}
                    </View>

                    <View style={[styles.itemFooter, { borderTopColor: colors.border }]}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                        <Ionicons
                          name={sheet ? "document-text" : "cloud-upload-outline"}
                          size={14}
                          color={sheet ? colors.brandGreen : colors.textSecondary}
                        />
                        <Text style={{ fontSize: 12, color: sheet ? colors.brandGreen : colors.textSecondary, fontWeight: "600" }}>
                          {sheet ? "Answer Sheet Uploaded" : "Pending Upload"}
                        </Text>
                      </View>
                      {sheet ? (
                        <Button
                          title="Open"
                          variant="secondary"
                          size="small"
                          icon={<Ionicons name="open-outline" size={13} color={colors.text} />}
                          onPress={() => navigation.navigate(sheet.status === "FINALIZED" ? "ResultDetail" : "EvaluationDetail", { evaluationId: sheet.id })}
                        />
                      ) : (
                        <Button
                          title="Upload Sheet"
                          variant="gradient"
                          size="small"
                          icon={<Ionicons name="cloud-upload" size={13} color="#FFFFFF" />}
                          onPress={() => {
                            setSelectedStudentId(st.id);
                            setAttachedPages([]);
                            setUploadSheetModal(true);
                          }}
                        />
                      )}
                    </View>
                  </Card>
                );
              })
            )}
          </View>
        )}

        {/* SUBMISSIONS TAB */}
        {activeTab === "submissions" && (
          <View>
            <View style={styles.tabActionHeader}>
              <Text style={[styles.tabHeading, { color: colors.text }]}>
                Student Answer Sheets ({evaluations.length})
              </Text>
              <View style={{ flexDirection: "row", gap: 8 }}>
                <Button
                  title="Scan (Camera)"
                  icon={<Ionicons name="camera-outline" size={15} color="#FFFFFF" />}
                  variant="gradient"
                  size="small"
                  onPress={() => {
                    setScannerTarget("student_sheet");
                    setCameraScannerVisible(true);
                  }}
                />
                <Button
                  title="Upload"
                  icon={<Ionicons name="cloud-upload-outline" size={15} color={colors.text} />}
                  variant="secondary"
                  size="small"
                  onPress={() => setUploadSheetModal(true)}
                />
                <Button
                  title={bulkProgress || "Many Files"}
                  icon={<Ionicons name="documents-outline" size={15} color={colors.text} />}
                  variant="secondary"
                  size="small"
                  loading={!!bulkProgress}
                  disabled={!!bulkProgress}
                  onPress={handleBulkUploadSheets}
                />
              </View>
            </View>

            {/* Sheets not yet linked to a student: being identified, or held for the teacher */}
            {unassigned.length > 0 && (
              <Card style={styles.sectionCard}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Unidentified Answer Sheets ({unassigned.length})</Text>
                <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 8 }}>
                  Pick the student for each sheet to continue.
                </Text>
                {unassigned.map((d) => {
                  const working = BUSY_DOC.includes(d.status);
                  const read = d.identity?.read || {};
                  const details = [
                    read.name && `Name: ${read.name}`,
                    read.roll_number && `Roll: ${read.roll_number}`,
                    read.registration_number && `Reg: ${read.registration_number}`,
                    read.section && `Sec: ${read.section}`,
                  ].filter(Boolean).join("  •  ");
                  return (
                    <View
                      key={d.id}
                      style={{ paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, gap: 6 }}
                    >
                      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                        <Text style={{ flex: 1, fontSize: 13, fontWeight: "700", color: colors.text }} numberOfLines={1}>
                          {d.original_filename}
                        </Text>
                        <StatusBadge status={d.status} size="small" />
                      </View>
                      {working ? (
                        <Text style={{ fontSize: 12, color: colors.primary }}>{d.stage || "Reading student details..."}</Text>
                      ) : (
                        <>
                          <Text style={{ fontSize: 12, color: colors.text }}>{details || "Nothing legible"}</Text>
                          {!!d.identity?.note && <Text style={{ fontSize: 12, color: colors.warning }}>{d.identity.note}</Text>}
                          {!!d.error_message && <Text style={{ fontSize: 12, color: colors.error }}>{d.error_message}</Text>}
                          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
                            {d.pages.length > 0 && (
                              <Button title="Pick Student" variant="gradient" size="small" onPress={() => setAssignTarget(d)} />
                            )}
                            <Button title="Retry" variant="secondary" size="small" onPress={() => handleRetryIdentify(d)} />
                            <Button title="Delete" variant="secondary" size="small" onPress={() => handleDeleteUnassigned(d)} />
                          </View>
                        </>
                      )}
                    </View>
                  );
                })}
              </Card>
            )}

            {/* Failed uploads retry queue banner for network resilience */}
            {failedUploads.length > 0 && (
              <View
                style={{
                  backgroundColor: "rgba(220, 38, 38, 0.08)",
                  borderColor: "rgba(220, 38, 38, 0.3)",
                  borderWidth: 1,
                  borderRadius: 12,
                  padding: 12,
                  marginBottom: 14,
                }}
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
                  <Ionicons name="cloud-offline" size={16} color="#DC2626" />
                  <Text style={{ fontSize: 13, fontWeight: "700", color: "#DC2626" }}>
                    {failedUploads.length} Answer Sheet Upload(s) Failed (Network Issue)
                  </Text>
                </View>
                {failedUploads.map((f) => (
                  <View
                    key={f.id}
                    style={{
                      flexDirection: "row",
                      justifyContent: "space-between",
                      alignItems: "center",
                      paddingVertical: 6,
                      borderTopWidth: StyleSheet.hairlineWidth,
                      borderTopColor: "rgba(220, 38, 38, 0.2)",
                    }}
                  >
                    <View style={{ flex: 1, paddingRight: 8 }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>
                        {f.studentName} (Roll: {f.rollNumber})
                      </Text>
                      <Text style={{ fontSize: 11, color: colors.textSecondary }} numberOfLines={1}>
                        {f.error}
                      </Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => handleRetryFailedUpload(f)}
                      style={{
                        backgroundColor: "#DC2626",
                        paddingHorizontal: 12,
                        paddingVertical: 6,
                        borderRadius: 6,
                        flexDirection: "row",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      <Ionicons name="refresh" size={12} color="#FFFFFF" />
                      <Text style={{ color: "#FFFFFF", fontSize: 11, fontWeight: "700" }}>Retry</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            )}

            {evaluations.length === 0 ? (
              <Card style={styles.scannerPromptCard}>
                <View style={[styles.scannerPromptIcon, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
                  <Ionicons name="scan-outline" size={44} color={colors.primary} />
                </View>
                <Text style={[styles.scannerPromptTitle, { color: colors.text }]}>
                  No Answer Sheets Uploaded
                </Text>
                <Text style={[styles.scannerPromptDesc, { color: colors.textSecondary }]}>
                  Scan with the camera or upload files. Students are matched automatically.
                </Text>

                <Button
                  title="Scan Student Sheet (Camera)"
                  icon={<Ionicons name="camera-outline" size={18} color="#FFFFFF" />}
                  variant="gradient"
                  size="large"
                  onPress={() => {
                    setScannerTarget("student_sheet");
                    setCameraScannerVisible(true);
                  }}
                  fullWidth
                  style={{ marginBottom: 10, marginTop: 6 }}
                />

                <Button
                  title="Upload Existing PDF / Image File"
                  icon={<Ionicons name="document-attach-outline" size={18} color={colors.text} />}
                  variant="secondary"
                  size="medium"
                  onPress={() => setUploadSheetModal(true)}
                  fullWidth
                />
              </Card>
            ) : (
              evaluations.map((ev) => {
                const isFinalized = ev.status === "FINALIZED";
                const isDocBusy = !!(ev.document && BUSY_DOC.includes(ev.document.status));
                const isRunning = ev.run_status === "RUNNING";
                const pageCount = ev.document?.pages?.length ?? null;
                const detectedCount = ev.detected_answers ?? 0;
                const needReviewCount = ev.unresolved_answers ?? 0;

                return (
                  <Card key={ev.id} style={styles.itemCard}>
                    <View style={styles.itemHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.studentItemName, { color: colors.text }]}>
                          {ev.student?.name}
                        </Text>
                        <Text style={[styles.studentItemRoll, { color: colors.textSecondary }]}>
                          Roll: {ev.student?.roll_number}
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end", gap: 4 }}>
                        {isDocBusy ? (
                          <StatusBadge status={ev.document?.status || "OCR_PROCESSING"} />
                        ) : (
                          <StatusBadge status={ev.status} />
                        )}
                        {isFinalized && ev.total_marks !== null && (
                          <PenScore score={ev.total_marks} maxScore={ev.maximum_marks} size="small" />
                        )}
                      </View>
                    </View>

                    {/* Metadata summary (Pages, answers detected, needs review) like on laptop */}
                    <View style={styles.submissionMetaRow}>
                      <View style={styles.submissionMetaItem}>
                        <Ionicons name="document-text-outline" size={13} color={colors.textSecondary} />
                        <Text style={[styles.submissionMetaText, { color: colors.textSecondary }]}>
                          {pageCount ? `${pageCount} Page${pageCount > 1 ? "s" : ""}` : "1 Page"}
                        </Text>
                      </View>
                      <View style={styles.submissionMetaItem}>
                        <Ionicons name="checkmark-done-outline" size={13} color={colors.textSecondary} />
                        <Text style={[styles.submissionMetaText, { color: colors.textSecondary }]}>
                          {detectedCount} Answer{detectedCount === 1 ? "" : "s"}
                        </Text>
                      </View>
                      {needReviewCount > 0 && (
                        <View style={styles.unresolvedBadge}>
                          <Text style={styles.unresolvedBadgeText}>
                            {needReviewCount} Need Review
                          </Text>
                        </View>
                      )}
                    </View>

                    {/* Live OCR stage indicator */}
                    {isDocBusy && (
                      <View
                        style={[
                          styles.docBusyBanner,
                          { backgroundColor: "rgba(7, 159, 189, 0.1)", borderColor: colors.primary },
                        ]}
                      >
                        <ActivityIndicator size="small" color={colors.primary} />
                        <Text style={[styles.docBusyBannerText, { color: colors.primary }]} numberOfLines={1}>
                          {ev.document?.stage || "Reading student paper..."}
                        </Text>
                      </View>
                    )}

                    {/* AI Evaluation Running indicator */}
                    {isRunning && (
                      <View
                        style={[
                          styles.docBusyBanner,
                          { backgroundColor: "rgba(245, 158, 11, 0.12)", borderColor: "#F59E0B" },
                        ]}
                      >
                        <ActivityIndicator size="small" color="#F59E0B" />
                        <Text style={[styles.docBusyBannerText, { color: "#F59E0B" }]}>
                          Evaluating answers with Ollama AI ({ev.run_progress || 0}%)...
                        </Text>
                      </View>
                    )}

                    {isFinalized && (
                      <View
                        style={[
                          styles.finalizedReadonlyBadge,
                          { backgroundColor: "rgba(37, 200, 120, 0.1)", borderColor: colors.brandGreen },
                        ]}
                      >
                        <Ionicons name="lock-closed" size={13} color={colors.brandGreen} />
                        <Text style={[styles.finalizedReadonlyText, { color: colors.brandGreen }]}>
                          Finalized (Read-Only) — Marks locked
                        </Text>
                      </View>
                    )}

                    <View style={styles.btnRow}>
                      {isDocBusy ? (
                        <>
                          <Button
                            title="Reading Paper..."
                            icon={<ActivityIndicator size="small" color="#FFFFFF" />}
                            variant="gradient"
                            size="small"
                            disabled
                            onPress={() => {}}
                            style={{ flex: 1 }}
                          />
                          <Button
                            icon={<Ionicons name="trash-outline" size={15} color={colors.error} />}
                            variant="secondary"
                            size="small"
                            onPress={() => handleDeleteAnswerSheet(ev)}
                          />
                        </>
                      ) : isFinalized ? (
                        <>
                          <Button
                            title="View Result"
                            icon={<Ionicons name="ribbon-outline" size={14} color="#FFFFFF" />}
                            variant="gradient"
                            size="small"
                            onPress={() => navigation.navigate("ResultDetail", { evaluationId: ev.id })}
                            style={{ flex: 1 }}
                          />
                          <Button
                            title="Review Answers"
                            icon={<Ionicons name="eye-outline" size={14} color={colors.text} />}
                            variant="secondary"
                            size="small"
                            onPress={() => navigation.navigate("EvaluationDetail", { evaluationId: ev.id })}
                            style={{ flex: 1 }}
                          />
                        </>
                      ) : (
                        <>
                          <Button
                            title={isRunning ? "Evaluating..." : "Run Evaluation"}
                            icon={
                              isRunning ? (
                                <ActivityIndicator size="small" color="#FFFFFF" />
                              ) : (
                                <Ionicons name="play" size={14} color="#FFFFFF" />
                              )
                            }
                            variant="gradient"
                            size="small"
                            onPress={() => handleRunEvaluation(ev.id)}
                            disabled={isRunning || actionLoading}
                            loading={actionLoading && !isRunning}
                            style={{ flex: 1 }}
                          />
                          <Button
                            title="Review"
                            icon={<Ionicons name="eye-outline" size={14} color={colors.text} />}
                            variant="secondary"
                            size="small"
                            onPress={() => navigation.navigate("EvaluationDetail", { evaluationId: ev.id })}
                            style={{ flex: 1 }}
                          />
                          <Button
                            icon={<Ionicons name="trash-outline" size={15} color={colors.error} />}
                            variant="secondary"
                            size="small"
                            onPress={() => handleDeleteAnswerSheet(ev)}
                          />
                        </>
                      )}
                    </View>
                  </Card>
                );
              })
            )}
          </View>
        )}

        {/* EVALUATIONS TAB */}
        {activeTab === "evaluations" && (
          <View>
            <View style={styles.tabActionHeader}>
              <Text style={[styles.tabHeading, { color: colors.text }]}>
                Marked Evaluations ({evaluations.length})
              </Text>
            </View>

            {evaluations.length === 0 ? (
              <Empty
                icon="checkbox-outline"
                title="No Evaluations Completed"
                description="Upload answer sheets and run evaluation."
              />
            ) : (
              evaluations.map((ev) => (
                <TouchableOpacity
                  key={ev.id}
                  activeOpacity={0.8}
                  onPress={() => navigation.navigate("EvaluationDetail", { evaluationId: ev.id })}
                >
                  <Card style={styles.itemCard}>
                    <View style={styles.itemHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.studentItemName, { color: colors.text }]}>
                          {ev.student?.name}
                        </Text>
                        <Text style={[styles.studentItemRoll, { color: colors.textSecondary }]}>
                          Roll: {ev.student?.roll_number}
                        </Text>
                      </View>
                      <PenScore score={ev.total_marks} maxScore={ev.maximum_marks} />
                    </View>

                    <View style={[styles.itemFooter, { borderTopColor: colors.border }]}>
                      <StatusBadge status={ev.status} />
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                        <Text style={[styles.reviewLink, { color: colors.primary }]}>Review Details</Text>
                        <Ionicons name="chevron-forward" size={14} color={colors.primary} />
                      </View>
                    </View>
                  </Card>
                </TouchableOpacity>
              ))
            )}
          </View>
        )}

        {/* RESULTS TAB (Score report & Exam Finalization - Laptop Parity) */}
        {activeTab === "results" && (() => {
          const finalizedResults = results.filter((r) => r.status === "FINALIZED");
          const totalMax = finalizedResults.length > 0 && finalizedResults[0].maximum_marks ? finalizedResults[0].maximum_marks : (exam?.total_marks || 100);
          const avgScore = finalizedResults.length > 0
            ? Math.round(finalizedResults.reduce((sum, r) => sum + (r.total_marks || 0), 0) / finalizedResults.length)
            : 0;
          const highestScore = finalizedResults.length > 0
            ? Math.max(...finalizedResults.map((r) => r.total_marks || 0))
            : 0;
          const passCount = finalizedResults.filter((r) => (r.percentage || 0) >= 40).length;
          const passRate = finalizedResults.length > 0 ? Math.round((passCount / finalizedResults.length) * 100) : 0;
          const allFinalized = evaluations.length > 0 && finalizedResults.length === evaluations.length;

          return (
            <View>
              <View style={styles.tabActionHeader}>
                <View>
                  <Text style={[styles.tabHeading, { color: colors.text }]}>
                    Exam Results ({results.length})
                  </Text>
                  <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                    {finalizedResults.length} of {evaluations.length || results.length} finalized
                  </Text>
                </View>
                {exam?.status !== "FINALIZED" && (
                  <Button
                    title="Finalize Exam"
                    icon={<Ionicons name="ribbon-outline" size={15} color="#FFFFFF" />}
                    variant="gradient"
                    size="small"
                    onPress={handleFinalizeExam}
                    disabled={!allFinalized || finalizingExam}
                    loading={finalizingExam}
                  />
                )}
              </View>

              {exam?.status === "FINALIZED" && (
                <View style={[styles.alertBanner, { backgroundColor: "rgba(37, 200, 120, 0.12)", borderColor: colors.brandGreen, marginBottom: 14 }]}>
                  <Ionicons name="checkmark-done-circle" size={18} color={colors.brandGreen} />
                  <Text style={[styles.alertText, { color: colors.text }]}>
                    This exam is finalized and closed. Results and marks are permanently recorded.
                  </Text>
                </View>
              )}

              {/* Performance Stats Cards */}
              {finalizedResults.length > 0 && (
                <View style={styles.resultsStatsRow}>
                  <Card style={styles.resultsStatCard}>
                    <Text style={[styles.resultsStatValue, { color: colors.primary }]}>{avgScore} / {totalMax}</Text>
                    <Text style={[styles.resultsStatLabel, { color: colors.textSecondary }]}>Class Average</Text>
                  </Card>
                  <Card style={styles.resultsStatCard}>
                    <Text style={[styles.resultsStatValue, { color: colors.brandGreen }]}>{highestScore} / {totalMax}</Text>
                    <Text style={[styles.resultsStatLabel, { color: colors.textSecondary }]}>Highest Score</Text>
                  </Card>
                  <Card style={styles.resultsStatCard}>
                    <Text style={[styles.resultsStatValue, { color: colors.text }]}>{passRate}%</Text>
                    <Text style={[styles.resultsStatLabel, { color: colors.textSecondary }]}>Pass Rate</Text>
                  </Card>
                </View>
              )}

              {results.length === 0 ? (
                <Empty
                  icon="trophy-outline"
                  title="No Results Yet"
                  description="Results appear once students are finalized."
                />
              ) : (
                results.map((ev, index) => (
                  <TouchableOpacity
                    key={ev.id}
                    activeOpacity={0.8}
                    onPress={() => navigation.navigate(ev.status === "FINALIZED" ? "ResultDetail" : "EvaluationDetail", { evaluationId: ev.id })}
                  >
                    <Card key={ev.id} style={styles.itemCard}>
                      <View style={styles.itemHeader}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, flex: 1 }}>
                          <View style={[styles.rankCircle, { backgroundColor: index < 3 ? `${colors.primary}22` : colors.surfaceElevated }]}>
                            <Text style={[styles.rankText, { color: index < 3 ? colors.primary : colors.textSecondary }]}>
                              {index + 1}
                            </Text>
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={[styles.studentItemName, { color: colors.text }]}>
                              {ev.student?.name}
                            </Text>
                            <Text style={[styles.studentItemRoll, { color: colors.textSecondary }]}>
                              Roll No: {ev.student?.roll_number}
                            </Text>
                          </View>
                        </View>
                        {ev.status === "FINALIZED" ? (
                          <PenScore score={ev.total_marks} maxScore={ev.maximum_marks} />
                        ) : (
                          <StatusBadge status={ev.status} />
                        )}
                      </View>

                      <View style={[styles.itemFooter, { borderTopColor: colors.border }]}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                          <StatusBadge status={ev.status} />
                          {ev.percentage !== null && (
                            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.textSecondary }}>
                              {ev.percentage}%
                            </Text>
                          )}
                        </View>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                          <Text style={[styles.reviewLink, { color: colors.primary }]}>View Details</Text>
                          <Ionicons name="chevron-forward" size={14} color={colors.primary} />
                        </View>
                      </View>
                    </Card>
                  </TouchableOpacity>
                ))
              )}
              {exam.status === "FINALIZED" && (exam.files_purge_at || exam.files_purged_at) && (
                <Card style={styles.sectionCard}>
                  <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                    {exam.files_purged_at
                      ? `Uploaded files were deleted on ${new Date(exam.files_purged_at).toLocaleString()}. Student PDF reports were kept.`
                      : `Uploaded files, page images and raw AI output will be deleted on ${new Date(exam.files_purge_at!).toLocaleString()}. Student PDF reports are kept.`}
                  </Text>
                  {!exam.files_purged_at && (
                    <Button title="Delete Files Now" variant="secondary" size="small" onPress={handlePurgeFilesNow} style={{ marginTop: 8 }} />
                  )}
                </Card>
              )}
              {classOutcomes && classOutcomes.finalized_students > 0 && (
                <View style={{ marginTop: 14 }}>
                  <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 8 }}>
                    Class average across {classOutcomes.finalized_students} finalized student(s)
                  </Text>
                  <OutcomeTables outcomes={classOutcomes} />
                </View>
              )}
            </View>
          );
        })()}
      </ScrollView>

      {/* Less-used question actions */}
      <ModalDialog
        visible={!!moreTarget}
        onClose={() => setMoreTarget(null)}
        title={moreTarget ? `Question ${moreTarget.display_number}` : ""}
      >
        {moreTarget && (
          <View style={{ gap: 8 }}>
            {[
              { label: "Split", icon: "cut-outline", color: colors.text, run: () => { setSelectedQuestionForSplit(moreTarget); setSplitModalVisible(true); } },
              { label: "Merge", icon: "git-merge-outline", color: colors.text, run: () => { setSelectedQuestionForMerge(moreTarget); setMergeModalVisible(true); } },
              { label: "Flag for review", icon: "flag-outline", color: colors.warning, run: () => { setSelectedQuestionForReview(moreTarget); setReviewModalVisible(true); } },
              { label: "Delete", icon: "trash-outline", color: colors.error, run: () => handleDeleteQuestion(moreTarget) },
            ].map((item) => (
              <TouchableOpacity
                key={item.label}
                onPress={() => {
                  setMoreTarget(null);
                  item.run();
                }}
                style={[styles.studentSelectRow, { borderColor: colors.border, backgroundColor: colors.surface, justifyContent: "flex-start", gap: 10 }]}
              >
                <Ionicons name={item.icon as any} size={16} color={item.color} />
                <Text style={{ fontWeight: "600", color: item.color }}>{item.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </ModalDialog>

      {/* K level + course outcome for one question */}
      <ModalDialog
        visible={!!outcomeTarget}
        onClose={() => setOutcomeTarget(null)}
        title={outcomeTarget ? `Question ${outcomeTarget.display_number}` : ""}
        subtitle="Bloom's knowledge level and course outcome"
        footer={
          <Button
            title="Done"
            variant="gradient"
            fullWidth
            onPress={async () => {
              if (outcomeTarget && coInput.trim() !== (outcomeTarget.course_outcome || "")) {
                await saveOutcome(outcomeTarget, { course_outcome: coInput.trim() || null });
              }
              setOutcomeTarget(null);
            }}
          />
        }
      >
        {outcomeTarget && (
          <View style={{ gap: 12 }}>
            {outcomeTarget.k_level_source === "SUGGESTED" && (
              <Text style={{ fontSize: 12, color: colors.warning }}>
                {outcomeTarget.k_level} was suggested from the question's wording. Tap a level to confirm or change it.
              </Text>
            )}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {Object.entries(K_LEVEL_NAMES).map(([k, name]) => {
                const on = outcomeTarget.k_level === k;
                return (
                  <TouchableOpacity
                    key={k}
                    onPress={() => saveOutcome(outcomeTarget, { k_level: k })}
                    style={[styles.studentSelectRow, { borderColor: on ? colors.primary : colors.border, backgroundColor: on ? "rgba(7, 159, 189, 0.15)" : colors.surface, width: "47%" }]}
                  >
                    <Text style={{ fontWeight: "700", color: on ? colors.primary : colors.text }}>{k}</Text>
                    <Text style={{ fontSize: 12, color: colors.textSecondary }}>{name}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <Input
              label="Course Outcome"
              placeholder="e.g. CO1"
              value={coInput}
              onChangeText={setCoInput}
              autoCapitalize="characters"
            />
          </View>
        )}
      </ModalDialog>

      {/* Pick the student for an answer sheet that could not be matched automatically */}
      <ModalDialog
        visible={!!assignTarget}
        onClose={() => setAssignTarget(null)}
        title="Pick the Student"
        subtitle={assignTarget?.original_filename}
      >
        {assignTarget && (() => {
          const takenIds = new Set(evaluations.map((e) => e.student.id));
          const candIds = new Set(assignTarget.candidates.map((c) => c.id));
          const rows = [
            ...assignTarget.candidates.filter((c) => !takenIds.has(c.id)).map((c) => ({ ...c, likely: true })),
            ...students.filter((st) => !candIds.has(st.id) && !takenIds.has(st.id)).map((st) => ({ ...st, likely: false })),
          ];
          return (
            <ScrollView style={{ maxHeight: 360 }}>
              {rows.length === 0 && (
                <Text style={{ fontSize: 13, color: colors.textSecondary }}>Every student in this class already has a sheet.</Text>
              )}
              {rows.map((st) => (
                <TouchableOpacity
                  key={st.id}
                  disabled={actionLoading}
                  onPress={() => handleAssignSheet(assignTarget, st.id)}
                  style={[styles.studentSelectRow, { backgroundColor: colors.surface, borderColor: st.likely ? colors.primary : colors.border }]}
                >
                  <Text style={{ fontWeight: "600", color: colors.text, flex: 1 }}>
                    {st.roll_number} — {st.name}
                    {st.registration_number ? ` (${st.registration_number})` : ""}
                  </Text>
                  {st.likely && <Badge label="Likely" variant="teal" size="small" />}
                </TouchableOpacity>
              ))}
            </ScrollView>
          );
        })()}
      </ModalDialog>

      {/* Upload Student Sheet Modal with multi-page compilation */}
      <ModalDialog
        visible={uploadSheetModal}
        onClose={() => {
          if (!uploadingSheet && !compilingPages) {
            setUploadSheetModal(false);
          }
        }}
        title="Upload Student Answer Sheet"
        subtitle="One student's sheet: single or multi-page"
        footer={
          <View style={{ gap: 6, width: "100%" }}>
            <Button
              title={
                compilingPages
                  ? "Compiling Document..."
                  : uploadingSheet
                  ? "Submitting Answer Sheet..."
                  : "Submit Answer Sheet"
              }
              icon={<Ionicons name="cloud-upload" size={18} color="#FFFFFF" />}
              onPress={handleSubmitStudentSheet}
              variant="gradient"
              loading={uploadingSheet || compilingPages}
              disabled={compilingPages || uploadingSheet || attachedPages.length === 0}
              fullWidth
            />
            {attachedPages.length === 0 && (
              <Text
                style={{
                  fontSize: 11,
                  textAlign: "center",
                  color: colors.textSecondary,
                  marginTop: 2,
                }}
              >
                Scan or attach answer sheet pages to submit
              </Text>
            )}
          </View>
        }
      >
        <View
          style={{ flexDirection: "row", gap: 8, padding: 10, borderRadius: 10, marginBottom: 12, backgroundColor: colors.surfaceElevated }}
        >
          <Ionicons name="person-circle-outline" size={18} color={colors.primary} />
          <Text style={{ flex: 1, fontSize: 12, color: colors.textSecondary }}>
            The student is matched from the details written on the sheet.
          </Text>
        </View>

        <Text style={[styles.modalLabel, { color: colors.textSecondary }]}>
          Answer Sheet Pages ({attachedPages.length}) *
        </Text>

        {compilingPages ? (
          <View style={[styles.compilingBox, { borderColor: colors.primary }]}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={[styles.compilingText, { color: colors.primary }]}>
              Compiling {attachedPages.length} pages into a multi-page PDF document...
            </Text>
          </View>
        ) : attachedPages.length > 0 ? (
          <View style={{ marginBottom: 12, gap: 8 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 95 }}>
              <View style={{ flexDirection: "row", gap: 8, paddingVertical: 4 }}>
                {attachedPages.map((page, idx) => (
                  <View
                    key={idx}
                    style={[
                      styles.attachedPageCard,
                      { borderColor: colors.border, backgroundColor: colors.surfaceElevated },
                    ]}
                  >
                    <View style={styles.attachedPageHeader}>
                      <Ionicons
                        name={page.mimeType?.includes("pdf") ? "document-text" : "image-outline"}
                        size={16}
                        color={colors.primary}
                      />
                      <TouchableOpacity
                        onPress={() => setAttachedPages((prev) => prev.filter((_, i) => i !== idx))}
                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                      >
                        <Ionicons name="close-circle" size={16} color={colors.error} />
                      </TouchableOpacity>
                    </View>
                    <Text style={[styles.attachedPageTitle, { color: colors.text }]}>Page {idx + 1}</Text>
                    <Text style={[styles.attachedPageSub, { color: colors.textSecondary }]} numberOfLines={1}>
                      {page.name || "scanned_page.jpg"}
                    </Text>
                  </View>
                ))}
              </View>
            </ScrollView>

            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button
                title="+ Scan Page"
                icon={<Ionicons name="camera-outline" size={15} color="#FFFFFF" />}
                variant="gradient"
                size="small"
                onPress={() => {
                  setUploadSheetModal(false);
                  setScannerTarget("student_sheet");
                  setCameraScannerVisible(true);
                }}
                style={{ flex: 1 }}
              />
              <Button
                title="+ Add Photo/File"
                icon={<Ionicons name="add" size={15} color={colors.text} />}
                variant="secondary"
                size="small"
                onPress={handlePickStudentFile}
                style={{ flex: 1 }}
              />
            </View>
            <Text style={{ fontSize: 11, color: colors.brandGreen, textAlign: "center" }}>
              {attachedPages.length} page(s) attached
            </Text>
          </View>
        ) : (
          <View style={{ gap: 10, marginBottom: 8 }}>
            <Button
              title="Scan with Camera (Multi-Page)"
              icon={<Ionicons name="camera-outline" size={18} color="#FFFFFF" />}
              variant="gradient"
              size="medium"
              onPress={() => {
                setUploadSheetModal(false);
                setScannerTarget("student_sheet");
                setCameraScannerVisible(true);
              }}
              fullWidth
            />
            <Button
              title="Upload File(s) (PDF or Photos)"
              icon={<Ionicons name="cloud-upload-outline" size={18} color={colors.text} />}
              variant="secondary"
              size="medium"
              onPress={handlePickStudentFile}
              fullWidth
            />
            <Text style={{ fontSize: 11, color: colors.textSecondary, textAlign: "center" }}>
              Pages are combined in order into one file.
            </Text>
          </View>
        )}
      </ModalDialog>

      {/* Question Management Modals */}
      <EditQuestionModal
        visible={editModalVisible}
        question={selectedQuestionForEdit}
        examId={examId}
        onClose={() => setEditModalVisible(false)}
        onSuccess={() => {
          loadTabData("questions");
          fetchExamDetail();
        }}
      />

      <SplitQuestionModal
        visible={splitModalVisible}
        question={selectedQuestionForSplit}
        onClose={() => setSplitModalVisible(false)}
        onSuccess={() => {
          loadTabData("questions");
          fetchExamDetail();
        }}
      />

      <MergeQuestionModal
        visible={mergeModalVisible}
        question={selectedQuestionForMerge}
        allQuestions={questionsData?.questions || []}
        onClose={() => setMergeModalVisible(false)}
        onSuccess={() => {
          loadTabData("questions");
          fetchExamDetail();
        }}
      />

      <ReviewQuestionModal
        visible={reviewModalVisible}
        question={selectedQuestionForReview}
        onClose={() => setReviewModalVisible(false)}
        onSuccess={() => {
          loadTabData("questions");
          fetchExamDetail();
        }}
      />

      {/* Answer Key Management Modals */}
      <EditAnswerKeyModal
        visible={editKeyModalVisible}
        row={selectedKeyForRow}
        questions={keysData?.questions || []}
        onClose={() => setEditKeyModalVisible(false)}
        onSuccess={handleKeyUpdateSuccess}
      />

      <ResolveAnswerKeyModal
        visible={resolveKeyModalVisible}
        row={selectedKeyForRow}
        questions={keysData?.questions || []}
        onClose={() => setResolveKeyModalVisible(false)}
        onSuccess={handleKeyUpdateSuccess}
      />

      <ValidationSummaryModal
        visible={validationModalVisible}
        validation={validationResult}
        onClose={() => setValidationModalVisible(false)}
        onReviewIssue={handleReviewValidationIssue}
        onProceedToSubmissions={() => {
          setActiveTab("submissions");
          scrollToActiveTab("submissions");
          loadTabData("submissions");
        }}
      />

      {/* Multi-Page Document Scanner Camera Modal */}
      <DocumentScannerModal
        visible={cameraScannerVisible}
        onClose={() => setCameraScannerVisible(false)}
        onComplete={
          scannerTarget === "student_sheet"
            ? handleScannedStudentSheetComplete
            : scannerTarget === "answer_key"
            ? handleScannedAnswerKeyComplete
            : handleScannedPaperComplete
        }
        students={scannerTarget === "student_sheet" ? students : undefined}
        currentStudentId={scannerTarget === "student_sheet" ? selectedStudentId : undefined}
        onScanNextStudent={scannerTarget === "student_sheet" ? handleScanNextStudentBatch : undefined}
        title={
          scannerTarget === "student_sheet"
            ? (selectedStudent ? `Scan Sheet: ${selectedStudent.name}` : "Scan Student Answer Sheet")
            : scannerTarget === "answer_key"
            ? "Scan Official Answer Key"
            : "Scan Question Paper"
        }
        docTitlePrefix={
          scannerTarget === "student_sheet"
            ? (selectedStudent ? `${selectedStudent.name.replace(/[^a-zA-Z0-9]/g, "")}_Sheet` : "AnswerSheet")
            : scannerTarget === "answer_key"
            ? "AnswerKey"
            : "QP"
        }
        examTitle={exam.name}
      />

      {/* Total Marks Verification & Popup Modal */}
      <ModalDialog
        visible={totalMarksModalVisible}
        onClose={() => setTotalMarksModalVisible(false)}
        title="Verify Exam Total Marks"
        subtitle={`Detected from Question Paper: ${questionsData?.sum_of_marks ?? 0} Marks (${questionsData?.questions?.length ?? 0} Questions)`}
      >
        <View style={{ marginBottom: 14 }}>
          <View
            style={{
              padding: 12,
              borderRadius: 10,
              backgroundColor: "rgba(7, 159, 189, 0.08)",
              borderWidth: 1,
              borderColor: colors.border,
              marginBottom: 10,
            }}
          >
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 6 }}>
              <Text style={{ fontSize: 13, color: colors.textSecondary }}>Paper Detected Total:</Text>
              <Text style={{ fontSize: 16, fontWeight: "800", color: colors.primary }}>
                {questionsData?.sum_of_marks ?? 0} Marks
              </Text>
            </View>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ fontSize: 13, color: colors.textSecondary }}>Current Declared Total:</Text>
              <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>
                {exam?.total_marks ?? 0} Marks
              </Text>
            </View>
          </View>

          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text, marginBottom: 10, lineHeight: 18 }}>
            Is {questionsData?.sum_of_marks ?? 0} marks the correct total marks for this examination?
          </Text>

          <Input
            label="Adjust Total Marks (if students have question choices)"
            placeholder="e.g. 100"
            value={customTotalMarks}
            onChangeText={setCustomTotalMarks}
            keyboardType="numeric"
          />
        </View>

        <View style={{ gap: 8 }}>
          {questionsData?.sum_of_marks !== undefined && questionsData.sum_of_marks > 0 && (
            <Button
              title={`Yes, Set to ${questionsData.sum_of_marks} Marks (From Paper)`}
              icon={<Ionicons name="checkmark-circle" size={16} color="#FFFFFF" />}
              variant="gradient"
              loading={actionLoading}
              onPress={() => handleUpdateTotalMarks(questionsData.sum_of_marks)}
              fullWidth
            />
          )}

          {customTotalMarks !== "" && parseFloat(customTotalMarks) !== questionsData?.sum_of_marks && (
            <Button
              title={`Apply Custom (${customTotalMarks} Marks)`}
              icon={<Ionicons name="save-outline" size={16} color="#FFFFFF" />}
              variant="primary"
              loading={actionLoading}
              onPress={() => {
                const num = parseFloat(customTotalMarks);
                if (isNaN(num) || num <= 0) {
                  Alert.alert("Validation", "Please enter a valid positive number for total marks.");
                  return;
                }
                handleUpdateTotalMarks(num);
              }}
              fullWidth
            />
          )}

          <Button
            title={`Keep Current (${exam?.total_marks} Marks)`}
            variant="secondary"
            onPress={() => setTotalMarksModalVisible(false)}
            fullWidth
          />
        </View>
      </ModalDialog>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  ocrProgressBox: {
    marginTop: 12,
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
  },
  ocrProgressCard: {
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
  },
  ocrProgressHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  ocrProgressTitle: {
    fontSize: 14,
    fontWeight: "700",
    flex: 1,
    marginLeft: 8,
  },
  ocrStageText: {
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 8,
  },
  progressBarTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    overflow: "hidden",
    marginBottom: 6,
  },
  progressBarFill: {
    height: "100%",
    borderRadius: 3,
  },
  ocrHintText: {
    fontSize: 12,
  },
  summaryBar: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 12,
  },
  summaryStatsRow: {
    marginBottom: 8,
  },
  summaryStatsText: {
    fontSize: 13,
    lineHeight: 18,
  },
  summaryActionsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  alertBanner: {
    flexDirection: "row",
    alignItems: "center",
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    gap: 8,
  },
  alertText: {
    fontSize: 13,
    flex: 1,
    lineHeight: 17,
  },
  questionCard: {
    marginBottom: 12,
    padding: 14,
  },
  qCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    flexWrap: "wrap",
    gap: 6,
  },
  qNumberText: {
    fontSize: 16,
    fontWeight: "700",
  },
  reviewReasonBanner: {
    flexDirection: "row",
    alignItems: "center",
    padding: 8,
    borderRadius: 6,
    marginBottom: 8,
    gap: 6,
  },
  reviewReasonText: {
    fontSize: 12,
    fontWeight: "600",
    flex: 1,
  },
  questionBodyText: {
    fontSize: 14,
    lineHeight: 21,
    marginBottom: 10,
  },
  cropBox: {
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
  },
  cropBoxHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 6,
  },
  cropBoxLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  cropImage: {
    minHeight: 120,
    maxHeight: 220,
    width: "100%",
    borderRadius: 6,
  },
  qActionsBar: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 6,
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  actionPill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  actionPillSec: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    gap: 4,
  },
  actionPillGhost: {
    padding: 6,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
  },
  actionPillText: {
    fontSize: 12,
    fontWeight: "600",
  },
  actionPillTextWhite: {
    fontSize: 12,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  headerBanner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerInfo: {
    flex: 1,
    marginRight: 8,
  },
  examTitle: {
    fontSize: 18,
    fontWeight: "800",
  },
  examSub: {
    fontSize: 12,
    marginTop: 2,
  },
  verifyLinkPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    borderWidth: 1,
  },
  verifyLinkText: {
    fontSize: 10,
    fontWeight: "700",
  },
  tabBarWrapper: {
    borderBottomWidth: 1,
    flexGrow: 0,
    flexShrink: 0,
  },
  tabScrollView: {
    flexGrow: 0,
  },
  tabBar: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    flexDirection: "row",
    alignItems: "center",
  },
  tabItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderBottomWidth: 2.5,
    marginHorizontal: 3,
    borderRadius: 8,
    gap: 6,
    flexShrink: 0,
  },
  tabText: {
    fontSize: 13,
    letterSpacing: 0.2,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionCard: {
    padding: 16,
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 12,
  },
  grid2: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  gridItem: {
    width: "48%",
  },
  gridLabel: {
    fontSize: 11,
    fontWeight: "500",
  },
  gridValue: {
    fontSize: 13,
    fontWeight: "700",
    marginTop: 2,
  },
  instructionsBox: {
    marginTop: 14,
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  instructionsLabel: {
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 4,
  },
  instructionsText: {
    fontSize: 13,
    lineHeight: 18,
  },
  workflowRow: {
    gap: 12,
  },
  wfStep: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  wfText: {
    fontSize: 14,
    fontWeight: "600",
  },
  docInfoRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 14,
  },
  docName: {
    fontSize: 15,
    fontWeight: "700",
  },
  docMeta: {
    fontSize: 11,
    marginTop: 2,
  },
  btnRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 10,
  },
  tabActionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
    flexWrap: "wrap",
    gap: 8,
  },
  tabHeading: {
    fontSize: 16,
    fontWeight: "700",
  },
  warningText: {
    fontSize: 12,
    marginTop: 2,
    fontWeight: "500",
  },
  itemCard: {
    padding: 14,
    marginBottom: 10,
  },
  itemHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  qMarksText: {
    fontSize: 13,
    fontWeight: "700",
  },
  qText: {
    fontSize: 14,
    marginTop: 8,
    lineHeight: 20,
  },
  criteriaBox: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(255,255,255,0.1)",
  },
  criteriaTitle: {
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 4,
  },
  criteriaItem: {
    fontSize: 12,
    lineHeight: 16,
  },
  studentItemName: {
    fontSize: 15,
    fontWeight: "700",
  },
  studentItemRoll: {
    fontSize: 12,
    marginTop: 2,
  },
  itemFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
  },
  reviewLink: {
    fontSize: 12,
    fontWeight: "600",
  },
  modalLabel: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
  },
  studentSelectRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 6,
  },
  filePickerBox: {
    padding: 16,
    borderRadius: 10,
    borderWidth: 1.5,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  filePickerText: {
    fontSize: 13,
    fontWeight: "600",
    textAlign: "center",
  },
  scannerPromptCard: {
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  scannerPromptIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  scannerPromptTitle: {
    fontSize: 18,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 8,
  },
  scannerPromptDesc: {
    fontSize: 13,
    textAlign: "center",
    lineHeight: 18,
    marginBottom: 20,
    paddingHorizontal: 8,
  },
  selectedFileCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 10,
  },
  selectedFileIconBox: {
    width: 38,
    height: 38,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  selectedFileName: {
    fontSize: 13,
    fontWeight: "700",
  },
  selectedFileMeta: {
    fontSize: 11,
    fontWeight: "600",
    marginTop: 2,
  },
  cardActionsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
  },
  verifiedTag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: "rgba(37, 200, 120, 0.12)",
  },
  verifiedTagText: {
    fontSize: 12,
    fontWeight: "600",
  },
  verifyAllBannerCard: {
    padding: 16,
    borderRadius: 14,
    borderWidth: 1,
  },
  verifyAllBannerContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  verifyAllIconBox: {
    width: 44,
    height: 44,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  verifyAllBannerTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  verifyAllBannerDesc: {
    fontSize: 12,
    lineHeight: 17,
    marginTop: 2,
  },
  finalizedReadonlyBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    marginBottom: 4,
  },
  finalizedReadonlyText: {
    fontSize: 12,
    fontWeight: "700",
  },
  submissionMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 12,
    marginTop: 8,
    marginBottom: 6,
  },
  submissionMetaItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  submissionMetaText: {
    fontSize: 12,
    fontWeight: "500",
  },
  unresolvedBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: "rgba(245, 158, 11, 0.15)",
  },
  unresolvedBadgeText: {
    fontSize: 11,
    fontWeight: "700",
    color: "#F59E0B",
  },
  docBusyBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    marginVertical: 6,
  },
  docBusyBannerText: {
    fontSize: 12,
    fontWeight: "600",
    flex: 1,
  },
  studentModeTabs: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
  },
  studentModeTab: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(150, 150, 150, 0.2)",
  },
  studentModeTabText: {
    fontSize: 12,
    fontWeight: "600",
  },
  compilingBox: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 16,
    borderRadius: 10,
    borderWidth: 1,
    borderStyle: "dashed",
    marginVertical: 10,
  },
  compilingText: {
    fontSize: 13,
    fontWeight: "600",
  },
  attachedPageCard: {
    width: 110,
    padding: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  attachedPageHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  attachedPageTitle: {
    fontSize: 12,
    fontWeight: "700",
  },
  attachedPageSub: {
    fontSize: 10,
    marginTop: 2,
  },
  unsubmittedPill: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
  },
  unsubmittedText: {
    fontSize: 11,
    fontWeight: "600",
  },
  resultsStatsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
  },
  resultsStatCard: {
    flex: 1,
    padding: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  resultsStatValue: {
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 2,
  },
  resultsStatLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  rankCircle: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  rankText: {
    fontSize: 12,
    fontWeight: "800",
  },
  preconditionBannerCard: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 12,
  },
  preconditionBannerTitle: {
    fontSize: 13,
    fontWeight: "700",
  },
  preconditionBannerText: {
    fontSize: 11,
    lineHeight: 15,
    marginTop: 2,
  },
  totalMarksCard: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1.5,
    marginTop: 12,
  },
  totalMarksHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  totalMarksIconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  totalMarksCardTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  totalMarksCardSub: {
    fontSize: 12,
    lineHeight: 16,
    marginTop: 2,
  },
  totalMarksActionRow: {
    marginTop: 10,
    alignItems: "flex-end",
  },
});
