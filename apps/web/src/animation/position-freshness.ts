import {
  millisecondsToMicroseconds,
  parseUtcMicroseconds,
} from './exact-time.ts';

export type PositionFreshnessPolicy = {
  version: 'southbank-position-freshness-v1';
  stale_after_seconds: number;
  expired_after_seconds: number;
};

export type PositionAge = 'current' | 'stale' | 'expired' | 'unknown';
export type FreshnessResult =
  | { status: 'ready'; freshness: PositionAge }
  | {
      status: 'unavailable';
      reason: 'invalid-policy' | 'invalid-clock' | 'invalid-observation';
    };

/** Validate wire values before any BigInt conversion; never invent default TTLs. */
export function parsePositionFreshnessPolicy(
  value: unknown,
): PositionFreshnessPolicy | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null;
  const policy = value as Record<string, unknown>;
  const stale = policy.stale_after_seconds;
  const expired = policy.expired_after_seconds;
  if (
    policy.version !== 'southbank-position-freshness-v1' ||
    typeof stale !== 'number' ||
    !Number.isSafeInteger(stale) ||
    stale < 0 ||
    typeof expired !== 'number' ||
    !Number.isSafeInteger(expired) ||
    expired <= stale
  )
    return null;
  return {
    version: policy.version,
    stale_after_seconds: stale,
    expired_after_seconds: expired,
  };
}

/** Pass the parent's latest observation and the playhead, never a delayed pose sample. */
export function evaluatePositionFreshness(
  observedAt: unknown,
  playheadMs: number,
  policyValue: unknown,
): FreshnessResult {
  const policy = parsePositionFreshnessPolicy(policyValue);
  if (policy === null)
    return { status: 'unavailable', reason: 'invalid-policy' };
  const atUs = millisecondsToMicroseconds(playheadMs);
  if (atUs === null) return { status: 'unavailable', reason: 'invalid-clock' };
  if (observedAt === null) return { status: 'ready', freshness: 'unknown' };
  const observedUs = parseUtcMicroseconds(observedAt);
  if (observedUs === null)
    return { status: 'unavailable', reason: 'invalid-observation' };
  if (observedUs > atUs) return { status: 'ready', freshness: 'unknown' };
  const ageUs = atUs - observedUs;
  return {
    status: 'ready',
    freshness:
      ageUs >= BigInt(policy.expired_after_seconds) * 1_000_000n
        ? 'expired'
        : ageUs >= BigInt(policy.stale_after_seconds) * 1_000_000n
          ? 'stale'
          : 'current',
  };
}
