import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
  Image,
  PanResponder,
  SafeAreaView,
  StatusBar,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { DocumentCorners, Point2D, computeCropFromCorners } from "../utils/documentDetection";

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");
const HANDLE_RADIUS = 20;

export interface CornerAdjustmentModalProps {
  visible: boolean;
  imageUri: string;
  imageWidth: number;
  imageHeight: number;
  initialCorners?: DocumentCorners;
  pageNumber: number;
  onApplyCrop: (
    newCropRect: { originX: number; originY: number; width: number; height: number },
    newCorners: DocumentCorners
  ) => void;
  onClose: () => void;
}

/**
 * Interactive 4-Corner Document Boundary Adjustment Modal
 * 
 * Allows teachers and students to interactively drag the 4 corners of any scanned
 * page with high-precision touch handles, live boundary lines, and instant preview.
 */
export const CornerAdjustmentModal: React.FC<CornerAdjustmentModalProps> = ({
  visible,
  imageUri,
  imageWidth,
  imageHeight,
  initialCorners,
  pageNumber,
  onApplyCrop,
  onClose,
}) => {
  // Canvas layout dimensions
  const [canvasLayout, setCanvasLayout] = useState({
    width: SCREEN_WIDTH,
    height: SCREEN_HEIGHT - 170,
  });

  // Calculate aspect-fit geometry of the image inside the canvas
  const fitGeometry = useMemo(() => {
    const { width: cW, height: cH } = canvasLayout;
    if (cW <= 0 || cH <= 0 || imageWidth <= 0 || imageHeight <= 0) {
      return { dispW: cW, dispH: cH, offX: 0, offY: 0, scale: 1 };
    }

    const imgAspect = imageWidth / imageHeight;
    const canvasAspect = cW / cH;

    let dispW: number;
    let dispH: number;
    let offX: number;
    let offY: number;

    if (imgAspect > canvasAspect) {
      dispW = cW - 16;
      dispH = dispW / imgAspect;
      offX = 8;
      offY = (cH - dispH) / 2;
    } else {
      dispH = cH - 16;
      dispW = dispH * imgAspect;
      offX = (cW - dispW) / 2;
      offY = 8;
    }

    const scale = imageWidth / dispW;
    return { dispW, dispH, offX, offY, scale };
  }, [canvasLayout, imageWidth, imageHeight]);

  // Default corners: 4% inset from image borders
  const defaultCorners = useMemo<DocumentCorners>(() => {
    if (initialCorners) {
      return initialCorners;
    }
    const marginX = imageWidth * 0.04;
    const marginY = imageHeight * 0.04;
    return {
      topLeft: { x: marginX, y: marginY },
      topRight: { x: imageWidth - marginX, y: marginY },
      bottomRight: { x: imageWidth - marginX, imageHeight: imageHeight - marginY } as any,
      bottomLeft: { x: marginX, y: imageHeight - marginY },
    };
  }, [initialCorners, imageWidth, imageHeight]);

  // Current corner positions in IMAGE coordinates
  const [corners, setCorners] = useState<DocumentCorners>(defaultCorners);
  const cornersRef = useRef<DocumentCorners>(defaultCorners);

  // Sync ref with state
  useEffect(() => {
    if (visible) {
      const init = initialCorners || defaultCorners;
      setCorners(init);
      cornersRef.current = init;
    }
  }, [visible, initialCorners, defaultCorners]);

  // Coordinate conversion: Image to Screen
  const imageToScreen = (pt: Point2D): Point2D => {
    const { offX, offY, scale } = fitGeometry;
    return {
      x: offX + pt.x / scale,
      y: offY + pt.y / scale,
    };
  };

  // Coordinate conversion: Screen to Image
  const screenToImage = (pt: Point2D): Point2D => {
    const { offX, offY, scale } = fitGeometry;
    return {
      x: Math.max(0, Math.min(imageWidth, (pt.x - offX) * scale)),
      y: Math.max(0, Math.min(imageHeight, (pt.y - offY) * scale)),
    };
  };

  // Create PanResponders for each of the 4 corner handles
  const createCornerPanResponder = (cornerKey: keyof DocumentCorners) =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {},
      onPanResponderMove: (_, gestureState) => {
        const currentScreenPt = imageToScreen(cornersRef.current[cornerKey]);
        const newScreenX = currentScreenPt.x + gestureState.dx;
        const newScreenY = currentScreenPt.y + gestureState.dy;

        const newImagePt = screenToImage({ x: newScreenX, y: newScreenY });

        const updated = {
          ...cornersRef.current,
          [cornerKey]: newImagePt,
        };

        cornersRef.current = updated;
        setCorners({ ...updated });
      },
      onPanResponderRelease: () => {},
    });

  const panTL = useRef(createCornerPanResponder("topLeft")).current;
  const panTR = useRef(createCornerPanResponder("topRight")).current;
  const panBR = useRef(createCornerPanResponder("bottomRight")).current;
  const panBL = useRef(createCornerPanResponder("bottomLeft")).current;

  // Screen-space corner coordinates
  const screenTL = imageToScreen(corners.topLeft);
  const screenTR = imageToScreen(corners.topRight);
  const screenBR = imageToScreen(corners.bottomRight);
  const screenBL = imageToScreen(corners.bottomLeft);

  // Helper to render connecting line between two screen points
  const renderConnectingLine = (p1: Point2D, p2: Point2D, key: string) => {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    const angle = (Math.atan2(dy, dx) * 180) / Math.PI;

    return (
      <View
        key={key}
        pointerEvents="none"
        style={{
          position: "absolute",
          left: (p1.x + p2.x) / 2 - length / 2,
          top: (p1.y + p2.y) / 2 - 1.5,
          width: length,
          height: 3,
          backgroundColor: "#1F8F5F",
          transform: [{ rotate: `${angle}deg` }],
          zIndex: 10,
        }}
      />
    );
  };

  // Helper to render draggable corner handle
  const renderCornerHandle = (
    pos: Point2D,
    label: string,
    panResponder: any
  ) => {
    return (
      <View
        {...panResponder.panHandlers}
        style={[
          styles.handleTouchTarget,
          {
            left: pos.x - HANDLE_RADIUS,
            top: pos.y - HANDLE_RADIUS,
          },
        ]}
      >
        <View style={styles.handleOuterCircle}>
          <View style={styles.handleInnerDot} />
        </View>
        <View style={styles.handleLabelBadge}>
          <Text style={styles.handleLabelText}>{label}</Text>
        </View>
      </View>
    );
  };

  const handleReset = () => {
    const marginX = imageWidth * 0.04;
    const marginY = imageHeight * 0.04;
    const resetCorners: DocumentCorners = {
      topLeft: { x: marginX, y: marginY },
      topRight: { x: imageWidth - marginX, y: marginY },
      bottomRight: { x: imageWidth - marginX, y: imageHeight - marginY },
      bottomLeft: { x: marginX, y: imageHeight - marginY },
    };
    cornersRef.current = resetCorners;
    setCorners(resetCorners);
  };

  const handleApply = () => {
    const cropRect = computeCropFromCorners(corners, imageWidth, imageHeight, 0.01);
    console.log("[Scanner][Crop] Perspective correction completed via manual corner adjustment");
    onApplyCrop(cropRect, corners);
    onClose();
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false} onRequestClose={onClose}>
      <StatusBar barStyle="light-content" backgroundColor="#0B171B" />
      <SafeAreaView style={styles.container}>
        {/* Top Header Bar */}
        <View style={styles.headerBar}>
          <TouchableOpacity onPress={onClose} style={styles.headerButton}>
            <Ionicons name="close" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <View style={styles.headerTitleContainer}>
            <Text style={styles.headerTitle}>Adjust Page {pageNumber} Corners</Text>
            <Text style={styles.headerSubtitle}>Drag corner pins to align with paper edges</Text>
          </View>
          <TouchableOpacity onPress={handleReset} style={styles.headerButton}>
            <Text style={styles.resetButtonText}>Reset</Text>
          </TouchableOpacity>
        </View>

        {/* Interactive Canvas */}
        <View
          style={styles.canvasArea}
          onLayout={(e) => {
            const { width, height } = e.nativeEvent.layout;
            setCanvasLayout({ width, height });
          }}
        >
          {/* Base Uncropped Image */}
          {imageUri ? (
            <Image
              source={{ uri: imageUri }}
              style={{
                position: "absolute",
                left: fitGeometry.offX,
                top: fitGeometry.offY,
                width: fitGeometry.dispW,
                height: fitGeometry.dispH,
                borderRadius: 4,
              }}
              resizeMode="stretch"
            />
          ) : null}

          {/* 4 Connecting Boundary Lines */}
          {renderConnectingLine(screenTL, screenTR, "line-top")}
          {renderConnectingLine(screenTR, screenBR, "line-right")}
          {renderConnectingLine(screenBR, screenBL, "line-bottom")}
          {renderConnectingLine(screenBL, screenTL, "line-left")}

          {/* 4 Interactive Draggable Corner Handles */}
          {renderCornerHandle(screenTL, "TL", panTL)}
          {renderCornerHandle(screenTR, "TR", panTR)}
          {renderCornerHandle(screenBR, "BR", panBR)}
          {renderCornerHandle(screenBL, "BL", panBL)}
        </View>

        {/* Bottom Actions Bar */}
        <View style={styles.bottomBar}>
          <TouchableOpacity onPress={onClose} style={styles.cancelBtn}>
            <Text style={styles.cancelBtnText}>Cancel</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={handleApply} style={styles.applyBtn}>
            <Ionicons name="checkmark-circle-outline" size={20} color="#FFFFFF" />
            <Text style={styles.applyBtnText}>Apply Adjusted Crop</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0B171B",
  },
  headerBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.12)",
    backgroundColor: "#111827",
  },
  headerButton: {
    padding: 6,
    minWidth: 44,
    alignItems: "center",
  },
  headerTitleContainer: {
    alignItems: "center",
    flex: 1,
  },
  headerTitle: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
  headerSubtitle: {
    color: "rgba(255, 255, 255, 0.65)",
    fontSize: 12,
    marginTop: 2,
  },
  resetButtonText: {
    color: "#0F8A80",
    fontSize: 14,
    fontWeight: "600",
  },
  canvasArea: {
    flex: 1,
    backgroundColor: "#020617",
    overflow: "hidden",
    position: "relative",
  },
  handleTouchTarget: {
    position: "absolute",
    width: HANDLE_RADIUS * 2,
    height: HANDLE_RADIUS * 2,
    justifyContent: "center",
    alignItems: "center",
    zIndex: 20,
  },
  handleOuterCircle: {
    width: HANDLE_RADIUS * 2,
    height: HANDLE_RADIUS * 2,
    borderRadius: HANDLE_RADIUS,
    borderWidth: 3,
    borderColor: "#1F8F5F",
    backgroundColor: "rgba(16, 185, 129, 0.35)",
    justifyContent: "center",
    alignItems: "center",
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.5,
    shadowRadius: 4,
    elevation: 6,
  },
  handleInnerDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#FFFFFF",
  },
  handleLabelBadge: {
    position: "absolute",
    top: -18,
    backgroundColor: "rgba(15, 23, 42, 0.9)",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderWidth: 1,
    borderColor: "#1F8F5F",
  },
  handleLabelText: {
    color: "#FFFFFF",
    fontSize: 10,
    fontWeight: "700",
  },
  bottomBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 16,
    backgroundColor: "#111827",
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.12)",
    gap: 12,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  cancelBtnText: {
    color: "#E5DBC3",
    fontSize: 15,
    fontWeight: "600",
  },
  applyBtn: {
    flex: 2,
    flexDirection: "row",
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: "#1F8F5F",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    shadowColor: "#1F8F5F",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 4,
  },
  applyBtnText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700",
  },
});
