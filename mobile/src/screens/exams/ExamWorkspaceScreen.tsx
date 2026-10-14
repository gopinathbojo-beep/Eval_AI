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
} from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { StatusBadge, Badge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Input } from "../../components/Input";
import { ModalDialog } from "../../components/ModalDialog";
import { DocumentScannerModal } from "../../components/DocumentScannerModal";
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
            size: A4 portrait;
            margin: 0;
          }
          html, body {
            margin: 0;
            padding: 0;
            background-color: #ffffff;
          }
          .page {
            page-break-after: always;
            break-after: page;
            width: 100%;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            box-sizing: border-box;
          }
          .page:last-child {
            page-break-after: auto;
            break-after: auto;
          }
          img {
            max-width: 100%;
            max-height: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            display: block;
            margin: auto;
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

type TabType = "overview" | "paper" | "questions" | "answerKey" | "submissions" | "evaluations";

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
  const [students, setStudents] = useState<Student[]>([]);

  // Action states
  const [actionLoading, setActionLoading] = useState(false);

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
  const [uploadingSheet, setUploadingSheet] = useState(false);
  const [studentMode, setStudentMode] = useState<"existing" | "new">("existing");
  const [newStudentName, setNewStudentName] = useState("");
  const [newStudentRoll, setNewStudentRoll] = useState("");
  const [compilingPages, setCompilingPages] = useState(false);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [pickedFile, setPickedFile] = useState<any>(null);
  const [cameraScannerVisible, setCameraScannerVisible] = useState(false);
  const [scannerTarget, setScannerTarget] = useState<"question_paper" | "answer_key" | "student_sheet">("question_paper");

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
      if (tab === "questions") {
        const q = await api<QuestionsResponse>(`/exams/${examId}/questions`);
        setQuestionsData(q);
      } else if (tab === "answerKey") {
        const k = await api<KeysResponse>(`/exams/${examId}/answer-keys`);
        setKeysData(k);
      } else if (tab === "submissions") {
        const sheets = await api<Evaluation[]>(`/exams/${examId}/answer-sheets`);
        setEvaluations(sheets);
      } else if (tab === "evaluations") {
        const evs = await api<Evaluation[]>(`/exams/${examId}/results`);
        setEvaluations(evs);
      }
    } catch (err: any) {
      console.warn("Tab load error:", err);
    }
  }, [examId]);

  useEffect(() => {
    fetchExamDetail();
  }, [fetchExamDetail]);

  useEffect(() => {
    loadTabData(activeTab);
    scrollToActiveTab(activeTab);
  }, [activeTab, loadTabData, scrollToActiveTab]);

  // Active polling while question paper, answer key, or any student sheet is running OCR or extraction
  const BUSY_DOC = ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"];
  const isPaperBusy = !!(exam?.question_paper && BUSY_DOC.includes(exam.question_paper.status));
  const isKeyBusy = !!(exam?.answer_key_document && BUSY_DOC.includes(exam.answer_key_document.status));
  const hasBusySheet = evaluations.some(
    (e) => (e.document && BUSY_DOC.includes(e.document.status)) || e.run_status === "RUNNING"
  );

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
      } else if (activeTab === "submissions") {
        loadTabData("submissions");
      } else if (activeTab === "evaluations") {
        loadTabData("evaluations");
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
      Alert.alert(
        "Bulk Accept Complete",
        `${res.accepted} complete question(s) verified and accepted.`
      );
      await Promise.all([loadTabData("questions"), fetchExamDetail()]);
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

      Alert.alert("Success", "Question paper uploaded! OCR extraction started.");
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
        copyToCacheDirectory: false,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) return;

      const file = result.assets[0];
      await executeQuestionPaperUpload({
        uri: file.uri,
        name: file.name,
        mimeType: file.mimeType,
      });
    } catch (err: any) {
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

      Alert.alert("Success", "Answer key uploaded!");
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
        copyToCacheDirectory: false,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) return;

      const file = result.assets[0];
      await executeAnswerKeyUpload({
        uri: file.uri,
        name: file.name,
        mimeType: file.mimeType,
      });
    } catch (err: any) {
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

      // Show summary containing total processed, verified, needs review, and failed entries
      setValidationResult({
        valid: res.valid,
        summary: res.summary,
        blocking_issues: res.blocking_issues || [],
        issues: res.issues || [],
      });
      setValidationModalVisible(true);
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
    const unapprovedKeys = keysData.keys.filter((k) => k.verification_status !== "VERIFIED");

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
    if (unapprovedKeys.length > 0) {
      blockers.push(`${unapprovedKeys.length} answer(s) pending individual teacher verification.`);
    }

    if (blockers.length > 0) {
      Alert.alert(
        "Verification Incomplete",
        `All individual answers must be resolved and verified before final verification:\n\n• ${blockers.join(
          "\n• "
        )}\n\nPlease resolve any issues and tap "Verify Answer" on each answer card.`,
        [{ text: "OK" }]
      );
      return;
    }

    try {
      setActionLoading(true);
      const res = await api<{ verified: number }>(`/exams/${examId}/answer-keys/verify`, {
        method: "POST",
      });
      Alert.alert(
        "Answer Key Verified",
        `All ${res.verified} official answers verified and locked! Exam is now ready for evaluation.`
      );
      await Promise.all([loadTabData("answerKey"), fetchExamDetail()]);
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
      Alert.alert("Verified", "All canonical questions have been verified!");
      fetchExamDetail();
      loadTabData("questions");
    } catch (err: any) {
      Alert.alert("Error", err.message || "Verification failed");
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
        copyToCacheDirectory: false,
      });
      if (res.canceled || !res.assets || res.assets.length === 0) return;

      if (res.assets.length === 1) {
        setPickedFile(res.assets[0]);
      } else {
        // Multiple pages picked: compile into a clean multi-page PDF!
        setCompilingPages(true);
        try {
          const compiled = await compileAssetsToMultiPagePdf(
            res.assets,
            `Student_AnswerSheet_${Date.now()}`
          );
          setPickedFile(compiled);
        } catch (compileErr: any) {
          Alert.alert("Compilation Failed", "Failed to compile multiple pages into a document. Please try again.");
        } finally {
          setCompilingPages(false);
        }
      }
    } catch (err: any) {
      Alert.alert("File Selection Failed", err.message || "Failed to select answer sheet.");
    }
  };

  const handleScannedStudentSheetComplete = async (file: { uri: string; name: string; type: string }) => {
    setPickedFile({
      uri: file.uri,
      name: file.name,
      mimeType: file.type || "application/pdf",
    });
    setCameraScannerVisible(false);
    setUploadSheetModal(true);
  };

  const handleSubmitStudentSheet = async () => {
    if (uploadingSheet) return;

    const isNew = studentMode === "new";
    if (isNew) {
      if (!newStudentName.trim() || !newStudentRoll.trim()) {
        Alert.alert("Student Details Required", "Please enter both the student's name and roll number.");
        return;
      }
    } else {
      if (!selectedStudentId) {
        Alert.alert("Student Required", "Please select an enrolled student.");
        return;
      }
    }

    if (!pickedFile) {
      Alert.alert("Answer Sheet Required", "Please select or scan an answer sheet document.");
      return;
    }

    try {
      setUploadingSheet(true);
      const params: Record<string, string> = isNew
        ? { student_name: newStudentName.trim(), roll_number: newStudentRoll.trim() }
        : { student_id: selectedStudentId };

      await uploadFileNative(`/exams/${examId}/answer-sheets`, pickedFile.uri, {
        fileName: pickedFile.name,
        mimeType: pickedFile.mimeType || "application/pdf",
        params,
      });

      setUploadSheetModal(false);
      setPickedFile(null);
      setNewStudentName("");
      setNewStudentRoll("");
      Alert.alert("Success", "Answer sheet submitted successfully! OCR processing has started.");
      fetchExamDetail();
      loadTabData("submissions");
    } catch (err: any) {
      Alert.alert("Submission Failed", err.message || "Failed to submit answer sheet. Please try again.");
    } finally {
      setUploadingSheet(false);
    }
  };

  // Run AI Evaluation with precise status handling
  const handleRunEvaluation = async (evaluationId: string) => {
    const targetEv = evaluations.find((e) => e.id === evaluationId);
    if (targetEv?.status === "FINALIZED") {
      Alert.alert(
        "Evaluation Finalized (Read-Only)",
        `The evaluation for ${targetEv.student?.name || "this student"} is finalized and approved. Finalized evaluations are permanently locked and cannot be re-evaluated or modified.`
      );
      return;
    }

    if (targetEv?.document && BUSY_DOC.includes(targetEv.document.status)) {
      Alert.alert(
        "Processing in Progress",
        `The student's answer sheet is currently ${targetEv.document.stage || "being processed by OCR"}. Please wait until reading finishes.`
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
      } else if (err.code === "OCR_NOT_FINISHED") {
        Alert.alert(
          "Processing in Progress",
          "The answer sheet is still being read and processed by OCR. Please wait a few seconds and try again."
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
    { key: "paper", label: "Question Paper", icon: "document-text-outline" },
    { key: "questions", label: "Questions", icon: "list-outline" },
    { key: "answerKey", label: "Answer Key", icon: "key-outline" },
    { key: "submissions", label: "Submissions", icon: "cloud-upload-outline" },
    { key: "evaluations", label: "Evaluations", icon: "checkbox-outline" },
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
              <Text style={[styles.cardTitle, { color: colors.text }]}>Workflow Progress</Text>
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
                    Use the document scanner camera to automatically detect paper edges, crop out background clutter, straighten, and scan multiple pages in sequence.
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
                        onPress={handleVerifyQuestions}
                      />
                    )}
                  </View>
                )}
              </View>

              {/* Marks Warning Banner */}
              {questionsData?.marks_warning && (
                <View style={[styles.alertBanner, { backgroundColor: "rgba(234, 179, 8, 0.12)", borderColor: colors.warning }]}>
                  <Ionicons name="warning-outline" size={18} color={colors.warning} />
                  <Text style={[styles.alertText, { color: colors.text }]}>
                    {questionsData.marks_warning} This is only a warning; some papers offer student choice.
                  </Text>
                </View>
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
                    description="Upload the question paper in the 'Paper' tab, or manually add questions."
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
                          {q.ocr_confidence !== null && (
                            <Badge
                              label={`conf. ${Math.round(q.ocr_confidence * 100)}%`}
                              variant="muted"
                            />
                          )}
                          <StatusBadge status={q.verification_status} />
                        </View>
                      </View>

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
                              What the model read (approximate crop):
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
                            onPress={() => {
                              setSelectedQuestionForSplit(q);
                              setSplitModalVisible(true);
                            }}
                            style={[styles.actionPillSec, { borderColor: colors.border }]}
                          >
                            <Ionicons name="cut-outline" size={14} color={colors.text} />
                            <Text style={[styles.actionPillText, { color: colors.text }]}>Split</Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            onPress={() => {
                              setSelectedQuestionForMerge(q);
                              setMergeModalVisible(true);
                            }}
                            style={[styles.actionPillSec, { borderColor: colors.border }]}
                          >
                            <Ionicons name="git-merge-outline" size={14} color={colors.text} />
                            <Text style={[styles.actionPillText, { color: colors.text }]}>Merge</Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            onPress={() => {
                              setSelectedQuestionForReview(q);
                              setReviewModalVisible(true);
                            }}
                            style={[styles.actionPillSec, { borderColor: colors.border }]}
                          >
                            <Ionicons name="flag-outline" size={14} color={colors.warning} />
                            <Text style={[styles.actionPillText, { color: colors.warning }]}>Review</Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            onPress={() => handleDeleteQuestion(q)}
                            style={styles.actionPillGhost}
                          >
                            <Ionicons name="trash-outline" size={14} color={colors.error} />
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
                  Generating standard solutions, criteria, and marking schemes for all verified questions. Please allow 20–40 seconds.
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
                  Scan official answer sheets with the camera across multiple pages with auto edge detection, upload an existing PDF / Image file, or generate solutions automatically with Ollama AI.
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
              </View>
            </View>

            {evaluations.length === 0 ? (
              <Card style={styles.scannerPromptCard}>
                <View style={[styles.scannerPromptIcon, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
                  <Ionicons name="scan-outline" size={44} color={colors.primary} />
                </View>
                <Text style={[styles.scannerPromptTitle, { color: colors.text }]}>
                  No Answer Sheets Uploaded
                </Text>
                <Text style={[styles.scannerPromptDesc, { color: colors.textSecondary }]}>
                  Scan multiple handwritten pages using the camera with edge detection or upload digital answer sheets (PDF / Image) to begin evaluation.
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
                          {ev.document?.stage || "Reading student paper with OCR..."}
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
                            style={{ flex: 1 }}
                          />
                          <Button
                            icon={<Ionicons name="trash-outline" size={15} color={colors.danger} />}
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
                            icon={<Ionicons name="trash-outline" size={15} color={colors.danger} />}
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
                description="Upload student answer sheets and run evaluation to see scores and grading breakdown."
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
      </ScrollView>

      {/* Upload Student Sheet Modal with multi-page compilation and on-the-fly student creation */}
      <ModalDialog
        visible={uploadSheetModal}
        onClose={() => {
          if (!uploadingSheet && !compilingPages) {
            setUploadSheetModal(false);
          }
        }}
        title="Upload Student Answer Sheet"
        subtitle="Upload single or multi-page handwritten sheets"
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
              disabled={
                compilingPages ||
                uploadingSheet ||
                !pickedFile ||
                (studentMode === "new"
                  ? !newStudentName.trim() || !newStudentRoll.trim()
                  : !selectedStudentId)
              }
              fullWidth
            />
            {(!pickedFile ||
              (studentMode === "new" ? !newStudentName.trim() || !newStudentRoll.trim() : !selectedStudentId)) && (
              <Text
                style={{
                  fontSize: 11,
                  textAlign: "center",
                  color: colors.textSecondary,
                  marginTop: 2,
                }}
              >
                {!pickedFile
                  ? "Scan or attach answer sheet pages to submit"
                  : studentMode === "new"
                  ? "Enter the student name and roll number to continue"
                  : "Select an enrolled student to enable submission"}
              </Text>
            )}
          </View>
        }
      >
        {/* Student Mode Selector Toggle */}
        <View style={styles.studentModeTabs}>
          <TouchableOpacity
            style={[
              styles.studentModeTab,
              studentMode === "existing" && {
                backgroundColor: colors.surfaceElevated,
                borderColor: colors.primary,
              },
            ]}
            onPress={() => setStudentMode("existing")}
          >
            <Ionicons
              name="people-outline"
              size={14}
              color={studentMode === "existing" ? colors.primary : colors.textSecondary}
            />
            <Text
              style={[
                styles.studentModeTabText,
                { color: studentMode === "existing" ? colors.primary : colors.textSecondary },
              ]}
            >
              Enrolled Student
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.studentModeTab,
              studentMode === "new" && {
                backgroundColor: colors.surfaceElevated,
                borderColor: colors.primary,
              },
            ]}
            onPress={() => setStudentMode("new")}
          >
            <Ionicons
              name="person-add-outline"
              size={14}
              color={studentMode === "new" ? colors.primary : colors.textSecondary}
            />
            <Text
              style={[
                styles.studentModeTabText,
                { color: studentMode === "new" ? colors.primary : colors.textSecondary },
              ]}
            >
              New Student
            </Text>
          </TouchableOpacity>
        </View>

        {studentMode === "existing" ? (
          <>
            <Text style={[styles.modalLabel, { color: colors.textSecondary }]}>Select Student *</Text>
            <ScrollView style={{ maxHeight: 130, marginBottom: 12 }}>
              {students.map((st) => {
                const isSelected = selectedStudentId === st.id;
                return (
                  <TouchableOpacity
                    key={st.id}
                    onPress={() => setSelectedStudentId(st.id)}
                    style={[
                      styles.studentSelectRow,
                      {
                        backgroundColor: isSelected ? "rgba(7, 159, 189, 0.15)" : colors.surface,
                        borderColor: isSelected ? colors.primary : colors.border,
                      },
                    ]}
                  >
                    <Text style={[{ fontWeight: "600" }, { color: isSelected ? colors.primary : colors.text }]}>
                      {st.name} (Roll: {st.roll_number})
                    </Text>
                    {isSelected && <Ionicons name="checkmark-circle" size={18} color={colors.primary} />}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </>
        ) : (
          <View style={{ marginBottom: 12, gap: 10 }}>
            <Input
              label="Student Full Name *"
              value={newStudentName}
              onChangeText={setNewStudentName}
              placeholder="e.g. Rahul Sharma"
            />
            <Input
              label="Roll Number *"
              value={newStudentRoll}
              onChangeText={setNewStudentRoll}
              placeholder="e.g. 25"
            />
          </View>
        )}

        <Text style={[styles.modalLabel, { color: colors.textSecondary }]}>
          Answer Sheet Pages *
        </Text>

        {compilingPages ? (
          <View style={[styles.compilingBox, { borderColor: colors.primary }]}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={[styles.compilingText, { color: colors.primary }]}>
              Compiling pages into a single multi-page PDF...
            </Text>
          </View>
        ) : pickedFile ? (
          <View
            style={[
              styles.selectedFileCard,
              {
                borderColor: colors.brandGreen,
                backgroundColor: "rgba(81, 188, 117, 0.08)",
              },
            ]}
          >
            <View style={[styles.selectedFileIconBox, { backgroundColor: "rgba(81, 188, 117, 0.15)" }]}>
              <Ionicons name="document-text" size={24} color={colors.brandGreen} />
            </View>
            <View style={{ flex: 1, marginHorizontal: 10 }}>
              <Text style={[styles.selectedFileName, { color: colors.text }]} numberOfLines={1}>
                {pickedFile.name || "student_answer_sheet.pdf"}
              </Text>
              <Text style={[styles.selectedFileMeta, { color: colors.brandGreen }]}>
                {pickedFile.pageCount
                  ? `${pickedFile.pageCount} Pages Compiled • Ready for evaluation`
                  : "Ready for evaluation"}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => setPickedFile(null)}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons name="close-circle" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
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
              title="Upload File(s) (PDF or Multiple Images)"
              icon={<Ionicons name="cloud-upload-outline" size={18} color={colors.text} />}
              variant="secondary"
              size="medium"
              onPress={handlePickStudentFile}
              fullWidth
            />
            <Text style={{ fontSize: 11, color: colors.textSecondary, textAlign: "center" }}>
              Tip: You can select multiple page images from gallery to auto-compile them into a multi-page document.
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
});
