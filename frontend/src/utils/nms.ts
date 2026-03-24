/**
 * Non-Maximum Suppression (NMS) utility for frontend detection filtering
 *
 * Used by VideoPlayer and StreamTest to filter overlapping detection boxes
 * based on IOU (Intersection over Union) threshold.
 */

export interface DetectionItem {
  box: [number, number, number, number]; // [x1, y1, x2, y2]
  score: number;
  className: string;
}

/**
 * Calculate IOU (Intersection over Union) between two bounding boxes.
 * Boxes are in [x1, y1, x2, y2] format.
 */
function calculateIOU(
  boxA: [number, number, number, number],
  boxB: [number, number, number, number],
): number {
  const [ax1, ay1, ax2, ay2] = boxA;
  const [bx1, by1, bx2, by2] = boxB;

  // Intersection coordinates
  const ix1 = Math.max(ax1, bx1);
  const iy1 = Math.max(ay1, by1);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);

  const interWidth = Math.max(0, ix2 - ix1);
  const interHeight = Math.max(0, iy2 - iy1);
  const intersection = interWidth * interHeight;

  if (intersection === 0) return 0;

  const areaA = (ax2 - ax1) * (ay2 - ay1);
  const areaB = (bx2 - bx1) * (by2 - by1);
  const union = areaA + areaB - intersection;

  return union > 0 ? intersection / union : 0;
}

/**
 * Apply Non-Maximum Suppression to a list of detection items.
 *
 * Groups detections by className, sorts each group by score descending,
 * and removes boxes that have IOU > iouThreshold with a higher-score box.
 *
 * @param detections  List of detection items (box, score, className)
 * @param iouThreshold  IOU threshold above which lower-score boxes are suppressed
 * @returns  Filtered list with overlapping lower-score boxes removed
 */
export function applyNMS(
  detections: DetectionItem[],
  iouThreshold: number,
): DetectionItem[] {
  if (detections.length === 0) return [];

  // Group by className
  const groups: Record<string, DetectionItem[]> = {};
  for (const det of detections) {
    if (!groups[det.className]) {
      groups[det.className] = [];
    }
    groups[det.className].push(det);
  }

  const result: DetectionItem[] = [];

  for (const className of Object.keys(groups)) {
    // Sort by score descending (highest score first)
    const sorted = [...groups[className]].sort((a, b) => b.score - a.score);
    const kept: DetectionItem[] = [];

    for (const candidate of sorted) {
      let suppressed = false;
      for (const keeper of kept) {
        const iou = calculateIOU(candidate.box, keeper.box);
        if (iou > iouThreshold) {
          suppressed = true;
          break;
        }
      }
      if (!suppressed) {
        kept.push(candidate);
      }
    }

    result.push(...kept);
  }

  return result;
}
