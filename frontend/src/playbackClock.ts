export type PlaybackSpeed = 2 | 4 | 8;
export const DEFAULT_PLAYBACK_SPEED: PlaybackSpeed = 2;
export const PLAYBACK_SPEEDS = [2, 4, 8] as const;
const TICKS_PER_DAY = 144;

export function playbackDayMs(speed: PlaybackSpeed): number {
  return 4000 / speed;
}

/** Advance the shared ten-minute replay cursor from a wall-clock anchor. */
export function playbackPosition(anchor: {day: number; minute: number}, elapsedMs: number, days: number, speed: PlaybackSpeed = DEFAULT_PLAYBACK_SPEED) {
  const start = anchor.day * TICKS_PER_DAY + Math.floor(anchor.minute / 10);
  const last = days * TICKS_PER_DAY - 1;
  const tick = Math.min(last, start + Math.floor(Math.max(0, elapsedMs) * TICKS_PER_DAY / playbackDayMs(speed)));
  return {day: Math.floor(tick / TICKS_PER_DAY), minute: (tick % TICKS_PER_DAY) * 10, complete: tick === last};
}
