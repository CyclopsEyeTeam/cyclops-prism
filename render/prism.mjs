/**
 * prism.mjs - Official Cyclops Studio Presence module for Prism.
 *
 * Implements:
 * - createPrism({ clock, composition, mood, palette })
 * - .apply(event) / .event(event)
 * - .state()
 * - .svg({ size, width, height, hud, reducedMotion, calm, composition, mood, palette })
 * - .paint(ctx, { width, height, dpr, pointer, time, reducedMotion, calm, composition, mood, palette })
 * - .rgba(W, H, { time, t, mood, palette, reducedMotion, calm, composition })
 * - .cells(cols, rows, { time, t, mood, palette, ground, hd, reducedMotion, calm, composition })
 * - .layout({ width, height, view, composition })
 * - .animation()
 * - .consumeCue(), .lastCue()
 * - .setComposition(c), .setMood(m)
 * - .proposeGesture(proposal), .ringBounds(opts), .visualField(redMot)
 * - slot()
 * - IDENTITY descriptor export
 *
 * Purity Invariant:
 * Pure Presence consumer. Contains zero Antigravity hook specifics, filesystem I/O,
 * raw commands, paths, prompt/response content, or raw hashes.
 */

import { soundFor } from './prism-sound.mjs';

export const PROTOCOL_VERSION = 'cyclops-presence/1';
export const RENDERER_VERSION = 'prism-renderer/1.6.0';
export const VERSION = '1.6.0';
export const PAINTER_PROTOCOL = 'prism-gesture/1';

export const VISUAL_FIELD_BOUNDS = Object.freeze({
  ring_inclination: Object.freeze({ min: -45.0, max: 45.0, default: 0.0 }),
  orbital_tension: Object.freeze({ min: 0.0, max: 1.0, default: 0.35 }),
  counter_rotation_ratio: Object.freeze({ min: -3.0, max: -0.33, default: -1.0 }),
  facet_orientation: Object.freeze({ min: -30.0, max: 30.0, default: 0.0 }),
  body_deformation: Object.freeze({ min: 0.8, max: 1.25, default: 1.0 }),
  chromatic_dispersion: Object.freeze({ min: 0.0, max: 1.0, default: 0.6 }),
  optical_depth: Object.freeze({ min: 0.2, max: 1.0, default: 0.85 }),
  surface_shimmer: Object.freeze({ min: 0.0, max: 1.0, default: 0.4 }),
  motion_rhythm: Object.freeze({ min: 0.5, max: 2.0, default: 1.0 }),
  expansion_contraction: Object.freeze({ min: 0.85, max: 1.15, default: 1.0 }),
  gesture_duration: Object.freeze({ min: 200, max: 6000, default: 1200 }),
  settle_character: Object.freeze({ min: 0.1, max: 0.9, default: 0.65 }),
  chromatic_aberration: Object.freeze({ min: 0.0, max: 1.0, default: 0.5 }),
});

export const MOTION_CURVES = Object.freeze({
  linear: (p) => p,
  easeInQuad: (p) => p * p,
  easeOutQuad: (p) => p * (2 - p),
  easeInOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : (p - 1) * (2 * p - 2) * (2 * p - 2) + 1),
  elasticOut: (p) => {
    if (p === 0 || p === 1) return p;
    return Math.sin(-13 * (Math.PI / 2) * (p + 1)) * Math.pow(2, -10 * p) + 1;
  },
  settleDamped: (p) => 1 - Math.exp(-4 * p) * Math.cos(Math.PI * p),
});

export const PALETTE_NAMES = Object.freeze([
  'crystalline',
  'aurora',
  'solar',
  'nebula',
  'emerald',
  'supernova',
  'zen',
]);

export const MOODS = Object.freeze({
  crystalline: Object.freeze({
    stops1: Object.freeze(['#00F2FE', '#FFFFFF', '#00E5A3', '#00F2FE']),
    stops2: Object.freeze(['#FFFFFF', '#00F2FE', '#7928CA', '#FFFFFF']),
    coreColor: '#00F2FE',
    facetColor: '#FFFFFF',
    haloColor: '#00F2FE',
  }),
  aurora: Object.freeze({
    stops1: Object.freeze(['#00F2FE', '#00E5A3', '#FF6EB4', '#7928CA']),
    stops2: Object.freeze(['#7928CA', '#FF6EB4', '#00E5A3', '#00F2FE']),
    coreColor: '#00F2FE',
    facetColor: '#FFF6D6',
    haloColor: '#FF6EB4',
  }),
  solar: Object.freeze({
    stops1: Object.freeze(['#FFB020', '#FF8042', '#FFF6D6', '#FFB020']),
    stops2: Object.freeze(['#FF8042', '#FFF6D6', '#FF4D4D', '#FFB020']),
    coreColor: '#FFB020',
    facetColor: '#FFF6D6',
    haloColor: '#FFB020',
  }),
  nebula: Object.freeze({
    stops1: Object.freeze(['#7928CA', '#FF6EB4', '#3B49DF', '#00F2FE']),
    stops2: Object.freeze(['#FF6EB4', '#7928CA', '#00F2FE', '#3B49DF']),
    coreColor: '#7928CA',
    facetColor: '#FF6EB4',
    haloColor: '#7928CA',
  }),
  emerald: Object.freeze({
    stops1: Object.freeze(['#00E5A3', '#00F2FE', '#FFF6D6', '#00E5A3']),
    stops2: Object.freeze(['#00F2FE', '#00E5A3', '#3B49DF', '#00E5A3']),
    coreColor: '#00E5A3',
    facetColor: '#FFF6D6',
    haloColor: '#00E5A3',
  }),
  supernova: Object.freeze({
    stops1: Object.freeze(['#FFF6D6', '#FFB020', '#FF6EB4', '#00F2FE']),
    stops2: Object.freeze(['#00F2FE', '#7928CA', '#FF4D4D', '#FFF6D6']),
    coreColor: '#FFF6D6',
    facetColor: '#FFFFFF',
    haloColor: '#FFB020',
  }),
  zen: Object.freeze({
    stops1: Object.freeze(['#00F2FE', '#3B49DF', '#00E5A3', '#00F2FE']),
    stops2: Object.freeze(['#3B49DF', '#00E5A3', '#00F2FE', '#3B49DF']),
    coreColor: '#00F2FE',
    facetColor: '#E0F2FE',
    haloColor: '#3B49DF',
  }),
});

export const IDENTITY = Object.freeze({
  id: 'prism',
  displayName: 'Prism',
  rendererVersion: RENDERER_VERSION,
  protocolVersion: PROTOCOL_VERSION,
  capabilities: Object.freeze([
    'renderer.compact',
    'renderer.full',
    'renderer.side',
    'renderer.top',
    'renderer.focus',
    'renderer.slot',
    'renderer.rgba',
    'renderer.cells',
    'presentation.calm',
    'presentation.reducedMotion',
    'presentation.moods',
    'audio.semantic',
  ]),
});

export const EVENTS = Object.freeze([
  'session.wake',
  'session.end',
  'turn.attend',
  'turn.synthesize',
  'turn.resolve',
  'turn.halt',
  'turn.interrupt',
  'refract.start',
  'refract.resolve',
  'refract.halt',
  'branch.start',
  'branch.resolve',
  'approval.request',
  'reply.crystallize',
  'reply.copied',
]);

let instanceCounter = 0;

// Finite safe kind color mapping for refraction tethers
const KIND_COLORS = Object.freeze({
  inspect: '#00F2FE', // hyper-cyan
  change: '#FFB020',  // solar gold
  execute: '#7928CA', // violet
  service: '#00E5A3', // emerald teal
  other: '#3B49DF',   // deep indigo
});

// Multi-spectral orbit colors for branch satellites
const SATELLITE_COLORS = Object.freeze([
  '#FFB020', // solar gold
  '#00F2FE', // hyper-cyan
  '#7928CA', // electric violet
  '#00E5A3', // emerald teal
]);

function hexToRgb01(hex) {
  const s = String(hex || '#00F2FE').replace('#', '').trim();
  if (s.length !== 6) return [0, 0.95, 1.0];
  const n = parseInt(s, 16);
  if (!Number.isFinite(n)) return [0, 0.95, 1.0];
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function hexWithAlpha(hex, alpha) {
  const [r, g, b] = hexToRgb01(hex);
  const a = Math.max(0, Math.min(1, Number.isFinite(alpha) ? alpha : 1));
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${a.toFixed(3)})`;
}

function packRgb24(r, g, b) {
  const ri = Math.max(0, Math.min(255, Math.round(r * 255)));
  const gi = Math.max(0, Math.min(255, Math.round(g * 255)));
  const bi = Math.max(0, Math.min(255, Math.round(b * 255)));
  return (ri << 16) | (gi << 8) | bi;
}

const QUADRANTS = [
  0x20, 0x2598, 0x259D, 0x2580,
  0x2596, 0x258C, 0x259E, 0x259B,
  0x2597, 0x259A, 0x2590, 0x259C,
  0x2584, 0x2599, 0x259F, 0x2588,
];

/** Canonical unit-circle mark for other panes and peer presence slots. */
export function slot(context = {}) {
  const size = context.size || 32;
  return `
    <g class="presence-slot-prism" data-identity="prism" data-feature="slot-signature" transform="scale(${size / 32})">
      <defs>
        <linearGradient id="prism-slot-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#00F2FE" />
          <stop offset="100%" stop-color="#3B49DF" />
        </linearGradient>
        <radialGradient id="prism-slot-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#00F2FE" stop-opacity="0.32" />
          <stop offset="100%" stop-color="#7928CA" stop-opacity="0" />
        </radialGradient>
      </defs>
      <!-- Ambient Caustic Halo -->
      <circle cx="16" cy="16" r="14" fill="url(#prism-slot-halo)" />
      <!-- Dual Polarized Rings -->
      <ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="#00F2FE" stroke-width="1.2" transform="rotate(-25 16 16)" opacity="0.85" />
      <ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="#7928CA" stroke-width="1" transform="rotate(25 16 16)" opacity="0.6" />
      <!-- Faceted Rhombus Core -->
      <polygon points="16,6 23,16 16,26 9,16" fill="url(#prism-slot-grad)" opacity="0.95" />
      <!-- Internal Crown Refraction Lines -->
      <path d="M16,6 L16,11 M23,16 L19.5,16 M16,26 L16,21 M9,16 L12.5,16" stroke="#FFFFFF" stroke-width="0.6" opacity="0.45" />
      <!-- Central Focus Node -->
      <polygon points="16,11 19.5,16 16,21 12.5,16" fill="#FFF6D6" opacity="0.9" />
    </g>
  `.trim();
}

/** Create an isolated Prism presence instance for Cyclops Studio. */
export function createPrism(options = {}) {
  const opts = typeof options === 'function' ? { clock: options } : (options || {});
  const getClock = typeof opts.clock === 'function' ? opts.clock : () => Date.now() / 1000;
  const instanceId = ++instanceCounter;
  const prefix = `prism_${instanceId}_`;

  // Internal semantic state
  let currentSeq = 0;
  let mode = 'idle'; // idle, attending, synthesizing, refracting, branching, approval, resolved, halted, ended
  let offer = null; // { kind: 'answer', token } or null
  let isEnded = false;
  let lastCueEmitted = null; // { name, at }
  let currentComposition = opts.composition || 'full';
  if (currentComposition === 'beside') currentComposition = 'side';
  let currentMood = (opts.mood || opts.palette || null);
  let hostConnected = true;
  let currentReplyToken = null;
  let turnsResolved = 0;
  let lastEventAt = 0;

  // Smooth gaze vector for the inner crystal facet
  let gazeX = 0;
  let gazeY = 0;

  // Active relational maps (stored by index/kind to prevent raw hash leakage into presentation)
  const activeCalls = new Map(); // key -> { kind, seq, t }
  const activeBranches = new Map(); // key -> { seq, t }

  // Painter VisualField & Gesture engine
  let hostRunId = null;
  const activeGestures = [];

  const NON_MOTION_DIMENSIONS = new Set([
    'chromatic_dispersion',
    'surface_shimmer',
    'optical_depth',
    'chromatic_aberration',
  ]);

  function computeVisualField(now = getClock(), motionOpts = false) {
    const isStill = typeof motionOpts === 'object'
      ? Boolean(motionOpts.reducedMotion || motionOpts.calm)
      : Boolean(motionOpts);
    const ambientBreath = isStill ? 0 : Math.sin(now * 1.3) * 0.025;
    const ambientShimmer = isStill ? 0 : (Math.sin(now * 2.8) + 1) * 0.2;
    const field = {
      ring_inclination: VISUAL_FIELD_BOUNDS.ring_inclination.default,
      orbital_tension: VISUAL_FIELD_BOUNDS.orbital_tension.default,
      counter_rotation_ratio: VISUAL_FIELD_BOUNDS.counter_rotation_ratio.default,
      facet_orientation: VISUAL_FIELD_BOUNDS.facet_orientation.default,
      body_deformation: VISUAL_FIELD_BOUNDS.body_deformation.default,
      chromatic_dispersion: VISUAL_FIELD_BOUNDS.chromatic_dispersion.default,
      optical_depth: VISUAL_FIELD_BOUNDS.optical_depth.default,
      surface_shimmer: Math.min(1.0, VISUAL_FIELD_BOUNDS.surface_shimmer.default + ambientShimmer),
      motion_rhythm: VISUAL_FIELD_BOUNDS.motion_rhythm.default,
      expansion_contraction: VISUAL_FIELD_BOUNDS.expansion_contraction.default + ambientBreath,
      settle_character: VISUAL_FIELD_BOUNDS.settle_character.default,
      chromatic_aberration: VISUAL_FIELD_BOUNDS.chromatic_aberration.default,
    };

    // Filter expired gestures
    for (let i = activeGestures.length - 1; i >= 0; i--) {
      const g = activeGestures[i];
      if (now >= g.endTime || now >= g.expiresAt) {
        activeGestures.splice(i, 1);
      }
    }

    if (activeGestures.length === 0 || !hostConnected || isEnded) {
      return field;
    }

    // Deterministic Composition Rules:
    // 1. Group active gestures and find maximum priority
    let maxPriority = -Infinity;
    for (const g of activeGestures) {
      if (g.priority > maxPriority) maxPriority = g.priority;
    }

    const dimDeltas = {};
    const dimWeights = {};

    for (const g of activeGestures) {
      // Priority suppression: gestures below maxPriority - 1 are suppressed
      if (g.priority < maxPriority - 1) continue;

      const durSec = g.durationMs / 1000;
      const progress = Math.max(0, Math.min(1, (now - g.startTime) / durSec));
      const curveFn = MOTION_CURVES[g.motionCurve] || MOTION_CURVES.easeInOutCubic;
      const curvedProgress = curveFn(progress);

      // C1 smooth envelope shaped by motion curve (0 at start -> 1 at peak -> 0 at finish)
      // Under reduced motion or calm: non-motion expressions are drawn static without oscillation
      const envelope = isStill ? 1.0 : Math.sin(Math.PI * curvedProgress);
      const factor = (g.priority === maxPriority) ? 1.0 : 0.5;
      const w = envelope * g.energy * factor;

      if (w <= 0.0001) continue;

      for (const [dimKey, targetVal] of Object.entries(g.dimensions)) {
        if (!VISUAL_FIELD_BOUNDS[dimKey]) continue;
        // Under reduced motion or calm: keep motion-type extensions strictly at home.
        // Only non-motion dimensions (chromatic_dispersion, surface_shimmer, optical_depth, chromatic_aberration) can show.
        if (isStill && !NON_MOTION_DIMENSIONS.has(dimKey)) {
          continue;
        }
        const defVal = VISUAL_FIELD_BOUNDS[dimKey].default;
        const delta = (targetVal - defVal) * w;
        dimDeltas[dimKey] = (dimDeltas[dimKey] || 0) + delta;
        dimWeights[dimKey] = (dimWeights[dimKey] || 0) + w;
      }
    }

    // Shared dimension blending and return to ambient equilibrium (Core Rule 4: Pulled Home)
    for (const [dimKey, totalWeight] of Object.entries(dimWeights)) {
      if (totalWeight > 0) {
        const normalizedDelta = dimDeltas[dimKey] / Math.max(1.0, totalWeight);
        field[dimKey] += normalizedDelta;
      }
      const b = VISUAL_FIELD_BOUNDS[dimKey];
      field[dimKey] = Math.max(b.min, Math.min(b.max, field[dimKey]));
    }

    return field;
  }

  function proposeGesture(proposal) {
    if (!proposal || typeof proposal !== 'object') {
      return { accepted: false, reason: 'Proposal must be a JSON object' };
    }
    if (proposal.protocol !== PAINTER_PROTOCOL) {
      return { accepted: false, reason: `Unsupported protocol: ${proposal.protocol}` };
    }
    if (!proposal.gestureId || typeof proposal.gestureId !== 'string') {
      return { accepted: false, reason: 'Invalid or missing gestureId' };
    }
    if (hostRunId && (!proposal.runId || proposal.runId !== hostRunId)) {
      return { accepted: false, reason: `Run authority mismatch: expected ${hostRunId}, got ${proposal.runId || 'unauthenticated'}` };
    }
    const now = getClock();
    let expiresAt = proposal.expiresAt;
    if (typeof expiresAt === 'number') {
      if (expiresAt > 1e11) expiresAt /= 1000;
      if (now > expiresAt) {
        return { accepted: false, reason: 'Proposal has expired' };
      }
    }
    const durationMs = typeof proposal.durationMs === 'number' ? proposal.durationMs : 1200;
    if (durationMs < 200 || durationMs > 6000) {
      return { accepted: false, reason: `Duration ${durationMs}ms outside allowed window [200, 6000]ms` };
    }
    if (proposal.eventRelation && proposal.eventRelation.required) {
      const reqType = proposal.eventRelation.type;
      const modeMap = {
        'turn.attend': 'attending',
        'turn.synthesize': 'synthesizing',
        'turn.resolve': 'resolved',
        'turn.halt': 'halted',
        'refract.start': 'refracting',
        'branch.start': 'branching',
        'approval.request': 'approval',
        'session.wake': 'idle',
        'session.end': 'ended',
      };
      const expectedMode = modeMap[reqType] || (reqType.includes('.') ? reqType.split('.').pop() : reqType);
      if (expectedMode !== mode && reqType !== mode) {
        return { accepted: false, reason: `Requires active host mode ${reqType}, currently in ${mode}` };
      }
    }

    // Expressive priority capped to [-2, 2]; host truth always dominates
    const priority = typeof proposal.priority === 'number' ? Math.max(-2, Math.min(2, proposal.priority)) : 0;
    const energy = typeof proposal.energy === 'number' ? Math.max(0.0, Math.min(1.0, proposal.energy)) : 0.5;
    const curve = typeof proposal.motionCurve === 'string' && MOTION_CURVES[proposal.motionCurve] ? proposal.motionCurve : 'easeInOutCubic';

    const clampedDims = {};
    if (proposal.dimensions && typeof proposal.dimensions === 'object') {
      for (const [k, v] of Object.entries(proposal.dimensions)) {
        const cleanKey = k.startsWith('prism.') ? k.slice(6) : k;
        if (VISUAL_FIELD_BOUNDS[cleanKey] && typeof v === 'number' && Number.isFinite(v)) {
          const b = VISUAL_FIELD_BOUNDS[cleanKey];
          clampedDims[cleanKey] = Math.max(b.min, Math.min(b.max, v));
        }
      }
    }
    if (Object.keys(clampedDims).length === 0) {
      return { accepted: false, reason: 'No valid dimensions provided' };
    }

    const startTime = now;
    const endTime = now + (durationMs / 1000);

    const gestureItem = {
      gestureId: proposal.gestureId,
      runId: proposal.runId,
      priority,
      energy,
      motionCurve: curve,
      dimensions: clampedDims,
      durationMs,
      startTime,
      endTime,
      expiresAt: proposal.expiresAt || endTime,
    };

    activeGestures.push(gestureItem);
    return { accepted: true, gestureId: proposal.gestureId };
  }

  function apply(event) {
    if (isEnded) return; // session.end is terminal
    if (!event || typeof event !== 'object' || typeof event.type !== 'string') return;

    // Reject stale or duplicate sequence numbers
    if (typeof event.seq === 'number' && event.seq <= currentSeq) return;
    if (typeof event.seq === 'number') currentSeq = event.seq;

    const typ = event.type;
    const key = event.key || event.id;
    const now = getClock();
    const stamp = typeof event.t === 'number' && Number.isFinite(event.t) ? event.t : now;
    lastEventAt = stamp;

    // Semantic state transition (supporting both Prism native events and universal Studio/Spark aliases)
    switch (typ) {
      case 'session.wake':
        mode = 'idle';
        offer = null;
        if (event.fresh) turnsResolved = 0;
        activeCalls.clear();
        activeBranches.clear();
        activeGestures.length = 0;
        break;

      case 'session.end':
        mode = 'ended';
        offer = null;
        isEnded = true;
        activeGestures.length = 0;
        break;

      case 'turn.attend':
      case 'turn.start':
      case 'prompt.submit':
        mode = 'attending';
        offer = null;
        break;

      case 'turn.synthesize':
      case 'stream':
        mode = 'synthesizing';
        offer = null;
        break;

      case 'approval.request':
      case 'tool.ask':
        mode = 'approval';
        break;

      case 'refract.start':
      case 'tool.start':
        mode = 'refracting';
        if (key && typeof key === 'string' && !activeCalls.has(key)) {
          const rawKind = event.kind || event.family || 'other';
          const safeKind = KIND_COLORS[rawKind] ? rawKind : 'other';
          activeCalls.set(key, { kind: safeKind, seq: event.seq || currentSeq, t: stamp });
        }
        break;

      case 'refract.resolve':
      case 'refract.halt':
      case 'tool.end':
        if (key && typeof key === 'string') {
          activeCalls.delete(key);
        }
        break;

      case 'branch.start':
      case 'side.ask':
        if (mode !== 'refracting') mode = 'branching';
        if (key && typeof key === 'string' && !activeBranches.has(key)) {
          activeBranches.set(key, { seq: event.seq || currentSeq, t: stamp });
        }
        break;

      case 'branch.resolve':
      case 'side.answer':
        if (key && typeof key === 'string') {
          activeBranches.delete(key);
        }
        break;

      case 'turn.resolve':
      case 'turn.end':
        if (event.reason && event.reason !== 'answer') {
          mode = 'halted';
          offer = null;
        } else {
          mode = 'resolved';
          turnsResolved += 1;
          offer = (hostConnected && currentReplyToken) ? { kind: 'answer', token: currentReplyToken } : null;
        }
        break;

      case 'turn.halt':
      case 'turn.interrupt':
        mode = 'halted';
        offer = null;
        break;

      case 'reply.crystallize':
        offer = (hostConnected && currentReplyToken) ? { kind: 'answer', token: currentReplyToken } : null;
        break;

      case 'reply.copied':
        offer = null;
        if (mode === 'resolved') {
          mode = 'idle';
        }
        break;

      default:
        // Ignore unrecognized events safely without throwing
        break;
    }

    // Dynamic mode resolution from active relations
    if (!isEnded && mode !== 'approval' && mode !== 'resolved' && mode !== 'halted') {
      if (activeCalls.size > 0) {
        mode = 'refracting';
      } else if (activeBranches.size > 0) {
        mode = 'branching';
      }
    }

    // Sonic cue emission: only emit for live events, NEVER during historical replay, NEVER when disconnected
    const cue = soundFor(event);
    if (cue && hostConnected && stamp >= (now - 2.0) && stamp <= (now + 0.5)) {
      lastCueEmitted = { name: cue.name, at: stamp };
    }
  }

  function consumeCue() {
    const c = lastCueEmitted;
    lastCueEmitted = null;
    return c;
  }

  function lastCue() {
    return lastCueEmitted;
  }

  function getHoverText() {
    let base = 'Prism · ready';
    if (isEnded) base = 'Prism · ended';
    else if (!hostConnected) base = 'Prism · disconnected';
    else if (mode === 'idle') base = 'Prism · ready';
    else if (mode === 'attending') base = 'Prism · attending';
    else if (mode === 'synthesizing') base = 'Prism · synthesizing';
    else if (mode === 'approval') base = 'Prism · awaiting consent';
    else if (mode === 'refracting') {
      const kinds = new Set();
      for (const call of activeCalls.values()) kinds.add(call.kind);
      const sorted = [...kinds].sort().join(', ');
      base = sorted ? `Prism · refracting · ${sorted}` : 'Prism · refracting';
    } else if (mode === 'branching') {
      const n = activeBranches.size;
      base = n === 1 ? 'Prism · 1 branch' : `Prism · ${n} branches`;
    } else if (mode === 'resolved') {
      base = offer ? 'Prism · crystallized · 1 ready' : 'Prism · crystallized';
    } else if (mode === 'halted') base = 'Prism · halted';

    if (activeGestures.length > 0 && hostConnected && !isEnded) {
      return `${base} ✎ painted`;
    }
    return base;
  }

  function state() {
    const isReadyOffer = Boolean(hostConnected && offer);
    return {
      hover: getHoverText(),
      glyph: isEnded ? '·' : (!hostConnected ? '⟐' : (mode === 'approval' ? '⟨!⟩' : (mode === 'resolved' ? '✦' : '⟐'))),
      mode,
      turns: turnsResolved,
      offer: isReadyOffer ? offer : null,
      ended: isEnded,
      connected: hostConnected,
      personRequired: mode === 'approval',
      composition: currentComposition,
      mood: currentMood,
      activeCalls: activeCalls.size,
      activeBranches: activeBranches.size,
      lanes: [...activeCalls.values()].map((c, idx) => ({ index: idx + 1, kind: c.kind })),
      painted: activeGestures.length > 0,
      expressionSource: activeGestures.length > 0 ? 'painter' : 'ambient',
    };
  }

  function layout({ width = 120, height = 120, view = null, composition = null } = {}) {
    let comp = composition || currentComposition;
    if (view) {
      if (view === 'beside' || view === 'side') comp = 'side';
      else if (view === 'top') comp = 'top';
      else if (view === 'only' || view === 'full') comp = 'full';
      else if (view === 'focus') comp = 'focus';
    } else if (comp === 'beside') {
      comp = 'side';
    } else if (!composition && (width > 0 && height > 0)) {
      if (width < height * 0.7) {
        comp = 'side';
      } else if (width > height * 2.2) {
        comp = 'top';
      } else {
        comp = 'full';
      }
    }
    const minDim = Math.min(width, height);
    return {
      width,
      height,
      composition: comp,
      view: view || (comp === 'side' ? 'beside' : (comp === 'top' ? 'top' : 'only')),
      cx: width / 2,
      cy: height / 2,
      scale: comp === 'focus' ? minDim * 1.2 : minDim,
    };
  }

  function animation() {
    return {
      continuous: !isEnded && hostConnected,
      fps: 30,
      visualField: computeVisualField(),
      activeGestures: activeGestures.length,
    };
  }

  function computeGazeTarget({ comp = 'full', pointer = null, cx = 60, cy = 60, isStill = false } = {}) {
    if (isStill || isEnded || !hostConnected) return [0, 0];
    if (mode === 'approval') return [0, 0]; // steady dead-center gaze when awaiting consent
    if (pointer && typeof pointer.x === 'number' && typeof pointer.y === 'number') {
      const dx = (pointer.x - cx) / Math.max(1, cx);
      const dy = (pointer.y - cy) / Math.max(1, cy);
      const d = Math.hypot(dx, dy);
      if (d > 0.02) {
        const clampD = Math.min(1, d);
        return [(dx / d) * clampD * 0.22, (dy / d) * clampD * 0.22];
      }
    }
    if (activeCalls.size > 0) {
      // Glance toward the latest active refraction ray
      const idx = activeCalls.size - 1;
      let rayAngle = (idx * (Math.PI * 2) / Math.max(1, activeCalls.size)) - (Math.PI / 2);
      if (comp === 'side') {
        const side = idx % 2 === 0 ? 1 : -1;
        rayAngle = (side > 0 ? 0 : Math.PI) + ((Math.floor(idx / 2) - 0.5) * 0.4);
      }
      return [Math.cos(rayAngle) * 0.18, Math.sin(rayAngle) * 0.18];
    }
    if (mode === 'resolved' || offer) {
      return [0, 0.16]; // Glance warmly down toward the held-out crystal offer
    }
    if (mode === 'attending') {
      return [0, 0.12]; // Attentive downward lean toward the person typing
    }
    return [0, 0];
  }

  function computeGeometry({
    comp = 'full',
    field,
    size = 120,
    width = null,
    height = null,
    scale = 1.0,
    place = null,
    gesture = null,
    pulse = null,
    reducedMotion = false,
    calm = false,
    isApproval = false,
  } = {}) {
    const isStill = Boolean(reducedMotion || calm);
    const w = width || size;
    const h = height || size;
    const cx = w / 2;
    const cy = h / 2;
    const minDim = Math.min(w, h);

    const effectivePlace = isStill ? { x: 0, y: 0 } : ((place && typeof place === 'object') ? place : { x: 0, y: 0 });
    const effectiveScale = isStill ? 1.0 : (typeof scale === 'number' && Number.isFinite(scale) ? scale : 1.0);
    const effectiveGesture = isStill ? 'none' : (typeof gesture === 'string' ? gesture : 'none');
    const effectivePulse = isStill ? 1.0 : (typeof pulse === 'number' && Number.isFinite(pulse) ? pulse : (effectiveGesture === 'pulse' ? 1.08 : 1.0));

    // Place translation bounded to 15% of radius (relative travel)
    const travelLimit = 0.15 * (minDim / 2);
    const shiftX = (effectivePlace.x || 0) * travelLimit;
    const shiftY = -(effectivePlace.y || 0) * travelLimit; // place.y is up (+1), screen y is down (+1)
    const posX = cx + shiftX;
    const posY = cy + shiftY;

    // Composition-specific base adjustments
    let baseRx1 = minDim * 0.42;
    let baseRy1 = minDim * 0.16;
    let ringAngle1 = (isApproval ? -42 : -25) + field.ring_inclination;
    let ringAngle2 = (isApproval ? 42 : 25) - field.ring_inclination;
    let baseCoreHx = minDim * 0.16;
    let baseCoreHy = minDim * 0.22;

    if (comp === 'side') {
      baseRx1 = minDim * 0.38;
      baseRy1 = minDim * 0.14;
      ringAngle1 = -65 + field.ring_inclination;
      ringAngle2 = 65 - field.ring_inclination;
      baseCoreHx = minDim * 0.14;
      baseCoreHy = minDim * 0.28;
    } else if (comp === 'top') {
      baseRx1 = minDim * 0.48;
      baseRy1 = minDim * 0.18;
      ringAngle1 = -15 + field.ring_inclination;
      ringAngle2 = 15 - field.ring_inclination;
      baseCoreHx = minDim * 0.24;
      baseCoreHy = minDim * 0.16;
    } else if (comp === 'focus') {
      baseRx1 = minDim * 0.46;
      baseRy1 = minDim * 0.20;
      ringAngle1 = -25 + field.ring_inclination;
      ringAngle2 = 25 - field.ring_inclination;
      baseCoreHx = minDim * 0.20;
      baseCoreHy = minDim * 0.28;
    }

    const tensionScaleX = 1.0 + (field.orbital_tension - 0.35) * 0.25;
    const tensionScaleY = Math.max(0.6, 1.0 - (field.orbital_tension - 0.35) * 0.25);
    const combinedScale = effectiveScale * field.expansion_contraction * effectivePulse;

    const rawRx1 = baseRx1 * combinedScale * tensionScaleX;
    const rawRy1 = baseRy1 * combinedScale * tensionScaleY;
    const rawCoreHx = baseCoreHx * combinedScale;
    const rawCoreHy = baseCoreHy * combinedScale * field.body_deformation;

    // Extents of rotated ellipses (outer rings)
    const rad1 = ringAngle1 * Math.PI / 180;
    const rad2 = ringAngle2 * Math.PI / 180;
    const strokeWidth = 1.5;

    const extX1 = Math.sqrt((rawRx1 * Math.cos(rad1)) ** 2 + (rawRy1 * Math.sin(rad1)) ** 2) + strokeWidth / 2;
    const extY1 = Math.sqrt((rawRx1 * Math.sin(rad1)) ** 2 + (rawRy1 * Math.cos(rad1)) ** 2) + strokeWidth / 2;
    const extX2 = Math.sqrt((rawRx1 * Math.cos(rad2)) ** 2 + (rawRy1 * Math.sin(rad2)) ** 2) + strokeWidth / 2;
    const extY2 = Math.sqrt((rawRx1 * Math.sin(rad2)) ** 2 + (rawRy1 * Math.cos(rad2)) ** 2) + strokeWidth / 2;

    const ringExtentX = Math.max(extX1, extX2);
    const ringExtentY = Math.max(extY1, extY2);

    // Diamond core extents
    const coreRad = field.facet_orientation * Math.PI / 180;
    const coreExtentX = Math.max(Math.abs(rawCoreHx * Math.cos(coreRad)), Math.abs(rawCoreHy * Math.sin(coreRad)));
    const coreExtentY = Math.max(Math.abs(rawCoreHx * Math.sin(coreRad)), Math.abs(rawCoreHy * Math.cos(coreRad)));

    const maxExtentX = Math.max(ringExtentX, coreExtentX);
    const maxExtentY = Math.max(ringExtentY, coreExtentY);

    // Frame safety margin: at least 1.5px padding from frame boundary
    const padding = 1.5;
    const maxAllowedX = Math.min(posX - padding, w - posX - padding);
    const maxAllowedY = Math.min(posY - padding, h - posY - padding);

    const overflowX = maxExtentX > maxAllowedX ? maxExtentX / maxAllowedX : 1.0;
    const overflowY = maxExtentY > maxAllowedY ? maxExtentY / maxAllowedY : 1.0;
    const overflowRatio = Math.max(overflowX, overflowY);

    // Bounded Total Size: when multiplying factors exceed frame clearance, scale total size uniformly
    const containmentFactor = overflowRatio > 1.0 ? (1.0 / overflowRatio) : 1.0;

    const rx1 = rawRx1 * containmentFactor;
    const ry1 = rawRy1 * containmentFactor;
    const coreHx = rawCoreHx * containmentFactor;
    const coreHy = rawCoreHy * containmentFactor;

    // Actual outer bounds of the rings after total size containment
    const actualExtX1 = Math.sqrt((rx1 * Math.cos(rad1)) ** 2 + (ry1 * Math.sin(rad1)) ** 2) + strokeWidth / 2;
    const actualExtY1 = Math.sqrt((rx1 * Math.sin(rad1)) ** 2 + (ry1 * Math.cos(rad1)) ** 2) + strokeWidth / 2;
    const actualExtX2 = Math.sqrt((rx1 * Math.cos(rad2)) ** 2 + (ry1 * Math.sin(rad2)) ** 2) + strokeWidth / 2;
    const actualExtY2 = Math.sqrt((rx1 * Math.sin(rad2)) ** 2 + (ry1 * Math.cos(rad2)) ** 2) + strokeWidth / 2;

    const finalRingExtX = Math.max(actualExtX1, actualExtX2);
    const finalRingExtY = Math.max(actualExtY1, actualExtY2);

    const ringBounds = {
      minX: posX - finalRingExtX,
      maxX: posX + finalRingExtX,
      minY: posY - finalRingExtY,
      maxY: posY + finalRingExtY,
    };

    return {
      w,
      h,
      cx,
      cy,
      minDim,
      posX,
      posY,
      rx1,
      ry1,
      coreHx,
      coreHy,
      ringAngle1,
      ringAngle2,
      containmentFactor,
      ringBounds,
      inBounds: ringBounds.minX >= 0 && ringBounds.maxX <= w && ringBounds.minY >= 0 && ringBounds.maxY <= h,
    };
  }

  function svg({
    size = 120,
    width = null,
    height = null,
    hud = true,
    reducedMotion = false,
    calm = false,
    composition = null,
    scale = null,
    place = null,
    gesture = null,
    pulse = null,
    mood = null,
    palette = null,
  } = {}) {
    let comp = composition || currentComposition;
    if (comp === 'beside') comp = 'side';
    const isStill = Boolean(reducedMotion || calm);
    const now = getClock();
    const field = computeVisualField(now, isStill);

    const isApproval = mode === 'approval';
    const isWorking = mode === 'refracting' || mode === 'branching' || mode === 'synthesizing';
    const isCrystallized = mode === 'resolved';
    const isHalted = mode === 'halted';

    const geom = computeGeometry({
      comp,
      field,
      size,
      width,
      height,
      scale,
      place,
      gesture,
      pulse,
      reducedMotion,
      calm,
      isApproval,
    });

    const visuals = deriveVisuals(mood || palette || currentMood);
    const ringOpacity = !hostConnected ? 0.25 : (isEnded ? 0.2 : (isHalted ? 0.4 : (isWorking ? 0.9 : 0.65)));
    const haloOpacity = !hostConnected || isEnded ? 0.08 : (isWorking ? 0.36 : (isCrystallized ? 0.42 : 0.22));

    // Active tool refraction rays
    const toolRays = [];
    const callCount = activeCalls.size;
    let callIdx = 0;
    for (const call of activeCalls.values()) {
      let rayAngle;
      if (comp === 'side') {
        const side = callIdx % 2 === 0 ? 1 : -1;
        rayAngle = (side > 0 ? 0 : Math.PI) + ((Math.floor(callIdx / 2) - 0.5) * 0.4);
      } else if (comp === 'top') {
        const side = callIdx % 2 === 0 ? 1 : -1;
        rayAngle = (side > 0 ? 0 : Math.PI) + (Math.floor(callIdx / 2) * 0.3 * (callIdx % 4 === 0 ? 1 : -1));
      } else {
        rayAngle = (callIdx * (Math.PI * 2) / Math.max(1, callCount)) - (Math.PI / 2);
      }

      const reach = (comp === 'focus' ? geom.minDim * 0.45 : geom.minDim * 0.38) * geom.containmentFactor;
      const rx = geom.posX + Math.cos(rayAngle) * reach;
      const ry = geom.posY + Math.sin(rayAngle) * reach;
      const rayColor = !hostConnected ? '#6B7280' : (KIND_COLORS[call.kind] || '#00F2FE');
      const rayOpacity = !hostConnected ? 0.25 : 0.85;
      const dotOpacity = !hostConnected ? 0.25 : 0.9;
      const dash = !hostConnected ? '1,3' : '3,2';

      toolRays.push(`
        <line x1="${geom.posX.toFixed(2)}" y1="${geom.posY.toFixed(2)}" x2="${rx.toFixed(2)}" y2="${ry.toFixed(2)}" stroke="${rayColor}" stroke-width="1.2" stroke-dasharray="${dash}" opacity="${rayOpacity}" />
        <circle cx="${rx.toFixed(2)}" cy="${ry.toFixed(2)}" r="${(geom.minDim * 0.035).toFixed(2)}" fill="${rayColor}" opacity="${dotOpacity}" />
      `);
      callIdx++;
    }

    // Active branch satellites
    const branchNodes = [];
    const branchCount = activeBranches.size;
    for (let i = 0; i < branchCount; i++) {
      let angle;
      if (comp === 'side') {
        const side = i % 2 === 0 ? 1 : -1;
        angle = (side > 0 ? 0 : Math.PI) + ((Math.floor(i / 2) + 1) * 0.5);
      } else {
        angle = (i * (Math.PI * 2) / Math.max(1, branchCount)) + (Math.PI / 4);
      }
      const bOrbit = (comp === 'focus' ? geom.minDim * 0.50 : geom.minDim * 0.44) * geom.containmentFactor;
      const bx = geom.posX + Math.cos(angle) * bOrbit;
      const by = geom.posY + Math.sin(angle) * bOrbit;
      const satColor = !hostConnected ? '#4B5563' : SATELLITE_COLORS[i % SATELLITE_COLORS.length];
      const satStroke = !hostConnected ? '#6B7280' : '#00F2FE';
      const satOpacity = !hostConnected ? 0.25 : 0.9;
      branchNodes.push(`
        <polygon points="${bx.toFixed(2)},${(by - 4).toFixed(2)} ${(bx + 4).toFixed(2)},${by.toFixed(2)} ${bx.toFixed(2)},${(by + 4).toFixed(2)} ${(bx - 4).toFixed(2)},${by.toFixed(2)}" fill="${satColor}" stroke="${satStroke}" stroke-width="1.2" opacity="${satOpacity}" />
      `);
    }

    // Answered-turn crown constellation stars
    const crownStars = [];
    const starCount = Math.min(7, turnsResolved);
    if (starCount > 0 && hostConnected && !isEnded) {
      const crownRadius = Math.min(geom.rx1 * 0.95, geom.minDim * 0.44);
      for (let s = 0; s < starCount; s++) {
        const frac = (s + 0.5) / starCount - 0.5;
        const sAngle = -Math.PI / 2 + frac * 1.3;
        const sx = geom.posX + Math.cos(sAngle) * crownRadius;
        const sy = geom.posY + Math.sin(sAngle) * (geom.ry1 * 1.85);
        const sr = (geom.minDim * 0.014).toFixed(2);
        crownStars.push(`<circle cx="${sx.toFixed(2)}" cy="${sy.toFixed(2)}" r="${sr}" fill="#FFF6D6" opacity="0.82" />`);
      }
    }

    // Held-out crystallized offer jewel below the core
    const offerRatio = isCrystallized && hostConnected && !isEnded ? 1 : 0;
    const offerY = (geom.coreHy * 1.24).toFixed(2);
    const offerR = (geom.minDim * 0.028).toFixed(2);
    const offerJewelSvg = offerRatio > 0
      ? `<path d="M0,${(geom.coreHy * 1.08).toFixed(2)} L${offerR},${offerY} L0,${(geom.coreHy * 1.40).toFixed(2)} L-${offerR},${offerY} Z" fill="#FFF6D6" stroke="#00F2FE" stroke-width="0.8" opacity="0.92" />`
      : '';

    // Internal 8-facet crown refraction lines connecting outer diamond to inner jewel
    const ix = (geom.coreHx * 0.58).toFixed(2);
    const iy = (geom.coreHy * 0.58).toFixed(2);
    const ox = geom.coreHx.toFixed(2);
    const oy = geom.coreHy.toFixed(2);
    const crownPaths = `<path d="M0,-${oy} L0,-${iy} M${ox},0 L${ix},0 M0,${oy} L0,${iy} M-${ox},0 L-${ix},0 M-${(geom.coreHx * 0.5).toFixed(2)},-${(geom.coreHy * 0.5).toFixed(2)} L0,-${iy} M${(geom.coreHx * 0.5).toFixed(2)},-${(geom.coreHy * 0.5).toFixed(2)} L0,-${iy}" stroke="#FFFFFF" stroke-width="0.65" opacity="${isEnded ? 0.15 : 0.42}" fill="none" />`;

    const hover = getHoverText();
    const titleElem = hud ? `<title>${hover}</title>` : '';
    const innerRingRx = (geom.rx1 * 0.68).toFixed(2);
    const innerRingRy = (geom.ry1 * 0.68).toFixed(2);
    const innerRingAngle = ((geom.ringAngle1 + geom.ringAngle2) * 0.5 + 90).toFixed(2);

    return `
<svg viewBox="0 0 ${geom.w} ${geom.h}" width="${geom.w}" height="${geom.h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${hover}" data-identity="prism" data-mode="${mode}" data-composition="${comp}" data-painted="${activeGestures.length > 0}">
  ${titleElem}
  <defs>
    <radialGradient id="${prefix}halo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${visuals.haloColor}" stop-opacity="${haloOpacity.toFixed(2)}" />
      <stop offset="60%" stop-color="${visuals.ring2Color}" stop-opacity="${(haloOpacity * 0.45).toFixed(2)}" />
      <stop offset="100%" stop-color="${visuals.ring1Color}" stop-opacity="0" />
    </radialGradient>
    <linearGradient id="${prefix}grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${visuals.ring1Color}" />
      <stop offset="52%" stop-color="${visuals.coreColor}" />
      <stop offset="100%" stop-color="${visuals.ring2Color}" />
    </linearGradient>
    <linearGradient id="${prefix}ring1" x1="0%" y1="0%" x2="100%" y2="0%">
      ${visuals.stops1.map((c, idx) => `<stop offset="${(idx / (visuals.stops1.length - 1) * 100).toFixed(0)}%" stop-color="${c}" />`).join('\n      ')}
    </linearGradient>
    <linearGradient id="${prefix}ring2" x1="100%" y1="0%" x2="0%" y2="100%">
      ${visuals.stops2.map((c, idx) => `<stop offset="${(idx / (visuals.stops2.length - 1) * 100).toFixed(0)}%" stop-color="${c}" />`).join('\n      ')}
    </linearGradient>
  </defs>

  <!-- Ambient Caustic Halo & Turn Constellation -->
  <g class="prism-caustics">
    <circle cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" r="${(geom.rx1 * 1.08).toFixed(2)}" fill="url(#${prefix}halo)" />
    ${crownStars.join('\n    ')}
  </g>

  <!-- Ambient Ground / Polarized Rings -->
  <g class="prism-rings">
    <ellipse cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" rx="${geom.rx1.toFixed(2)}" ry="${geom.ry1.toFixed(2)}" fill="none" stroke="url(#${prefix}ring1)" stroke-width="1.5" transform="rotate(${geom.ringAngle1} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})" opacity="${ringOpacity}" />
    <ellipse cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" rx="${geom.rx1.toFixed(2)}" ry="${geom.ry1.toFixed(2)}" fill="none" stroke="url(#${prefix}ring2)" stroke-width="1.2" transform="rotate(${geom.ringAngle2} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})" opacity="${(ringOpacity * 0.8).toFixed(2)}" />
    <ellipse cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" rx="${innerRingRx}" ry="${innerRingRy}" fill="none" stroke="url(#${prefix}ring1)" stroke-width="0.75" stroke-dasharray="2,3" transform="rotate(${innerRingAngle} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})" opacity="${(ringOpacity * 0.52).toFixed(2)}" />
  </g>

  <!-- Refraction Tool Rays -->
  <g class="prism-refractions">${toolRays.join('')}</g>

  <!-- Branch Satellite Nodes -->
  <g class="prism-satellites">${branchNodes.join('')}</g>

  <!-- Central Faceted Diamond Core -->
  <g class="prism-core" transform="translate(${geom.posX.toFixed(2)}, ${geom.posY.toFixed(2)}) rotate(${field.facet_orientation.toFixed(2)})">
    <polygon points="0,${(-geom.coreHy).toFixed(2)} ${(geom.coreHx).toFixed(2)},0 0,${(geom.coreHy).toFixed(2)} ${(-geom.coreHx).toFixed(2)},0" fill="url(#${prefix}grad)" opacity="${isEnded ? 0.3 : (!hostConnected ? 0.4 : 0.9)}" />
    <!-- Inner Refractive Facet -->
    <polygon points="0,${(-geom.coreHy * 0.58).toFixed(2)} ${(geom.coreHx * 0.58).toFixed(2)},0 0,${(geom.coreHy * 0.58).toFixed(2)} ${(-geom.coreHx * 0.58).toFixed(2)},0" fill="${visuals.facetColor}" opacity="${isEnded ? 0.4 : (!hostConnected ? 0.5 : (0.95 * field.optical_depth).toFixed(2))}" />
    ${crownPaths}
    ${offerJewelSvg}
    ${field.surface_shimmer > 0.5 ? `<circle cx="0" cy="${(-geom.coreHy * 0.3).toFixed(2)}" r="${(geom.minDim * 0.02 * field.surface_shimmer).toFixed(2)}" fill="#FFFFFF" opacity="${((field.surface_shimmer - 0.5) * 1.8).toFixed(2)}" />` : ''}
  </g>
</svg>`.trim();
  }

  function deriveVisuals(requestedMood = null) {
    const isApproval = mode === 'approval';
    const isEndedMode = isEnded || mode === 'ended';
    const isHalted = mode === 'halted';
    const isCrystallized = mode === 'resolved';
    const isAttending = mode === 'attending';

    let primaryKind = '';
    if (activeCalls.size > 0) {
      primaryKind = activeCalls.values().next().value?.kind || '';
    }

    const activeMoodKey = requestedMood && MOODS[requestedMood] ? requestedMood : (currentMood && MOODS[currentMood] ? currentMood : null);

    let stops1;
    let stops2;
    let coreColor;
    let facetColor;
    let haloColor = '#00F2FE';

    if (!hostConnected) {
      stops1 = ['#374151', '#4B5563', '#374151'];
      stops2 = ['#1F2937', '#374151', '#1F2937'];
      coreColor = '#374151';
      facetColor = '#6B7280';
      haloColor = '#374151';
    } else if (isApproval) {
      stops1 = ['#FF4D4D', '#FFB020', '#FF4D4D', '#FFB020'];
      stops2 = ['#FFB020', '#FF4D4D', '#FFB020', '#FF4D4D'];
      coreColor = '#FF8042';
      facetColor = '#FFE066';
      haloColor = '#FF4D4D';
    } else if (isEndedMode) {
      stops1 = ['#1F2937', '#374151', '#1F2937'];
      stops2 = ['#111827', '#1F2937', '#111827'];
      coreColor = '#111827';
      facetColor = '#4B5563';
      haloColor = '#111827';
    } else if (isHalted) {
      stops1 = ['#374151', '#6B7280', '#374151'];
      stops2 = ['#4B5563', '#374151', '#4B5563'];
      coreColor = '#374151';
      facetColor = '#9CA3AF';
      haloColor = '#4B5563';
    } else if (activeMoodKey && mode !== 'refracting' && !isCrystallized) {
      const m = MOODS[activeMoodKey];
      stops1 = [...m.stops1];
      stops2 = [...m.stops2];
      coreColor = m.coreColor;
      facetColor = m.facetColor;
      haloColor = m.haloColor;
    } else if (isCrystallized) {
      stops1 = ['#FFF6D6', '#00F2FE', '#FFF6D6', '#00E5A3'];
      stops2 = ['#00F2FE', '#FFF6D6', '#7928CA', '#FFF6D6'];
      coreColor = '#FFF6D6';
      facetColor = '#FFFFFF';
      haloColor = '#FFF6D6';
    } else if (mode === 'refracting') {
      if (primaryKind === 'change') {
        stops1 = ['#FFB020', '#FF8042', '#00F2FE', '#FFB020'];
        stops2 = ['#00F2FE', '#FFB020', '#7928CA', '#FF8042'];
        coreColor = '#FFB020';
        facetColor = '#FFFFFF';
        haloColor = '#FFB020';
      } else if (primaryKind === 'execute') {
        stops1 = ['#7928CA', '#4C1D95', '#00F2FE', '#7928CA'];
        stops2 = ['#00F2FE', '#7928CA', '#FFF6D6', '#4C1D95'];
        coreColor = '#7928CA';
        facetColor = '#7928CA';
        haloColor = '#7928CA';
      } else if (primaryKind === 'inspect') {
        stops1 = ['#00F2FE', '#00E5A3', '#FFF6D6', '#00F2FE'];
        stops2 = ['#00E5A3', '#00F2FE', '#7928CA', '#00E5A3'];
        coreColor = '#00F2FE';
        facetColor = '#FFFFFF';
        haloColor = '#00F2FE';
      } else if (primaryKind === 'service') {
        stops1 = ['#00E5A3', '#00F2FE', '#00E5A3', '#FFF6D6'];
        stops2 = ['#00F2FE', '#00E5A3', '#FFB020', '#00F2FE'];
        coreColor = '#00E5A3';
        facetColor = '#00E5A3';
        haloColor = '#00E5A3';
      } else {
        stops1 = ['#00F2FE', '#FFB020', '#7928CA', '#00E5A3'];
        stops2 = ['#7928CA', '#00E5A3', '#FFB020', '#00F2FE'];
        coreColor = '#00F2FE';
        facetColor = '#00F2FE';
        haloColor = '#00F2FE';
      }
    } else if (isAttending) {
      stops1 = ['#00F2FE', '#00E5A3', '#7928CA', '#FFF6D6'];
      stops2 = ['#7928CA', '#FFF6D6', '#FFB020', '#00F2FE'];
      coreColor = '#00F2FE';
      facetColor = '#FFFFFF';
      haloColor = '#00F2FE';
    } else {
      // Signature iridescent dispersion (synthesizing, branching, idle)
      stops1 = ['#00F2FE', '#00E5A3', '#7928CA', '#FFF6D6'];
      stops2 = ['#7928CA', '#FFF6D6', '#FFB020', '#00F2FE'];
      coreColor = '#00F2FE';
      facetColor = '#FFF6D6';
      haloColor = '#7928CA';
    }

    return {
      stops1,
      stops2,
      ring1Color: stops1[0],
      ring2Color: stops2[0],
      coreColor,
      facetColor,
      haloColor,
    };
  }

  function paint(
    ctx,
    {
      width = 200,
      height = 200,
      dpr = 1,
      pointer = null,
      time = null,
      t: tAlias = null,
      reducedMotion = false,
      calm = false,
      composition = null,
      scale = null,
      place = null,
      gesture = null,
      pulse = null,
      mood = null,
      palette = null,
    } = {}
  ) {
    if (!ctx) return;
    let comp = composition || currentComposition;
    if (comp === 'beside') comp = 'side';
    const isStill = Boolean(reducedMotion || calm);
    const w = width;
    const h = height;
    const cx = w / 2;
    const cy = h / 2;
    const minDim = Math.min(w, h);

    const rawTime = typeof time === 'number' && Number.isFinite(time) ? time : tAlias;
    const t = typeof rawTime === 'number' && Number.isFinite(rawTime) ? rawTime : getClock();

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    const isApproval = mode === 'approval';
    const isWorking = mode === 'refracting' || mode === 'branching' || mode === 'synthesizing';
    const isCrystallized = mode === 'resolved';
    const isHalted = mode === 'halted';

    const visuals = deriveVisuals(mood || palette || currentMood);
    const field = computeVisualField(t, isStill);

    const geom = computeGeometry({
      comp,
      field,
      size: minDim,
      width: w,
      height: h,
      scale,
      place,
      gesture,
      pulse,
      reducedMotion: isStill,
      calm,
      isApproval,
    });

    // Parallax tilt calculation: bounded to +/- 10px (suppressed in reduced motion)
    let tiltX = 0;
    let tiltY = 0;
    if (!isStill && pointer && typeof pointer.x === 'number' && typeof pointer.y === 'number') {
      const dx = (pointer.x - cx) / Math.max(1, cx);
      const dy = (pointer.y - cy) / Math.max(1, cy);
      tiltX = Math.max(-10, Math.min(10, dx * 10));
      tiltY = Math.max(-10, Math.min(10, dy * 10));
    }

    // Smooth inner-facet gaze tracking
    const [targetGx, targetGy] = computeGazeTarget({ comp, pointer, cx, cy, isStill });
    gazeX = isStill ? 0 : gazeX + (targetGx - gazeX) * 0.25;
    gazeY = isStill ? 0 : gazeY + (targetGy - gazeY) * 0.25;

    ctx.translate(geom.posX + tiltX, geom.posY + tiltY);

    // Rotation angles: smoothly advancing or parked
    let angle1 = -0.44;
    let angle2 = 0.44;
    if (comp === 'side') {
      angle1 = -1.13;
      angle2 = 1.13;
    } else if (comp === 'top') {
      angle1 = -0.26;
      angle2 = 0.26;
    }

    if (!isStill && !isEnded) {
      const speed = isWorking ? 1.2 : (calm ? 0.3 : 0.6);
      const rhythm = field.motion_rhythm;
      angle1 += (t * speed * 0.5 * rhythm * (field.counter_rotation_ratio / -1.0)) + (field.ring_inclination * Math.PI / 180);
      angle2 -= (t * speed * 0.5 * rhythm) - (field.ring_inclination * Math.PI / 180);
    }

    const alpha = isEnded ? 0.25 : (isHalted ? 0.45 : 1.0);

    const ringRx = geom.rx1;
    const ringRy = geom.ry1;
    const coreW = geom.coreHx;
    const coreH = geom.coreHy;

    // 0. Ambient Caustic Radial Halo behind the rings & core
    if (typeof ctx.createRadialGradient === 'function' && !isEnded && hostConnected) {
      const haloR = Math.max(12, ringRx * 1.15);
      const hg = ctx.createRadialGradient(0, 0, coreW * 0.2, 0, 0, haloR);
      const haloAlpha = isWorking ? 0.32 : (isCrystallized ? 0.38 : 0.20);
      hg.addColorStop(0, hexWithAlpha(visuals.haloColor, haloAlpha));
      hg.addColorStop(0.55, hexWithAlpha(visuals.ring2Color, haloAlpha * 0.45));
      hg.addColorStop(1, hexWithAlpha(visuals.ring1Color, 0));
      ctx.save();
      ctx.fillStyle = hg;
      ctx.beginPath();
      ctx.arc(0, 0, haloR, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // 1. Primary Polarized Ring with optical dispersion gradient
    ctx.save();
    ctx.rotate(angle1);
    ctx.beginPath();
    if (typeof ctx.ellipse === 'function') {
      ctx.ellipse(0, 0, ringRx, ringRy, 0, 0, Math.PI * 2);
    } else {
      ctx.arc(0, 0, 36, 0, Math.PI * 2);
    }
    if (typeof ctx.createLinearGradient === 'function') {
      const g1 = ctx.createLinearGradient(-ringRx, -ringRy, ringRx, ringRy);
      for (let s = 0; s < visuals.stops1.length; s++) {
        g1.addColorStop(s / (visuals.stops1.length - 1), visuals.stops1[s]);
      }
      ctx.strokeStyle = g1;
    } else {
      ctx.strokeStyle = visuals.ring1Color;
    }
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = alpha * 0.85;
    ctx.stroke();

    // Travelling photon glint on Primary Ring
    if (!isStill && !isEnded && hostConnected) {
      const glintPhi = (t * 2.2) % (Math.PI * 2);
      const gx1 = Math.cos(glintPhi) * ringRx;
      const gy1 = Math.sin(glintPhi) * ringRy;
      ctx.beginPath();
      ctx.arc(gx1, gy1, Math.max(1.5, minDim * 0.014), 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.globalAlpha = alpha * 0.92;
      ctx.fill();
    }
    ctx.restore();

    // 2. Secondary Polarized Ring with counter-dispersion gradient
    ctx.save();
    ctx.rotate(angle2);
    ctx.beginPath();
    if (typeof ctx.ellipse === 'function') {
      ctx.ellipse(0, 0, ringRx, ringRy, 0, 0, Math.PI * 2);
    } else {
      ctx.arc(0, 0, 36, 0, Math.PI * 2);
    }
    if (typeof ctx.createLinearGradient === 'function') {
      const g2 = ctx.createLinearGradient(ringRx, -ringRy, -ringRx, ringRy);
      for (let s = 0; s < visuals.stops2.length; s++) {
        g2.addColorStop(s / (visuals.stops2.length - 1), visuals.stops2[s]);
      }
      ctx.strokeStyle = g2;
    } else {
      ctx.strokeStyle = visuals.ring2Color;
    }
    ctx.lineWidth = 1.2;
    ctx.globalAlpha = alpha * 0.75;
    ctx.stroke();

    // Travelling photon glint on Secondary Ring
    if (!isStill && !isEnded && hostConnected) {
      const glintPhi2 = -(t * 1.85 + Math.PI * 0.5) % (Math.PI * 2);
      const gx2 = Math.cos(glintPhi2) * ringRx;
      const gy2 = Math.sin(glintPhi2) * ringRy;
      ctx.beginPath();
      ctx.arc(gx2, gy2, Math.max(1.3, minDim * 0.012), 0, Math.PI * 2);
      ctx.fillStyle = '#FFF6D6';
      ctx.globalAlpha = alpha * 0.88;
      ctx.fill();
    }
    ctx.restore();

    // 2b. 3rd Inner Harmonic Gossamer Ring
    if (!isEnded && hostConnected) {
      ctx.save();
      const angle3 = ((angle1 + angle2) * 0.5) + (isStill ? Math.PI / 2 : -t * 0.75);
      ctx.rotate(angle3);
      ctx.beginPath();
      if (typeof ctx.ellipse === 'function') {
        ctx.ellipse(0, 0, ringRx * 0.68, ringRy * 0.68, 0, 0, Math.PI * 2);
      } else {
        ctx.arc(0, 0, 24, 0, Math.PI * 2);
      }
      ctx.strokeStyle = visuals.facetColor;
      ctx.lineWidth = 0.8;
      ctx.globalAlpha = alpha * 0.38;
      if (typeof ctx.setLineDash === 'function') ctx.setLineDash([2, 3]);
      ctx.stroke();
      if (typeof ctx.setLineDash === 'function') ctx.setLineDash([]);
      ctx.restore();
    }

    // 3. Active Tool Refraction Lines
    const callCount = activeCalls.size;
    if (callCount > 0) {
      let idx = 0;
      for (const call of activeCalls.values()) {
        let rayAngle;
        if (comp === 'side') {
          const side = idx % 2 === 0 ? 1 : -1;
          rayAngle = (side > 0 ? 0 : Math.PI) + ((Math.floor(idx / 2) - 0.5) * 0.4);
        } else if (comp === 'top') {
          const side = idx % 2 === 0 ? 1 : -1;
          rayAngle = (side > 0 ? 0 : Math.PI) + (Math.floor(idx / 2) * 0.3 * (idx % 4 === 0 ? 1 : -1));
        } else {
          rayAngle = (idx * (Math.PI * 2) / callCount) - (Math.PI / 2);
        }

        const rx = Math.cos(rayAngle) * 44;
        const ry = Math.sin(rayAngle) * 44;
        const rayColor = !hostConnected ? '#6B7280' : (KIND_COLORS[call.kind] || '#00F2FE');

        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(rx, ry);
        ctx.strokeStyle = rayColor;
        ctx.lineWidth = 1.2;
        ctx.globalAlpha = !hostConnected ? alpha * 0.25 : alpha * 0.85;
        if (typeof ctx.setLineDash === 'function') {
          ctx.setLineDash(!hostConnected ? [1, 3] : [3, 2]);
        }
        ctx.stroke();
        if (typeof ctx.setLineDash === 'function') {
          ctx.setLineDash([]);
        }

        // Endpoint focus node
        ctx.beginPath();
        ctx.arc(rx, ry, !hostConnected ? 2.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = rayColor;
        ctx.globalAlpha = !hostConnected ? alpha * 0.25 : alpha * 0.95;
        ctx.fill();

        idx++;
      }
    }

    // 4. Active Branch Orbiting Satellites
    const branchCount = activeBranches.size;
    if (branchCount > 0) {
      const orbitAngleBase = (!reducedMotion && hostConnected ? t * 0.6 : 0) + (Math.PI / 4);
      for (let i = 0; i < branchCount; i++) {
        let bAngle;
        if (comp === 'side') {
          const side = i % 2 === 0 ? 1 : -1;
          bAngle = (side > 0 ? 0 : Math.PI) + ((Math.floor(i / 2) + 1) * 0.5);
        } else {
          bAngle = orbitAngleBase + (i * (Math.PI * 2) / branchCount);
        }
        const bx = Math.cos(bAngle) * 52;
        const by = Math.sin(bAngle) * 52;
        const satColor = !hostConnected ? '#4B5563' : SATELLITE_COLORS[i % SATELLITE_COLORS.length];
        const satStroke = !hostConnected ? '#6B7280' : '#00F2FE';

        ctx.beginPath();
        ctx.moveTo(bx, by - 4.5);
        ctx.lineTo(bx + 4.5, by);
        ctx.lineTo(bx, by + 4.5);
        ctx.lineTo(bx - 4.5, by);
        ctx.closePath();
        ctx.fillStyle = satColor;
        ctx.strokeStyle = satStroke;
        ctx.lineWidth = 1.0;
        ctx.globalAlpha = !hostConnected ? alpha * 0.25 : alpha * 0.9;
        ctx.fill();
        ctx.stroke();
      }
    }

    // 4b. Answered-Turn Constellation Crown Stars
    const starCount = Math.min(7, turnsResolved);
    if (starCount > 0 && hostConnected && !isEnded) {
      const crownR = Math.min(ringRx * 0.95, minDim * 0.44);
      for (let s = 0; s < starCount; s++) {
        const frac = (s + 0.5) / starCount - 0.5;
        const sAng = -Math.PI / 2 + frac * 1.3;
        const sx = Math.cos(sAng) * crownR;
        const sy = Math.sin(sAng) * (ringRy * 1.85);
        const twinkle = isStill ? 0.8 : 0.65 + 0.35 * Math.sin(t * 2.4 + s * 1.3);
        ctx.beginPath();
        ctx.arc(sx, sy, Math.max(1.2, minDim * 0.013), 0, Math.PI * 2);
        ctx.fillStyle = '#FFF6D6';
        ctx.globalAlpha = alpha * twinkle;
        ctx.fill();
      }
    }

    // 5. Faceted Diamond Core
    ctx.save();
    if (field.facet_orientation !== 0) {
      ctx.rotate(field.facet_orientation * Math.PI / 180);
    }
    ctx.beginPath();
    ctx.moveTo(0, -coreH);
    ctx.lineTo(coreW, 0);
    ctx.lineTo(0, coreH);
    ctx.lineTo(-coreW, 0);
    ctx.closePath();
    ctx.fillStyle = visuals.coreColor;
    ctx.globalAlpha = alpha * 0.9;
    ctx.fill();

    // 6. Inner Crystalline Focus Facet (with subtle gaze shift toward active work or pointer)
    const gxShift = gazeX * coreW;
    const gyShift = gazeY * coreH;
    ctx.beginPath();
    ctx.moveTo(gxShift, -coreH * 0.56 + gyShift);
    ctx.lineTo(coreW * 0.56 + gxShift, gyShift);
    ctx.lineTo(gxShift, coreH * 0.56 + gyShift);
    ctx.lineTo(-coreW * 0.56 + gxShift, gyShift);
    ctx.closePath();
    ctx.fillStyle = visuals.facetColor;
    ctx.globalAlpha = alpha * field.optical_depth;
    ctx.fill();

    // 6b. 8-Facet Internal Crown Refraction Lines
    ctx.beginPath();
    ctx.moveTo(0, -coreH);
    ctx.lineTo(gxShift, -coreH * 0.56 + gyShift);
    ctx.moveTo(coreW, 0);
    ctx.lineTo(coreW * 0.56 + gxShift, gyShift);
    ctx.moveTo(0, coreH);
    ctx.lineTo(gxShift, coreH * 0.56 + gyShift);
    ctx.moveTo(-coreW, 0);
    ctx.lineTo(-coreW * 0.56 + gxShift, gyShift);
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 0.75;
    ctx.globalAlpha = alpha * 0.42;
    ctx.stroke();

    // 6c. Held-Out Crystallized Offer Jewel below the Core
    if (isCrystallized && hostConnected && !isEnded) {
      const oy = coreH * 1.24;
      const orad = Math.max(2.5, minDim * 0.028);
      ctx.beginPath();
      ctx.moveTo(0, oy - orad);
      ctx.lineTo(orad, oy);
      ctx.lineTo(0, oy + orad);
      ctx.lineTo(-orad, oy);
      ctx.closePath();
      ctx.fillStyle = '#FFF6D6';
      ctx.globalAlpha = alpha * 0.95;
      ctx.fill();
    }

    // 7. Specular Shimmer Node
    if (field.surface_shimmer > 0.5) {
      ctx.beginPath();
      ctx.arc(gxShift * 0.5, -coreH * 0.3 + gyShift * 0.5, 3 * field.surface_shimmer, 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.globalAlpha = alpha * (field.surface_shimmer - 0.5) * 1.8;
      ctx.fill();
    }
    ctx.restore();

    ctx.restore();
    return getHoverText();
  }

  /**
   * Software RGBA pixel rasterizer (Uint8Array, W x H x 4) for canvases and pixel-protocol terminals.
   */
  function rgba(W = 96, H = 96, renderOpts = {}) {
    const w = Math.max(1, Math.floor(W));
    const h = Math.max(1, Math.floor(H));
    const out = new Uint8Array(w * h * 4);
    const isStill = Boolean(renderOpts.reducedMotion || renderOpts.calm);
    const rawT = renderOpts.time ?? renderOpts.t;
    const t = typeof rawT === 'number' && Number.isFinite(rawT) ? rawT : getClock();
    const comp = renderOpts.composition || currentComposition;
    const isApproval = mode === 'approval';
    const isWorking = mode === 'refracting' || mode === 'branching' || mode === 'synthesizing';
    const field = computeVisualField(t, isStill);
    const geom = computeGeometry({
      comp,
      field,
      size: Math.min(w, h),
      width: w,
      height: h,
      reducedMotion: isStill,
      calm: renderOpts.calm,
      isApproval,
    });
    const visuals = deriveVisuals(renderOpts.mood || renderOpts.palette || currentMood);

    const cRing1 = hexToRgb01(visuals.ring1Color);
    const cRing2 = hexToRgb01(visuals.ring2Color);
    const cCore = hexToRgb01(visuals.coreColor);
    const cFacet = hexToRgb01(visuals.facetColor);
    const cHalo = hexToRgb01(visuals.haloColor);

    const speed = isWorking ? 1.2 : 0.6;
    const rad1 = (geom.ringAngle1 * Math.PI / 180) + (isStill || isEnded ? 0 : t * speed * 0.5);
    const rad2 = (geom.ringAngle2 * Math.PI / 180) - (isStill || isEnded ? 0 : t * speed * 0.5);
    const cos1 = Math.cos(-rad1), sin1 = Math.sin(-rad1);
    const cos2 = Math.cos(-rad2), sin2 = Math.sin(-rad2);

    const rx = Math.max(2, geom.rx1);
    const ry = Math.max(1.5, geom.ry1);
    const coreHx = Math.max(1.5, geom.coreHx);
    const coreHy = Math.max(1.5, geom.coreHy);
    const haloR = Math.max(4, rx * 1.15);
    const masterAlpha = isEnded ? 0.3 : (!hostConnected ? 0.4 : 1.0);

    for (let py = 0; py < h; py++) {
      const dy = (py + 0.5) - geom.posY;
      for (let px = 0; px < w; px++) {
        const dx = (px + 0.5) - geom.posX;
        let r = 0, g = 0, b = 0, a = 0;

        // 1. Caustic radial halo
        const dist = Math.hypot(dx, dy);
        if (dist < haloR && !isEnded && hostConnected) {
          const u = 1 - dist / haloR;
          const ha = u * u * 0.28 * masterAlpha;
          r += cHalo[0] * ha;
          g += cHalo[1] * ha;
          b += cHalo[2] * ha;
          a = Math.min(1, a + ha);
        }

        // 2. Polarized Ring 1
        const x1 = dx * cos1 - dy * sin1;
        const y1 = dx * sin1 + dy * cos1;
        const e1 = Math.hypot(x1 / rx, y1 / ry);
        const dRing1 = Math.abs(e1 - 1.0) * Math.min(rx, ry);
        if (dRing1 < 1.6) {
          const ra = (1 - dRing1 / 1.6) * 0.85 * masterAlpha;
          r = r * (1 - ra) + cRing1[0] * ra;
          g = g * (1 - ra) + cRing1[1] * ra;
          b = b * (1 - ra) + cRing1[2] * ra;
          a = Math.min(1, a + ra * (1 - a));
        }

        // 3. Polarized Ring 2
        const x2 = dx * cos2 - dy * sin2;
        const y2 = dx * sin2 + dy * cos2;
        const e2 = Math.hypot(x2 / rx, y2 / ry);
        const dRing2 = Math.abs(e2 - 1.0) * Math.min(rx, ry);
        if (dRing2 < 1.5) {
          const ra2 = (1 - dRing2 / 1.5) * 0.78 * masterAlpha;
          r = r * (1 - ra2) + cRing2[0] * ra2;
          g = g * (1 - ra2) + cRing2[1] * ra2;
          b = b * (1 - ra2) + cRing2[2] * ra2;
          a = Math.min(1, a + ra2 * (1 - a));
        }

        // 4. Faceted Diamond Core & Inner Jewel
        const diamond = Math.abs(dx) / coreHx + Math.abs(dy) / coreHy;
        if (diamond <= 1.05) {
          const edge = Math.max(0, Math.min(1, (1.05 - diamond) * 6));
          const isInner = diamond <= 0.58;
          const col = isInner ? cFacet : cCore;
          const ca = edge * (isInner ? 0.96 : 0.88) * masterAlpha;
          r = r * (1 - ca) + col[0] * ca;
          g = g * (1 - ca) + col[1] * ca;
          b = b * (1 - ca) + col[2] * ca;
          a = Math.min(1, a + ca * (1 - a));
        }

        const idx = (py * w + px) * 4;
        out[idx] = Math.max(0, Math.min(255, Math.round(r * 255)));
        out[idx + 1] = Math.max(0, Math.min(255, Math.round(g * 255)));
        out[idx + 2] = Math.max(0, Math.min(255, Math.round(b * 255)));
        out[idx + 3] = Math.max(0, Math.min(255, Math.round(a * 255)));
      }
    }
    return out;
  }

  /**
   * Terminal cell renderer: Uint32Array of [codePoint, fg, bg] per cell (half-blocks or HD quadrants).
   */
  function cells(cols = 36, rows = 18, cellOpts = {}) {
    const cCols = Math.max(1, Math.floor(cols));
    const cRows = Math.max(1, Math.floor(rows));
    const hd = Boolean(cellOpts.hd);
    const ground = Array.isArray(cellOpts.ground) ? cellOpts.ground : [0.06, 0.07, 0.10];
    const pw = hd ? cCols * 2 : cCols;
    const ph = hd ? cRows * 4 : cRows * 2;
    const pixels = rgba(pw, ph, cellOpts);
    const out = new Uint32Array(cCols * cRows * 3);

    function sampleRgb(px, py) {
      const idx = (py * pw + px) * 4;
      const a = pixels[idx + 3] / 255;
      const r = ground[0] * (1 - a) + (pixels[idx] / 255) * a;
      const g = ground[1] * (1 - a) + (pixels[idx + 1] / 255) * a;
      const b = ground[2] * (1 - a) + (pixels[idx + 2] / 255) * a;
      return [r, g, b, a];
    }

    for (let cy = 0; cy < cRows; cy++) {
      for (let cx = 0; cx < cCols; cx++) {
        const cellOffset = (cy * cCols + cx) * 3;
        if (!hd) {
          const top = sampleRgb(cx, cy * 2);
          const bot = sampleRgb(cx, cy * 2 + 1);
          if (top[3] < 0.04 && bot[3] < 0.04) {
            out[cellOffset] = 0x20;
            out[cellOffset + 1] = 0x01000000;
            out[cellOffset + 2] = 0x01000000;
          } else {
            out[cellOffset] = 0x2580; // '▀'
            out[cellOffset + 1] = packRgb24(top[0], top[1], top[2]);
            out[cellOffset + 2] = packRgb24(bot[0], bot[1], bot[2]);
          }
        } else {
          // 2x2 sub-block quantization into Unicode quadrant characters
          const tl = sampleRgb(cx * 2, cy * 4);
          const tr = sampleRgb(cx * 2 + 1, cy * 4);
          const bl = sampleRgb(cx * 2, cy * 4 + 2);
          const br = sampleRgb(cx * 2 + 1, cy * 4 + 2);
          const samples = [tl, tr, bl, br];
          const maxA = Math.max(tl[3], tr[3], bl[3], br[3]);
          if (maxA < 0.04) {
            out[cellOffset] = 0x20;
            out[cellOffset + 1] = 0x01000000;
            out[cellOffset + 2] = 0x01000000;
          } else {
            const lumas = samples.map((s) => s[0] * 0.299 + s[1] * 0.587 + s[2] * 0.114);
            const mid = (Math.min(...lumas) + Math.max(...lumas)) * 0.5;
            let mask = 0;
            let fgR = 0, fgG = 0, fgB = 0, fgN = 0;
            let bgR = 0, bgG = 0, bgB = 0, bgN = 0;
            for (let bIdx = 0; bIdx < 4; bIdx++) {
              if (lumas[bIdx] >= mid) {
                mask |= (1 << bIdx);
                fgR += samples[bIdx][0]; fgG += samples[bIdx][1]; fgB += samples[bIdx][2]; fgN++;
              } else {
                bgR += samples[bIdx][0]; bgG += samples[bIdx][1]; bgB += samples[bIdx][2]; bgN++;
              }
            }
            if (fgN === 0) { fgR = bgR; fgG = bgG; fgB = bgB; fgN = bgN || 1; }
            if (bgN === 0) { bgR = ground[0]; bgG = ground[1]; bgB = ground[2]; bgN = 1; }
            out[cellOffset] = QUADRANTS[mask] || 0x2580;
            out[cellOffset + 1] = packRgb24(fgR / fgN, fgG / fgN, fgB / fgN);
            out[cellOffset + 2] = packRgb24(bgR / bgN, bgG / bgN, bgB / bgN);
          }
        }
      }
    }
    return out;
  }

  function setComposition(c) {
    if (c === 'beside') c = 'side';
    if (['full', 'side', 'top', 'focus'].includes(c)) {
      currentComposition = c;
    }
  }

  function setMood(m) {
    if (!m) {
      currentMood = null;
    } else if (MOODS[String(m).toLowerCase()]) {
      currentMood = String(m).toLowerCase();
    }
  }

  function mount(container, mountOpts = {}) {
    if (typeof document === 'undefined' || !container) {
      return null;
    }
    const size = mountOpts.size || (typeof mountOpts.width === 'number' ? mountOpts.width : 200);
    const initialSvg = svg({ ...mountOpts, size });
    container.innerHTML = initialSvg;

    const svgElem = container.querySelector('svg');
    if (!svgElem) return null;

    const ellipse1 = svgElem.querySelectorAll('.prism-rings ellipse')[0];
    const ellipse2 = svgElem.querySelectorAll('.prism-rings ellipse')[1];
    const ellipse3 = svgElem.querySelectorAll('.prism-rings ellipse')[2];
    const coreGroup = svgElem.querySelector('.prism-core');
    const corePoly = coreGroup ? coreGroup.querySelectorAll('polygon')[0] : null;
    const facetPoly = coreGroup ? coreGroup.querySelectorAll('polygon')[1] : null;
    let shimmerCircle = coreGroup ? coreGroup.querySelector('circle') : null;

    const minDim = size;

    return {
      element: svgElem,
      update(updateOpts = {}) {
        const redMot = updateOpts.reducedMotion ?? false;
        const comp = updateOpts.composition || currentComposition;
        const now = getClock();
        const field = computeVisualField(now, redMot);

        const geom = computeGeometry({
          comp,
          field,
          size: minDim,
          scale: updateOpts.scale,
          place: updateOpts.place,
          gesture: updateOpts.gesture,
          pulse: updateOpts.pulse,
          reducedMotion: redMot,
          calm: updateOpts.calm,
        });

        if (ellipse1) {
          ellipse1.setAttribute('cx', geom.posX.toFixed(2));
          ellipse1.setAttribute('cy', geom.posY.toFixed(2));
          ellipse1.setAttribute('rx', geom.rx1.toFixed(2));
          ellipse1.setAttribute('ry', geom.ry1.toFixed(2));
          ellipse1.setAttribute('transform', `rotate(${geom.ringAngle1} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})`);
        }
        if (ellipse2) {
          ellipse2.setAttribute('cx', geom.posX.toFixed(2));
          ellipse2.setAttribute('cy', geom.posY.toFixed(2));
          ellipse2.setAttribute('rx', geom.rx1.toFixed(2));
          ellipse2.setAttribute('ry', geom.ry1.toFixed(2));
          ellipse2.setAttribute('transform', `rotate(${geom.ringAngle2} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})`);
        }
        if (ellipse3) {
          const innerAngle = ((geom.ringAngle1 + geom.ringAngle2) * 0.5 + 90).toFixed(2);
          ellipse3.setAttribute('cx', geom.posX.toFixed(2));
          ellipse3.setAttribute('cy', geom.posY.toFixed(2));
          ellipse3.setAttribute('rx', (geom.rx1 * 0.68).toFixed(2));
          ellipse3.setAttribute('ry', (geom.ry1 * 0.68).toFixed(2));
          ellipse3.setAttribute('transform', `rotate(${innerAngle} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})`);
        }
        if (coreGroup) {
          coreGroup.setAttribute('transform', `translate(${geom.posX.toFixed(2)}, ${geom.posY.toFixed(2)}) rotate(${field.facet_orientation.toFixed(2)})`);
        }
        if (corePoly) {
          corePoly.setAttribute('points', `0,${(-geom.coreHy).toFixed(2)} ${(geom.coreHx).toFixed(2)},0 0,${(geom.coreHy).toFixed(2)} ${(-geom.coreHx).toFixed(2)},0`);
        }
        if (facetPoly) {
          facetPoly.setAttribute('points', `0,${(-geom.coreHy * 0.58).toFixed(2)} ${(geom.coreHx * 0.58).toFixed(2)},0 0,${(geom.coreHy * 0.58).toFixed(2)} ${(-geom.coreHx * 0.58).toFixed(2)},0`);
          facetPoly.setAttribute('opacity', (0.95 * field.optical_depth).toFixed(2));
        }

        if (coreGroup) {
          if (field.surface_shimmer > 0.5) {
            if (!shimmerCircle) {
              shimmerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
              shimmerCircle.setAttribute('fill', '#FFFFFF');
              coreGroup.appendChild(shimmerCircle);
            }
            shimmerCircle.setAttribute('cx', '0');
            shimmerCircle.setAttribute('cy', (-geom.coreHy * 0.3).toFixed(2));
            shimmerCircle.setAttribute('r', (geom.minDim * 0.02 * field.surface_shimmer).toFixed(2));
            shimmerCircle.setAttribute('opacity', ((field.surface_shimmer - 0.5) * 1.8).toFixed(2));
          } else if (shimmerCircle) {
            shimmerCircle.remove();
            shimmerCircle = null;
          }
        }

        return field;
      },
      destroy() {
        if (container && svgElem.parentNode === container) {
          container.removeChild(svgElem);
        }
      }
    };
  }

  return {
    apply,
    event: apply, // Studio host integration: Studio calls p.live.event(ev)
    state,
    svg,
    paint,
    rgba,
    cells,
    mount,
    layout,
    animation,
    consumeCue,
    lastCue,
    setComposition,
    setMood,
    proposeGesture,
    ringBounds(opts = {}) {
      const comp = opts.composition || currentComposition;
      const isStill = Boolean(opts.reducedMotion || opts.calm);
      const field = computeVisualField(getClock(), isStill);
      return computeGeometry({ comp, field, ...opts });
    },
    visualField: (redMot = false) => computeVisualField(getClock(), redMot),
    activeGestures: () => activeGestures.map(g => ({ ...g })),
    clearGestures: () => { activeGestures.length = 0; },
    setHostRun(rId) { hostRunId = rId; },
    hostState(hs) {
      if (hs && typeof hs === 'object') {
        if (typeof hs.connected === 'boolean') {
          hostConnected = hs.connected;
          if (!hostConnected) {
            activeGestures.length = 0;
            offer = null;
          }
        }
        if (hs.runId !== undefined) {
          hostRunId = hs.runId;
        }

        if (hs.replyToken !== undefined) {
          currentReplyToken = hs.replyToken;
          if (mode === 'resolved' && hostConnected) {
            offer = currentReplyToken ? { kind: 'answer', token: currentReplyToken } : null;
          }
        }
        if (!hostConnected) {
          offer = null;
        }
      }
    },
  };
}
