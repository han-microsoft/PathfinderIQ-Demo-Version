/**
 * ringTone — Web Audio API phone ring tone synthesiser.
 *
 * Module role:
 *   Generates a classic dual-tone phone ring (440 Hz + 480 Hz) using the
 *   Web Audio API. No audio files needed — pure oscillator synthesis.
 *   Produces two ring bursts (1s on, 2s off) per cycle.
 *
 * Key collaborators:
 *   - CallEngineerRenderer.tsx — calls ``playRingTone`` during the calling
 *     animation and on "Call Again" clicks
 *
 * Dependents:
 *   Used by: CallEngineerRenderer.tsx only
 */

/**
 * Play a phone ring tone sequence using the Web Audio API.
 *
 * Synthesises a dual-tone ring (440 Hz + 480 Hz) with configurable cycle
 * count. Each cycle is 1 second of tone followed by a 2-second pause.
 *
 * @param cycles  Number of ring-ring cycles to play (default: 2).
 * @returns       A promise that resolves when the full sequence finishes,
 *                and a cancel function to stop playback early.
 */
export function playRingTone(cycles = 2): { promise: Promise<void>; cancel: () => void } {
  /* AudioContext — created fresh each invocation so multiple calls don't collide */
  const ctx = new AudioContext();

  /* Duration constants (seconds) */
  const RING_ON = 0.8;   // tone duration per burst
  const RING_GAP = 0.2;  // gap between the two bursts in a ring-ring
  const RING_OFF = 1.5;  // silence between ring-ring cycles
  const CYCLE = RING_ON + RING_GAP + RING_ON + RING_OFF; // total per cycle

  /* Total sequence length */
  const totalDuration = cycles * CYCLE;

  /* Master gain — controls overall volume and provides a kill switch */
  const masterGain = ctx.createGain();
  masterGain.gain.value = 0.15; // moderate volume — not startling
  masterGain.connect(ctx.destination);

  /* Schedule ring bursts across all cycles */
  for (let c = 0; c < cycles; c++) {
    const cycleStart = c * CYCLE;

    /* Each cycle has two short bursts (ring-ring) */
    const burstStarts = [cycleStart, cycleStart + RING_ON + RING_GAP];

    for (const start of burstStarts) {
      /* 440 Hz oscillator — first component of the dual tone */
      const osc1 = ctx.createOscillator();
      osc1.type = "sine";
      osc1.frequency.value = 440;

      /* 480 Hz oscillator — second component of the dual tone */
      const osc2 = ctx.createOscillator();
      osc2.type = "sine";
      osc2.frequency.value = 480;

      /* Per-burst gain envelope — ramps up/down to avoid clicks */
      const burstGain = ctx.createGain();
      burstGain.gain.setValueAtTime(0, ctx.currentTime + start);
      burstGain.gain.linearRampToValueAtTime(1, ctx.currentTime + start + 0.02);
      burstGain.gain.setValueAtTime(1, ctx.currentTime + start + RING_ON - 0.02);
      burstGain.gain.linearRampToValueAtTime(0, ctx.currentTime + start + RING_ON);

      /* Connect oscillators → burst gain → master gain → speakers */
      osc1.connect(burstGain);
      osc2.connect(burstGain);
      burstGain.connect(masterGain);

      /* Schedule start and stop times */
      osc1.start(ctx.currentTime + start);
      osc1.stop(ctx.currentTime + start + RING_ON);
      osc2.start(ctx.currentTime + start);
      osc2.stop(ctx.currentTime + start + RING_ON);
    }
  }

  /* Promise resolves when the full sequence is done */
  const promise = new Promise<void>((resolve) => {
    setTimeout(() => {
      ctx.close().catch(() => {});
      resolve();
    }, totalDuration * 1000);
  });

  /* Cancel function — immediately silences and closes the context */
  const cancel = () => {
    try {
      masterGain.gain.cancelScheduledValues(ctx.currentTime);
      masterGain.gain.setValueAtTime(0, ctx.currentTime);
      ctx.close().catch(() => {});
    } catch {
      /* AudioContext may already be closed — safe to ignore */
    }
  };

  return { promise, cancel };
}
