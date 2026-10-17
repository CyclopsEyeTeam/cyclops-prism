/**
 * prism.mjs - Official Cyclops Studio Presence module for Prism.
 *
 * Implements:
 * - createPrism({ clock, composition })
 * - .apply(event)
 * - .state()
 * - .svg({ size, width, height, hud, reducedMotion, calm, composition })
 * - .paint(ctx, { width, height, dpr, pointer, time, reducedMotion, calm, composition })
 * - .layout({ width, height, view, composition })
 * - .animation()
 * - .consumeCue(), .lastCue()
 * - slot()
 * - IDENTITY descriptor export
 *
 * Purity Invariant:
 * Pure Presence consumer. Contains zero Antigravity hook specifics, filesystem I/O,
 * raw commands, paths, prompt/response content, or raw hashes.
 */

import { soundFor } from './prism-sound.mjs';

export const PROTOCOL_VERSION = 'cyclops-presence/1';
export const RENDERER_VERSION = 'prism-renderer/1.2.1';
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
    'presentation.calm',
    'presentation.reducedMotion',
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
      </defs>
      <!-- Dual Polarized Rings -->
      <ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="#00F2FE" stroke-width="1.2" transform="rotate(-25 16 16)" opacity="0.85" />
      <ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="#7928CA" stroke-width="1" transform="rotate(25 16 16)" opacity="0.6" />
      <!-- Faceted Rhombus Core -->
      <polygon points="16,6 23,16 16,26 9,16" fill="url(#prism-slot-grad)" opacity="0.95" />
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
  let offer = null; // 'crystallize' or null
  let isEnded = false;
  let lastCueEmitted = null; // { name, at }
  let currentComposition = opts.composition || 'full';
  if (currentComposition === 'beside') currentComposition = 'side';
  let hostConnected = true;
  let currentReplyToken = null;

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
    const key = event.key;
    const now = getClock();
    const stamp = typeof event.t === 'number' && Number.isFinite(event.t) ? event.t : now;

    // Semantic state transition
    switch (typ) {
      case 'session.wake':
        mode = 'idle';
        offer = null;
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
        mode = 'attending';
        offer = null;
        break;

      case 'turn.synthesize':
        mode = 'synthesizing';
        offer = null;
        break;

      case 'approval.request':
        mode = 'approval';
        break;

      case 'refract.start':
        mode = 'refracting';
        if (key && typeof key === 'string' && !activeCalls.has(key)) {
          const rawKind = event.kind;
          const safeKind = KIND_COLORS[rawKind] ? rawKind : 'other';
          activeCalls.set(key, { kind: safeKind, seq: event.seq || currentSeq, t: stamp });
        }
        break;

      case 'refract.resolve':
      case 'refract.halt':
        if (key && typeof key === 'string') {
          activeCalls.delete(key);
        }
        break;

      case 'branch.start':
        if (mode !== 'refracting') mode = 'branching';
        if (key && typeof key === 'string' && !activeBranches.has(key)) {
          activeBranches.set(key, { seq: event.seq || currentSeq, t: stamp });
        }
        break;

      case 'branch.resolve':
        if (key && typeof key === 'string') {
          activeBranches.delete(key);
        }
        break;

      case 'turn.resolve':
        mode = 'resolved';
        offer = (hostConnected && currentReplyToken) ? { kind: 'answer', token: currentReplyToken } : null;
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
      offer: isReadyOffer ? offer : null,
      ended: isEnded,
      connected: hostConnected,
      personRequired: mode === 'approval',
      composition: currentComposition,
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

    const visuals = deriveVisuals();
    const ringOpacity = !hostConnected ? 0.25 : (isEnded ? 0.2 : (isHalted ? 0.4 : (isWorking ? 0.9 : 0.65)));

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

    const hover = getHoverText();
    const titleElem = hud ? `<title>${hover}</title>` : '';

    return `
<svg viewBox="0 0 ${geom.w} ${geom.h}" width="${geom.w}" height="${geom.h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${hover}" data-identity="prism" data-mode="${mode}" data-composition="${comp}" data-painted="${activeGestures.length > 0}">
  ${titleElem}
  <defs>
    <linearGradient id="${prefix}grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${visuals.ring1Color}" />
      <stop offset="100%" stop-color="${visuals.ring2Color}" />
    </linearGradient>
    <linearGradient id="${prefix}ring1" x1="0%" y1="0%" x2="100%" y2="0%">
      ${visuals.stops1.map((c, idx) => `<stop offset="${(idx / (visuals.stops1.length - 1) * 100).toFixed(0)}%" stop-color="${c}" />`).join('\n      ')}
    </linearGradient>
    <linearGradient id="${prefix}ring2" x1="100%" y1="0%" x2="0%" y2="100%">
      ${visuals.stops2.map((c, idx) => `<stop offset="${(idx / (visuals.stops2.length - 1) * 100).toFixed(0)}%" stop-color="${c}" />`).join('\n      ')}
    </linearGradient>
  </defs>

  <!-- Ambient Ground / Polarized Rings -->
  <g class="prism-rings">
    <ellipse cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" rx="${geom.rx1.toFixed(2)}" ry="${geom.ry1.toFixed(2)}" fill="none" stroke="url(#${prefix}ring1)" stroke-width="1.5" transform="rotate(${geom.ringAngle1} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})" opacity="${ringOpacity}" />
    <ellipse cx="${geom.posX.toFixed(2)}" cy="${geom.posY.toFixed(2)}" rx="${geom.rx1.toFixed(2)}" ry="${geom.ry1.toFixed(2)}" fill="none" stroke="url(#${prefix}ring2)" stroke-width="1.2" transform="rotate(${geom.ringAngle2} ${geom.posX.toFixed(2)} ${geom.posY.toFixed(2)})" opacity="${(ringOpacity * 0.8).toFixed(2)}" />
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
    ${field.surface_shimmer > 0.5 ? `<circle cx="0" cy="${(-geom.coreHy * 0.3).toFixed(2)}" r="${(geom.minDim * 0.02 * field.surface_shimmer).toFixed(2)}" fill="#FFFFFF" opacity="${((field.surface_shimmer - 0.5) * 1.8).toFixed(2)}" />` : ''}
  </g>
</svg>`.trim();
  }


  function deriveVisuals() {
    const isApproval = mode === 'approval';
    const isEndedMode = isEnded || mode === 'ended';
    const isHalted = mode === 'halted';
    const isCrystallized = mode === 'resolved';
    const isAttending = mode === 'attending';

    let primaryKind = '';
    if (activeCalls.size > 0) {
      primaryKind = activeCalls.values().next().value?.kind || '';
    }

    let stops1;
    let stops2;
    let coreColor;
    let facetColor;

    if (!hostConnected) {
      stops1 = ['#374151', '#4B5563', '#374151'];
      stops2 = ['#1F2937', '#374151', '#1F2937'];
      coreColor = '#374151';
      facetColor = '#6B7280';
    } else if (isApproval) {
      stops1 = ['#FF4D4D', '#FFB020', '#FF4D4D', '#FFB020'];
      stops2 = ['#FFB020', '#FF4D4D', '#FFB020', '#FF4D4D'];
      coreColor = '#FF8042';
      facetColor = '#FFE066';
    } else if (isEndedMode) {
      stops1 = ['#1F2937', '#374151', '#1F2937'];
      stops2 = ['#111827', '#1F2937', '#111827'];
      coreColor = '#111827';
      facetColor = '#4B5563';
    } else if (isHalted) {
      stops1 = ['#374151', '#6B7280', '#374151'];
      stops2 = ['#4B5563', '#374151', '#4B5563'];
      coreColor = '#374151';
      facetColor = '#9CA3AF';
    } else if (isCrystallized) {
      stops1 = ['#FFF6D6', '#00F2FE', '#FFF6D6', '#00E5A3'];
      stops2 = ['#00F2FE', '#FFF6D6', '#7928CA', '#FFF6D6'];
      coreColor = '#FFF6D6';
      facetColor = '#FFFFFF';
    } else if (mode === 'refracting') {
      if (primaryKind === 'change') {
        stops1 = ['#FFB020', '#FF8042', '#00F2FE', '#FFB020'];
        stops2 = ['#00F2FE', '#FFB020', '#7928CA', '#FF8042'];
        coreColor = '#FFB020';
        facetColor = '#FFFFFF';
      } else if (primaryKind === 'execute') {
        stops1 = ['#7928CA', '#4C1D95', '#00F2FE', '#7928CA'];
        stops2 = ['#00F2FE', '#7928CA', '#FFF6D6', '#4C1D95'];
        coreColor = '#7928CA';
        facetColor = '#7928CA';
      } else if (primaryKind === 'inspect') {
        stops1 = ['#00F2FE', '#00E5A3', '#FFF6D6', '#00F2FE'];
        stops2 = ['#00E5A3', '#00F2FE', '#7928CA', '#00E5A3'];
        coreColor = '#00F2FE';
        facetColor = '#FFFFFF';
      } else if (primaryKind === 'service') {
        stops1 = ['#00E5A3', '#00F2FE', '#00E5A3', '#FFF6D6'];
        stops2 = ['#00F2FE', '#00E5A3', '#FFB020', '#00F2FE'];
        coreColor = '#00E5A3';
        facetColor = '#00E5A3';
      } else {
        stops1 = ['#00F2FE', '#FFB020', '#7928CA', '#00E5A3'];
        stops2 = ['#7928CA', '#00E5A3', '#FFB020', '#00F2FE'];
        coreColor = '#00F2FE';
        facetColor = '#00F2FE';
      }
    } else if (isAttending) {
      stops1 = ['#00F2FE', '#00E5A3', '#7928CA', '#FFF6D6'];
      stops2 = ['#7928CA', '#FFF6D6', '#FFB020', '#00F2FE'];
      coreColor = '#00F2FE';
      facetColor = '#FFFFFF';
    } else {
      // Signature iridescent dispersion (synthesizing, branching, idle)
      stops1 = ['#00F2FE', '#00E5A3', '#7928CA', '#FFF6D6'];
      stops2 = ['#7928CA', '#FFF6D6', '#FFB020', '#00F2FE'];
      coreColor = '#00F2FE';
      facetColor = '#FFF6D6';
    }

    return {
      stops1,
      stops2,
      ring1Color: stops1[0],
      ring2Color: stops2[0],
      coreColor,
      facetColor,
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
      reducedMotion = false,
      calm = false,
      composition = null,
      scale = null,
      place = null,
      gesture = null,
      pulse = null,
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

    const t = typeof time === 'number' && Number.isFinite(time) ? time : getClock();

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    const isApproval = mode === 'approval';
    const isWorking = mode === 'refracting' || mode === 'branching' || mode === 'synthesizing';
    const isHalted = mode === 'halted';

    const visuals = deriveVisuals();
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
    ctx.restore();

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

    // 6. Inner Crystalline Focus Facet
    ctx.beginPath();
    ctx.moveTo(0, -coreH * 0.56);
    ctx.lineTo(coreW * 0.56, 0);
    ctx.lineTo(0, coreH * 0.56);
    ctx.lineTo(-coreW * 0.56, 0);
    ctx.closePath();
    ctx.fillStyle = visuals.facetColor;
    ctx.globalAlpha = alpha * field.optical_depth;
    ctx.fill();

    // 7. Specular Shimmer Node
    if (field.surface_shimmer > 0.5) {
      ctx.beginPath();
      ctx.arc(0, -coreH * 0.3, 3 * field.surface_shimmer, 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.globalAlpha = alpha * (field.surface_shimmer - 0.5) * 1.8;
      ctx.fill();
    }
    ctx.restore();

    ctx.restore();
  }

  function setComposition(c) {
    if (c === 'beside') c = 'side';
    if (['full', 'side', 'top', 'focus'].includes(c)) {
      currentComposition = c;
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
    const coreGroup = svgElem.querySelector('.prism-core');
    const corePoly = coreGroup ? coreGroup.querySelectorAll('polygon')[0] : null;
    const facetPoly = coreGroup ? coreGroup.querySelectorAll('polygon')[1] : null;
    let shimmerCircle = coreGroup ? coreGroup.querySelector('circle') : null;

    const cx = size / 2;
    const cy = size / 2;
    const minDim = size;

    return {
      element: svgElem,
      update(updateOpts = {}) {
        const redMot = updateOpts.reducedMotion ?? false;
        const comp = updateOpts.composition || currentComposition;
        const now = getClock();
        const field = computeVisualField(now, redMot);

        const tensionScaleX = 1.0 + (field.orbital_tension - 0.35) * 0.25;
        const tensionScaleY = Math.max(0.6, 1.0 - (field.orbital_tension - 0.35) * 0.25);
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
    mount,
    layout,
    animation,
    consumeCue,
    lastCue,
    setComposition,
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
