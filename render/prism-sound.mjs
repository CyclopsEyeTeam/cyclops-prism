/**
 * prism-sound.mjs - Prism Crystalline Harmonic Voice & Sonic Identity.
 *
 * Implements:
 * - CUES metadata dictionary (including voiced identity "name")
 * - soundFor(event) mapping Presence semantic events to sonic cues
 * - createSoundGate({ clock }) for studio playback control with debounce / stale suppression
 * - synthesize(name, sampleRate) for pure mathematical audio generation
 * - prepareBuffer(name, audioContext) for Web Audio playback
 */

export const VERSION = 'prism-sound/2';

export const CUES = Object.freeze({
  wake: {
    duration: 0.8,
    base: 'F#4',
    description: 'Warm sub-pulse blooming into an open-fifth crystal overtone',
  },
  attend: {
    duration: 0.35,
    base: 'F#5',
    description: 'Delicate high crystal ping with silky Hann attack and clean decay',
  },
  ask: {
    duration: 0.45,
    base: 'C#5',
    description: 'Gentle dual-tone aperture pause chime',
  },
  resolve: {
    duration: 0.45,
    base: 'A5->C#6',
    description: 'Resonant twin-strike glass resolve chime with continuous onset',
  },
  bloom: {
    duration: 1.1,
    base: 'F#4-C#6',
    description: 'Luminous refractive crystal bloom wave with shimmering tail',
  },
  halt: {
    duration: 0.4,
    base: 'F#4-G4',
    description: 'Damped dissonant crystal friction clash with gentle release',
  },
  copied: {
    duration: 0.55,
    base: 'C#5->F#5',
    description: 'Radiant open-fifth upward dispersion chime with smooth glide',
  },
  name: {
    duration: 2.2,
    base: 'F#3',
    description: 'Voiced identity greeting: "I am Prism", pure physical formant synthesis',
  },
});

const EVENT_CUE_MAP = {
  'session.wake': 'wake',
  'turn.attend': 'attend',
  'approval.request': 'ask',
  'refract.resolve': 'resolve',
  'turn.resolve': 'bloom',
  'turn.halt': 'halt',
  'turn.interrupt': 'halt',
  'reply.copied': 'copied',
  'presence.open': 'name',
};

/** Map a semantic presence event to a sonic cue */
export function soundFor(ev, level = 'full') {
  if (level === 'off') return null;
  if (!ev || typeof ev !== 'object' || typeof ev.type !== 'string') return null;
  const cueName = EVENT_CUE_MAP[ev.type];
  if (!cueName || !CUES[cueName]) return null;
  const cueMeta = CUES[cueName];
  return { name: cueName, duration: cueMeta.duration, seconds: cueMeta.duration };
}

/** Audio playback gate managing studio sound delivery */
export function createSoundGate({ clock = () => Date.now() / 1000 } = {}) {
  let enabled = false;
  let busyUntil = 0;

  return {
    setEnabled(value) {
      enabled = Boolean(value);
      if (!enabled) busyUntil = 0;
    },
    take(ev, now = clock()) {
      if (!enabled) return null;
      const cue = soundFor(ev);
      if (!cue) return null;

      // Event timestamp must be valid and live (not stale replay, not future)
      const t = typeof ev.t === 'number' && Number.isFinite(ev.t) ? ev.t : now;
      if (t > now || now - t > 1.5) return null;

      // Cooldown to prevent overlapping cacophony
      if (now < busyUntil) return null;

      busyUntil = now + cue.duration;
      return cue;
    },
  };
}

/** Studio audio host companion factory */
export function createPrismSound() {
  const gate = createSoundGate();
  return {
    observe(ev) { return soundFor(ev); },
    soundFor(ev, level = 'full') { return soundFor(ev, level); },
    prepareBuffer,
    createSoundGate,
  };
}

// Base frequencies matching build_audio.py
const TAU = 2.0 * Math.PI;
const F_SHARP_2 = 92.4986;
const C_SHARP_3 = 138.591;
const F_SHARP_3 = 184.997;
const F_SHARP_4 = 369.994;
const C_SHARP_5 = 554.365;
const F_SHARP_5 = 739.989;
const A_5 = 880.000;
const C_SHARP_6 = 1108.731;
const F_SHARP_6 = 1479.978;
const G_4 = 391.995;

function clamp(v, min = -1.0, max = 1.0) {
  return Math.max(min, Math.min(max, v));
}

function hannAttack(t, dur) {
  if (t <= 0.0) return 0.0;
  if (t >= dur) return 1.0;
  return 0.5 * (1.0 - Math.cos(Math.PI * (t / dur)));
}

function hannRelease(t, totalDur, relDur) {
  const rem = totalDur - t;
  if (rem <= 0.0) return 0.0;
  if (rem >= relDur) return 1.0;
  return 0.5 * (1.0 - Math.cos(Math.PI * (rem / relDur)));
}

function smoothstepPath(pts) {
  return function (t) {
    if (t <= pts[0][0]) return pts[0][1];
    for (let i = 1; i < pts.length; i++) {
      const t1 = pts[i][0];
      const v1 = pts[i][1];
      const t0 = pts[i - 1][0];
      const v0 = pts[i - 1][1];
      if (t <= t1) {
        const u = (t - t0) / (t1 - t0);
        return v0 + (v1 - v0) * u * u * (3.0 - 2.0 * u);
      }
    }
    return pts[pts.length - 1][1];
  };
}

class KlattResonator {
  constructor(rate) {
    this.rate = rate;
    this.y1 = 0.0;
    this.y2 = 0.0;
  }

  process(x, f, bw) {
    const C = -Math.exp(-TAU * bw / this.rate);
    const B = 2.0 * Math.exp(-Math.PI * bw / this.rate) * Math.cos(TAU * f / this.rate);
    const A = 1.0 - B - C;
    const y = A * x + B * this.y1 + C * this.y2;
    this.y2 = this.y1;
    this.y1 = y;
    return y;
  }
}

/** Pure mathematical waveform synthesizer mirroring build_audio.py */
export function synthesize(name, sampleRate = 48000) {
  const cue = CUES[name];
  if (!cue) throw new Error(`Unknown Prism sound cue: ${name}`);
  if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 96000) {
    throw new Error(`Invalid sample rate: ${sampleRate}`);
  }

  const length = Math.round(cue.duration * sampleRate);
  const out = new Float32Array(length);

  switch (name) {
    case 'wake': {
      const duration = 0.8;
      const res = new KlattResonator(sampleRate);
      let seed = 0x5A17F00D;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 3200.0, 1600.0);

        // Front noise transient (aperture breath contact)
        const fnEnv = hannAttack(t, 0.008) * Math.exp(-t / 0.030);
        const frontNoise = 0.16 * filtNoise * fnEnv;

        // Sub tone (Bass foundation)
        const subEnv = hannAttack(t, 0.035) * Math.exp(-t / 0.35);
        const sub = 0.42 * Math.sin(TAU * F_SHARP_2 * t) * subEnv;

        // Blooming crystalline harmonics
        const harmEnv = hannAttack(t, 0.08) * Math.exp(-t / 0.38);
        const root = 0.38 * Math.sin(TAU * F_SHARP_4 * t);
        const fifth = 0.30 * Math.sin(TAU * C_SHARP_5 * t);
        const crystal = 0.12 * Math.sin(TAU * F_SHARP_5 * t) * Math.exp(-t / 0.25);
        const harm = harmEnv * (root + fifth + crystal);

        const rel = hannRelease(t, duration, 0.04);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'attend': {
      const duration = 0.35;
      const res = new KlattResonator(sampleRate);
      let seed = 0xA11ED;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 3600.0, 1800.0);

        // Front noise transient (tactile glass impact)
        const fnEnv = hannAttack(t, 0.005) * Math.exp(-t / 0.018);
        const frontNoise = 0.18 * filtNoise * fnEnv;

        // Sub tone (Bass foundation)
        const subEnv = hannAttack(t, 0.020) * Math.exp(-t / 0.14);
        const sub = 0.38 * Math.sin(TAU * F_SHARP_2 * t) * subEnv;

        // Crystal ping harmonics
        const harmEnv = hannAttack(t, 0.020) * Math.exp(-t / 0.09);
        const p1 = 0.42 * Math.sin(TAU * F_SHARP_5 * t);
        const p2 = 0.28 * Math.sin(TAU * C_SHARP_6 * t);
        const p3 = 0.10 * Math.sin(TAU * F_SHARP_6 * t) * Math.exp(-t / 0.05);
        const harm = harmEnv * (p1 + p2 + p3);

        const rel = hannRelease(t, duration, 0.03);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'resolve': {
      const duration = 0.45;
      const res = new KlattResonator(sampleRate);
      let seed = 0x7E501FE;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 3800.0, 1800.0);

        const rel = hannRelease(t, duration, 0.03);

        // Strike 1 front transient
        const att1 = hannAttack(t, 0.005);
        const dec1 = Math.exp(-t / 0.020);
        const fn1 = 0.14 * filtNoise * att1 * dec1;

        // Strike 2 front transient
        const t2 = t - 0.08;
        let fn2 = 0.0;
        let envS2 = 0.0;
        if (t2 > 0.0) {
          const att2 = hannAttack(t2, 0.005);
          const dec2 = Math.exp(-t2 / 0.022);
          fn2 = 0.16 * filtNoise * att2 * dec2;
          envS2 = hannAttack(t2, 0.025) * Math.exp(-t2 / 0.20);
        }

        // Sub tone (Bass foundation)
        const subEnv = hannAttack(t, 0.025) * Math.exp(-t / 0.24);
        const sub = 0.38 * Math.sin(TAU * F_SHARP_2 * t) * subEnv;

        // Glass chime harmonics
        const envS1 = hannAttack(t, 0.025) * Math.exp(-t / 0.16);
        const strike1 = 0.42 * Math.sin(TAU * A_5 * t) * envS1;
        const strike2 = 0.46 * Math.sin(TAU * C_SHARP_6 * t) * envS2;
        const overtone = 0.12 * Math.sin(TAU * F_SHARP_6 * t) * envS2;

        const raw = rel * (fn1 + fn2 + sub + strike1 + strike2 + overtone);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'bloom': {
      const duration = 1.1;
      const res = new KlattResonator(sampleRate);
      let seed = 0xB1003;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 3000.0, 1600.0);

        // Front noise transient
        const fnEnv = hannAttack(t, 0.012) * Math.exp(-t / 0.050);
        const frontNoise = 0.15 * filtNoise * fnEnv;

        // Sub tone (Bass foundation)
        const subEnv = hannAttack(t, 0.040) * Math.exp(-t / 0.55);
        const sub = 0.40 * Math.sin(TAU * F_SHARP_2 * t) * subEnv;

        // Refractive harmonics
        const harmEnv = hannAttack(t, 0.09) * Math.exp(-t / 0.46);
        const shimmer = 1.0 + 0.04 * Math.sin(TAU * 6.5 * t);
        const h1 = 0.28 * Math.sin(TAU * F_SHARP_4 * t);
        const h2 = 0.28 * Math.sin(TAU * C_SHARP_5 * t);
        const h3 = 0.20 * Math.sin(TAU * F_SHARP_5 * t * shimmer);
        const h4 = 0.14 * Math.sin(TAU * C_SHARP_6 * t * shimmer);
        const harm = harmEnv * (h1 + h2 + h3 + h4);

        const rel = hannRelease(t, duration, 0.05);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'halt': {
      const duration = 0.4;
      const res = new KlattResonator(sampleRate);
      let seed = 0x8A17;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 2200.0, 1200.0);

        // Front noise transient
        const fnEnv = hannAttack(t, 0.006) * Math.exp(-t / 0.022);
        const frontNoise = 0.20 * filtNoise * fnEnv;

        // Sub tone (Bass thud)
        const subEnv = hannAttack(t, 0.015) * Math.exp(-t / 0.13);
        const sub = 0.44 * Math.sin(TAU * F_SHARP_2 * t) * subEnv;

        // Clash harmonics
        const harmEnv = hannAttack(t, 0.025) * Math.exp(-t / 0.11);
        const c1 = 0.38 * Math.sin(TAU * F_SHARP_4 * t);
        const c2 = 0.32 * Math.sin(TAU * G_4 * t);
        const harm = harmEnv * (c1 + c2);

        const rel = hannRelease(t, duration, 0.03);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'ask': {
      const duration = 0.45;
      const res = new KlattResonator(sampleRate);
      let seed = 0xA5C;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 3200.0, 1500.0);

        // Front noise transient
        const fnEnv = hannAttack(t, 0.007) * Math.exp(-t / 0.025);
        const frontNoise = 0.15 * filtNoise * fnEnv;

        // Sub tone (Bass foundation)
        const subEnv = hannAttack(t, 0.025) * Math.exp(-t / 0.20);
        const sub = (0.34 * Math.sin(TAU * C_SHARP_3 * t) + 0.18 * Math.sin(TAU * F_SHARP_2 * t)) * subEnv;

        // Chime harmonics
        const harmEnv = hannAttack(t, 0.035) * Math.exp(-t / 0.18);
        const c1 = 0.34 * Math.sin(TAU * C_SHARP_5 * t);
        const c2 = 0.30 * Math.sin(TAU * F_SHARP_5 * t);
        const harm = harmEnv * (c1 + c2);

        const rel = hannRelease(t, duration, 0.03);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'copied': {
      const duration = 0.55;
      const res = new KlattResonator(sampleRate);
      let seed = 0xC091ED;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const rawNoise = (seed / 4294967295) * 2.0 - 1.0;
        const filtNoise = res.process(rawNoise, 4200.0, 2000.0);

        // Front noise transient
        const fnEnv = hannAttack(t, 0.005) * Math.exp(-t / 0.020);
        const frontNoise = 0.18 * filtNoise * fnEnv;

        const u = Math.min(1.0, t / 0.14);
        const glideU = u * u * (3.0 - 2.0 * u);

        // Sub tone (Bass glide)
        const fSub = F_SHARP_2 + (C_SHARP_3 - F_SHARP_2) * glideU;
        const subEnv = hannAttack(t, 0.020) * Math.exp(-t / 0.22);
        const sub = 0.38 * Math.sin(TAU * fSub * t) * subEnv;

        // Chime harmonics
        const harmEnv = hannAttack(t, 0.030) * Math.exp(-t / 0.20);
        const freq = C_SHARP_5 + (F_SHARP_5 - C_SHARP_5) * glideU;
        const sweep = 0.42 * Math.sin(TAU * freq * t);
        const bell = 0.26 * Math.sin(TAU * F_SHARP_6 * t) * Math.exp(-t / 0.09);
        const harm = harmEnv * (sweep + bell);

        const rel = hannRelease(t, duration, 0.03);
        const raw = rel * (frontNoise + sub + harm);
        out[i] = clamp(Math.tanh(raw * 1.05) / 1.05);
      }
      break;
    }

    case 'name': {
      const duration = 2.2;
      const F_TABLE = [
        [0.00, 520, 1150, 2450],
        [0.08, 730, 1200, 2500],
        [0.22, 580, 1650, 2580],
        [0.32, 330, 2150, 2800],
        [0.38, 640, 1720, 2480],
        [0.48, 560, 1550, 2450],
        [0.54, 280, 1050, 2300],
        [0.65, 280, 1050, 2300],
        [0.68, 380, 1300, 2300],
        [0.72, 400, 1200, 2000],
        [0.78, 420, 1250, 1680],
        [0.86, 400, 1400, 1720],
        [0.92, 380, 2050, 2650],
        [1.04, 380, 2050, 2650],
        [1.10, 340, 1850, 2600],
        [1.20, 320, 1600, 2500],
        [1.25, 450, 1350, 2400],
        [1.32, 280, 1050, 2300],
        [1.52, 280, 1050, 2300],
      ];

      const F1 = smoothstepPath(F_TABLE.map((r) => [r[0], r[1]]));
      const F2 = smoothstepPath(F_TABLE.map((r) => [r[0], r[2]]));
      const F3 = smoothstepPath(F_TABLE.map((r) => [r[0], r[3]]));

      const voicePath = smoothstepPath([
        [0.00, 0.00], [0.08, 0.90], [0.26, 0.85], [0.34, 0.20],
        [0.37, 0.88], [0.47, 0.82], [0.53, 0.55], [0.63, 0.40], [0.67, 0.00],
        [0.72, 0.00], [0.76, 0.80], [1.02, 0.88], [1.12, 0.65], [1.22, 0.70],
        [1.32, 0.50], [1.46, 0.25], [1.56, 0.00]
      ]);

      const nasalPath = smoothstepPath([
        [0.00, 0.00], [0.50, 0.00], [0.54, 1.00], [0.64, 1.00], [0.67, 0.00],
        [1.30, 0.00], [1.34, 1.00], [1.50, 1.00], [1.56, 0.00]
      ]);

      const pitchPath = smoothstepPath([
        [0.00, F_SHARP_3 * 1.08], [0.25, F_SHARP_3 * 1.02], [0.50, F_SHARP_3 * 0.96],
        [0.75, F_SHARP_3 * 1.12], [0.95, F_SHARP_3 * 1.08], [1.18, F_SHARP_3 * 0.98],
        [1.48, F_SHARP_3 * 0.88]
      ]);

      const pBurst = smoothstepPath([[0.708, 0.00], [0.722, 0.30], [0.738, 0.00]]);
      const zFric = smoothstepPath([[1.05, 0.00], [1.11, 0.25], [1.18, 0.22], [1.24, 0.00]]);

      const R0 = new KlattResonator(sampleRate);
      const R1 = new KlattResonator(sampleRate);
      const R2 = new KlattResonator(sampleRate);
      const R3 = new KlattResonator(sampleRate);
      const R4 = new KlattResonator(sampleRate);
      const RN = new KlattResonator(sampleRate);
      const P_res = new KlattResonator(sampleRate);
      const Z_res = new KlattResonator(sampleRate);
      const FN_res = new KlattResonator(sampleRate);

      let prngSeed = 0x713C9241;
      const rnd = () => {
        prngSeed = (prngSeed ^ (prngSeed << 13)) >>> 0;
        prngSeed = (prngSeed ^ (prngSeed >>> 17)) >>> 0;
        prngSeed = (prngSeed ^ (prngSeed << 5)) >>> 0;
        return (prngSeed / 0xFFFFFFFF) * 2.0 - 1.0;
      };

      const voiceOut = new Float32Array(length);
      const subOut = new Float32Array(length);

      let ph = 0.0;
      let tilt = 0.0;
      let aspNoise = 0.0;

      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const f0 = pitchPath(t) * (1.0 + 0.002 * Math.sin(TAU * 4.6 * t));
        ph += TAU * f0 / sampleRate;

        let src = 0.0;
        for (let k = 1; k * f0 < 5200.0; k++) {
          const freq = k * f0;
          const rolloff = Math.exp(-freq / 1900.0);
          src += (Math.sin(k * ph) / Math.pow(k, 1.28)) * rolloff;
        }
        tilt += 0.45 * (src - tilt);

        const noise = rnd();
        const v = voicePath(t);

        aspNoise += 0.20 * (noise - aspNoise);
        const glottal = (tilt + 0.022 * aspNoise) * v;

        const r1_out = R1.process(glottal, F1(t), 95.0);
        const r2_out = R2.process(r1_out, F2(t), 115.0);
        const r3_out = R3.process(r2_out, F3(t), 160.0);
        const openMouth = R4.process(r3_out, 3400.0, 280.0);

        const murmur = RN.process(glottal, 260.0, 90.0) * 1.4;
        const nz = nasalPath(t);

        // Chest undertone reinforcement (provides the warm, grounded body under the front face vowels)
        const chestUndertone = R0.process(glottal, f0, 75.0) * 0.45;
        let y = openMouth * (1.0 - nz) + murmur * nz + chestUndertone;

        // Filter noise streams continuously to eliminate startup transients
        const pFiltered = P_res.process(noise, 950.0, 1100.0);
        const zFiltered = Z_res.process(noise, 5200.0, 1600.0);

        y += pBurst(t) * pFiltered * 0.45;
        y += zFric(t) * zFiltered * 0.30;

        // Front noise breath transient on initial vocal onset (airy breath of "I")
        const fnEnv = hannAttack(t, 0.010) * Math.exp(-t / 0.035);
        const fnFilt = FN_res.process(noise, 2800.0, 1500.0);
        y += 0.16 * fnFilt * fnEnv;

        voiceOut[i] = y;
      }

      // Sub-bass grounding foot with deep F#2 foundation (immediate rise at front face)
      const subEnv = smoothstepPath([[0.0, 0.0], [0.04, 0.38], [0.20, 0.36], [0.4, 0.34], [1.2, 0.28], [1.7, 0.0]]);
      let phSub = 0.0;
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const fSub = pitchPath(Math.min(t, 1.4)) / 2.0;
        phSub += TAU * fSub / sampleRate;
        const subTone = 0.70 * Math.sin(phSub) + 0.30 * Math.sin(TAU * F_SHARP_2 * t);
        subOut[i] = subEnv(t) * subTone;
      }

      // Crystalline celestial optical glints
      const glintFreqs = [F_SHARP_3 * 6.0, F_SHARP_3 * 8.0, F_SHARP_3 * 9.0, F_SHARP_3 * 12.0, F_SHARP_3 * 14.0, F_SHARP_3 * 16.0];
      for (let idx = 0; idx < glintFreqs.length; idx++) {
        const t0 = 1.30 + idx * 0.09;
        const dur = 0.28;
        const amp = 0.035 * (1.0 - idx * 0.12);
        const startI = Math.round(t0 * sampleRate);
        const lenI = Math.round(dur * sampleRate);
        for (let j = 0; j < lenI; j++) {
          if (startI + j >= length) break;
          const u = j / sampleRate;
          const glintEnv = hannAttack(u, 0.03) * Math.exp(-u / 0.11);
          voiceOut[startI + j] += amp * glintEnv * Math.sin(TAU * glintFreqs[idx] * u);
        }
      }

      // Combine with 2-pole cascaded analog-style low-pass smoothing filter
      let peak = 0.0;
      let lp1 = 0.0;
      let lp2 = 0.0;

      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const rel = hannRelease(t, duration, 0.05);
        const rawVal = (voiceOut[i] + subOut[i]) * rel;
        lp1 += 0.40 * (rawVal - lp1);
        lp2 += 0.40 * (lp1 - lp2);
        const val = Math.tanh(lp2 * 1.02) / 1.02;
        out[i] = val;
        if (Math.abs(val) > peak) peak = Math.abs(val);
      }

      const gain = 0.82 / Math.max(1e-6, peak);
      for (let i = 0; i < length; i++) {
        out[i] = clamp(out[i] * gain);
      }
      break;
    }
  }

  // Smooth final sample to zero to prevent DC pop
  out[length - 1] = 0;
  return out;
}

// Web Audio API buffer cache
const bufferCache = new WeakMap();

export async function prepareBuffer(name, audioContext) {
  if (!audioContext) throw new Error('AudioContext required');
  let cache = bufferCache.get(audioContext);
  if (!cache) {
    cache = new Map();
    bufferCache.set(audioContext, cache);
  }

  if (!cache.has(name)) {
    cache.set(name, (async () => {
      // Resolve asset candidates based on Studio vendor projection and local layout
      const candidates = [];
      if (name === 'name') {
        candidates.push(new URL('./prism-name.wav', import.meta.url));
        candidates.push(new URL('./sounds/prism/name.wav', import.meta.url));
        candidates.push(new URL('./prism-sounds/name.wav', import.meta.url));
      } else {
        candidates.push(new URL(`./sounds/prism/${name}.wav`, import.meta.url));
        candidates.push(new URL(`./prism-sounds/${name}.wav`, import.meta.url));
      }
      candidates.push(new URL(`../../assets/audio/${name}.wav`, import.meta.url));

      for (const url of candidates) {
        try {
          const resp = await fetch(url);
          if (resp.ok) {
            const ab = await resp.arrayBuffer();
            return await audioContext.decodeAudioData(ab);
          }
        } catch {
          // Continue to next candidate
        }
      }

      // Mathematical synthesizer fallback if assets are unavailable
      // Yield to the event loop first to prevent blocking immediate UI frames
      await new Promise((resolve) => setTimeout(resolve, 0));
      const samples = synthesize(name, audioContext.sampleRate);
      const buffer = audioContext.createBuffer(1, samples.length, audioContext.sampleRate);
      buffer.copyToChannel(samples, 0);
      return buffer;
    })());
  }

  return cache.get(name);
}
