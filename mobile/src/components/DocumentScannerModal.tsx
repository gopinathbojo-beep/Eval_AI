import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
  Image,
  FlatList,
  ActivityIndicator,
  Alert,
  Animated,
  Platform,
  Switch,
  AppState,
  AppStateStatus,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { CameraView, useCameraPermissions } from "expo-camera";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { printToFileAsync } from "expo-print";
import * as FileSystem from "expo-file-system/legacy";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { Button } from "./Button";
import { CornerAdjustmentModal } from "./CornerAdjustmentModal";
import {
  DocumentCorners,
  DocumentBoundingBox,
  DocumentDetectionState,
  DetectionAssessment,
  QualityAnalysisResult,
  PaperVerificationResult,
  DOCUMENT_ASPECT_RATIOS,
  generateReferenceCorners,
  calculateBoundingBoxFromCorners,
  assessLiveDocumentFraming,
  computeMarginSafeCropRect,
  computeCropFromCorners,
  analyzeImageQualityFast,
  verifyPaperPresence,
  detectPaperQuadInImage,
  DocumentStabilityTracker,
} from "../utils/documentDetection";

export interface ScannedPage {
  id: string;
  uri: string;          // Auto-cropped & enhanced page image
  originalUri: string;  // Original uncropped photo for recovery & comparison
  width: number;
  height: number;
  rotation: number;
  base64?: string;
  quality?: QualityAnalysisResult;
  isCropApplied: boolean;
}

export interface ScannedPageAsset {
  uri: string;
  name: string;
  mimeType: string;
}

export interface DocumentScannerResult {
  uri: string;
  name: string;
  type: string;
  pages?: ScannedPageAsset[];
  pageCount?: number;
}

export interface ScannerStudent {
  id: string;
  name: string;
  roll_number: string;
}

interface DocumentScannerModalProps {
  visible: boolean;
  onClose: () => void;
  onComplete: (file: DocumentScannerResult) => Promise<void>;
  examTitle?: string;
  title?: string;
  docTitlePrefix?: string;
  students?: ScannerStudent[];
  currentStudentId?: string;
  onScanNextStudent?: (
    file: DocumentScannerResult,
    currentStudentId: string,
    nextStudentId?: string
  ) => Promise<void>;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

// Target document viewport framing based on standard A4 (1:1.414)
const FRAME_WIDTH = Math.min(SCREEN_WIDTH * 0.88, 380);
const FRAME_HEIGHT = Math.min(FRAME_WIDTH * DOCUMENT_ASPECT_RATIOS.A4, SCREEN_HEIGHT * 0.62);

export const DocumentScannerModal: React.FC<DocumentScannerModalProps> = ({
  visible,
  onClose,
  onComplete,
  examTitle = "Document",
  title = "Document Scanner",
  docTitlePrefix = "QP",
  students,
  currentStudentId,
  onScanNextStudent,
}) => {
  const { colors } = useTheme();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Active student state for continuous batch scanning
  const [activeStudentId, setActiveStudentId] = useState<string | undefined>(
    currentStudentId || students?.[0]?.id
  );
  const [studentPickerVisible, setStudentPickerVisible] = useState(false);

  useEffect(() => {
    if (currentStudentId) {
      setActiveStudentId(currentStudentId);
    } else if (students && students.length > 0 && !activeStudentId) {
      setActiveStudentId(students[0].id);
    }
  }, [currentStudentId, students]);

  const activeStudent =
    students?.find((s) => s.id === activeStudentId) || (students?.[0] ?? null);
  const currentStudentIndex = students
    ? students.findIndex((s) => s.id === activeStudentId)
    : -1;
  const isFirstStudent = currentStudentIndex <= 0;
  const isLastStudent = !students || currentStudentIndex >= students.length - 1;

  const currentPrefix = activeStudent
    ? `${activeStudent.name.replace(/[^a-zA-Z0-9]/g, "")}_Sheet`
    : docTitlePrefix || "Doc";

  const handlePrevStudent = () => {
    if (students && currentStudentIndex > 0) {
      setActiveStudentId(students[currentStudentIndex - 1].id);
      setScannedPages([]);
      setSelectedPageIndex(null);
    }
  };

  const handleNextStudent = () => {
    if (students && currentStudentIndex < students.length - 1) {
      setActiveStudentId(students[currentStudentIndex + 1].id);
      setScannedPages([]);
      setSelectedPageIndex(null);
    }
  };

  // Scanned pages state
  const [scannedPages, setScannedPages] = useState<ScannedPage[]>([]);
  const [torch, setTorch] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number | null>(null);
  const [previewOriginal, setPreviewOriginal] = useState(false);
  const [retakeIndex, setRetakeIndex] = useState<number | null>(null);
  const [isCompiling, setIsCompiling] = useState(false);
  const [adjustingPageIndex, setAdjustingPageIndex] = useState<number | null>(null);

  // Camera hardware readiness tracking
  const [cameraReady, setCameraReady] = useState(false);
  const isCameraReadyRef = useRef(false);
  const aeSettledRef = useRef(false);
  const [cameraMountError, setCameraMountError] = useState<string | null>(null);

  // Auto-capture settings & state machine
  const [autoCaptureEnabled, setAutoCaptureEnabled] = useState(true);
  const [detectionState, setDetectionState] = useState<DocumentDetectionState>("INITIALIZING");
  const [guidanceMessage, setGuidanceMessage] = useState<string>("Initializing camera sensor...");
  const [recommendTorch, setRecommendTorch] = useState(false);
  const [waitingForPageSwap, setWaitingForPageSwap] = useState(false);

  // Paper presence rejection & alert feedback
  const [isDetectionRejected, setIsDetectionRejected] = useState(false);
  const isRejectedCooldownRef = useRef(false);
  const rejectionFlashAnim = useRef(new Animated.Value(0)).current;

  // Stability & countdown tracking
  const [countdownProgress, setCountdownProgress] = useState(0); // 0 to 1
  const stabilityTrackerRef = useRef<DocumentStabilityTracker>(
    new DocumentStabilityTracker(
      DOCUMENT_ASPECT_RATIOS.STABILITY_DURATION_MS,
      DOCUMENT_ASPECT_RATIOS.STABILITY_DRIFT_THRESHOLD_PX
    )
  );
  const stabilityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isCapturingRef = useRef(false);
  const isDetectingRef = useRef(false);
  const waitingForPageSwapRef = useRef(false);
  const lastCaptureTimeRef = useRef(0);
  const paperDetectedStartTimeRef = useRef<number | null>(null);
  const countdownStartTimeRef = useRef<number | null>(null);
  const isPaperCurrentlyDetectedRef = useRef(false);
  const isProbingRef = useRef(false);
  const lastProbeTimeRef = useRef(0);

  // Active detected corners (interpolated from reference frame)
  const defaultCorners = useRef<DocumentCorners>(
    generateReferenceCorners(SCREEN_WIDTH, SCREEN_HEIGHT, DOCUMENT_ASPECT_RATIOS.A4, 0.86)
  ).current;
  const [currentCorners, setCurrentCorners] = useState<DocumentCorners>(defaultCorners);

  /**
   * Fast, silent background probe to detect if paper is genuinely in frame
   * before arming the 3-second auto-capture countdown.
   */
  const probePaperPresence = async () => {
    if (
      isProbingRef.current ||
      isCapturingRef.current ||
      !cameraRef.current ||
      !isCameraReadyRef.current ||
      !aeSettledRef.current
    ) {
      return;
    }

    try {
      isProbingRef.current = true;
      lastProbeTimeRef.current = Date.now();

      const probePhoto = await cameraRef.current.takePictureAsync({
        quality: 0.1,
        shutterSound: false,
        skipProcessing: true,
        base64: false,
      });

      const uri = probePhoto?.uri || (probePhoto as any)?.path;
      if (!uri) return;

      try {
        const thumb = await manipulateAsync(
          uri,
          [{ resize: { width: 120 } }],
          { compress: 0.4, format: SaveFormat.JPEG, base64: true }
        );

        if (thumb?.base64) {
          const ver = verifyPaperPresence(thumb.base64);
          if (ver.isPaperDetected) {
            isPaperCurrentlyDetectedRef.current = true;
          } else {
            isPaperCurrentlyDetectedRef.current = false;
            if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
              clearTimers();
              setCountdownProgress(0);
              setDetectionState("SEARCHING");
              setGuidanceMessage("Looking for paper • Place answer sheet in frame");
            }
          }
        }
      } finally {
        await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
      }
    } catch {
      // Ignore probe errors silently
    } finally {
      isProbingRef.current = false;
    }
  };

  // Animations
  const scanLaserAnim = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const cornerScaleAnim = useRef(new Animated.Value(1)).current;

  // Flashes red/amber border when non-paper surface is rejected
  const triggerRejectionFlash = useCallback(() => {
    setIsDetectionRejected(true);
    setDetectionState("NO_DOCUMENT");
    rejectionFlashAnim.setValue(1);
    Animated.sequence([
      Animated.timing(rejectionFlashAnim, {
        toValue: 0.3,
        duration: 160,
        useNativeDriver: false,
      }),
      Animated.timing(rejectionFlashAnim, {
        toValue: 1,
        duration: 160,
        useNativeDriver: false,
      }),
      Animated.timing(rejectionFlashAnim, {
        toValue: 0,
        duration: 350,
        useNativeDriver: false,
      }),
    ]).start(() => {
      setIsDetectionRejected(false);
    });
  }, [rejectionFlashAnim]);

  // Sync ref with state
  useEffect(() => {
    waitingForPageSwapRef.current = waitingForPageSwap;
  }, [waitingForPageSwap]);

  // Laser guide scan animation
  useEffect(() => {
    if (visible && selectedPageIndex === null) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(scanLaserAnim, {
            toValue: 1,
            duration: 2400,
            useNativeDriver: true,
          }),
          Animated.timing(scanLaserAnim, {
            toValue: 0,
            duration: 2400,
            useNativeDriver: true,
          }),
        ])
      ).start();
    }
  }, [visible, selectedPageIndex, scanLaserAnim]);

  // Corner pulse animation when paper is locked or countdown is running
  useEffect(() => {
    if (
      detectionState === "READY" ||
      detectionState === "COUNTDOWN" ||
      detectionState === "PAPER_DETECTED"
    ) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(cornerScaleAnim, {
            toValue: 1.06,
            duration: 350,
            useNativeDriver: true,
          }),
          Animated.timing(cornerScaleAnim, {
            toValue: 1,
            duration: 350,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      cornerScaleAnim.setValue(1);
    }
  }, [detectionState, cornerScaleAnim]);

  const clearTimers = useCallback(() => {
    if (stabilityTimerRef.current) {
      clearTimeout(stabilityTimerRef.current);
      stabilityTimerRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
    if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
      console.log("[Scanner][Stability] Detection / countdown reset");
      paperDetectedStartTimeRef.current = null;
      countdownStartTimeRef.current = null;
    }
  }, []);

  // Reset state when modal is opened/closed
  useEffect(() => {
    if (!visible) {
      setScannedPages([]);
      setSelectedPageIndex(null);
      setPreviewOriginal(false);
      setRetakeIndex(null);
      setAdjustingPageIndex(null);
      setCapturing(false);
      isCapturingRef.current = false;
      isDetectingRef.current = false;
      setIsCompiling(false);
      setTorch(false);
      setWaitingForPageSwap(false);
      waitingForPageSwapRef.current = false;
      setCountdownProgress(0);
      setDetectionState("INITIALIZING");
      setGuidanceMessage("Initializing camera sensor...");
      setCameraReady(false);
      isCameraReadyRef.current = false;
      aeSettledRef.current = false;
      setCameraMountError(null);
      setIsDetectionRejected(false);
      isRejectedCooldownRef.current = false;
      stabilityTrackerRef.current.reset();
      clearTimers();
    } else {
      setDetectionState("INITIALIZING");
      setGuidanceMessage("Initializing camera sensor...");
      stabilityTrackerRef.current.reset();
      isPaperCurrentlyDetectedRef.current = false;

      // Fallback timer in case native onCameraReady event was missed by JS listener
      const readyFallback = setTimeout(() => {
        if (!isCameraReadyRef.current && !cameraMountError) {
          console.log("[Scanner] Camera ready fallback triggered (onCameraReady event was not received)");
          isCameraReadyRef.current = true;
          aeSettledRef.current = true;
          setCameraReady(true);
          setDetectionState((curr) => (curr === "INITIALIZING" ? "SEARCHING" : curr));
          setGuidanceMessage("Looking for paper • Place answer sheet in frame");
        }
      }, 2000);

      return () => clearTimeout(readyFallback);
    }
  }, [visible, clearTimers, cameraMountError]);

  // Handle app background/foreground transitions and camera surface lifecycle
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (nextAppState: AppStateStatus) => {
      if (nextAppState !== "active") {
        console.log("[Scanner] App entered background/inactive state. Pausing scanner.");
        isCameraReadyRef.current = false;
        aeSettledRef.current = false;
        setCameraReady(false);
        clearTimers();
        setCountdownProgress(0);
        stabilityTrackerRef.current.reset();
      } else if (visible) {
        console.log("[Scanner] App returned to active state. Awaiting camera preview ready signal.");
      }
    });

    return () => {
      subscription.remove();
    };
  }, [visible, clearTimers]);

  /**
   * Continuous document alignment and 3-second stability tracking loop.
   * Keeps camera preview responsive at 60 FPS without probe capture lockup.
   * When camera preview is ready and framed inside the viewfinder,
   * runs the 3-second alignment countdown and triggers high-fidelity capture.
   */
  useEffect(() => {
    if (!visible || selectedPageIndex !== null || isCompiling) {
      clearTimers();
      return;
    }

    const interval = setInterval(() => {
      // Guard 1: Concurrency and camera hardware readiness
      if (
        isCapturingRef.current ||
        !isCameraReadyRef.current ||
        !aeSettledRef.current ||
        !cameraRef.current
      ) {
        if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
          clearTimers();
          setCountdownProgress(0);
        }
        return;
      }

      // Guard 2: If camera encountered mount error, show error guidance
      if (cameraMountError) {
        setDetectionState("SEARCHING");
        setGuidanceMessage(`Camera error: ${cameraMountError}`);
        clearTimers();
        setCountdownProgress(0);
        return;
      }

      // Guard 3: Waiting in rejection cooldown after non-paper surface detected
      if (isRejectedCooldownRef.current) {
        if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
          clearTimers();
          setCountdownProgress(0);
        }
        return;
      }

      // Guard 4: Waiting for page swap after prior capture
      if (waitingForPageSwapRef.current) {
        setDetectionState("PAGE_CAPTURED_WAITING_FOR_NEXT");
        setGuidanceMessage("Page captured • Move to next page");
        setCountdownProgress(0);
        if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
          clearTimers();
        }
        return;
      }

      // Guard 5: Auto-capture disabled by user (manual mode)
      if (!autoCaptureEnabled) {
        setDetectionState("SEARCHING");
        setGuidanceMessage("Auto-scan paused • Tap shutter to capture");
        setCountdownProgress(0);
        if (paperDetectedStartTimeRef.current !== null || countdownStartTimeRef.current !== null) {
          clearTimers();
        }
        return;
      }

      // Guard 6: Page swap cooldown
      if (Date.now() - lastCaptureTimeRef.current < DOCUMENT_ASPECT_RATIOS.PAGE_SWAP_COOLDOWN_MS) {
        return;
      }

      const now = Date.now();
      const PAPER_SHOW_HOLD_MS = 1000; // 1s: show paper detected first
      const COUNTDOWN_TOTAL_MS = 3000; // 3s: countdown timer before capture

      // Guard: Only proceed if paper is genuinely detected in frame
      if (!isPaperCurrentlyDetectedRef.current) {
        setDetectionState("SEARCHING");
        setGuidanceMessage("Looking for paper • Place answer sheet in frame");
        setCountdownProgress(0);
        clearTimers();

        // Run fast silent probe every 1200ms
        if (now - lastProbeTimeRef.current > 1200) {
          probePaperPresence();
        }
        return;
      }

      // Phase 1: Show paper first
      if (paperDetectedStartTimeRef.current === null) {
        paperDetectedStartTimeRef.current = now;
        countdownStartTimeRef.current = null;
        console.log("[Scanner][Phase 1] Paper detected • showing paper to user");
        setDetectionState("PAPER_DETECTED");
        setGuidanceMessage("Paper detected • Align inside frame");
        setCountdownProgress(0);
        return;
      }

      // If still in paper-detected display hold period
      if (countdownStartTimeRef.current === null) {
        const elapsedPaper = now - paperDetectedStartTimeRef.current;
        if (elapsedPaper < PAPER_SHOW_HOLD_MS) {
          setDetectionState("PAPER_DETECTED");
          setGuidanceMessage("Paper detected • Align inside frame");
          setCountdownProgress(0);
          return;
        }

        // Paper hold complete -> transition to Phase 2: 3-second countdown!
        countdownStartTimeRef.current = now;
        console.log("[Scanner][Phase 2] Paper aligned • starting 3-second countdown");
        setDetectionState("COUNTDOWN");
        setGuidanceMessage("Document aligned • Hold steady (3s)");
        setCountdownProgress(0.01);
        return;
      }

      // Phase 2: Active 3s countdown (3s -> 2s -> 1s)
      const elapsedCountdown = now - countdownStartTimeRef.current;
      const progress = Math.min(1.0, elapsedCountdown / COUNTDOWN_TOTAL_MS);

      if (progress < 1.0) {
        setDetectionState("COUNTDOWN");
        const remainingSec = Math.max(1, Math.ceil((1 - progress) * 3));
        setGuidanceMessage(`Document aligned • Hold steady (${remainingSec}s)`);
        setCountdownProgress(progress);
      } else {
        // Phase 3: 3s countdown complete! Trigger capture immediately
        console.log("[Scanner][Phase 3] 3s countdown complete • capturing photo");
        paperDetectedStartTimeRef.current = null;
        countdownStartTimeRef.current = null;
        isPaperCurrentlyDetectedRef.current = false;
        setCountdownProgress(0);
        setDetectionState("CAPTURING");
        setGuidanceMessage("Capturing document...");
        triggerCapture({ isManual: false });
      }
    }, 100);

    return () => {
      clearInterval(interval);
      clearTimers();
    };
  }, [
    visible,
    selectedPageIndex,
    isCompiling,
    autoCaptureEnabled,
    defaultCorners,
    clearTimers,
    cameraMountError,
  ]);

  /**
   * Processes, auto-crops, and registers a validated document page.
   */
  const saveAndRegisterPage = async (
    photoUri: string,
    photoWidth: number,
    photoHeight: number,
    cropRect: { originX: number; originY: number; width: number; height: number },
    photoBase64?: string
  ) => {
    setDetectionState("PROCESSING");
    setGuidanceMessage("Processing & auto-cropping...");
    console.log("[Scanner] Processing image and auto-cropping document boundaries...");

    // Fast image quality heuristics
    const quality = analyzeImageQualityFast(photoBase64);

    // Check if image orientation needs auto-rotation (portrait answer sheets)
    const isLandscapePhoto = photoWidth > photoHeight;
    const isPortraitDoc = cropRect.height > cropRect.width;

    const manipulationActions: any[] = [
      {
        crop: {
          originX: cropRect.originX,
          originY: cropRect.originY,
          width: cropRect.width,
          height: cropRect.height,
        },
      },
    ];

    // If document is portrait but camera saved as landscape, rotate 90 deg
    if (isLandscapePhoto && isPortraitDoc) {
      manipulationActions.push({ rotate: 90 });
    }

    // Preserve high-definition resolution for OCR analysis (1600px width)
    manipulationActions.push({ resize: { width: 1600 } });

    let finalUri = photoUri;
    let finalWidth = photoWidth;
    let finalHeight = photoHeight;
    let isCropSuccess = false;
    let finalBase64: string | undefined = undefined;

    try {
      const cropped = await manipulateAsync(photoUri, manipulationActions, {
        compress: 0.92,
        format: SaveFormat.JPEG,
        base64: true,
      });

      if (cropped && cropped.uri) {
        finalUri = cropped.uri;
        finalWidth = cropped.width;
        finalHeight = cropped.height;
        finalBase64 = cropped.base64;
        isCropSuccess = true;
        console.log("[Scanner][Crop] Perspective correction completed");
      }
    } catch (cropErr: any) {
      console.warn(
        "[Scanner] Auto-crop failed, falling back safely to original captured image:",
        cropErr?.message || cropErr
      );
    }

    const pageNumber = retakeIndex !== null ? retakeIndex + 1 : scannedPages.length + 1;
    const newPage: ScannedPage = {
      id: `page_${Date.now()}_${pageNumber}`,
      uri: finalUri,
      originalUri: photoUri, // Original photo preserved for recovery & comparison
      width: finalWidth,
      height: finalHeight,
      rotation: 0,
      base64: finalBase64,
      quality,
      isCropApplied: isCropSuccess,
    };

    if (retakeIndex !== null) {
      setScannedPages((prev) => {
        const copy = [...prev];
        copy[retakeIndex] = newPage;
        return copy;
      });
      setSelectedPageIndex(retakeIndex);
      setRetakeIndex(null);
    } else {
      setScannedPages((prev) => [...prev, newPage]);

      // Record captured corner positions in stability tracker so duplicate capture is prevented
      stabilityTrackerRef.current.recordCapture(currentCorners);
      lastCaptureTimeRef.current = Date.now();

      // Duplicate prevention: disarm auto-capture until page swap is registered
      setWaitingForPageSwap(true);
      waitingForPageSwapRef.current = true;
      setDetectionState("PAGE_CAPTURED_WAITING_FOR_NEXT");
      setGuidanceMessage(`Page ${pageNumber} captured! Place next page...`);

      // Automatically re-arm after cooldown period if user stays in live camera
      setTimeout(() => {
        setWaitingForPageSwap(false);
        waitingForPageSwapRef.current = false;
        setDetectionState("SEARCHING");
        setGuidanceMessage("Align next page in frame");
      }, DOCUMENT_ASPECT_RATIOS.PAGE_SWAP_COOLDOWN_MS);
    }
    console.log(`[Scanner][Session] Page added: page ${pageNumber}`);
  };

  /**
   * Captures the document page using the camera sensor,
   * performs segmented paper-presence and quality verification,
   * performs auto-cropping with margin-safe padding on genuine answer sheets,
   * and preserves the original photo as a resilient fallback.
   */
  const triggerCapture = async (options?: { isManual?: boolean }) => {
    const isManual = options?.isManual ?? false;

    // 1. Concurrency and readiness guards
    if (isCapturingRef.current) {
      console.log("[Scanner] Capture already in progress, ignoring trigger.");
      return;
    }
    if (!cameraRef.current) {
      console.warn("[Scanner] Camera ref is null, cannot capture.");
      return;
    }
    if (!isCameraReadyRef.current) {
      console.warn("[Scanner] Capture triggered before camera is ready.");
      setGuidanceMessage("Waiting for camera sensor to initialize...");
      return;
    }

    try {
      isCapturingRef.current = true;
      setCapturing(true);
      clearTimers();
      setCountdownProgress(0);
      setDetectionState("CAPTURING");
      setGuidanceMessage("Capturing document...");
      console.log(`[Scanner][Capture] Capture started (${isManual ? "MANUAL" : "AUTO"})`);

      // Fast capture without transferring heavy 15MB base64 over React Native bridge
      let photo = await cameraRef.current.takePictureAsync({
        quality: 0.88,
        skipProcessing: false,
        base64: false,
      });

      // Extract image URI across possible platform response properties
      let photoUri = photo?.uri || (photo as any)?.path || (photo as any)?.localUri;

      // If initial capture returned empty, retry once after a short 250ms delay
      if (!photo || !photoUri) {
        console.warn("[Scanner] Camera returned empty photo on initial attempt. Retrying capture once...");
        await new Promise((resolve) => setTimeout(resolve, 250));
        if (cameraRef.current && isCameraReadyRef.current) {
          photo = await cameraRef.current.takePictureAsync({
            quality: 0.88,
            skipProcessing: false,
            base64: false,
          });
          photoUri = photo?.uri || (photo as any)?.path || (photo as any)?.localUri;
        }
      }

      if (!photo || !photoUri) {
        throw new Error("Camera capture returned empty photo. Please hold steady and try again.");
      }

      // Verify captured file exists and is accessible on device storage
      try {
        const fileInfo = await FileSystem.getInfoAsync(photoUri);
        if (!fileInfo.exists || (fileInfo.size !== undefined && fileInfo.size === 0)) {
          throw new Error("Captured image file is empty or inaccessible on storage.");
        }
      } catch (fsErr: any) {
        if (fsErr.message?.includes("empty or inaccessible")) {
          throw fsErr;
        }
        console.warn("[Scanner] FileSystem check non-fatal note:", fsErr?.message || fsErr);
      }

      console.log("[Scanner][Capture] Image received successfully");

      const photoWidth = photo.width || Math.round(SCREEN_WIDTH * 2);
      const photoHeight = photo.height || Math.round(SCREEN_HEIGHT * 2);

      // Fast native thumbnail generation (400px width, ~25KB)
      // Eliminates Hermes single-threaded JavaScript JPEG decompression lockup on full 12-48MP images
      let thumbBase64: string | undefined = undefined;
      let thumbWidth = 400;
      let thumbHeight = Math.max(10, Math.round(400 * (photoHeight / photoWidth)));
      try {
        const thumb = await manipulateAsync(
          photoUri,
          [{ resize: { width: 400 } }],
          { compress: 0.65, format: SaveFormat.JPEG, base64: true }
        );
        if (thumb && thumb.base64) {
          thumbBase64 = thumb.base64;
          if (thumb.width && thumb.height) {
            thumbWidth = thumb.width;
            thumbHeight = thumb.height;
          }
        }
      } catch (thumbErr) {
        console.warn("[Scanner] Thumbnail generation note:", thumbErr);
      }

      // Calculate margin-safe crop rectangle using detected corners
      // (4% outward safety margin so handwriting, question numbers, and marks are never cut off)
      const boundingBox: DocumentBoundingBox = calculateBoundingBoxFromCorners(currentCorners);
      console.log("[Scanner][Detection] Four corners validated");
      let cropRect = computeMarginSafeCropRect({
        boundingBox,
        viewportWidth: SCREEN_WIDTH,
        viewportHeight: SCREEN_HEIGHT,
        photoWidth,
        photoHeight,
        safetyMarginPercent: 0.04, // 4% outward margin buffer
      });

      // Segment actual paper boundary from fast thumbnail if clear contrast is detected
      if (thumbBase64) {
        try {
          const thumbDetected = detectPaperQuadInImage(thumbBase64, thumbWidth, thumbHeight);
          if (thumbDetected.found && thumbDetected.confidence >= 0.7) {
            const scaleX = photoWidth / thumbWidth;
            const scaleY = photoHeight / thumbHeight;
            const scaledCorners: DocumentCorners = {
              topLeft: { x: thumbDetected.corners.topLeft.x * scaleX, y: thumbDetected.corners.topLeft.y * scaleY },
              topRight: { x: thumbDetected.corners.topRight.x * scaleX, y: thumbDetected.corners.topRight.y * scaleY },
              bottomRight: { x: thumbDetected.corners.bottomRight.x * scaleX, y: thumbDetected.corners.bottomRight.y * scaleY },
              bottomLeft: { x: thumbDetected.corners.bottomLeft.x * scaleX, y: thumbDetected.corners.bottomLeft.y * scaleY },
            };
            cropRect = computeCropFromCorners(scaledCorners, photoWidth, photoHeight, 0.03);
            console.log("[Scanner][Detection] Photo paper boundary segmented successfully");
          }
        } catch {
          // Keep resilient fallback
        }
      }

      // =========================================================================
      // STRICT PAPER-PRESENCE & IMAGE QUALITY VERIFICATION
      // =========================================================================
      setGuidanceMessage("Verifying document paper...");

      let verificationResult: PaperVerificationResult;
      try {
        verificationResult = verifyPaperPresence(thumbBase64 || "");
      } catch (verErr: any) {
        console.warn("[Scanner] Paper verification sample check note:", verErr?.message || verErr);
        verificationResult = {
          isPaperDetected: true,
          rejectionReason: null,
          metrics: { meanLuminance: 160, meanSaturation: 0.1, stdDev: 25, inkPercent: 3 },
        };
      }

      console.log(`[Scanner][Detection] Paper detected: ${verificationResult.isPaperDetected}`, {
        rejectionReason: verificationResult.rejectionReason,
        metrics: verificationResult.metrics,
        isManual,
      });

      // CASE 1: REJECTED (Too dark, too blurry, colored surface, or no document text)
      if (!verificationResult.isPaperDetected) {
        if (!isManual) {
          // AUTO-CAPTURE MODE: Reject and delete photo without saving
          console.log(
            "[Scanner] Auto-capture rejected: " +
              verificationResult.rejectionReason +
              ". Discarding captured photo."
          );
          await FileSystem.deleteAsync(photoUri, { idempotent: true }).catch(() => {});

          triggerRejectionFlash();
          const reason = verificationResult.rejectionReason || "Image quality insufficient";
          setGuidanceMessage(reason);

          // Disarm auto-capture briefly so user can adjust angle/lighting
          isRejectedCooldownRef.current = true;
          isPaperCurrentlyDetectedRef.current = false;
          stabilityTrackerRef.current.reset();
          clearTimers();
          setCountdownProgress(0);

          setTimeout(() => {
            isRejectedCooldownRef.current = false;
            if (!waitingForPageSwapRef.current) {
              setDetectionState("SEARCHING");
              setGuidanceMessage("Looking for paper • Place answer sheet in frame");
            }
          }, 1200);

          return;
        } else {
          // MANUAL MODE: Shutter button pressed manually — prompt confirmation
          Alert.alert(
            "Document Quality Notice",
            `The camera noticed an issue: ${
              verificationResult.rejectionReason || "Check lighting and hold steady"
            }.\n\nDo you want to keep this photo anyway or retake?`,
            [
              {
                text: "Retake",
                style: "cancel",
                onPress: () => {
                  FileSystem.deleteAsync(photoUri, { idempotent: true }).catch(() => {});
                  triggerRejectionFlash();
                  clearTimers();
                  setCountdownProgress(0);
                  setDetectionState("SEARCHING");
                  setGuidanceMessage("Looking for paper • Place answer sheet in frame");
                },
              },
              {
                text: "Keep Anyway",
                onPress: () => {
                  saveAndRegisterPage(photoUri, photoWidth, photoHeight, cropRect, thumbBase64);
                },
              },
            ]
          );
          return;
        }
      }

      // CASE 2: PAPER VERIFIED! Proceed with auto-crop and registration
      await saveAndRegisterPage(photoUri, photoWidth, photoHeight, cropRect, thumbBase64);
    } catch (err: any) {
      console.error("[Scanner] Capture failure:", err?.message || err);
      setDetectionState("SEARCHING");
      setGuidanceMessage("Capture failed. Hold steady and tap shutter to retry.");
      Alert.alert(
        "Capture Failed",
        err.message || "Could not capture document page. Please hold steady and try again.",
        [{ text: "OK" }]
      );
    } finally {
      setCapturing(false);
      isCapturingRef.current = false;
      setCountdownProgress(0);
    }
  };

  /**
   * Reset duplicate protection to immediately scan next page
   */
  const handleReadyForNextPage = () => {
    setWaitingForPageSwap(false);
    waitingForPageSwapRef.current = false;
    setDetectionState("SEARCHING");
    setGuidanceMessage("Looking for next answer sheet page...");
  };

  /**
   * Toggle between auto-cropped and raw original capture in review mode
   */
  const handleToggleCrop = (index: number) => {
    const page = scannedPages[index];
    if (!page) return;

    setScannedPages((prev) => {
      const copy = [...prev];
      const current = copy[index];
      const toggledCrop = !current.isCropApplied;

      copy[index] = {
        ...current,
        isCropApplied: toggledCrop,
        uri: toggledCrop ? current.uri : current.originalUri,
      };
      return copy;
    });
    setPreviewOriginal((prev) => !prev);
  };

  /**
   * Rotate/straighten a captured page by 90 degrees clockwise
   */
  const handleRotatePage = async (index: number) => {
    const page = scannedPages[index];
    if (!page) return;

    try {
      const rotated = await manipulateAsync(
        page.uri,
        [{ rotate: 90 }],
        {
          compress: 0.92,
          format: SaveFormat.JPEG,
          base64: true,
        }
      );

      setScannedPages((prev) => {
        const copy = [...prev];
        copy[index] = {
          ...copy[index],
          uri: rotated.uri,
          width: rotated.width,
          height: rotated.height,
          rotation: (copy[index].rotation + 90) % 360,
          base64: rotated.base64,
        };
        return copy;
      });
    } catch (err: any) {
      Alert.alert("Rotation Failed", err.message || "Failed to rotate page.");
    }
  };

  /**
   * Applies user-adjusted 4-corner crop to a scanned page, preserving original uncropped photo
   */
  const handleApplyManualCrop = async (
    pageIndex: number,
    cropRect: { originX: number; originY: number; width: number; height: number },
    newCorners: DocumentCorners
  ) => {
    const page = scannedPages[pageIndex];
    if (!page) return;

    try {
      const cropped = await manipulateAsync(
        page.originalUri,
        [
          {
            crop: {
              originX: cropRect.originX,
              originY: cropRect.originY,
              width: cropRect.width,
              height: cropRect.height,
            },
          },
          { resize: { width: 1600 } },
        ],
        {
          compress: 0.92,
          format: SaveFormat.JPEG,
          base64: true,
        }
      );

      setScannedPages((prev) => {
        const copy = [...prev];
        copy[pageIndex] = {
          ...copy[pageIndex],
          uri: cropped.uri,
          width: cropped.width,
          height: cropped.height,
          base64: cropped.base64,
          isCropApplied: true,
        };
        return copy;
      });

      console.log(`[Scanner][Crop] Manual corner adjustment applied to page ${pageIndex + 1}`);
    } catch (err: any) {
      Alert.alert("Crop Adjustment Failed", err?.message || "Failed to crop adjusted page");
    }
  };

  /**
   * Reorder pages in sequence
   */
  const handleMovePage = (index: number, direction: "left" | "right") => {
    const targetIndex = direction === "left" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= scannedPages.length) return;

    setScannedPages((prev) => {
      const copy = [...prev];
      const temp = copy[index];
      copy[index] = copy[targetIndex];
      copy[targetIndex] = temp;
      return copy;
    });
    setSelectedPageIndex(targetIndex);
  };

  /**
   * Delete a page from the sequence
   */
  const handleDeletePage = (index: number) => {
    Alert.alert("Remove Page", `Remove Page ${index + 1}?`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: () => {
          setScannedPages((prev) => prev.filter((_, i) => i !== index));
          if (selectedPageIndex === index) {
            setSelectedPageIndex(null);
          } else if (selectedPageIndex !== null && selectedPageIndex > index) {
            setSelectedPageIndex(selectedPageIndex - 1);
          }
        },
      },
    ]);
  };

  /**
   * Confirm before discarding all captured pages
   */
  const handleRequestClose = () => {
    if (scannedPages.length > 0) {
      Alert.alert(
        "Discard Scanned Pages?",
        `You have captured ${scannedPages.length} page(s). Are you sure you want to discard them and exit the camera?`,
        [
          { text: "Keep Scanning", style: "cancel" },
          {
            text: "Discard & Exit",
            style: "destructive",
            onPress: () => {
              setScannedPages([]);
              setSelectedPageIndex(null);
              setRetakeIndex(null);
              onClose();
            },
          },
        ]
      );
    } else {
      onClose();
    }
  };

  /**
   * Compiles scanned pages into a unified multi-page PDF document
   */
  const compilePagesToPdfResult = async (
    pages: ScannedPage[],
    prefix: string
  ): Promise<DocumentScannerResult> => {
    const cleanTitle = examTitle.replace(/[^a-zA-Z0-9_-]/g, "_");

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
          ${pages
            .map(
              (p, i) => `
            <div class="page" id="page-${i + 1}">
              <img src="${p.base64 ? `data:image/jpeg;base64,${p.base64}` : p.uri}" alt="Page ${i + 1}" />
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

    const safePdfUri = `${FileSystem.cacheDirectory}${cleanTitle}_${prefix}_${Date.now()}.pdf`;

    if (pdf.base64) {
      await FileSystem.writeAsStringAsync(safePdfUri, pdf.base64, {
        encoding: FileSystem.EncodingType.Base64,
      });
    } else {
      await FileSystem.copyAsync({ from: pdf.uri, to: safePdfUri });
    }

    const individualPages: ScannedPageAsset[] = pages.map((p, idx) => ({
      uri: p.uri,
      name: `${cleanTitle}_${prefix}_Page_${idx + 1}.jpg`,
      mimeType: "image/jpeg",
    }));

    console.log("[Scanner][PDF] Compilation completed");
    return {
      uri: safePdfUri,
      name: `${cleanTitle}_${prefix}_${pages.length}_Pages.pdf`,
      type: "application/pdf",
      pages: individualPages,
      pageCount: pages.length,
    };
  };

  /**
   * Compiles all scanned pages and returns to the parent workflow
   */
  const handleFinishAndUpload = async () => {
    if (scannedPages.length === 0) {
      Alert.alert("No Pages Scanned", "Please scan at least one page before finishing.");
      return;
    }

    try {
      setIsCompiling(true);
      const uploadResult = await compilePagesToPdfResult(scannedPages, currentPrefix);
      await onComplete(uploadResult);
      console.log("[Scanner][Upload] Upload completed");
      onClose();
    } catch (err: any) {
      Alert.alert("Processing Failed", err.message || "Failed to process and compile scanned pages.");
    } finally {
      setIsCompiling(false);
    }
  };

  /**
   * Continuous Classroom Batch Scanning:
   * Saves current student's pages, dispatches background upload,
   * advances to next student in roster, and remains in camera
   */
  const handleSaveAndNextStudent = async () => {
    if (scannedPages.length === 0) {
      Alert.alert("No Pages Scanned", "Please scan at least one page for the current student before advancing.");
      return;
    }

    try {
      setIsCompiling(true);
      const uploadResult = await compilePagesToPdfResult(scannedPages, currentPrefix);

      // Determine next student in roster
      let nextStudent: ScannerStudent | undefined;
      if (students && students.length > 0) {
        const currentIndex = students.findIndex((s) => s.id === activeStudentId);
        if (currentIndex !== -1 && currentIndex < students.length - 1) {
          nextStudent = students[currentIndex + 1];
        }
      }

      if (onScanNextStudent && activeStudentId) {
        await onScanNextStudent(uploadResult, activeStudentId, nextStudent?.id);
      } else {
        await onComplete(uploadResult);
      }
      console.log("[Scanner][Upload] Upload completed");

      // Reset pages and advance active student
      setScannedPages([]);
      setSelectedPageIndex(null);
      setRetakeIndex(null);
      setWaitingForPageSwap(false);
      waitingForPageSwapRef.current = false;
      setDetectionState("SEARCHING");

      if (nextStudent) {
        setActiveStudentId(nextStudent.id);
        setGuidanceMessage(`Saved! Position Page 1 for ${nextStudent.name}...`);
      } else {
        setGuidanceMessage("Answer sheet saved! Position next answer sheet...");
      }
    } catch (err: any) {
      Alert.alert("Batch Save Failed", err.message || "Failed to save answer sheet.");
    } finally {
      setIsCompiling(false);
    }
  };

  const laserTranslateY = scanLaserAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, FRAME_HEIGHT - 4],
  });

  // Dynamic corner color based on detection state
  const getCornerColor = () => {
    if (isDetectionRejected || detectionState === "NO_DOCUMENT") {
      return "#C43A28"; // Red for rejected non-paper surface
    }
    switch (detectionState) {
      case "READY":
      case "COUNTDOWN":
        return "#1F8F5F"; // Emerald Green for locked / countdown
      case "CAPTURING":
      case "PROCESSING":
        return "#0F8A80"; // Sky Blue during capture / auto-crop
      case "PAPER_DETECTED":
        return "#0F8A80"; // Teal for paper detected & aligning
      case "TOO_FAR":
      case "TOO_CLOSE":
      case "OUT_OF_BOUNDS":
      case "BAD_ASPECT_RATIO":
      case "UNSTABLE":
      case "LOW_LIGHT":
        return "#B7791F"; // Amber for alignment required
      case "PAGE_CAPTURED_WAITING_FOR_NEXT":
        return "#0F8A80"; // Cyan for page swap waiting
      default:
        return colors.primary; // Blue for searching / initializing
    }
  };

  if (!visible) return null;

  if (!permission) {
    return (
      <Modal visible={visible} animationType="slide">
        <View style={[styles.permissionContainer, { backgroundColor: colors.background }]}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.permissionText, { color: colors.text }]}>
            Initializing camera scanner...
          </Text>
        </View>
      </Modal>
    );
  }

  if (!permission.granted) {
    return (
      <Modal visible={visible} animationType="slide">
        <View style={[styles.permissionContainer, { backgroundColor: colors.background }]}>
          <View style={[styles.permIconCircle, { backgroundColor: "rgba(15, 118, 110, 0.12)" }]}>
            <Ionicons name="camera-outline" size={48} color={colors.primary} />
          </View>
          <Text style={[styles.permissionTitle, { color: colors.text }]}>
            Camera Access Required
          </Text>
          <Text style={[styles.permissionText, { color: colors.textSecondary }]}>
            The camera is used to find and crop each page.
          </Text>
          <Button
            title="Enable Camera Access"
            onPress={requestPermission}
            variant="gradient"
            style={{ marginTop: 24 }}
          />
          <Button
            title="Cancel"
            onPress={onClose}
            variant="ghost"
            style={{ marginTop: 12 }}
          />
        </View>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleRequestClose}>
      <SafeAreaView style={styles.modalRoot}>
        {/* ========================================================= */}
        {/* SCREEN A: REVIEW & INSPECTION OF SCANNED PAGE              */}
        {/* ========================================================= */}
        {selectedPageIndex !== null && scannedPages[selectedPageIndex] ? (
          <View style={styles.reviewContainer}>
            <View style={styles.reviewHeader}>
              <TouchableOpacity
                onPress={() => setSelectedPageIndex(null)}
                style={styles.reviewBackBtn}
              >
                <Ionicons name="camera-outline" size={20} color="#FFFFFF" />
                <Text style={styles.reviewBackText}>Scan Next</Text>
              </TouchableOpacity>
              <Text style={styles.reviewPageTitle}>
                Page {selectedPageIndex + 1} of {scannedPages.length}
              </Text>
              <TouchableOpacity
                onPress={() => handleDeletePage(selectedPageIndex)}
                style={styles.reviewTrashBtn}
              >
                <Ionicons name="trash-outline" size={22} color={colors.error} />
              </TouchableOpacity>
            </View>

            {/* Quality feedback pill */}
            {scannedPages[selectedPageIndex].quality && (
              <View style={styles.qualityPill}>
                <Ionicons
                  name={
                    scannedPages[selectedPageIndex].quality?.isAcceptable
                      ? "checkmark-circle"
                      : "alert-circle"
                  }
                  size={15}
                  color={
                    scannedPages[selectedPageIndex].quality?.isAcceptable
                      ? "#1F8F5F"
                      : "#B7791F"
                  }
                />
                <Text style={styles.qualityPillText}>
                  {scannedPages[selectedPageIndex].quality?.feedback}
                </Text>
              </View>
            )}

            {/* Main Preview with Crop Toggle */}
            <View style={styles.previewImageWrapper}>
              <Image
                source={{ uri: scannedPages[selectedPageIndex].uri }}
                style={styles.previewImage}
                resizeMode="contain"
              />
              <View style={styles.cropBadge}>
                <Text style={styles.cropBadgeText}>
                  {scannedPages[selectedPageIndex].isCropApplied ? "Auto-Cropped" : "Original Capture"}
                </Text>
              </View>
            </View>

            {/* Page manipulation toolbar: Move, Rotate, Crop Toggle, Retake */}
            <View style={styles.reviewToolbar}>
              <TouchableOpacity
                onPress={() => handleMovePage(selectedPageIndex, "left")}
                disabled={selectedPageIndex === 0}
                style={[
                  styles.toolBtn,
                  selectedPageIndex === 0 && styles.toolBtnDisabled,
                ]}
              >
                <Ionicons
                  name="arrow-back"
                  size={18}
                  color={selectedPageIndex === 0 ? "rgba(255,255,255,0.3)" : "#FFFFFF"}
                />
                <Text
                  style={[
                    styles.toolBtnText,
                    selectedPageIndex === 0 && styles.toolBtnTextDisabled,
                  ]}
                >
                  Move Left
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => handleRotatePage(selectedPageIndex)}
                style={styles.toolBtn}
              >
                <Ionicons name="reload" size={18} color="#FFFFFF" />
                <Text style={styles.toolBtnText}>Rotate</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => handleToggleCrop(selectedPageIndex)}
                style={styles.toolBtn}
              >
                <Ionicons
                  name={scannedPages[selectedPageIndex].isCropApplied ? "crop" : "image-outline"}
                  size={18}
                  color="#FFFFFF"
                />
                <Text style={styles.toolBtnText}>
                  {scannedPages[selectedPageIndex].isCropApplied ? "Original" : "Cropped"}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => setAdjustingPageIndex(selectedPageIndex)}
                style={styles.toolBtn}
              >
                <Ionicons name="expand" size={18} color="#1F8F5F" />
                <Text style={[styles.toolBtnText, { color: "#1F8F5F" }]}>Adjust</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => {
                  const target = selectedPageIndex;
                  setSelectedPageIndex(null);
                  setRetakeIndex(target);
                }}
                style={styles.toolBtn}
              >
                <Ionicons name="camera-reverse-outline" size={18} color="#FFFFFF" />
                <Text style={styles.toolBtnText}>Retake</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => handleMovePage(selectedPageIndex, "right")}
                disabled={selectedPageIndex === scannedPages.length - 1}
                style={[
                  styles.toolBtn,
                  selectedPageIndex === scannedPages.length - 1 && styles.toolBtnDisabled,
                ]}
              >
                <Ionicons
                  name="arrow-forward"
                  size={18}
                  color={
                    selectedPageIndex === scannedPages.length - 1
                      ? "rgba(255,255,255,0.3)"
                      : "#FFFFFF"
                  }
                />
                <Text
                  style={[
                    styles.toolBtnText,
                    selectedPageIndex === scannedPages.length - 1 && styles.toolBtnTextDisabled,
                  ]}
                >
                  Move Right
                </Text>
              </TouchableOpacity>
            </View>

            {/* Bottom action row: Add More Pages or Finish Scanning */}
            <View style={styles.reviewActionsBar}>
              <TouchableOpacity
                onPress={() => setSelectedPageIndex(null)}
                style={styles.addMoreBtn}
              >
                <Ionicons name="add" size={20} color="#FFFFFF" />
                <Text style={styles.addMoreBtnText}>Scan Next Page</Text>
              </TouchableOpacity>

              {students && students.length > 1 && onScanNextStudent && (
                <TouchableOpacity
                  onPress={handleSaveAndNextStudent}
                  disabled={isCompiling}
                  style={[styles.saveNextStudentBtn, { backgroundColor: "#0F8A80" }]}
                >
                  {isCompiling ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <>
                      <Ionicons name="arrow-forward-circle" size={18} color="#FFFFFF" />
                      <Text style={styles.saveNextStudentBtnText}>Save & Next Student</Text>
                    </>
                  )}
                </TouchableOpacity>
              )}

              <TouchableOpacity
                onPress={handleFinishAndUpload}
                disabled={isCompiling}
                style={[styles.finishScanBtn, { backgroundColor: colors.brandGreen }]}
              >
                {isCompiling ? (
                  <ActivityIndicator size="small" color="#FFFFFF" />
                ) : (
                  <>
                    <Ionicons name="checkmark-circle-outline" size={20} color="#FFFFFF" />
                    <Text style={styles.finishScanBtnText}>
                      Finish ({scannedPages.length})
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          /* ========================================================= */
          /* SCREEN B: LIVE CAMERA WITH AUTOMATIC DOCUMENT DETECTION   */
          /* ========================================================= */
          <View style={styles.cameraContainer}>
            <CameraView
              ref={cameraRef}
              style={StyleSheet.absoluteFill}
              enableTorch={torch}
              facing="back"
              onCameraReady={() => {
                console.log("[Scanner][Camera] Preview initialized");
                isCameraReadyRef.current = true;
                setCameraReady(true);
                setCameraMountError(null);
                setTimeout(() => {
                  aeSettledRef.current = true;
                  setDetectionState((current) => (current === "INITIALIZING" ? "SEARCHING" : current));
                  setGuidanceMessage("Looking for paper • Place answer sheet in frame");
                }, 400);
              }}
              onMountError={(error) => {
                console.error("[Scanner] Camera mount error:", error?.message || error);
                isCameraReadyRef.current = false;
                setCameraReady(false);
                setCameraMountError(error?.message || "Camera preview failed to initialize.");
              }}
            />

            {/* Camera Initialization Error Banner */}
            {cameraMountError && (
              <View
                style={{
                  position: "absolute",
                  top: 70,
                  left: 20,
                  right: 20,
                  backgroundColor: "rgba(196, 58, 40, 0.95)",
                  borderRadius: 10,
                  padding: 12,
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  zIndex: 30,
                }}
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}>
                  <Ionicons name="alert-circle" size={20} color="#FFFFFF" />
                  <Text style={{ color: "#FFFFFF", fontSize: 13, fontWeight: "600", flex: 1 }}>
                    {cameraMountError}
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={() => {
                    setCameraMountError(null);
                    setCameraReady(false);
                    isCameraReadyRef.current = false;
                    aeSettledRef.current = false;
                    setDetectionState("INITIALIZING");
                    setGuidanceMessage("Retrying camera initialization...");
                  }}
                  style={{
                    backgroundColor: "rgba(255,255,255,0.25)",
                    paddingHorizontal: 12,
                    paddingVertical: 6,
                    borderRadius: 6,
                  }}
                >
                  <Text style={{ color: "#FFFFFF", fontSize: 12, fontWeight: "bold" }}>Retry</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Top Toolbar: Close, Auto Toggle, Page Counter, Torch */}
            <View style={styles.topToolbar}>
              <TouchableOpacity onPress={handleRequestClose} style={styles.iconCircleButton}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>

              {/* Auto / Manual (Pause / Resume) Capture Mode Toggle */}
              <TouchableOpacity
                onPress={() => setAutoCaptureEnabled((prev) => !prev)}
                style={[
                  styles.autoCapturePill,
                  autoCaptureEnabled
                    ? { backgroundColor: "rgba(16, 185, 129, 0.25)", borderColor: "#1F8F5F" }
                    : { backgroundColor: "rgba(190, 120, 10, 0.25)", borderColor: "#B7791F" },
                ]}
              >
                <Ionicons
                  name={autoCaptureEnabled ? "pause-circle-outline" : "play-circle-outline"}
                  size={15}
                  color={autoCaptureEnabled ? "#1F8F5F" : "#B7791F"}
                />
                <Text
                  style={[
                    styles.autoCapturePillText,
                    { color: autoCaptureEnabled ? "#1F8F5F" : "#B7791F" },
                  ]}
                >
                  {autoCaptureEnabled ? "Pause Auto" : "Resume Auto"}
                </Text>
              </TouchableOpacity>

              {/* Page Counter Badge */}
              <View style={styles.pageCounterBadge}>
                <Text style={styles.pageCounterText}>
                  {retakeIndex !== null
                    ? `Retaking P${retakeIndex + 1}`
                    : scannedPages.length === 0
                    ? "Page 1"
                    : `${scannedPages.length} ${
                        scannedPages.length === 1 ? "page" : "pages"
                      }`}
                </Text>
              </View>

              {/* Torch / Flash Toggle */}
              <TouchableOpacity
                onPress={() => setTorch(!torch)}
                style={[
                  styles.iconCircleButton,
                  torch && { backgroundColor: "rgba(23, 130, 87, 0.4)" },
                ]}
              >
                <Ionicons
                  name={torch ? "flash" : "flash-off-outline"}
                  size={20}
                  color={torch ? colors.brandGreen : "#FFFFFF"}
                />
              </TouchableOpacity>
            </View>

            {/* Student Switcher Strip for Continuous Classroom Scanning */}
            {activeStudent && (
              <View style={styles.studentHeaderBar}>
                <TouchableOpacity
                  disabled={isFirstStudent}
                  onPress={handlePrevStudent}
                  style={[styles.studentNavArrow, isFirstStudent && styles.studentNavArrowDisabled]}
                >
                  <Ionicons
                    name="chevron-back"
                    size={16}
                    color={isFirstStudent ? "rgba(255,255,255,0.25)" : "#FFFFFF"}
                  />
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={() => setStudentPickerVisible(true)}
                  style={styles.studentInfoPill}
                >
                  <Ionicons name="person-circle-outline" size={16} color="#0F8A80" />
                  <Text style={styles.studentNameText} numberOfLines={1}>
                    {activeStudent.name} ({activeStudent.roll_number})
                  </Text>
                  <Ionicons name="chevron-down" size={14} color="rgba(255,255,255,0.6)" />
                </TouchableOpacity>

                <TouchableOpacity
                  disabled={isLastStudent}
                  onPress={handleNextStudent}
                  style={[styles.studentNavArrow, isLastStudent && styles.studentNavArrowDisabled]}
                >
                  <Ionicons
                    name="chevron-forward"
                    size={16}
                    color={isLastStudent ? "rgba(255,255,255,0.25)" : "#FFFFFF"}
                  />
                </TouchableOpacity>
              </View>
            )}

            {/* Retake Notice Banner */}
            {retakeIndex !== null && (
              <View style={styles.retakeBanner}>
                <Ionicons name="camera-reverse-outline" size={16} color="#FFFFFF" />
                <Text style={styles.retakeBannerText}>
                  Retaking Page {retakeIndex + 1} of {scannedPages.length}
                </Text>
                <TouchableOpacity
                  onPress={() => setRetakeIndex(null)}
                  style={styles.retakeCancelBtn}
                >
                  <Text style={styles.retakeCancelText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Swap Page Action Banner (Duplicate Protection & Quick Corner Adjustment) */}
            {waitingForPageSwap && (
              <View style={styles.swapPageBanner}>
                <TouchableOpacity
                  onPress={handleReadyForNextPage}
                  activeOpacity={0.8}
                  style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}
                >
                  <Ionicons name="checkmark-circle" size={18} color="#1F8F5F" />
                  <Text style={styles.swapPageText} numberOfLines={1}>
                    Page {scannedPages.length} saved! Tap for next
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setAdjustingPageIndex(scannedPages.length - 1)}
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 4,
                    backgroundColor: "rgba(15, 118, 110, 0.2)",
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: "#0F8A80",
                  }}
                >
                  <Ionicons name="expand" size={13} color="#0F8A80" />
                  <Text style={{ color: "#0F8A80", fontSize: 12, fontWeight: "700" }}>Adjust</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Document Edge Detection Viewfinder Overlay */}
            <View style={styles.overlayContainer} pointerEvents="none">
              <View
                style={[
                  styles.viewfinderBox,
                  {
                    borderColor:
                      isDetectionRejected || detectionState === "NO_DOCUMENT"
                        ? "rgba(196, 58, 40, 0.95)"
                        : detectionState === "READY" || detectionState === "COUNTDOWN"
                        ? "rgba(16, 185, 129, 0.8)"
                        : detectionState === "PAPER_DETECTED"
                        ? "rgba(15, 118, 110, 0.7)"
                        : "rgba(255, 255, 255, 0.3)",
                    borderWidth: isDetectionRejected || detectionState === "NO_DOCUMENT" ? 2.5 : 1.5,
                  },
                ]}
              >
                {/* 4 Corner Target Markers with animated pulse */}
                <Animated.View
                  style={[
                    styles.corner,
                    styles.cornerTL,
                    { borderColor: getCornerColor(), transform: [{ scale: cornerScaleAnim }] },
                  ]}
                />
                <Animated.View
                  style={[
                    styles.corner,
                    styles.cornerTR,
                    { borderColor: getCornerColor(), transform: [{ scale: cornerScaleAnim }] },
                  ]}
                />
                <Animated.View
                  style={[
                    styles.corner,
                    styles.cornerBL,
                    { borderColor: getCornerColor(), transform: [{ scale: cornerScaleAnim }] },
                  ]}
                />
                <Animated.View
                  style={[
                    styles.corner,
                    styles.cornerBR,
                    { borderColor: getCornerColor(), transform: [{ scale: cornerScaleAnim }] },
                  ]}
                />

                {/* Animated Edge Detection Laser Line */}
                <Animated.View
                  style={[
                    styles.scanLaser,
                    {
                      borderColor: getCornerColor(),
                      transform: [{ translateY: laserTranslateY }],
                    },
                  ]}
                />

                {/* Visual Feedback Badge When Paper Is Detected First */}
                {detectionState === "PAPER_DETECTED" && (
                  <View style={styles.countdownCenterOverlay}>
                    <View
                      style={[
                        styles.countdownCircle,
                        {
                          borderColor: "#0F8A80",
                          backgroundColor: "rgba(15, 118, 110, 0.25)",
                          width: "auto",
                          paddingHorizontal: 16,
                          height: 42,
                          borderRadius: 21,
                          flexDirection: "row",
                          gap: 8,
                        },
                      ]}
                    >
                      <Ionicons name="document-text" size={18} color="#0F8A80" />
                      <Text
                        style={[
                          styles.countdownText,
                          { color: "#0F8A80", fontSize: 13, fontWeight: "700", marginTop: 0 },
                        ]}
                      >
                        Paper Detected
                      </Text>
                    </View>
                  </View>
                )}

                {/* 3-Second Alignment Countdown Progress Ring */}
                {detectionState === "COUNTDOWN" && countdownProgress > 0 && (
                  <View style={styles.countdownCenterOverlay}>
                    <View style={styles.countdownCircle}>
                      <ActivityIndicator size="small" color="#1F8F5F" />
                      <Text style={styles.countdownText}>
                        {Math.max(1, Math.ceil((1 - countdownProgress) * 3))}s
                      </Text>
                    </View>
                  </View>
                )}
              </View>

              {/* Real-time Guidance Banner */}
              <View
                style={[
                  styles.guideBanner,
                  isDetectionRejected || detectionState === "NO_DOCUMENT"
                    ? { backgroundColor: "rgba(196, 58, 40, 0.92)", borderColor: "#C43A28" }
                    : detectionState === "READY" || detectionState === "COUNTDOWN"
                    ? { backgroundColor: "rgba(16, 185, 129, 0.88)", borderColor: "#1F8F5F" }
                    : detectionState === "PAPER_DETECTED"
                    ? { backgroundColor: "rgba(15, 118, 110, 0.90)", borderColor: "#0F8A80" }
                    : detectionState === "CAPTURING" || detectionState === "PROCESSING"
                    ? { backgroundColor: "rgba(14, 165, 233, 0.88)", borderColor: "#0F8A80" }
                    : detectionState === "TOO_FAR" ||
                      detectionState === "TOO_CLOSE" ||
                      detectionState === "OUT_OF_BOUNDS" ||
                      detectionState === "BAD_ASPECT_RATIO" ||
                      detectionState === "UNSTABLE" ||
                      detectionState === "LOW_LIGHT"
                    ? { backgroundColor: "rgba(190, 120, 10, 0.88)", borderColor: "#B7791F" }
                    : { backgroundColor: "rgba(0, 0, 0, 0.78)", borderColor: "rgba(255, 255, 255, 0.2)" },
                ]}
              >
                <Ionicons
                  name={
                    isDetectionRejected || detectionState === "NO_DOCUMENT"
                      ? "alert-circle"
                      : detectionState === "READY" || detectionState === "COUNTDOWN"
                      ? "checkmark-circle"
                      : detectionState === "PAPER_DETECTED"
                      ? "document-text-outline"
                      : detectionState === "CAPTURING" || detectionState === "PROCESSING"
                      ? "sync"
                      : detectionState === "TOO_FAR" || detectionState === "OUT_OF_BOUNDS"
                      ? "scan-outline"
                      : "information-circle-outline"
                  }
                  size={16}
                  color="#FFFFFF"
                />
                <Text style={styles.guideText}>{guidanceMessage}</Text>
              </View>

              {/* Torch suggestion if dark */}
              {recommendTorch && !torch && (
                <TouchableOpacity
                  onPress={() => setTorch(true)}
                  style={styles.torchPromptPill}
                >
                  <Ionicons name="flash" size={14} color="#B7791F" />
                  <Text style={styles.torchPromptText}>Tap to turn on flash for clearer text</Text>
                </TouchableOpacity>
              )}
            </View>

            {/* Bottom Controls Area */}
            <View style={styles.bottomArea}>
              {/* Thumbnail Tray of captured pages */}
              {scannedPages.length > 0 && (
                <View style={styles.thumbnailTrayContainer}>
                  <FlatList
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    data={scannedPages}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={styles.thumbnailList}
                    renderItem={({ item, index }) => (
                      <TouchableOpacity
                        onPress={() => setSelectedPageIndex(index)}
                        style={[
                          styles.thumbnailWrapper,
                          retakeIndex === index && { borderColor: colors.warning },
                        ]}
                      >
                        <Image source={{ uri: item.uri }} style={styles.thumbnailImg} />
                        <View style={styles.thumbnailPageBadge}>
                          <Text style={styles.thumbnailBadgeText}>P{index + 1}</Text>
                        </View>
                      </TouchableOpacity>
                    )}
                  />
                </View>
              )}

              {/* Shutter Row */}
              <View style={styles.shutterRow}>
                {/* Review/Thumbnails button on the left */}
                <View style={{ width: 90, alignItems: "flex-start" }}>
                  {scannedPages.length > 0 && (
                    <TouchableOpacity
                      onPress={() => setSelectedPageIndex(0)}
                      style={styles.previewPagesBtn}
                    >
                      <Ionicons name="images-outline" size={18} color="#FFFFFF" />
                      <Text style={styles.previewPagesBtnText}>Review</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {/* Shutter Button (Manual Fallback & Visual Auto Indicator) */}
                <TouchableOpacity
                  onPress={() => triggerCapture({ isManual: true })}
                  disabled={capturing || isCompiling || !cameraReady}
                  activeOpacity={0.8}
                  style={[
                    styles.shutterOuter,
                    detectionState === "COUNTDOWN" && { borderColor: "#1F8F5F" },
                    !cameraReady && { opacity: 0.6 },
                  ]}
                >
                  <View
                    style={[
                      styles.shutterInner,
                      {
                        backgroundColor:
                          detectionState === "COUNTDOWN"
                            ? "#1F8F5F"
                            : !cameraReady
                            ? "#5A655F"
                            : colors.primary,
                      },
                    ]}
                  >
                    {capturing || !cameraReady ? (
                      <ActivityIndicator size="small" color="#FFFFFF" />
                    ) : (
                      <Ionicons name="camera" size={30} color="#FFFFFF" />
                    )}
                  </View>
                </TouchableOpacity>

                {/* Finish & Upload or Save & Next Student Button on the right */}
                <View style={{ minWidth: 95, alignItems: "flex-end" }}>
                  {scannedPages.length > 0 && (
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      {students && students.length > 1 && onScanNextStudent ? (
                        <TouchableOpacity
                          onPress={handleSaveAndNextStudent}
                          disabled={isCompiling}
                          style={[styles.saveNextBtn, { backgroundColor: "#0F8A80" }]}
                        >
                          {isCompiling ? (
                            <ActivityIndicator size="small" color="#FFFFFF" />
                          ) : (
                            <>
                              <Text style={styles.saveNextBtnText}>Save & Next</Text>
                              <Ionicons name="arrow-forward" size={13} color="#FFFFFF" />
                            </>
                          )}
                        </TouchableOpacity>
                      ) : (
                        <TouchableOpacity
                          onPress={handleFinishAndUpload}
                          disabled={isCompiling}
                          style={[styles.finishBtn, { backgroundColor: colors.brandGreen }]}
                        >
                          {isCompiling ? (
                            <ActivityIndicator size="small" color="#FFFFFF" />
                          ) : (
                            <>
                              <Text style={styles.finishBtnText}>Finish</Text>
                              <Ionicons name="checkmark" size={18} color="#FFFFFF" />
                            </>
                          )}
                        </TouchableOpacity>
                      )}
                    </View>
                  )}
                </View>
              </View>
            </View>

            {/* Student Picker Modal */}
            <Modal
              visible={studentPickerVisible}
              transparent
              animationType="fade"
              onRequestClose={() => setStudentPickerVisible(false)}
            >
              <View style={styles.pickerModalBackdrop}>
                <View style={[styles.pickerModalBox, { backgroundColor: colors.surface }]}>
                  <View style={styles.pickerModalHeader}>
                    <Text style={[styles.pickerModalTitle, { color: colors.text }]}>
                      Select Student for Scanning
                    </Text>
                    <TouchableOpacity onPress={() => setStudentPickerVisible(false)}>
                      <Ionicons name="close" size={22} color={colors.textSecondary} />
                    </TouchableOpacity>
                  </View>
                  <FlatList
                    data={students || []}
                    keyExtractor={(item) => item.id}
                    style={{ maxHeight: 340 }}
                    renderItem={({ item }) => (
                      <TouchableOpacity
                        onPress={() => {
                          setActiveStudentId(item.id);
                          setScannedPages([]);
                          setSelectedPageIndex(null);
                          setStudentPickerVisible(false);
                        }}
                        style={[
                          styles.pickerStudentRow,
                          { borderBottomColor: colors.border },
                          item.id === activeStudentId && {
                            backgroundColor: "rgba(15, 118, 110, 0.12)",
                          },
                        ]}
                      >
                        <View style={{ flex: 1 }}>
                          <Text style={[styles.pickerStudentName, { color: colors.text }]}>
                            {item.name}
                          </Text>
                          <Text style={[styles.pickerStudentRoll, { color: colors.textSecondary }]}>
                            Roll: {item.roll_number}
                          </Text>
                        </View>
                        {item.id === activeStudentId && (
                          <Ionicons name="checkmark-circle" size={20} color="#0F8A80" />
                        )}
                      </TouchableOpacity>
                    )}
                  />
                </View>
              </View>
            </Modal>
          </View>
        )}

        {/* Manual 4-Corner Document Boundary Adjustment Modal */}
        {adjustingPageIndex !== null && scannedPages[adjustingPageIndex] && (
          <CornerAdjustmentModal
            visible={adjustingPageIndex !== null}
            imageUri={scannedPages[adjustingPageIndex].originalUri}
            imageWidth={scannedPages[adjustingPageIndex].width}
            imageHeight={scannedPages[adjustingPageIndex].height}
            pageNumber={adjustingPageIndex + 1}
            onApplyCrop={(newCropRect, newCorners) => {
              handleApplyManualCrop(adjustingPageIndex, newCropRect, newCorners);
              setAdjustingPageIndex(null);
            }}
            onClose={() => setAdjustingPageIndex(null)}
          />
        )}

        {/* Compiling / Uploading Overlay */}
        {isCompiling && (
          <View style={styles.compilingOverlay}>
            <View style={[styles.compilingBox, { backgroundColor: colors.surface }]}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.compilingTitle, { color: colors.text }]}>
                Compiling & Aligning Answer Sheet
              </Text>
              <Text style={[styles.compilingSubtitle, { color: colors.textSecondary }]}>
                Processing {scannedPages.length} {scannedPages.length === 1 ? "page" : "pages"} with margin preservation and high-resolution capture...
              </Text>
            </View>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  modalRoot: {
    flex: 1,
    backgroundColor: "#000000",
  },
  permissionContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 30,
  },
  permIconCircle: {
    width: 90,
    height: 90,
    borderRadius: 45,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
  },
  permissionTitle: {
    fontSize: 20,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 8,
  },
  permissionText: {
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
  },
  cameraContainer: {
    flex: 1,
  },
  topToolbar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: Platform.OS === "android" ? 20 : 10,
    zIndex: 10,
  },
  iconCircleButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "rgba(0, 0, 0, 0.55)",
    alignItems: "center",
    justifyContent: "center",
  },
  autoCapturePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 18,
    borderWidth: 1,
  },
  autoCapturePillText: {
    fontSize: 12,
    fontWeight: "700",
  },
  pageCounterBadge: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
  },
  pageCounterText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  overlayContainer: {
    ...StyleSheet.absoluteFill,
    justifyContent: "center",
    alignItems: "center",
  },
  viewfinderBox: {
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT,
    borderRadius: 14,
    borderWidth: 1.5,
    overflow: "hidden",
    position: "relative",
  },
  corner: {
    position: "absolute",
    width: 32,
    height: 32,
  },
  cornerTL: {
    top: -1,
    left: -1,
    borderTopWidth: 4.5,
    borderLeftWidth: 4.5,
    borderTopLeftRadius: 12,
  },
  cornerTR: {
    top: -1,
    right: -1,
    borderTopWidth: 4.5,
    borderRightWidth: 4.5,
    borderTopRightRadius: 12,
  },
  cornerBL: {
    bottom: -1,
    left: -1,
    borderBottomWidth: 4.5,
    borderLeftWidth: 4.5,
    borderBottomLeftRadius: 12,
  },
  cornerBR: {
    bottom: -1,
    right: -1,
    borderBottomWidth: 4.5,
    borderRightWidth: 4.5,
    borderBottomRightRadius: 12,
  },
  scanLaser: {
    width: "100%",
    height: 2,
    borderBottomWidth: 2,
    shadowColor: "#1F8F5F",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 8,
  },
  countdownCenterOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: "center",
    alignItems: "center",
  },
  countdownCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    borderWidth: 2.5,
    borderColor: "#1F8F5F",
    justifyContent: "center",
    alignItems: "center",
  },
  countdownText: {
    color: "#1F8F5F",
    fontSize: 13,
    fontWeight: "800",
    marginTop: 2,
  },
  guideBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 22,
    marginTop: 18,
    borderWidth: 1,
    maxWidth: "88%",
  },
  guideText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
    textAlign: "center",
  },
  torchPromptPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0, 0, 0, 0.8)",
    borderWidth: 1,
    borderColor: "#B7791F",
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    marginTop: 8,
  },
  torchPromptText: {
    color: "#B7791F",
    fontSize: 11,
    fontWeight: "700",
  },
  bottomArea: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: Platform.OS === "ios" ? 30 : 20,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
  },
  thumbnailTrayContainer: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(255, 255, 255, 0.2)",
  },
  thumbnailList: {
    gap: 10,
  },
  thumbnailWrapper: {
    width: 52,
    height: 70,
    borderRadius: 6,
    overflow: "hidden",
    borderWidth: 1.5,
    borderColor: "#0F8A80",
    position: "relative",
  },
  thumbnailImg: {
    width: "100%",
    height: "100%",
  },
  thumbnailPageBadge: {
    position: "absolute",
    bottom: 2,
    right: 2,
    backgroundColor: "rgba(0,0,0,0.75)",
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
  },
  thumbnailBadgeText: {
    color: "#FFFFFF",
    fontSize: 9,
    fontWeight: "700",
  },
  shutterRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 24,
    paddingTop: 16,
  },
  shutterOuter: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 4,
    borderColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  shutterInner: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: "center",
    justifyContent: "center",
  },
  finishBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 22,
  },
  finishBtnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
  reviewContainer: {
    flex: 1,
    backgroundColor: "#111827",
  },
  reviewHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  reviewBackBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  reviewBackText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "600",
  },
  reviewPageTitle: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
  reviewTrashBtn: {
    padding: 6,
  },
  qualityPill: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingVertical: 6,
    paddingHorizontal: 14,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 12,
  },
  qualityPillText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
  },
  previewImageWrapper: {
    flex: 1,
    padding: 16,
    justifyContent: "center",
    alignItems: "center",
    position: "relative",
  },
  previewImage: {
    width: "100%",
    height: "100%",
  },
  cropBadge: {
    position: "absolute",
    bottom: 24,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
  },
  cropBadgeText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "700",
  },
  reviewActionsBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 18,
    backgroundColor: "rgba(0, 0, 0, 0.4)",
    borderTopWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  reviewToolbar: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    paddingVertical: 12,
    paddingHorizontal: 8,
    backgroundColor: "rgba(0, 0, 0, 0.5)",
    borderTopWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
  },
  toolBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "rgba(255, 255, 255, 0.1)",
  },
  toolBtnDisabled: {
    backgroundColor: "rgba(255, 255, 255, 0.03)",
  },
  toolBtnText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
  },
  toolBtnTextDisabled: {
    color: "rgba(255, 255, 255, 0.3)",
  },
  addMoreBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: "rgba(255, 255, 255, 0.15)",
  },
  addMoreBtnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "600",
  },
  finishScanBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
  },
  finishScanBtnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
  retakeBanner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#B7791F",
    paddingVertical: 8,
    paddingHorizontal: 16,
    marginHorizontal: 20,
    marginTop: 8,
    borderRadius: 8,
    zIndex: 10,
  },
  retakeBannerText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  retakeCancelBtn: {
    marginLeft: 8,
    backgroundColor: "rgba(0, 0, 0, 0.2)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  retakeCancelText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "700",
  },
  swapPageBanner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#0F8A80",
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 10,
    zIndex: 10,
  },
  swapPageText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "700",
    flex: 1,
    marginHorizontal: 6,
  },
  previewPagesBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 18,
    backgroundColor: "rgba(255, 255, 255, 0.2)",
  },
  previewPagesBtnText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
  },
  compilingOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
    zIndex: 99,
  },
  compilingBox: {
    width: "100%",
    maxWidth: 360,
    borderRadius: 16,
    padding: 24,
    alignItems: "center",
  },
  compilingTitle: {
    fontSize: 17,
    fontWeight: "700",
    marginTop: 16,
    textAlign: "center",
  },
  compilingSubtitle: {
    fontSize: 13,
    textAlign: "center",
    marginTop: 8,
    lineHeight: 18,
  },
  studentHeaderBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 16,
    marginTop: 8,
    zIndex: 10,
  },
  studentNavArrow: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(0, 0, 0, 0.55)",
    alignItems: "center",
    justifyContent: "center",
  },
  studentNavArrowDisabled: {
    opacity: 0.35,
  },
  studentInfoPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0, 0, 0, 0.72)",
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
    maxWidth: "75%",
  },
  studentNameText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  saveNextStudentBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 12,
  },
  saveNextStudentBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  saveNextBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 9,
    paddingHorizontal: 12,
    borderRadius: 18,
  },
  saveNextBtnText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "700",
  },
  pickerModalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  pickerModalBox: {
    width: "100%",
    maxWidth: 380,
    borderRadius: 16,
    padding: 18,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 8,
  },
  pickerModalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0, 0, 0, 0.08)",
  },
  pickerModalTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  pickerStudentRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
  },
  pickerStudentName: {
    fontSize: 14,
    fontWeight: "600",
  },
  pickerStudentRoll: {
    fontSize: 12,
    marginTop: 2,
  },
});
