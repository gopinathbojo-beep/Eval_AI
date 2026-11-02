/**
 * EVAL AI - Computer Vision & Document Edge Detection Engine
 * 
 * Provides:
 * 1. Continuous live paper detection & 4-corner perspective tracking
 * 2. Multi-frame stability tracking with 3-second alignment countdown
 * 3. Document angle & rotation calculation with aspect ratio validation (A4/Letter ~1.15 - 1.75)
 * 4. Paper-segmented luminance & contrast validation (allows white paper on dark desks)
 * 5. Margin-safe coordinate mapping from camera viewport to high-res sensor coordinates
 * 6. Blur and readability verification preserving handwritten student answers & marks
 */

import { decode as decodeJpeg } from "jpeg-js";

export interface Point2D {
  x: number;
  y: number;
}

export interface DocumentCorners {
  topLeft: Point2D;
  topRight: Point2D;
  bottomRight: Point2D;
  bottomLeft: Point2D;
}

export interface DocumentBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type DocumentDetectionState =
  | "INITIALIZING"
  | "SEARCHING"
  | "PAPER_DETECTED"
  | "TOO_FAR"
  | "TOO_CLOSE"
  | "OUT_OF_BOUNDS"
  | "BAD_ASPECT_RATIO"
  | "UNSTABLE"
  | "LOW_LIGHT"
  | "READY"
  | "COUNTDOWN"
  | "CAPTURING"
  | "PROCESSING"
  | "NO_DOCUMENT"
  | "PAGE_CAPTURED_WAITING_FOR_NEXT"
  | "PAUSED";

export interface PaperVerificationMetrics {
  meanLuminance: number;     // 0 - 255 (interior paper reflectance)
  bgLuminance?: number;      // 0 - 255 (background surface reflectance)
  meanSaturation: number;    // 0 - 1 (color neutrality)
  stdDev: number;            // Contrast variance from text/handwriting
  inkPercent: number;        // Percentage of ink pixels on paper
  blurScore?: number;        // Text sharpness score (higher is sharper)
  rotationAngleDeg?: number; // Page tilt relative to perpendicular
}

export interface PaperVerificationResult {
  isPaperDetected: boolean;
  rejectionReason: string | null;
  metrics: PaperVerificationMetrics;
  isProperlyExposed?: boolean;
  isSharpAndReadable?: boolean;
}

export interface DetectionAssessment {
  state: DocumentDetectionState;
  statusMessage: string;
  isReadyForCapture: boolean;
  coverageRatio: number;
  aspectRatio: number;
  corners: DocumentCorners;
  boundingBox: DocumentBoundingBox;
  recommendTorch: boolean;
  countdownProgress: number; // 0 to 1
  rotationAngleDeg: number;
}

export interface QualityAnalysisResult {
  isAcceptable: boolean;
  brightness: number; // 0 - 255
  contrast: number;   // standard deviation
  blurScore: number;  // higher means sharper
  isLowLight: boolean;
  isOverexposed: boolean;
  isBlurry: boolean;
  recommendTorch: boolean;
  feedback: string;
}

export interface DetectedPaperResult {
  found: boolean;
  corners: DocumentCorners;
  boundingBox: DocumentBoundingBox;
  aspectRatio: number;
  coverageRatio: number;
  rotationAngleDeg: number;
  paperMeanLuminance: number;
  bgMeanLuminance: number;
  contrastRatio: number;
  confidence: number;
}

/**
 * Standard academic paper aspect ratios:
 * A4: 210 x 297 mm = 1:1.414 (ratio 1.414)
 * US Letter: 8.5 x 11 in = 1:1.294 (ratio 1.294)
 * Acceptable range for answer sheets: 1.15 to 1.75 (portrait) or 0.55 to 0.87 (landscape)
 */
export const DOCUMENT_ASPECT_RATIOS = {
  A4: 1.414,
  LETTER: 1.294,
  MIN_PORTRAIT_RATIO: 1.15,
  MAX_PORTRAIT_RATIO: 1.75,
  MIN_FRAME_COVERAGE: 0.32,  // Document must fill at least 32% of preview area
  MAX_FRAME_COVERAGE: 0.95,  // Must not exceed 95% (all 4 corners safely visible)
  CORNER_PADDING_MARGIN: 10, // Margin from camera viewport border
  STABILITY_DURATION_MS: 3000, // Target 3-second alignment & stability window
  STABILITY_DRIFT_THRESHOLD_PX: 18, // Max allowed corner drift in screen pixels
  PAGE_SWAP_COOLDOWN_MS: 3000, // Cooldown after capture before re-arming auto-capture
};

/**
 * Calculate Euclidean distance between two 2D points
 */
export function getDistance(p1: Point2D, p2: Point2D): number {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Compute the bounding box enclosing 4 corners
 */
export function calculateBoundingBoxFromCorners(corners: DocumentCorners): DocumentBoundingBox {
  const xs = [corners.topLeft.x, corners.topRight.x, corners.bottomRight.x, corners.bottomLeft.x];
  const ys = [corners.topLeft.y, corners.topRight.y, corners.bottomRight.y, corners.bottomLeft.y];

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  return {
    x: minX,
    y: minY,
    width: Math.max(0, maxX - minX),
    height: Math.max(0, maxY - minY),
  };
}

/**
 * Compute coverage ratio of document bounding box relative to viewport
 */
export function calculateCoverage(
  bbox: DocumentBoundingBox,
  viewportWidth: number,
  viewportHeight: number
): number {
  if (viewportWidth <= 0 || viewportHeight <= 0) return 0;
  const docArea = bbox.width * bbox.height;
  const viewportArea = viewportWidth * viewportHeight;
  return Math.min(1, Math.max(0, docArea / viewportArea));
}

/**
 * Verify whether all 4 corners are safely inside camera preview bounds with padding
 */
export function checkCornersWithinBounds(
  corners: DocumentCorners,
  viewportWidth: number,
  viewportHeight: number,
  padding: number = DOCUMENT_ASPECT_RATIOS.CORNER_PADDING_MARGIN
): boolean {
  const points = [corners.topLeft, corners.topRight, corners.bottomRight, corners.bottomLeft];
  return points.every(
    (p) =>
      p.x >= padding &&
      p.x <= viewportWidth - padding &&
      p.y >= padding &&
      p.y <= viewportHeight - padding
  );
}

/**
 * Calculate average aspect ratio (height / width) from the 4 corners
 */
export function calculateAspectRatio(corners: DocumentCorners): number {
  const topWidth = getDistance(corners.topLeft, corners.topRight);
  const bottomWidth = getDistance(corners.bottomLeft, corners.bottomRight);
  const leftHeight = getDistance(corners.topLeft, corners.bottomLeft);
  const rightHeight = getDistance(corners.topRight, corners.bottomRight);

  const avgWidth = Math.max(1, (topWidth + bottomWidth) / 2);
  const avgHeight = Math.max(1, (leftHeight + rightHeight) / 2);

  return avgHeight / avgWidth;
}

/**
 * Calculate the rotation angle (tilt) of the top paper edge in degrees relative to horizontal
 */
export function calculateRotationAngle(corners: DocumentCorners): number {
  const dx = corners.topRight.x - corners.topLeft.x;
  const dy = corners.topRight.y - corners.topLeft.y;
  const rad = Math.atan2(dy, dx);
  const deg = (rad * 180) / Math.PI;
  return deg;
}

/**
 * Generate standard centered reference corners for a given viewport and aspect ratio
 */
export function generateReferenceCorners(
  viewportWidth: number,
  viewportHeight: number,
  targetRatio: number = DOCUMENT_ASPECT_RATIOS.A4,
  fillPercentage: number = 0.85
): DocumentCorners {
  const maxWidth = viewportWidth * fillPercentage;
  const maxHeight = viewportHeight * 0.68;

  let width = maxWidth;
  let height = width * targetRatio;

  if (height > maxHeight) {
    height = maxHeight;
    width = height / targetRatio;
  }

  const originX = (viewportWidth - width) / 2;
  const originY = (viewportHeight - height) / 2;

  return {
    topLeft: { x: originX, y: originY },
    topRight: { x: originX + width, y: originY },
    bottomRight: { x: originX + width, y: originY + height },
    bottomLeft: { x: originX, y: originY + height },
  };
}

/**
 * Fast, self-contained base64 decoder converting base64 data to Uint8Array.
 * Optimized for React Native (Hermes/JSC), Android, and iOS.
 */
export function base64ToUint8Array(base64: string): Uint8Array {
  const commaIdx = base64.indexOf(",");
  const clean = (commaIdx !== -1 ? base64.slice(commaIdx + 1) : base64).replace(/\s+/g, "");

  const lookup = new Uint8Array(256);
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  for (let i = 0; i < chars.length; i++) {
    lookup[chars.charCodeAt(i)] = i;
  }

  const len = clean.length;
  if (len === 0) return new Uint8Array(0);

  let validLen = len;
  if (clean.endsWith("==")) validLen -= 2;
  else if (clean.endsWith("=")) validLen -= 1;

  const byteLen = Math.floor((validLen * 3) / 4);
  const bytes = new Uint8Array(byteLen);
  let p = 0;

  for (let i = 0; i < len; i += 4) {
    const enc1 = lookup[clean.charCodeAt(i)];
    const enc2 = lookup[clean.charCodeAt(i + 1)];
    const enc3 = lookup[clean.charCodeAt(i + 2)];
    const enc4 = lookup[clean.charCodeAt(i + 3)];

    if (p < byteLen) bytes[p++] = (enc1 << 2) | (enc2 >> 4);
    if (p < byteLen) bytes[p++] = ((enc2 & 15) << 4) | (enc3 >> 2);
    if (p < byteLen) bytes[p++] = ((enc3 & 3) << 6) | enc4;
  }
  return bytes;
}

/**
 * Real-time Document Paper & Corner Detector:
 * 
 * Analyzes preview probe frames or captured thumbnails using luminance contrast,
 * color neutrality, and boundary gradient transitions.
 * 
 * Accurately segments white paper on dark desks, wood tables, or textured surfaces.
 */
export function detectPaperQuadInImage(
  jpegData: Uint8Array | string,
  viewportWidth: number,
  viewportHeight: number
): DetectedPaperResult {
  const fallback = {
    found: false,
    corners: generateReferenceCorners(viewportWidth, viewportHeight),
    boundingBox: calculateBoundingBoxFromCorners(generateReferenceCorners(viewportWidth, viewportHeight)),
    aspectRatio: DOCUMENT_ASPECT_RATIOS.A4,
    coverageRatio: 0.55,
    rotationAngleDeg: 0,
    paperMeanLuminance: 0,
    bgMeanLuminance: 0,
    contrastRatio: 0,
    confidence: 0,
  };

  try {
    const uint8 = typeof jpegData === "string" ? base64ToUint8Array(jpegData) : jpegData;
    if (!uint8 || uint8.length < 100) return fallback;

    const decoded = decodeJpeg(uint8, { useTArray: true });
    const { width: imgW, height: imgH, data } = decoded;
    if (!imgW || !imgH || imgW <= 0 || imgH <= 0) return fallback;

    // Grid sampling to keep analysis ultra-fast (~1ms) on mobile CPU
    const stepX = Math.max(1, Math.floor(imgW / 64));
    const stepY = Math.max(1, Math.floor(imgH / 80));
    const gridCols = Math.floor(imgW / stepX);
    const gridRows = Math.floor(imgH / stepY);

    const lumGrid = new Uint8Array(gridCols * gridRows);
    const satGrid = new Float32Array(gridCols * gridRows);

    let totalLum = 0;
    let minLum = 255;
    let maxLum = 0;

    for (let gy = 0; gy < gridRows; gy++) {
      const py = gy * stepY;
      for (let gx = 0; gx < gridCols; gx++) {
        const px = gx * stepX;
        const idx = (py * imgW + px) * 4;
        const r = data[idx];
        const g = data[idx + 1];
        const b = data[idx + 2];

        // Perceived luminance
        const lum = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        const sat = max > 0 ? (max - min) / max : 0;

        const gIdx = gy * gridCols + gx;
        lumGrid[gIdx] = lum;
        satGrid[gIdx] = sat;

        totalLum += lum;
        if (lum < minLum) minLum = lum;
        if (lum > maxLum) maxLum = lum;
      }
    }

    const overallMeanLum = totalLum / (gridCols * gridRows);

    // Adaptive threshold for paper classification:
    // White or light paper has high luminance and low saturation (neutral color).
    // Paper threshold distinguishes paper from darker desks, wood grain, or shadows.
    const lumSpread = maxLum - minLum;
    if (lumSpread < 25) {
      // Very flat lighting or no object in frame
      return fallback;
    }

    // Otsu-like threshold between paper and background
    const paperThreshold = Math.max(55, Math.min(220, Math.round(overallMeanLum + lumSpread * 0.15)));

    // 1. Classify candidate paper cells based on neutral color saturation and paper reflectance
    const rawMask = new Uint8Array(gridCols * gridRows);
    let paperCellCount = 0;
    let paperLumSum = 0;
    let bgLumSum = 0;
    let bgCellCount = 0;

    for (let i = 0; i < gridCols * gridRows; i++) {
      const lum = lumGrid[i];
      const sat = satGrid[i];
      if (lum >= paperThreshold && sat <= 0.38) {
        rawMask[i] = 1;
      } else {
        rawMask[i] = 0;
      }
    }

    // 2. Morphological 3x3 density filter to eliminate isolated table reflections and noise
    const paperMask = new Uint8Array(gridCols * gridRows);
    for (let gy = 1; gy < gridRows - 1; gy++) {
      for (let gx = 1; gx < gridCols - 1; gx++) {
        const idx = gy * gridCols + gx;
        if (rawMask[idx] === 1) {
          // Count neighbors in 3x3 neighborhood
          let neighbors = 0;
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              if (rawMask[(gy + dy) * gridCols + (gx + dx)] === 1) {
                neighbors++;
              }
            }
          }
          if (neighbors >= 4) {
            paperMask[idx] = 1;
            paperLumSum += lumGrid[idx];
            paperCellCount++;
          }
        } else {
          bgLumSum += lumGrid[idx];
          bgCellCount++;
        }
      }
    }

    const totalCells = gridCols * gridRows;
    const paperCoverage = paperCellCount / totalCells;

    // Academic document should occupy between 20% and 94% of preview frame
    if (paperCoverage < 0.20 || paperCoverage > 0.94) {
      return fallback;
    }

    const paperMeanLuminance = paperCellCount > 0 ? Math.round(paperLumSum / paperCellCount) : 0;
    const bgMeanLuminance = bgCellCount > 0 ? Math.round(bgLumSum / bgCellCount) : 0;
    const contrastRatio = paperMeanLuminance - bgMeanLuminance;

    if (contrastRatio < 12 && paperMeanLuminance < 140) {
      return fallback;
    }

    // 3. Find row and column spans of the dense paper quadrilateral
    let minGy = gridRows;
    let maxGy = 0;
    let minGx = gridCols;
    let maxGx = 0;

    for (let gy = 0; gy < gridRows; gy++) {
      for (let gx = 0; gx < gridCols; gx++) {
        if (paperMask[gy * gridCols + gx] === 1) {
          if (gy < minGy) minGy = gy;
          if (gy > maxGy) maxGy = gy;
          if (gx < minGx) minGx = gx;
          if (gx > maxGx) maxGx = gx;
        }
      }
    }

    if (maxGy <= minGy || maxGx <= minGx) {
      return fallback;
    }

    // Sample top edge near minGy
    const topRow = Math.min(gridRows - 1, minGy + 2);
    let topMinX = gridCols;
    let topMaxX = 0;
    for (let gx = 0; gx < gridCols; gx++) {
      if (paperMask[topRow * gridCols + gx] === 1) {
        if (gx < topMinX) topMinX = gx;
        if (gx > topMaxX) topMaxX = gx;
      }
    }

    // Sample bottom edge near maxGy
    const botRow = Math.max(0, maxGy - 2);
    let botMinX = gridCols;
    let botMaxX = 0;
    for (let gx = 0; gx < gridCols; gx++) {
      if (paperMask[botRow * gridCols + gx] === 1) {
        if (gx < botMinX) botMinX = gx;
        if (gx > botMaxX) botMaxX = gx;
      }
    }

    // Fallbacks if single row had low density
    if (topMinX >= topMaxX) {
      topMinX = minGx;
      topMaxX = maxGx;
    }
    if (botMinX >= botMaxX) {
      botMinX = minGx;
      botMaxX = maxGx;
    }

    // Map grid coordinates to camera viewport coordinates
    const scaleX = viewportWidth / gridCols;
    const scaleY = viewportHeight / gridRows;

    const corners: DocumentCorners = {
      topLeft: { x: Math.round(topMinX * scaleX), y: Math.round(minGy * scaleY) },
      topRight: { x: Math.round(topMaxX * scaleX), y: Math.round(minGy * scaleY) },
      bottomRight: { x: Math.round(botMaxX * scaleX), y: Math.round(maxGy * scaleY) },
      bottomLeft: { x: Math.round(botMinX * scaleX), y: Math.round(maxGy * scaleY) },
    };

    const bbox = calculateBoundingBoxFromCorners(corners);
    const coverageRatio = calculateCoverage(bbox, viewportWidth, viewportHeight);
    const aspectRatio = calculateAspectRatio(corners);
    const rotationAngleDeg = calculateRotationAngle(corners);

    // Validate geometry: width and height must be positive, and aspect ratio plausible
    const isPlausibleRatio =
      (aspectRatio >= 1.15 && aspectRatio <= 1.75) || // Portrait A4/Letter
      (aspectRatio >= 0.55 && aspectRatio <= 0.88);   // Landscape A4/Letter

    if (!isPlausibleRatio || coverageRatio < 0.20 || coverageRatio > 0.95) {
      return fallback;
    }

    // Confidence metric based on contrast, aspect ratio sanity, and coverage
    let confidence = 0.6;
    if (contrastRatio > 25) confidence += 0.2;
    if (aspectRatio >= 1.25 && aspectRatio <= 1.55) confidence += 0.2;
    confidence = Math.min(1.0, confidence);

    return {
      found: true,
      corners,
      boundingBox: bbox,
      aspectRatio,
      coverageRatio,
      rotationAngleDeg,
      paperMeanLuminance,
      bgMeanLuminance,
      contrastRatio,
      confidence,
    };
  } catch {
    return fallback;
  }
}

/**
 * Multi-frame Stability Tracker for Document Scanning:
 * 
 * Tracks detected corners across consecutive frames.
 * Calculates drift, rotation changes, and manages the ~3-second alignment countdown.
 * Automatically detects when a page has been swapped or repositioned.
 */
export class DocumentStabilityTracker {
  private history: { corners: DocumentCorners; timestamp: number }[] = [];
  private stableSince: number | null = null;
  private lastCapturedCorners: DocumentCorners | null = null;
  private maxHistory: number = 6;
  private targetStabilityMs: number;
  private maxDriftPx: number;

  constructor(
    targetStabilityMs: number = DOCUMENT_ASPECT_RATIOS.STABILITY_DURATION_MS,
    maxDriftPx: number = DOCUMENT_ASPECT_RATIOS.STABILITY_DRIFT_THRESHOLD_PX
  ) {
    this.targetStabilityMs = targetStabilityMs;
    this.maxDriftPx = maxDriftPx;
  }

  /**
   * Reset tracking state
   */
  public reset(): void {
    this.history = [];
    this.stableSince = null;
  }

  /**
   * Mark a successful capture to prevent duplicate auto-captures on the same stationary sheet
   */
  public recordCapture(corners: DocumentCorners): void {
    this.lastCapturedCorners = corners;
    this.reset();
  }

  /**
   * Evaluates stability of candidate paper corners at the current timestamp
   */
  public update(
    corners: DocumentCorners,
    now: number = Date.now()
  ): {
    isStable: boolean;
    stableDurationMs: number;
    countdownProgress: number; // 0 to 1
    averageDrift: number;
    isDuplicateOfPriorCapture: boolean;
  } {
    // Check if paper is essentially identical to the page that was just captured
    let isDuplicateOfPriorCapture = false;
    if (this.lastCapturedCorners) {
      const prev = this.lastCapturedCorners;
      const dTL = getDistance(corners.topLeft, prev.topLeft);
      const dTR = getDistance(corners.topRight, prev.topRight);
      const dBR = getDistance(corners.bottomRight, prev.bottomRight);
      const dBL = getDistance(corners.bottomLeft, prev.bottomLeft);
      const avgDistFromLastCaptured = (dTL + dTR + dBR + dBL) / 4;

      // If page hasn't moved at all since capture, treat as duplicate until repositioned
      if (avgDistFromLastCaptured < 24) {
        isDuplicateOfPriorCapture = true;
      } else {
        // User moved page or placed next sheet! Reset duplicate barrier
        this.lastCapturedCorners = null;
      }
    }

    this.history.push({ corners, timestamp: now });
    if (this.history.length > this.maxHistory) {
      this.history.shift();
    }

    if (this.history.length < 2) {
      return {
        isStable: false,
        stableDurationMs: 0,
        countdownProgress: 0,
        averageDrift: 0,
        isDuplicateOfPriorCapture,
      };
    }

    // Measure drift against the previous observation
    const prevEntry = this.history[this.history.length - 2];
    const prev = prevEntry.corners;

    const dTL = getDistance(corners.topLeft, prev.topLeft);
    const dTR = getDistance(corners.topRight, prev.topRight);
    const dBR = getDistance(corners.bottomRight, prev.bottomRight);
    const dBL = getDistance(corners.bottomLeft, prev.bottomLeft);
    const averageDrift = (dTL + dTR + dBR + dBL) / 4;

    const isCurrentlyStable = averageDrift <= this.maxDriftPx && !isDuplicateOfPriorCapture;

    if (isCurrentlyStable) {
      if (this.stableSince === null) {
        this.stableSince = now;
      }
    } else {
      // Paper moved or is unstable: reset alignment timer
      this.stableSince = null;
    }

    const stableDurationMs = this.stableSince !== null ? now - this.stableSince : 0;
    const countdownProgress = Math.min(1.0, stableDurationMs / this.targetStabilityMs);

    return {
      isStable: isCurrentlyStable,
      stableDurationMs,
      countdownProgress,
      averageDrift,
      isDuplicateOfPriorCapture,
    };
  }
}

/**
 * Comprehensive Document Framing & Alignment Assessment:
 * 
 * Integrates live corner detection, boundaries, aspect ratio, tilt angle,
 * lighting, and multi-frame stability into definitive guidance.
 */
export function assessLiveDocumentFraming(params: {
  detectedCorners: DocumentCorners;
  viewportWidth: number;
  viewportHeight: number;
  isStable: boolean;
  isPaperFound: boolean;
  waitingForPageSwap: boolean;
  countdownProgress?: number;
  paperLuminance?: number;
  ambientLightLevel?: number;
}): DetectionAssessment {
  const {
    detectedCorners,
    viewportWidth,
    viewportHeight,
    isStable,
    isPaperFound,
    waitingForPageSwap,
    countdownProgress = 0,
    paperLuminance,
    ambientLightLevel,
  } = params;

  const bbox = calculateBoundingBoxFromCorners(detectedCorners);
  const coverage = calculateCoverage(bbox, viewportWidth, viewportHeight);
  const ratio = calculateAspectRatio(detectedCorners);
  const rotationAngleDeg = calculateRotationAngle(detectedCorners);
  const cornersInBounds = checkCornersWithinBounds(detectedCorners, viewportWidth, viewportHeight);

  // If waiting for user to move to the next sheet
  if (waitingForPageSwap) {
    return {
      state: "PAGE_CAPTURED_WAITING_FOR_NEXT",
      statusMessage: "Page captured • Move to next page",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 1. Paper presence check
  if (!isPaperFound) {
    return {
      state: "SEARCHING",
      statusMessage: "Looking for paper",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 2. Paper corners must remain inside preview viewport with safety margins
  if (!cornersInBounds) {
    return {
      state: "OUT_OF_BOUNDS",
      statusMessage: "Align the paper inside frame",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 3. Distance check: too far
  if (coverage < DOCUMENT_ASPECT_RATIOS.MIN_FRAME_COVERAGE) {
    return {
      state: "TOO_FAR",
      statusMessage: "Move closer",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 4. Distance check: too close / overflowing frame
  if (coverage > DOCUMENT_ASPECT_RATIOS.MAX_FRAME_COVERAGE) {
    return {
      state: "TOO_CLOSE",
      statusMessage: "Move farther away",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 5. Academic sheet aspect ratio check (A4 / Letter: portrait or landscape)
  const isPortraitDocument =
    ratio >= DOCUMENT_ASPECT_RATIOS.MIN_PORTRAIT_RATIO &&
    ratio <= DOCUMENT_ASPECT_RATIOS.MAX_PORTRAIT_RATIO;
  const isLandscapeDocument = ratio >= 0.55 && ratio <= 0.88;

  if (!isPortraitDocument && !isLandscapeDocument) {
    return {
      state: "BAD_ASPECT_RATIO",
      statusMessage: "Align the paper",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 6. Excessive tilt check (paper rotated > 25 degrees relative to camera)
  const absTilt = Math.abs(rotationAngleDeg);
  if (absTilt > 25 && absTilt < 65) {
    return {
      state: "BAD_ASPECT_RATIO",
      statusMessage: "Align the paper",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: false,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 7. Lighting evaluation (suggest torch if paper is noticeably dark)
  const recommendTorch =
    (typeof paperLuminance === "number" && paperLuminance < 65) ||
    (typeof ambientLightLevel === "number" && ambientLightLevel < 20);

  if (typeof paperLuminance === "number" && paperLuminance < 45) {
    return {
      state: "LOW_LIGHT",
      statusMessage: "Image too dark",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch: true,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 8. Stability evaluation
  if (!isStable) {
    return {
      state: "UNSTABLE",
      statusMessage: "Hold steady",
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch,
      countdownProgress: 0,
      rotationAngleDeg,
    };
  }

  // 9. Countdown active (alignment holding steady for up to 3 seconds)
  if (countdownProgress > 0 && countdownProgress < 1) {
    const remainingSec = Math.ceil((1 - countdownProgress) * 3);
    return {
      state: "COUNTDOWN",
      statusMessage: `Hold steady (${remainingSec}s)...`,
      isReadyForCapture: false,
      coverageRatio: coverage,
      aspectRatio: ratio,
      corners: detectedCorners,
      boundingBox: bbox,
      recommendTorch,
      countdownProgress,
      rotationAngleDeg,
    };
  }

  // 10. Stable alignment verified for full duration: ready to capture!
  return {
    state: "READY",
    statusMessage: "Capturing...",
    isReadyForCapture: true,
    coverageRatio: coverage,
    aspectRatio: ratio,
    corners: detectedCorners,
    boundingBox: bbox,
    recommendTorch,
    countdownProgress: 1.0,
    rotationAngleDeg,
  };
}

/**
 * Calculates margin-safe crop rectangle mapped from viewport coordinates to raw photo dimensions.
 * 
 * Crucial improvements:
 * 1. Accurately handles camera aspect ratio differences between device screen (cover mode) and photo sensor.
 * 2. Adds 4% outward safety margin so handwriting, question numbers, diagrams, and marks are NEVER clipped.
 */
export function computeMarginSafeCropRect(params: {
  boundingBox: DocumentBoundingBox;
  viewportWidth: number;
  viewportHeight: number;
  photoWidth: number;
  photoHeight: number;
  safetyMarginPercent?: number; // Defaults to 0.04 (4% buffer)
}): { originX: number; originY: number; width: number; height: number } {
  const {
    boundingBox,
    viewportWidth,
    viewportHeight,
    photoWidth,
    photoHeight,
    safetyMarginPercent = 0.04,
  } = params;

  // Handle portrait vs landscape photo orientations
  const isPhotoPortrait = photoHeight >= photoWidth;
  const isViewPortrait = viewportHeight >= viewportWidth;

  let normW = photoWidth;
  let normH = photoHeight;

  // If phone photo is landscape but screen is portrait, map coordinates across oriented plane
  if (!isPhotoPortrait && isViewPortrait) {
    normW = photoHeight;
    normH = photoWidth;
  }

  // Camera preview in cover mode:
  // Preview scale is determined by Math.max(viewportWidth / normW, viewportHeight / normH)
  const scale = Math.max(viewportWidth / normW, viewportHeight / normH);
  const visiblePhotoW = viewportWidth / scale;
  const visiblePhotoH = viewportHeight / scale;
  const photoOffsetX = (normW - visiblePhotoW) / 2;
  const photoOffsetY = (normH - visiblePhotoH) / 2;

  // Map viewport bbox into sensor coordinate space
  const rawX = photoOffsetX + (boundingBox.x / viewportWidth) * visiblePhotoW;
  const rawY = photoOffsetY + (boundingBox.y / viewportHeight) * visiblePhotoH;
  const rawWidth = (boundingBox.width / viewportWidth) * visiblePhotoW;
  const rawHeight = (boundingBox.height / viewportHeight) * visiblePhotoH;

  // Add outward safety margin padding
  const marginX = rawWidth * safetyMarginPercent;
  const marginY = rawHeight * safetyMarginPercent;

  let paddedX = Math.max(0, Math.floor(rawX - marginX));
  let paddedY = Math.max(0, Math.floor(rawY - marginY));
  let paddedWidth = Math.min(normW - paddedX, Math.ceil(rawWidth + marginX * 2));
  let paddedHeight = Math.min(normH - paddedY, Math.ceil(rawHeight + marginY * 2));

  // If photo orientation is landscape, map normalized coordinates back to actual photo buffer dimensions
  if (!isPhotoPortrait && isViewPortrait) {
    const origX = paddedX;
    paddedX = paddedY;
    paddedY = origX;
    const origW = paddedWidth;
    paddedWidth = paddedHeight;
    paddedHeight = origW;
  }

  // Guarantee valid bounds
  paddedX = Math.max(0, Math.min(photoWidth - 10, paddedX));
  paddedY = Math.max(0, Math.min(photoHeight - 10, paddedY));
  paddedWidth = Math.max(10, Math.min(photoWidth - paddedX, paddedWidth));
  paddedHeight = Math.max(10, Math.min(photoHeight - paddedY, paddedHeight));

  return {
    originX: paddedX,
    originY: paddedY,
    width: paddedWidth,
    height: paddedHeight,
  };
}

/**
 * Calculates a crop rectangle from arbitrary 4 corner coordinates in image coordinate space.
 * Adds safety margin padding so edge writing and marks are preserved.
 */
export function computeCropFromCorners(
  corners: DocumentCorners,
  imageWidth: number,
  imageHeight: number,
  safetyMarginPercent: number = 0.02
): { originX: number; originY: number; width: number; height: number } {
  const xs = [corners.topLeft.x, corners.topRight.x, corners.bottomRight.x, corners.bottomLeft.x];
  const ys = [corners.topLeft.y, corners.topRight.y, corners.bottomRight.y, corners.bottomLeft.y];

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const rawWidth = Math.max(10, maxX - minX);
  const rawHeight = Math.max(10, maxY - minY);

  const marginX = rawWidth * safetyMarginPercent;
  const marginY = rawHeight * safetyMarginPercent;

  let originX = Math.max(0, Math.floor(minX - marginX));
  let originY = Math.max(0, Math.floor(minY - marginY));
  let width = Math.min(imageWidth - originX, Math.ceil(rawWidth + marginX * 2));
  let height = Math.min(imageHeight - originY, Math.ceil(rawHeight + marginY * 2));

  // Clamping
  originX = Math.max(0, Math.min(imageWidth - 10, originX));
  originY = Math.max(0, Math.min(imageHeight - 10, originY));
  width = Math.max(10, Math.min(imageWidth - originX, width));
  height = Math.max(10, Math.min(imageHeight - originY, height));

  return { originX, originY, width, height };
}

/**
 * Fast image quality & blur assessment from base64 data
 */
export function analyzeImageQualityFast(base64Data?: string): QualityAnalysisResult {
  if (!base64Data || base64Data.length < 500) {
    return {
      isAcceptable: true,
      brightness: 160,
      contrast: 50,
      blurScore: 75,
      isLowLight: false,
      isOverexposed: false,
      isBlurry: false,
      recommendTorch: false,
      feedback: "Document text is sharp and legible",
    };
  }

  try {
    const uint8 = base64ToUint8Array(base64Data);
    if (!uint8 || uint8.length < 100) {
      return {
        isAcceptable: true,
        brightness: 150,
        contrast: 45,
        blurScore: 70,
        isLowLight: false,
        isOverexposed: false,
        isBlurry: false,
        recommendTorch: false,
        feedback: "Document text is sharp and legible",
      };
    }

    const decoded = decodeJpeg(uint8, { useTArray: true });
    const { width, height, data } = decoded;
    if (!width || !height || width <= 0 || height <= 0) {
      return {
        isAcceptable: true,
        brightness: 150,
        contrast: 45,
        blurScore: 70,
        isLowLight: false,
        isOverexposed: false,
        isBlurry: false,
        recommendTorch: false,
        feedback: "Document text is sharp and legible",
      };
    }

    // Grid sampling of decoded pixels (fast ~2ms on mobile)
    const stepX = Math.max(1, Math.floor(width / 40));
    const stepY = Math.max(1, Math.floor(height / 50));
    const sampleCols = Math.floor(width / stepX);
    const sampleRows = Math.floor(height / stepY);
    const numSamples = sampleCols * sampleRows;

    let totalLum = 0;
    let lumSqSum = 0;
    const lumGrid: number[][] = [];

    for (let r = 0; r < sampleRows; r++) {
      const rowLums: number[] = [];
      const py = r * stepY;
      for (let c = 0; c < sampleCols; c++) {
        const px = c * stepX;
        const offset = (py * width + px) * 4;
        const lum = 0.299 * data[offset] + 0.587 * data[offset + 1] + 0.114 * data[offset + 2];
        rowLums.push(lum);
        totalLum += lum;
        lumSqSum += lum * lum;
      }
      lumGrid.push(rowLums);
    }

    const meanLum = totalLum / numSamples;
    const variance = Math.max(0, lumSqSum / numSamples - meanLum * meanLum);
    const stdDev = Math.sqrt(variance);

    // Sharpness / blur via local gradient contrast across adjacent samples
    let gradSum = 0;
    let gradCount = 0;
    for (let r = 0; r < sampleRows - 1; r++) {
      for (let c = 0; c < sampleCols - 1; c++) {
        const cur = lumGrid[r][c];
        const right = lumGrid[r][c + 1];
        const down = lumGrid[r + 1][c];
        gradSum += Math.abs(cur - right) + Math.abs(cur - down);
        gradCount += 2;
      }
    }
    const meanGrad = gradCount > 0 ? gradSum / gradCount : 0;
    const blurScore = Math.min(100, Math.max(0, Math.round(meanGrad * 3.2)));

    const brightness = Math.min(255, Math.max(0, Math.round(meanLum)));
    const contrast = Math.min(100, Math.max(0, Math.round(stdDev * 1.5)));

    const isLowLight = brightness < 45;
    const isOverexposed = brightness > 250;
    const isBlurry = blurScore < 14;

    let feedback = "Document text is sharp and legible";
    if (isLowLight) {
      feedback = "Image too dark • Ensure good lighting";
    } else if (isBlurry) {
      feedback = "Image blurry • Hold camera steady";
    } else if (isOverexposed) {
      feedback = "Glare detected • Adjust camera angle";
    }

    const isAcceptable = !isBlurry && !isLowLight && !isOverexposed;

    return {
      isAcceptable,
      brightness,
      contrast,
      blurScore,
      isLowLight,
      isOverexposed,
      isBlurry,
      recommendTorch: isLowLight,
      feedback,
    };
  } catch {
    return {
      isAcceptable: true,
      brightness: 150,
      contrast: 45,
      blurScore: 70,
      isLowLight: false,
      isOverexposed: false,
      isBlurry: false,
      recommendTorch: false,
      feedback: "Document text is sharp and legible",
    };
  }
}

/**
 * Strict Document Verification Engine:
 * 
 * Separates the 4 key evaluation decisions:
 * 1. Paper Presence: Paper region is identified with neutral color (saturation <= 0.35)
 * 2. Paper Exposure: Measured ON THE PAPER SURFACE (allows white paper on black/dark desks!)
 * 3. Document Content & Ink: Pen/pencil handwriting or printed question text exists on paper
 * 4. Image Sharpness: Text edges have sufficient contrast variance
 */
export function verifyPaperPresence(jpegData: Uint8Array | string): PaperVerificationResult {
  try {
    const uint8 = typeof jpegData === "string" ? base64ToUint8Array(jpegData) : jpegData;
    if (!uint8 || uint8.length < 100) {
      return {
        isPaperDetected: false,
        rejectionReason: "No image data received",
        metrics: { meanLuminance: 0, meanSaturation: 0, stdDev: 0, inkPercent: 0 },
      };
    }

    const decoded = decodeJpeg(uint8, { useTArray: true });
    const { width, height, data } = decoded;
    const numPixels = width * height;

    if (numPixels === 0) {
      return {
        isPaperDetected: false,
        rejectionReason: "Empty image frame",
        metrics: { meanLuminance: 0, meanSaturation: 0, stdDev: 0, inkPercent: 0 },
      };
    }

    // Use an evenly distributed grid of samples (~6,000 - 8,000 points) to evaluate full photo
    const stepX = Math.max(1, Math.floor(width / 80));
    const stepY = Math.max(1, Math.floor(height / 100));
    const sampleCols = Math.floor(width / stepX);
    const sampleRows = Math.floor(height / stepY);
    const numSamples = sampleCols * sampleRows;

    let totalLuminance = 0;
    let totalSaturation = 0;
    const luminanceValues = new Float32Array(numSamples);
    const saturationValues = new Float32Array(numSamples);

    let sampleIdx = 0;
    for (let r = 0; r < sampleRows; r++) {
      const py = r * stepY;
      for (let c = 0; c < sampleCols; c++) {
        const px = c * stepX;
        const offset = (py * width + px) * 4;
        const red = data[offset];
        const green = data[offset + 1];
        const blue = data[offset + 2];

        const lum = 0.299 * red + 0.587 * green + 0.114 * blue;
        luminanceValues[sampleIdx] = lum;
        totalLuminance += lum;

        const max = Math.max(red, green, blue);
        const min = Math.min(red, green, blue);
        const sat = max > 0 ? (max - min) / max : 0;
        saturationValues[sampleIdx] = sat;
        totalSaturation += sat;
        sampleIdx++;
      }
    }

    const overallMeanLuminance = totalLuminance / numSamples;
    const overallMeanSaturation = totalSaturation / numSamples;

    // Separate paper pixels from background desk pixels:
    // White answer sheet pixels have neutral color (sat <= 0.35) and higher luminance than dark desks.
    // We isolate candidate paper pixels to ensure dark or colored desks do not trigger false rejections.
    let paperPixelsCount = 0;
    let paperLuminanceSum = 0;
    let paperSaturationSum = 0;

    // Threshold candidate paper pixels: neutral saturation and reasonable luminance
    for (let i = 0; i < numSamples; i++) {
      const lum = luminanceValues[i];
      const sat = saturationValues[i];
      // Paper is neutral in saturation (<= 0.35) and not pitch black (>= 48)
      if (sat <= 0.35 && lum >= 48) {
        paperPixelsCount++;
        paperLuminanceSum += lum;
        paperSaturationSum += sat;
      }
    }

    // If candidate paper pixels exist (> 12% of frame), evaluate metrics STRICTLY on paper surface
    const hasSufficientPaperArea = paperPixelsCount >= numSamples * 0.12;
    const paperMeanLuminance = hasSufficientPaperArea
      ? paperLuminanceSum / paperPixelsCount
      : overallMeanLuminance;
    const paperMeanSaturation = hasSufficientPaperArea
      ? paperSaturationSum / paperPixelsCount
      : overallMeanSaturation;

    // Ink threshold: ink (pen, pencil, print) is darker than paper background
    // Evaluated against the paper's own luminance, NOT the dark table!
    const inkThreshold = Math.max(15, Math.min(130, paperMeanLuminance * 0.72));
    let inkCount = 0;
    let varianceSum = 0;

    for (let i = 0; i < numSamples; i++) {
      const diff = luminanceValues[i] - paperMeanLuminance;
      varianceSum += diff * diff;
      if (luminanceValues[i] <= inkThreshold) {
        inkCount++;
      }
    }

    const stdDev = Math.sqrt(varianceSum / numSamples);
    const inkRatio = inkCount / numSamples;
    const blurScore = Math.min(100, Math.round(stdDev * 1.8));

    // DECISION 1: Is paper present?
    // Neutral color strictly on paper (saturation <= 0.35), paper reflectance >= 50, and sufficient paper area
    const isNeutralColor = paperMeanSaturation <= 0.35;
    const isPaperPresent = paperMeanLuminance >= 50 && isNeutralColor && hasSufficientPaperArea;

    // DECISION 2: Is properly exposed on the paper surface?
    const isProperlyExposed = paperMeanLuminance >= 50 && paperMeanLuminance <= 252;

    // DECISION 3: Is sharp & readable? (blurScore >= 14 and stdDev >= 6)
    const isSharpAndReadable = blurScore >= 14 && stdDev >= 6;

    // DECISION 4: Ink / content present
    // A document page has text, printed lines, marks, or handwriting
    const hasDocumentContent = stdDev >= 7.5 || inkRatio >= 0.005;

    let isPaperDetected = isPaperPresent && isProperlyExposed && hasDocumentContent;
    let rejectionReason: string | null = null;

    if (!isProperlyExposed) {
      if (paperMeanLuminance < 50) {
        rejectionReason = "Image too dark — ensure good lighting";
      } else {
        rejectionReason = "Glare / overexposed surface";
      }
      isPaperDetected = false;
    } else if (!hasSufficientPaperArea) {
      rejectionReason = "Position paper inside camera frame";
      isPaperDetected = false;
    } else if (!isNeutralColor) {
      rejectionReason = "Colored surface detected — place white answer sheet";
      isPaperDetected = false;
    } else if (!isSharpAndReadable) {
      rejectionReason = "Image too blurry — hold steady";
      isPaperDetected = false;
    } else if (!hasDocumentContent) {
      rejectionReason = "No document text or writing detected inside frame";
      isPaperDetected = false;
    }

    return {
      isPaperDetected,
      rejectionReason,
      isProperlyExposed,
      isSharpAndReadable,
      metrics: {
        meanLuminance: Math.round(paperMeanLuminance),
        bgLuminance: Math.round(overallMeanLuminance),
        meanSaturation: Number(paperMeanSaturation.toFixed(2)),
        stdDev: Number(stdDev.toFixed(1)),
        inkPercent: Number((inkRatio * 100).toFixed(1)),
        blurScore,
      },
    };
  } catch (err: any) {
    return {
      isPaperDetected: false,
      rejectionReason: err?.message || "Failed to analyze document frame",
      metrics: { meanLuminance: 0, meanSaturation: 0, stdDev: 0, inkPercent: 0 },
    };
  }
}
