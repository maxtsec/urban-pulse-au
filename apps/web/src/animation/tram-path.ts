/** Geometry only: callers own receipt eligibility, matching, freshness and fallback. */
export type Coordinate = [longitude: number, latitude: number];

/** A full shape with server-supplied cumulative distances, validated once per load. */
export class TramPath {
  readonly shapeId: string;
  readonly #coordinates: readonly Coordinate[];
  readonly #distances: readonly number[];

  constructor(
    shapeId: string,
    coordinates: readonly (readonly number[])[],
    distancesMetres: readonly number[],
  ) {
    if (
      !shapeId ||
      coordinates.length < 2 ||
      coordinates.length !== distancesMetres.length ||
      distancesMetres[0] !== 0
    ) {
      throw new Error('Invalid tram path');
    }
    for (let i = 0; i < coordinates.length; i++) {
      const point = coordinates[i];
      const distance = distancesMetres[i];
      const coincident =
        i > 0 &&
        point[0] === coordinates[i - 1][0] &&
        point[1] === coordinates[i - 1][1];
      if (
        point.length !== 2 ||
        !point.every(Number.isFinite) ||
        Math.abs(point[0]) > 180 ||
        Math.abs(point[1]) > 90 ||
        !Number.isFinite(distance) ||
        distance < 0 ||
        (i > 0 && distance < distancesMetres[i - 1]) ||
        (i > 0 && coincident !== (distance === distancesMetres[i - 1]))
      ) {
        throw new Error('Invalid tram path');
      }
    }
    this.shapeId = shapeId;
    // Keep frame evaluation independent of mutations to decoded asset objects.
    this.#coordinates = coordinates.map(([lon, lat]) => [lon, lat]);
    this.#distances = [...distancesMetres];
    Object.freeze(this);
  }

  /** O(log vertices); outside-path distances never clamp to an invented position. */
  at(distanceMetres: number): Coordinate | null {
    const distances = this.#distances;
    if (
      !Number.isFinite(distanceMetres) ||
      distanceMetres < 0 ||
      distanceMetres > distances[distances.length - 1]
    ) {
      return null;
    }
    // Upper bound skips coincident vertices and avoids division by a zero-length edge.
    let low = 0;
    let high = distances.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (distances[middle] <= distanceMetres) low = middle + 1;
      else high = middle;
    }
    const previous = low - 1;
    const from = this.#coordinates[previous];
    if (low === distances.length || distanceMetres === distances[previous]) {
      return [...from];
    }
    const to = this.#coordinates[low];
    const fraction =
      (distanceMetres - distances[previous]) /
      (distances[low] - distances[previous]);
    return [
      from[0] + (to[0] - from[0]) * fraction,
      from[1] + (to[1] - from[1]) * fraction,
    ];
  }
}

export type MatchedObservation = Readonly<{
  shapeId: string;
  continuityId: string;
  observedAtUs: number;
  distanceMetres: number;
}>;

export type InterpolatedPosition = {
  coordinate: Coordinate;
  distanceMetres: number;
  displayAtMs: number;
  observationTimesUs: [number, number];
  label: 'Interpolated';
};

/** Evaluate one verified consecutive pair at an integer display clock, without state. */
export function interpolateTramBracket(
  path: TramPath,
  from: MatchedObservation,
  to: MatchedObservation,
  displayAtMs: number,
): InterpolatedPosition | null {
  const displayAtUs = displayAtMs * 1000;
  const duration = to.observedAtUs - from.observedAtUs;
  if (
    ![
      displayAtMs,
      displayAtUs,
      from.observedAtUs,
      to.observedAtUs,
      duration,
    ].every(Number.isSafeInteger) ||
    duration <= 0 ||
    displayAtUs < from.observedAtUs ||
    displayAtUs > to.observedAtUs ||
    !from.continuityId ||
    from.continuityId !== to.continuityId ||
    from.shapeId !== path.shapeId ||
    to.shapeId !== path.shapeId ||
    from.distanceMetres > to.distanceMetres ||
    !path.at(from.distanceMetres) ||
    !path.at(to.distanceMetres)
  ) {
    return null;
  }
  const fraction = (displayAtUs - from.observedAtUs) / duration;
  const distanceMetres =
    displayAtUs === to.observedAtUs
      ? to.distanceMetres
      : Math.min(
          to.distanceMetres,
          from.distanceMetres +
            (to.distanceMetres - from.distanceMetres) * fraction,
        );
  const coordinate = path.at(distanceMetres);
  if (!coordinate) return null;
  return {
    coordinate,
    distanceMetres,
    displayAtMs,
    observationTimesUs: [from.observedAtUs, to.observedAtUs],
    label: 'Interpolated',
  };
}
