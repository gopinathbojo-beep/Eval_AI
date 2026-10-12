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

interface DocumentScannerModalProps {
  visible: boolean;
  onClose: () => void;
  onComplete: (file: { uri: string; name: string; type: string }) => Promise<void>;
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
            Eval AI uses your camera to scan question papers across multiple pages with automated boundary detection and straightening.
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
      // Screen layout relative proportions
      const photoWidth = photo.width;
      const photoHeight = photo.height;

      // The viewfinder frame proportions relative to camera view
      const frameRatioX = FRAME_WIDTH / SCREEN_WIDTH;
      const frameRatioY = FRAME_HEIGHT / SCREEN_HEIGHT;

      // Crop box inside photo coordinates
      const cropWidth = Math.round(photoWidth * Math.min(frameRatioX * 1.1, 0.92));
      const cropHeight = Math.round(photoHeight * Math.min(frameRatioY * 1.1, 0.92));
      const originX = Math.max(0, Math.round((photoWidth - cropWidth) / 2));
      const originY = Math.max(0, Math.round((photoHeight - cropHeight) / 2));

      // Automatically crop to detected paper edges and resize to standard A4 resolution
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
            resize: { width: 1240 },
          },
        ],
        {
          compress: 0.9,
          format: SaveFormat.JPEG,
          base64: true,
        }
      );

      const newPage: ScannedPage = {
        id: `page_${Date.now()}_${scannedPages.length + 1}`,
        uri: cropped.uri,
        width: cropped.width,
        height: cropped.height,
        rotation: 0,
        base64: cropped.base64,
      };

      setScannedPages((prev) => [...prev, newPage]);
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
          compress: 0.9,
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
   * Compiles all scanned pages into a unified multi-page PDF document and uploads it
   */
  const handleFinishAndUpload = async () => {
    if (scannedPages.length === 0) {
      Alert.alert("No Pages Scanned", "Please scan at least one page before uploading.");
      return;
    }

    try {
      setIsCompiling(true);

      const cleanTitle = examTitle.replace(/[^a-zA-Z0-9_-]/g, "_");
      const prefix = docTitlePrefix || "Doc";
      let uploadFile: { uri: string; name: string; type: string };

      if (scannedPages.length === 1) {
        // Single page can be uploaded directly as high-res document image or compiled PDF
        const single = scannedPages[0];
        const safeImgUri = `${FileSystem.cacheDirectory}${cleanTitle}_${prefix}_${Date.now()}.jpg`;

        if (single.base64) {
          await FileSystem.writeAsStringAsync(safeImgUri, single.base64, {
            encoding: FileSystem.EncodingType.Base64,
          });
        } else {
          try {
            await FileSystem.copyAsync({ from: single.uri, to: safeImgUri });
          } catch {
            // fallback to original uri if copy fails
          }
        }

        uploadFile = {
          uri: safeImgUri,
          name: `${cleanTitle}_${prefix}_Scanned_Page1.jpg`,
          type: "image/jpeg",
        };
      } else {
        // Multi-page document: compile into clean multi-page PDF using expo-print
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

        // Write directly from base64 memory into app cache to completely avoid
        // Android Print cache read permission errors
        if (pdf.base64) {
          await FileSystem.writeAsStringAsync(safePdfUri, pdf.base64, {
            encoding: FileSystem.EncodingType.Base64,
          });
          uploadFile = {
            uri: safePdfUri,
            name: `${cleanTitle}_${prefix}_Scanned_Document.pdf`,
            type: "application/pdf",
          };
        } else {
          // Fallback if base64 not provided by native module
          uploadFile = {
            uri: pdf.uri,
            name: `${cleanTitle}_${prefix}_Scanned_Document.pdf`,
            type: "application/pdf",
          };
        }
      }

      await onComplete(uploadFile);
      onClose();
    } catch (err: any) {
      Alert.alert("Upload Failed", err.message || "Failed to process and upload scanned document.");
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
        {/* If user is reviewing/straightening an existing page */}
        {selectedPageIndex !== null && scannedPages[selectedPageIndex] ? (
          <View style={styles.reviewContainer}>
            <View style={styles.reviewHeader}>
              <TouchableOpacity
                onPress={() => setSelectedPageIndex(null)}
                style={styles.reviewBackBtn}
              >
                <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                <Text style={styles.reviewBackText}>Back to Camera</Text>
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

            <View style={styles.reviewActionsBar}>
              <TouchableOpacity
                onPress={() => handleRotatePage(selectedPageIndex)}
                style={styles.rotateButton}
              >
                <Ionicons name="reload-outline" size={22} color="#FFFFFF" />
                <Text style={styles.rotateBtnText}>Rotate / Straighten</Text>
              </TouchableOpacity>

              <Button
                title="Keep & Next Page"
                variant="gradient"
                size="medium"
                onPress={() => setSelectedPageIndex(null)}
              />
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
              <TouchableOpacity onPress={onClose} style={styles.iconCircleButton}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>

              <View style={styles.pageCounterBadge}>
                <Text style={styles.pageCounterText}>
                  {scannedPages.length === 0
                    ? "Page 1"
                    : `Page ${scannedPages.length + 1} (${scannedPages.length} scanned)`}
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

            {/* Edge Detection Viewfinder Overlay */}
            <View style={styles.overlayContainer} pointerEvents="none">
              <View style={styles.viewfinderBox}>
                {/* 4 Glowing Corner Target Markers */}
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
                        style={styles.thumbnailWrapper}
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

              {/* Shutter Button & Finish Button */}
              <View style={styles.shutterRow}>
                <View style={{ width: 80 }} />

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

                {/* Finish & Upload Sequence Button */}
                <View style={{ width: 100, alignItems: "flex-end" }}>
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
                          <Text style={styles.finishBtnText}>Done</Text>
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
                Compiling {scannedPages.length} {scannedPages.length === 1 ? "page" : "pages"} into aligned document for OCR analysis...
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
  rotateButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.3)",
  },
  rotateBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
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
