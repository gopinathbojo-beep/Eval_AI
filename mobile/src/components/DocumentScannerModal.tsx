import React, { useState, useRef, useEffect } from "react";
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
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { CameraView, useCameraPermissions } from "expo-camera";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { printToFileAsync } from "expo-print";
import * as FileSystem from "expo-file-system/legacy";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { Button } from "./Button";

interface ScannedPage {
  id: string;
  uri: string;
  width: number;
  height: number;
  rotation: number;
  base64?: string;
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

interface DocumentScannerModalProps {
  visible: boolean;
  onClose: () => void;
  onComplete: (file: DocumentScannerResult) => Promise<void>;
  examTitle?: string;
  title?: string;
  docTitlePrefix?: string;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

// Standard document aspect ratio (A4 is approx 1:1.414)
const FRAME_WIDTH = Math.min(SCREEN_WIDTH * 0.88, 380);
const FRAME_HEIGHT = Math.min(FRAME_WIDTH * 1.414, SCREEN_HEIGHT * 0.62);

export const DocumentScannerModal: React.FC<DocumentScannerModalProps> = ({
  visible,
  onClose,
  onComplete,
  examTitle = "Document",
  title = "Document Scanner",
  docTitlePrefix = "QP",
}) => {
  const { colors } = useTheme();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  const [scannedPages, setScannedPages] = useState<ScannedPage[]>([]);
  const [torch, setTorch] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number | null>(null);
  const [retakeIndex, setRetakeIndex] = useState<number | null>(null);
  const [isCompiling, setIsCompiling] = useState(false);

  // Animated laser scan effect for auto edge detection feedback
  const scanAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible && selectedPageIndex === null) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(scanAnim, {
            toValue: 1,
            duration: 2200,
            useNativeDriver: true,
          }),
          Animated.timing(scanAnim, {
            toValue: 0,
            duration: 2200,
            useNativeDriver: true,
          }),
        ])
      ).start();
    }
  }, [visible, selectedPageIndex, scanAnim]);

  // Reset state when modal is opened/closed
  useEffect(() => {
    if (!visible) {
      setScannedPages([]);
      setSelectedPageIndex(null);
      setRetakeIndex(null);
      setCapturing(false);
      setIsCompiling(false);
      setTorch(false);
    }
  }, [visible]);

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
          <View style={[styles.permIconCircle, { backgroundColor: "rgba(7, 159, 189, 0.12)" }]}>
            <Ionicons name="camera-outline" size={48} color={colors.primary} />
          </View>
          <Text style={[styles.permissionTitle, { color: colors.text }]}>
            Camera Access Required
          </Text>
          <Text style={[styles.permissionText, { color: colors.textSecondary }]}>
            Eval AI uses your camera to scan student answer sheets across multiple pages with automated boundary detection and straightening.
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

  /**
   * Captures the page, calculates document boundary coordinates relative to the full
   * photo resolution, and automatically crops out surrounding background/desk area.
   */
  const handleCapturePage = async () => {
    if (!cameraRef.current || capturing) return;

    try {
      setCapturing(true);

      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.95,
        base64: true,
        skipProcessing: false,
      });

      if (!photo || !photo.uri) {
        throw new Error("Camera capture returned empty photo.");
      }

      // Calculate relative framing of the document boundary
      const photoWidth = photo.width;
      const photoHeight = photo.height;

      const frameRatioX = FRAME_WIDTH / SCREEN_WIDTH;
      const frameRatioY = FRAME_HEIGHT / SCREEN_HEIGHT;

      const cropWidth = Math.round(photoWidth * Math.min(frameRatioX * 1.1, 0.92));
      const cropHeight = Math.round(photoHeight * Math.min(frameRatioY * 1.1, 0.92));
      const originX = Math.max(0, Math.round((photoWidth - cropWidth) / 2));
      const originY = Math.max(0, Math.round((photoHeight - cropHeight) / 2));

      // Automatically crop to detected paper edges and resize with high fidelity (1600px)
      const cropped = await manipulateAsync(
        photo.uri,
        [
          {
            crop: {
              originX,
              originY,
              width: cropWidth,
              height: cropHeight,
            },
          },
          {
            resize: { width: 1600 },
          },
        ],
        {
          compress: 0.92,
          format: SaveFormat.JPEG,
          base64: true,
        }
      );

      const pageNumber = retakeIndex !== null ? retakeIndex + 1 : scannedPages.length + 1;
      const newPage: ScannedPage = {
        id: `page_${Date.now()}_${pageNumber}`,
        uri: cropped.uri,
        width: cropped.width,
        height: cropped.height,
        rotation: 0,
        base64: cropped.base64,
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
      }
    } catch (err: any) {
      Alert.alert("Capture Failed", err.message || "Could not capture document page.");
    } finally {
      setCapturing(false);
    }
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
   * Compiles all scanned pages into a unified multi-page PDF document
   * and returns both the compiled document and the individual page assets
   */
  const handleFinishAndUpload = async () => {
    if (scannedPages.length === 0) {
      Alert.alert("No Pages Scanned", "Please scan at least one page before finishing.");
      return;
    }

    try {
      setIsCompiling(true);

      const cleanTitle = examTitle.replace(/[^a-zA-Z0-9_-]/g, "_");
      const prefix = docTitlePrefix || "Doc";

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
            ${scannedPages
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

      const individualPages: ScannedPageAsset[] = scannedPages.map((p, idx) => ({
        uri: p.uri,
        name: `${cleanTitle}_${prefix}_Page_${idx + 1}.jpg`,
        mimeType: "image/jpeg",
      }));

      const uploadResult: DocumentScannerResult = {
        uri: safePdfUri,
        name: `${cleanTitle}_${prefix}_${scannedPages.length}_Pages.pdf`,
        type: "application/pdf",
        pages: individualPages,
        pageCount: scannedPages.length,
      };

      await onComplete(uploadResult);
      onClose();
    } catch (err: any) {
      Alert.alert("Processing Failed", err.message || "Failed to process and compile scanned pages.");
    } finally {
      setIsCompiling(false);
    }
  };

  const laserTranslateY = scanAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, FRAME_HEIGHT - 4],
  });

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.modalRoot}>
        {/* If user is reviewing/editing an existing page */}
        {selectedPageIndex !== null && scannedPages[selectedPageIndex] ? (
          <View style={styles.reviewContainer}>
            <View style={styles.reviewHeader}>
              <TouchableOpacity
                onPress={() => setSelectedPageIndex(null)}
                style={styles.reviewBackBtn}
              >
                <Ionicons name="camera-outline" size={20} color="#FFFFFF" />
                <Text style={styles.reviewBackText}>Capture More</Text>
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

            <View style={styles.previewImageWrapper}>
              <Image
                source={{ uri: scannedPages[selectedPageIndex].uri }}
                style={styles.previewImage}
                resizeMode="contain"
              />
            </View>

            {/* Page manipulation toolbar: Move, Rotate, Retake */}
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
                onPress={() => {
                  const target = selectedPageIndex;
                  setSelectedPageIndex(null);
                  setRetakeIndex(target);
                }}
                style={styles.toolBtn}
              >
                <Ionicons name="camera-reverse-outline" size={18} color="#FFFFFF" />
                <Text style={styles.toolBtnText}>Retake Page</Text>
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
                <Text style={styles.addMoreBtnText}>Add More Pages</Text>
              </TouchableOpacity>

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
                      Finish ({scannedPages.length} {scannedPages.length === 1 ? "page" : "pages"})
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          /* Live Scanner View */
          <View style={styles.cameraContainer}>
            <CameraView
              ref={cameraRef}
              style={StyleSheet.absoluteFill}
              enableTorch={torch}
              facing="back"
            />

            {/* Top Toolbar */}
            <View style={styles.topToolbar}>
              <TouchableOpacity onPress={handleRequestClose} style={styles.iconCircleButton}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>

              <View style={styles.pageCounterBadge}>
                <Text style={styles.pageCounterText}>
                  {retakeIndex !== null
                    ? `Retaking Page ${retakeIndex + 1}`
                    : scannedPages.length === 0
                    ? "Page 1"
                    : `${scannedPages.length} ${
                        scannedPages.length === 1 ? "page" : "pages"
                      } captured`}
                </Text>
              </View>

              <TouchableOpacity
                onPress={() => setTorch(!torch)}
                style={[
                  styles.iconCircleButton,
                  torch && { backgroundColor: "rgba(81, 188, 117, 0.4)" },
                ]}
              >
                <Ionicons
                  name={torch ? "flash" : "flash-off-outline"}
                  size={20}
                  color={torch ? colors.brandGreen : "#FFFFFF"}
                />
              </TouchableOpacity>
            </View>

            {/* Retake Alert Banner if in retake mode */}
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

            {/* Edge Detection Viewfinder Overlay */}
            <View style={styles.overlayContainer} pointerEvents="none">
              <View style={styles.viewfinderBox}>
                {/* 4 Corner Target Markers */}
                <View style={[styles.corner, styles.cornerTL, { borderColor: colors.primary }]} />
                <View style={[styles.corner, styles.cornerTR, { borderColor: colors.primary }]} />
                <View style={[styles.corner, styles.cornerBL, { borderColor: colors.primary }]} />
                <View style={[styles.corner, styles.cornerBR, { borderColor: colors.primary }]} />

                {/* Animated Edge Detection Guide Line */}
                <Animated.View
                  style={[
                    styles.scanLaser,
                    {
                      borderColor: colors.brandGreen,
                      transform: [{ translateY: laserTranslateY }],
                    },
                  ]}
                />
              </View>

              <View style={styles.guideBanner}>
                <Ionicons name="scan-outline" size={16} color={colors.primary} />
                <Text style={styles.guideText}>
                  Align paper edges inside the frame • Auto-cropping active
                </Text>
              </View>
            </View>

            {/* Bottom Controls Area */}
            <View style={styles.bottomArea}>
              {/* Thumbnail Tray of captured pages in sequence */}
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

              {/* Shutter Button & Controls */}
              <View style={styles.shutterRow}>
                {/* Preview Pages button on the left */}
                <View style={{ width: 90, alignItems: "flex-start" }}>
                  {scannedPages.length > 0 && (
                    <TouchableOpacity
                      onPress={() => setSelectedPageIndex(0)}
                      style={styles.previewPagesBtn}
                    >
                      <Ionicons name="images-outline" size={18} color="#FFFFFF" />
                      <Text style={styles.previewPagesBtnText}>Preview</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {/* Capture Button */}
                <TouchableOpacity
                  onPress={handleCapturePage}
                  disabled={capturing || isCompiling}
                  activeOpacity={0.8}
                  style={styles.shutterOuter}
                >
                  <View style={[styles.shutterInner, { backgroundColor: colors.primary }]}>
                    {capturing ? (
                      <ActivityIndicator size="small" color="#FFFFFF" />
                    ) : (
                      <Ionicons name="camera" size={30} color="#FFFFFF" />
                    )}
                  </View>
                </TouchableOpacity>

                {/* Finish & Upload Sequence Button on the right */}
                <View style={{ width: 90, alignItems: "flex-end" }}>
                  {scannedPages.length > 0 && (
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
              </View>
            </View>
          </View>
        )}

        {/* Compiling / Uploading Overlay */}
        {isCompiling && (
          <View style={styles.compilingOverlay}>
            <View style={[styles.compilingBox, { backgroundColor: colors.surface }]}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.compilingTitle, { color: colors.text }]}>
                Processing Scanned Question Paper
              </Text>
              <Text style={[styles.compilingSubtitle, { color: colors.textSecondary }]}>
                Compiling {scannedPages.length} {scannedPages.length === 1 ? "page" : "pages"} into aligned document for page reading...
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
    paddingHorizontal: 20,
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
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.3)",
    overflow: "hidden",
    position: "relative",
  },
  corner: {
    position: "absolute",
    width: 28,
    height: 28,
  },
  cornerTL: {
    top: -1,
    left: -1,
    borderTopWidth: 4,
    borderLeftWidth: 4,
    borderTopLeftRadius: 10,
  },
  cornerTR: {
    top: -1,
    right: -1,
    borderTopWidth: 4,
    borderRightWidth: 4,
    borderTopRightRadius: 10,
  },
  cornerBL: {
    bottom: -1,
    left: -1,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderBottomLeftRadius: 10,
  },
  cornerBR: {
    bottom: -1,
    right: -1,
    borderBottomWidth: 4,
    borderRightWidth: 4,
    borderBottomRightRadius: 10,
  },
  scanLaser: {
    width: "100%",
    height: 2,
    borderBottomWidth: 2,
    shadowColor: "#51BC75",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 6,
  },
  guideBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0, 0, 0, 0.7)",
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
    marginTop: 16,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  guideText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
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
    borderColor: "#079FBD",
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
    backgroundColor: "#101719",
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
  previewImageWrapper: {
    flex: 1,
    padding: 16,
    justifyContent: "center",
    alignItems: "center",
  },
  previewImage: {
    width: "100%",
    height: "100%",
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
    backgroundColor: "#F59E0B",
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
});
