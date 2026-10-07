const MICROSECONDS_PER_SECOND = 1_000_000n;
const MICROSECONDS_PER_MILLISECOND = 1000n;
const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);

const leapYear = (year: number) =>
  year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const leapDaysBefore = (year: number) =>
  Math.floor((year - 1) / 4) -
  Math.floor((year - 1) / 100) +
  Math.floor((year - 1) / 400);

/** Canonical UTC view timestamps only; never truncate fractions with Date.parse. */
export function parseUtcMicroseconds(timestamp: unknown): bigint | null {
  if (
    typeof timestamp !== 'string' ||
    timestamp.length < 20 ||
    timestamp.length > 27
  )
    return null;
  const fields =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$/.exec(
      timestamp,
    );
  if (!fields || fields[0] !== timestamp) return null;
  const [year, month, day, hour, minute, second] = fields
    .slice(1, 7)
    .map(Number);
  const lengths = [
    31,
    leapYear(year) ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > lengths[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  )
    return null;
  const days =
    (year - 1970) * 365 +
    leapDaysBefore(year) -
    leapDaysBefore(1970) +
    lengths.slice(0, month - 1).reduce((sum, length) => sum + length, 0) +
    day -
    1;
  const seconds =
    BigInt(days) * 86400n + BigInt(hour * 3600 + minute * 60 + second);
  return (
    seconds * MICROSECONDS_PER_SECOND + BigInt((fields[7] ?? '').padEnd(6, '0'))
  );
}

/** Preserve the full integer millisecond value before multiplying. */
export function millisecondsToMicroseconds(
  milliseconds: number,
): bigint | null {
  return Number.isSafeInteger(milliseconds)
    ? BigInt(milliseconds) * MICROSECONDS_PER_MILLISECOND
    : null;
}

/** Used at the response's receipt anchor, not its delayed vehicle display time. */
export function receiptEligible(
  receivedAtUs: bigint | null,
  anchorMs: number,
): boolean {
  const anchorUs = millisecondsToMicroseconds(anchorMs);
  return (
    typeof receivedAtUs === 'bigint' &&
    anchorUs !== null &&
    receivedAtUs <= anchorUs
  );
}

/** Ceiling works before the epoch too; unsupported clocks cannot become boundaries. */
export function firstRepresentableMillisecond(
  timestampUs: bigint,
): number | null {
  const quotient = timestampUs / MICROSECONDS_PER_MILLISECOND;
  const ceiling =
    timestampUs % MICROSECONDS_PER_MILLISECOND > 0n ? quotient + 1n : quotient;
  return ceiling >= -MAX_SAFE && ceiling <= MAX_SAFE ? Number(ceiling) : null;
}

/** Bridge to the interpolation core's safe-number microseconds without losing a bit. */
export function safeObservationMicroseconds(
  timestampUs: bigint | null,
): number | null {
  return typeof timestampUs === 'bigint' &&
    timestampUs >= -MAX_SAFE &&
    timestampUs <= MAX_SAFE
    ? Number(timestampUs)
    : null;
}
