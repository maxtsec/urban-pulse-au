export type Box = { x: number; y: number; w: number; h: number };

export type LabelRequest = {
  id: string;
  /** Marker centre in map-container pixels. */
  x: number;
  y: number;
  width: number;
  height: number;
};

export type Offset = { dx: number; dy: number };

const GAP = 4;
const EDGE = 6;

function overlaps(a: Box, b: Box) {
  return (
    a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
  );
}

/**
 * Greedy label placement beside each marker icon. Earlier requests win, and a
 * label with no free side is collapsed rather than drawn over another marker.
 */
export function placeLabels(
  requests: LabelRequest[],
  obstacles: Box[],
  icon: { halfWidth: number; halfHeight: number },
  bounds: { width: number; height: number },
): Map<string, Offset | null> {
  const placed: Box[] = [];
  const result = new Map<string, Offset | null>();
  for (const label of requests) {
    const { width: w, height: h } = label;
    const candidates: Offset[] = [
      { dx: icon.halfWidth + GAP, dy: -h / 2 },
      { dx: -icon.halfWidth - GAP - w, dy: -h / 2 },
      { dx: -w / 2, dy: -icon.halfHeight - GAP - h },
      { dx: -w / 2, dy: icon.halfHeight + GAP },
      { dx: icon.halfWidth - 2, dy: -icon.halfHeight - h + 2 },
      { dx: -icon.halfWidth + 2 - w, dy: icon.halfHeight - 2 },
    ];
    const choice = candidates.find((offset) => {
      const box = { x: label.x + offset.dx, y: label.y + offset.dy, w, h };
      return (
        box.x >= EDGE &&
        box.y >= EDGE &&
        box.x + w <= bounds.width - EDGE &&
        box.y + h <= bounds.height - EDGE &&
        !obstacles.some((other) => overlaps(box, other)) &&
        !placed.some((other) => overlaps(box, other))
      );
    });
    if (choice)
      placed.push({ x: label.x + choice.dx, y: label.y + choice.dy, w, h });
    result.set(label.id, choice ?? null);
  }
  return result;
}
