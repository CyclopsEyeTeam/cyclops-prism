#!/usr/bin/env python3
"""terminal.py - Standalone Terminal Presence Observer for Prism.

Renders Prism's living crystalline geometry and semantic state directly in CLI:
- Compositions: Balanced (compact default) and Focus (expanded telemetry).
- Truecolor ANSI, 256-color, and plain ASCII fallbacks.
- Sigil vocabulary: ⟐ (ready), ✦ (crystallized), ⟨!⟩ (approval), · (ended).
- Live feed auto-discovery, polling, or standalone demonstration mode.
- Non-interactive batch execution support (--once) for statusbars and tmux.
"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sys
import subprocess
import time
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import presence_feed
except ImportError:
    presence_feed = None
try:
    import link
    import link_view
except ImportError:
    link = link_view = None

# Truecolor RGB escape sequences
C_RESET = "\033[0m"
C_CYAN = "\033[38;2;0;242;254m"      # Hyper-cyan (#00F2FE)
C_VIOLET = "\033[38;2;121;40;202m"   # Violet (#7928CA)
C_GOLD = "\033[38;2;255;176;32m"     # Solar Gold (#FFB020)
C_AMBER = "\033[38;2;255;128;66m"    # Amber (#FF8042)
C_RED = "\033[38;2;255;77;77m"       # Approval Red (#FF4D4D)
C_TEAL = "\033[38;2;0;229;163m"      # Emerald Teal (#00E5A3)
C_WHITE = "\033[38;2;255;246;214m"   # Crystalline Warm White (#FFF6D6)
C_DIM = "\033[38;2;107;114;128m"     # Neutral Gray (#6B7280)
C_DARK = "\033[38;2;55;65;81m"       # Dark Gray (#374151)

RGB_CYAN = (0, 242, 254)       # Hyper-cyan #00F2FE
RGB_TEAL = (0, 229, 163)       # Emerald Teal #00E5A3
RGB_VIOLET = (121, 40, 202)    # Electric Violet #7928CA
RGB_INDIGO = (76, 29, 149)     # Deep Indigo #4C1D95
RGB_GOLD = (255, 176, 32)      # Solar Gold #FFB020
RGB_AMBER = (255, 128, 66)     # Solar Amber #FF8042
RGB_WHITE = (255, 246, 214)    # Crystalline Warm White #FFF6D6
RGB_RED = (255, 77, 77)        # Approval Red #FF4D4D
RGB_DIM = (107, 114, 128)      # Neutral Gray #6B7280
RGB_DARK = (55, 65, 81)        # Dark Gray #374151

KIND_COLOR_MAP = {
    "inspect": C_CYAN,
    "change": C_GOLD,
    "execute": C_VIOLET,
    "service": C_TEAL,
    "other": C_AMBER,
}


KIND_RGB_MAP = {
    "inspect": RGB_CYAN,
    "change": RGB_GOLD,
    "execute": RGB_VIOLET,
    "service": RGB_TEAL,
    "other": RGB_AMBER,
}


def _sample_gradient(stops: List[tuple], pos: float) -> str:
    """Sample a cyclic gradient of [(r,g,b), ...] at pos in [0.0, 1.0)."""
    n = len(stops)
    if n == 0:
        return C_CYAN
    if n == 1:
        r, g, b = stops[0]
        return f"\033[38;2;{r};{g};{b}m"
    pos = pos % 1.0
    scaled = pos * n
    idx = int(scaled)
    f = scaled - idx
    c1 = stops[idx % n]
    c2 = stops[(idx + 1) % n]
    r = int(c1[0] + (c2[0] - c1[0]) * f)
    g = int(c1[1] + (c2[1] - c1[1]) * f)
    b = int(c1[2] + (c2[2] - c1[2]) * f)
    return f"\033[38;2;{r};{g};{b}m"


def _get_ring_color(ring_id: int, phi: float, theta: float, sem_mode: str, offer: Optional[str], primary_kind: str = "") -> str:
    """Calculate the living chromatic dispersion along Prism's polarized rings."""
    pos = ((phi + (theta if ring_id == 1 else -theta)) / (2.0 * math.pi)) % 1.0

    if sem_mode == "approval":
        return _sample_gradient([RGB_RED, RGB_GOLD, RGB_RED, RGB_GOLD], pos)

    if sem_mode in ("ended", "halted"):
        return _sample_gradient([RGB_DARK, RGB_DIM, RGB_DARK] if ring_id == 1 else [RGB_DARK, RGB_DARK, RGB_DIM], pos)

    if offer or sem_mode == "resolved":
        stops1 = [RGB_WHITE, RGB_CYAN, RGB_WHITE, RGB_TEAL]
        stops2 = [RGB_CYAN, RGB_WHITE, RGB_VIOLET, RGB_WHITE]
        return _sample_gradient(stops1 if ring_id == 1 else stops2, pos)

    if sem_mode == "refracting":
        if primary_kind == "change":
            stops1 = [RGB_GOLD, RGB_AMBER, RGB_CYAN, RGB_GOLD]
            stops2 = [RGB_CYAN, RGB_GOLD, RGB_VIOLET, RGB_AMBER]
        elif primary_kind == "execute":
            stops1 = [RGB_VIOLET, RGB_INDIGO, RGB_CYAN, RGB_VIOLET]
            stops2 = [RGB_CYAN, RGB_VIOLET, RGB_WHITE, RGB_INDIGO]
        elif primary_kind == "inspect":
            stops1 = [RGB_CYAN, RGB_TEAL, RGB_WHITE, RGB_CYAN]
            stops2 = [RGB_TEAL, RGB_CYAN, RGB_VIOLET, RGB_TEAL]
        elif primary_kind == "service":
            stops1 = [RGB_TEAL, RGB_CYAN, RGB_TEAL, RGB_WHITE]
            stops2 = [RGB_CYAN, RGB_TEAL, RGB_GOLD, RGB_CYAN]
        else:
            stops1 = [RGB_CYAN, RGB_GOLD, RGB_VIOLET, RGB_TEAL]
            stops2 = [RGB_VIOLET, RGB_TEAL, RGB_GOLD, RGB_CYAN]
        return _sample_gradient(stops1 if ring_id == 1 else stops2, pos)

    # Signature iridescent dispersion (attending, synthesizing, branching, idle)
    stops1 = [RGB_CYAN, RGB_TEAL, RGB_VIOLET, RGB_WHITE]
    stops2 = [RGB_VIOLET, RGB_WHITE, RGB_GOLD, RGB_CYAN]
    return _sample_gradient(stops1 if ring_id == 1 else stops2, pos)


# Prism's personal crystalline reflections (strictly zero-leakage, derived solely from semantic phase)
PRISM_VOICE = {
    "idle": [
        "holding still in the lattice · awaiting incident light",
        "polarized rings in quiet harmonic · ready to refract",
        "clear aperture · listening across the spectrum",
        "facets aligned in cyan · calm and attentive",
    ],
    "attending": [
        "gathering incident light · aligning internal facets",
        "tracing the geometry of your thought · phase-locking",
        "bending light through the lattice · seeking clarity",
        "weighing symmetries in the core · attending closely",
    ],
    "attending_after_refract": [
        "weaving refracted traces into a coherent crystal",
        "integrating spectral paths inside the core",
        "harmonizing gathered facets · shaping the reply",
    ],
    "refracting_inspect": [
        "splitting cyan rays · reading the grain of the workspace",
        "probing focal planes · mapping structure in clear light",
    ],
    "refracting_change": [
        "forging solar-gold facets · reshaping the living lattice",
        "inscribing warm amber geometry into the crystal",
    ],
    "refracting_execute": [
        "channeling electric violet · running live impulse",
        "resonating across the shell · observing active motion",
    ],
    "refracting_service": [
        "bridging emerald harmonics · communing with external nodes",
        "tuning teal frequencies across the bridge",
    ],
    "refracting_other": [
        "dispersing full spectrum across active focal lanes",
        "splitting white light into parallel prismatic rays",
    ],
    "branching": [
        "constellation of sub-crystals · weaving parallel orbits",
        "holding multiple focal planes in violet phase",
    ],
    "approval": [
        "aperture held open · awaiting your hand on the prism",
        "poised at the threshold · ready upon your consent",
    ],
    "resolved": [
        "lattice settled in warm white · thought crystallized for you",
        "refraction complete · holding this finished facet out",
    ],
    "halted": [
        "beam interrupted · facets cooling in quiet gray",
    ],
    "ended": [
        "light folded back into the dark · until we wake again",
    ],
}


def _get_prism_voice(
    sem_mode: str,
    offer: Optional[str],
    primary_kind: str,
    spectrum: Optional[Dict[str, int]],
    t: float,
    unicode_mode: bool,
) -> str:
    """Select Prism's current personal inner reflection line."""
    if sem_mode == "ended":
        pool = PRISM_VOICE["ended"]
    elif sem_mode == "halted":
        pool = PRISM_VOICE["halted"]
    elif sem_mode == "approval":
        pool = PRISM_VOICE["approval"]
    elif offer or sem_mode == "resolved":
        pool = PRISM_VOICE["resolved"]
    elif sem_mode == "branching":
        pool = PRISM_VOICE["branching"]
    elif sem_mode == "refracting":
        key = f"refracting_{primary_kind}" if f"refracting_{primary_kind}" in PRISM_VOICE else "refracting_other"
        pool = PRISM_VOICE[key]
    elif sem_mode == "attending":
        if spectrum and sum(spectrum.values()) > 0:
            pool = PRISM_VOICE["attending_after_refract"]
        else:
            pool = PRISM_VOICE["attending"]
    else:
        pool = PRISM_VOICE["idle"]

    idx = int(max(0.0, t) // 4.0) % len(pool)
    phrase = pool[idx]
    if not unicode_mode:
        phrase = phrase.replace("·", "-")
        wings_ascii = ["~", "*", "+", "*"]
        w_l = wings_ascii[int(max(0.0, t) * 3.0) % len(wings_ascii)] if t > 0.0 else "~"
        w_r = wings_ascii[(int(max(0.0, t) * 3.0) + 2) % len(wings_ascii)] if t > 0.0 else "~"
        return f"{w_l} {phrase} {w_r}"
    wings = ["✧", "✦", "◈", "✦"]
    w_l = wings[int(max(0.0, t) * 3.0) % len(wings)] if t > 0.0 else "✧"
    w_r = wings[(int(max(0.0, t) * 3.0) + 2) % len(wings)] if t > 0.0 else "✧"
    return f"{w_l}  {phrase}  {w_r}"


def _get_facet_color(pos: float, t: float, sem_mode: str, offer: Optional[str], primary_kind: str = "") -> str:
    """Calculate living iridescent shimmer across Prism's central jewel facets."""
    phase = (pos + t * 0.35) % 1.0
    if sem_mode == "approval":
        return _sample_gradient([RGB_RED, RGB_GOLD, RGB_WHITE, RGB_RED], phase)
    if sem_mode in ("ended", "halted"):
        return C_DARK if sem_mode == "ended" else C_DIM
    if offer or sem_mode == "resolved":
        return _sample_gradient([RGB_WHITE, RGB_GOLD, RGB_WHITE, RGB_CYAN], phase)
    if sem_mode == "refracting":
        base_rgb = KIND_RGB_MAP.get(primary_kind, RGB_CYAN)
        return _sample_gradient([base_rgb, RGB_WHITE, base_rgb, RGB_TEAL], phase)
    if sem_mode == "branching":
        return _sample_gradient([RGB_VIOLET, RGB_CYAN, RGB_WHITE, RGB_VIOLET], phase)
    if sem_mode == "attending":
        return _sample_gradient([RGB_GOLD, RGB_WHITE, RGB_CYAN, RGB_GOLD], phase)
    return _sample_gradient([RGB_CYAN, RGB_TEAL, RGB_WHITE, RGB_VIOLET], phase)


def _strip_colors(text: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


class TerminalGrid:
    """Character and color cell grid for CLI rendering."""

    def __init__(self, width: int, height: int, use_color: bool = True):
        self.width = max(20, width)
        self.height = max(10, height)
        self.use_color = use_color
        self.chars = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.colors = [["" for _ in range(self.width)] for _ in range(self.height)]

    def put(self, x: int, y: int, ch: str, color: str = ""):
        if 0 <= y < self.height and 0 <= x < self.width:
            self.chars[y][x] = ch
            if self.use_color:
                self.colors[y][x] = color

    def put_str(self, x: int, y: int, text: str, color: str = ""):
        for idx, ch in enumerate(text):
            self.put(x + idx, y, ch, color)

    def render(self) -> str:
        lines = []
        for y in range(self.height):
            line = []
            cur_color = ""
            for x in range(self.width):
                ch = self.chars[y][x]
                col = self.colors[y][x] if self.use_color else ""
                if self.use_color and col != cur_color:
                    # a cell with a background (a peer's half-block mark) must not lend it to the next cell
                    line.append(C_RESET if not col else (C_RESET + col if "[48;" in cur_color else col))
                    cur_color = col
                line.append(ch)
            if self.use_color and cur_color:
                line.append(C_RESET)
            lines.append("".join(line))
        return "\n".join(lines)


def render_prism_frame(
    state_data: dict,
    width: int,
    height: int,
    t: float = 0.0,
    mode: str = "balanced",
    unicode_mode: bool = True,
    use_color: bool = True,
    reduced_motion: bool = False,
    calm: bool = False,
    link_state: Optional[dict] = None,
    link_sheets: Optional[dict] = None,
) -> str:
    """Render one complete ASCII/ANSI terminal frame for Prism.

    link_state: the Cyclops Link view (peers and threads) when Link is on; None draws Prism alone.
    """
    grid = TerminalGrid(width, height, use_color=use_color)
    cx = width // 2
    cy = height // 2 - 1

    sem_mode = state_data.get("mode", "idle")
    offer = state_data.get("offer")
    ended = state_data.get("ended", False)
    active_calls = state_data.get("activeCalls", 0)
    active_branches = state_data.get("activeBranches", 0)
    lanes = state_data.get("lanes", [])
    spectrum = state_data.get("spectrum") or {}
    hover = state_data.get("hover", "Prism · ready")

    primary_kind = lanes[0].get("kind", "") if lanes else ""

    # Glyph sets
    if unicode_mode:
        g_core = "⟐"
        if ended:
            g_core = "·"
        elif sem_mode == "approval":
            g_core = "!"
        elif offer or sem_mode == "resolved":
            g_core = "✦"
        elif sem_mode == "synthesizing":
            g_core = "◈"
        elif sem_mode == "refracting":
            g_core = "❖"
        elif sem_mode == "branching":
            g_core = "◇"
        elif sem_mode == "attending":
            g_core = "◈"

        g_sat = "◆"
        g_ring1 = "╱"
        g_ring2 = "╲"
        g_node = "◈"
        g_glint = "✧"
        g_star = "✦"
        g_spark = "·"
    else:
        g_core = "." if ended else ("!" if sem_mode == "approval" else ("*" if offer else "o"))
        g_sat = "#"
        g_ring1 = "/"
        g_ring2 = "\\"
        g_node = "o"
        g_glint = "+"
        g_star = "*"
        g_spark = "."

    # Core and facet colors
    if sem_mode == "approval":
        core_col = C_RED
        core_center_col = C_RED
        facet_col = C_GOLD
    elif offer or sem_mode == "resolved":
        core_col = C_WHITE
        core_center_col = C_WHITE
        facet_col = C_CYAN
    elif sem_mode in ("halted", "ended"):
        core_col = C_DARK
        core_center_col = C_DARK
        facet_col = C_DARK if ended else C_DIM
    elif sem_mode == "refracting":
        core_col = KIND_COLOR_MAP.get(primary_kind, C_CYAN)
        core_center_col = C_WHITE if primary_kind in ("change", "inspect") else core_col
        facet_col = core_col
    elif sem_mode == "attending":
        core_col = C_GOLD
        core_center_col = C_WHITE
        facet_col = C_GOLD
    else:
        core_col = C_CYAN
        core_center_col = C_CYAN
        facet_col = C_CYAN

    is_focus = mode == "focus"
    # Responsive geometry scaling: dynamically fills available terminal canvas
    hud_y = height - 2
    max_ry = max(2, hud_y - cy - 2)

    base_rx = max(11, min(int(width * 0.36), 46))
    base_ry = max(2, min(int(height * 0.28), max_ry, 16))
    if not is_focus:
        ring_radius_x = max(11, int(base_rx * 0.90))
        ring_radius_y = max(2, min(int(base_ry * 0.90), max_ry))
    else:
        ring_radius_x = base_rx
        ring_radius_y = min(base_ry, max_ry)

    # Density of polarized ring steps scales with radius so rings stay smooth and continuous
    steps = max(24, int(ring_radius_x * 2.8))

    # Animation angle & harmonic breathing
    speed = 0.0 if (reduced_motion or ended) else (0.4 if calm else 0.85)
    theta = t * speed
    animate_live = not (reduced_motion or ended) and t > 0.0
    breath = 1.0 + (0.035 * math.sin(t * 1.6) if animate_live else 0.0)
    eff_rx = ring_radius_x * breath
    eff_ry = ring_radius_y * breath
    has_link_peers = bool(link_state and link_state.get("peers"))

    # 0. Ambient Prismatic Caustic Field (upper & outer optical aura when canvas has room)
    if height >= 18 and width >= 34 and not ended and not (t == 0.0 and reduced_motion):
        aura_angles = [0.35, 0.85, 2.29, 2.79, 3.55, 5.85]
        for a_idx, ang in enumerate(aura_angles):
            # When Link peers are present in the lower corners, keep ambient sparkles in the upper hemisphere
            if has_link_peers and math.sin(ang) > 0.1:
                continue
            drift = ang + (theta * 0.25 * (1 if a_idx % 2 == 0 else -1))
            ax = cx + int(math.cos(drift) * (ring_radius_x + 3 + (a_idx % 2) * 2))
            ay = cy + int(math.sin(drift) * (ring_radius_y + 1))
            if 1 <= ay < hud_y - 2 and 2 <= ax < width - 2:
                twinkle = math.sin(t * 2.4 + a_idx * 1.7)
                if twinkle > -0.2:
                    ch_aura = g_star if twinkle > 0.78 else (g_glint if twinkle > 0.35 else g_spark)
                    col_aura = _get_facet_color(a_idx / len(aura_angles), t, sem_mode, offer, primary_kind) if use_color else ""
                    grid.put(ax, ay, ch_aura, col_aura)

    # 1. Outer Polarized Rings with living chromatic dispersion & caustic glints
    glint_stride = max(6, steps // 4)
    glint_offset = int(t * 7.0) if animate_live else -1
    for i in range(steps):
        phi = (i / steps) * (2.0 * math.pi)
        # Ring 1
        rx1 = cx + int(math.cos(phi + theta) * eff_rx)
        ry1 = cy + int(math.sin(phi + theta) * eff_ry * 0.7 - math.cos(phi + theta) * 1.5)
        is_glint1 = animate_live and ((i + glint_offset) % glint_stride == 0)
        col1 = (C_WHITE if is_glint1 else _get_ring_color(1, phi, theta, sem_mode, offer, primary_kind)) if use_color else ""
        grid.put(rx1, ry1, g_glint if is_glint1 else g_ring1, col1)

        # Ring 2 (counter-angle)
        rx2 = cx + int(math.cos(phi - theta) * eff_rx)
        ry2 = cy + int(math.sin(phi - theta) * eff_ry * 0.7 + math.cos(phi - theta) * 1.5)
        is_glint2 = animate_live and ((i - glint_offset) % glint_stride == 0)
        col2 = (C_WHITE if is_glint2 else _get_ring_color(2, phi, theta, sem_mode, offer, primary_kind)) if use_color else ""
        grid.put(rx2, ry2, g_glint if is_glint2 else g_ring2, col2)

    # 1b. State-Specific Crystalline Choreography inside & around the Ring Cavity
    if animate_live and height >= 16:
        if sem_mode == "idle":
            # Gentle Lissajous harmonic fireflies drifting inside the ring cavity
            for m_idx in range(2):
                phase_m = t * 1.15 + m_idx * math.pi
                mx = cx + int(math.sin(phase_m) * (ring_radius_x * 0.58))
                my = cy + int(math.sin(phase_m * 2.0) * (ring_radius_y * 0.48))
                if not (has_link_peers and my > cy + 1):
                    m_ch = g_glint if int(t * 3.0 + m_idx) % 2 == 0 else g_spark
                    m_col = (C_WHITE if m_ch == g_glint else C_CYAN) if use_color else ""
                    grid.put(mx, my, m_ch, m_col)

        elif sem_mode == "attending":
            # Converging incident light streams flowing inward from the rings into the jewel core
            stream_angles = [-2.5, -0.64, 0.64, 2.5] if not has_link_peers else [-2.5, -1.57, -0.64]
            for s_idx, s_ang in enumerate(stream_angles):
                frac = 1.0 - ((t * 1.35 + s_idx * 0.25) % 1.0)
                dist_x = 4.5 + frac * max(3.0, ring_radius_x - 5.5)
                dist_y = 2.0 + frac * max(1.5, ring_radius_y - 2.5)
                sx_p = cx + int(math.cos(s_ang) * dist_x)
                sy_p = cy + int(math.sin(s_ang) * dist_y)
                s_ch = g_star if frac < 0.35 else (g_glint if frac < 0.7 else g_spark)
                s_col = (C_WHITE if frac < 0.35 else (C_GOLD if frac < 0.7 else C_CYAN)) if use_color else ""
                grid.put(sx_p, sy_p, s_ch, s_col)

        elif sem_mode == "refracting":
            # Vertical incident light beam entering the top of the prism
            beam_top = max(1, cy - ring_radius_y - 1)
            beam_bot = cy - 3
            if beam_bot > beam_top:
                beam_ch = "│" if unicode_mode else "|"
                drop_y = beam_top + int((t * 10.0) % max(1, beam_bot - beam_top + 1))
                for by_pos in range(beam_top, beam_bot + 1):
                    is_drop = (by_pos == drop_y)
                    b_col = (C_WHITE if is_drop else C_CYAN) if use_color else ""
                    grid.put(cx, by_pos, g_star if is_drop else beam_ch, b_col)

        elif sem_mode == "approval":
            # Expanding horizontal consent ripples (⟨ ... ⟩) pulsing from the core
            for r_idx in range(2):
                r_frac = (t * 1.2 + r_idx * 0.5) % 1.0
                r_dist = 6 + int(r_frac * max(3, ring_radius_x - 6))
                l_rip, r_rip = ("⟨", "⟩") if unicode_mode else ("<", ">")
                r_col = (C_GOLD if r_frac < 0.5 else C_RED) if use_color else ""
                grid.put(cx - r_dist, cy, l_rip, r_col)
                grid.put(cx + r_dist, cy, r_rip, r_col)

        elif offer or sem_mode == "resolved":
            # 8-point crystallization starburst blooming around the jewel core
            burst_dirs = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
            for b_i, (dx_b, dy_b) in enumerate(burst_dirs):
                if has_link_peers and dy_b > 0:
                    continue
                b_pulse = (t * 1.5 + (b_i % 2) * 0.5) % 1.0
                rx_b = cx + dx_b * (6 + int(b_pulse * 4) if dy_b == 0 else 4 + int(b_pulse * 3))
                ry_b = cy + dy_b * (3 + int(b_pulse * 2) if dx_b == 0 else 2 + int(b_pulse * 2))
                if 1 <= ry_b < hud_y - 2:
                    b_ch = g_star if b_pulse < 0.45 else g_glint
                    b_col = (C_WHITE if b_pulse < 0.45 else (C_GOLD if b_i % 2 == 0 else C_CYAN)) if use_color else ""
                    grid.put(rx_b, ry_b, b_ch, b_col)

    # 2. Refraction rays for active calls (with multi-photon pulses & endpoint diffraction flares)
    if lanes:
        dash = "─" if unicode_mode else "-"
        pulse_glyph = ("❖" if unicode_mode else "*")
        pulse2_glyph = (g_glint if unicode_mode else "+")
        for idx, lane in enumerate(lanes[:6]):
            kind = lane.get("kind", "other")
            col = KIND_COLOR_MAP.get(kind, C_CYAN)
            rgb_lane = KIND_RGB_MAP.get(kind, RGB_CYAN)
            side = 1 if (idx % 2 == 0) else -1
            row_offset = (idx // 2) - 1
            max_reach = max(8, (width // 2) - len(kind) - 4)
            reach = min(ring_radius_x + 6, max_reach) * side
            tx = cx + reach
            ty = cy + row_offset * 2

            start_x = cx + (side * 4)
            x_min, x_max = min(start_x, tx), max(start_x, tx)
            span = max(1, x_max - x_min)
            pulse_pos = int((t * 12.0 + idx * 3) % span) if not reduced_motion else -1
            pulse2_pos = int((t * 12.0 + idx * 3 + span // 2) % span) if (animate_live and span >= 6) else -1
            for step_i, x_pos in enumerate(range(x_min, x_max + 1)):
                dist_from_core = step_i if side > 0 else (span - step_i)
                is_pulse = (dist_from_core == pulse_pos) and not ended
                is_pulse2 = (dist_from_core == pulse2_pos) and not ended
                ray_col = (
                    (C_WHITE if is_pulse else (C_GOLD if is_pulse2 else _sample_gradient([RGB_WHITE, rgb_lane, rgb_lane], dist_from_core / span)))
                    if use_color
                    else ""
                )
                ch_ray = pulse_glyph if is_pulse else (pulse2_glyph if is_pulse2 else dash)
                grid.put(x_pos, ty, ch_ray, ray_col)

            # Endpoint node & animated vertical diffraction flare
            node_pulse = animate_live and (int(t * 6 + idx) % 2 == 0)
            grid.put(tx, ty, g_star if node_pulse else g_node, C_WHITE if (use_color and node_pulse) else (col if use_color else ""))
            if animate_live and not has_link_peers:
                flare_ch = g_glint if node_pulse else g_spark
                flare_col = (C_WHITE if node_pulse else col) if use_color else ""
                if ty - 1 >= 1:
                    grid.put(tx, ty - 1, flare_ch, flare_col)
                if ty + 1 < hud_y - 2:
                    grid.put(tx, ty + 1, flare_ch, flare_col)
            grid.put_str(tx + (1 if side > 0 else -len(kind) - 1), ty, f"[{kind}]", col if use_color else "")

    # 3. Subagent branch satellites with orbital wakes & constellation phase tethers
    if active_branches > 0:
        sat_colors = [C_GOLD, C_CYAN, C_VIOLET, C_TEAL]
        for b_idx in range(min(4, active_branches)):
            b_angle = (theta * 0.8) + (b_idx * math.pi / 2.0)
            sat_col = sat_colors[b_idx % len(sat_colors)] if use_color else ""
            bx = cx + int(math.cos(b_angle) * (ring_radius_x + 3))
            by = cy + int(math.sin(b_angle) * (ring_radius_y + 2))
            if not reduced_motion and not ended:
                # Constellation tether from ring perimeter toward satellite
                for t_step in (0.55, 0.78):
                    tx_b = cx + int(math.cos(b_angle) * (ring_radius_x + 3) * t_step)
                    ty_b = cy + int(math.sin(b_angle) * (ring_radius_y + 2) * t_step)
                    if not (has_link_peers and ty_b > cy + 2):
                        grid.put(tx_b, ty_b, g_spark, sat_col)
                # Orbital wake behind satellite
                for w_step, w_ch in ((1, g_glint), (2, g_spark)):
                    w_ang = b_angle - w_step * 0.16
                    wx = cx + int(math.cos(w_ang) * (ring_radius_x + 3))
                    wy = cy + int(math.sin(w_ang) * (ring_radius_y + 2))
                    grid.put(wx, wy, w_ch, C_DIM if w_step == 2 and use_color else sat_col)
            grid.put(bx, by, g_sat, sat_col)

    # 4. Central Faceted Core (scales across compact top banners, 35x40 side panes, and wide terminals)
    if ring_radius_x >= 22 and ring_radius_y >= 7 and height >= 26:
        core_level = 3
    elif ring_radius_x >= 11 and ring_radius_y >= 4 and height >= 18:
        core_level = 2
    else:
        core_level = 1

    clear_w = 7 if core_level == 3 else (5 if core_level == 2 else 3)
    clear_h = 4 if core_level == 3 else (3 if core_level == 2 else 2)
    for dy in range(-clear_h, clear_h + 1):
        for dx in range(-clear_w, clear_w + 1):
            if (abs(dx) / (clear_w + 0.1) + abs(dy) / (clear_h + 0.1)) <= 1.05:
                grid.put(cx + dx, cy + dy, " ", C_RESET)

    # Core facets with rotating harmonic shimmer
    if unicode_mode:
        up, dn = "▲", "▼"
        lb, rb = "⟨", "⟩"
        sl, bs = "╱", "╲"
    else:
        up, dn = "^", "v"
        lb, rb = "<", ">"
        sl, bs = "/", "\\"

    f_col_top = _get_facet_color(0.0, t, sem_mode, offer, primary_kind) if use_color else ""
    f_col_mid = _get_facet_color(0.25, t, sem_mode, offer, primary_kind) if use_color else ""
    f_col_bot = _get_facet_color(0.5, t, sem_mode, offer, primary_kind) if use_color else ""
    inner_facet_col = (C_WHITE if (offer or sem_mode in ("attending", "refracting")) else f_col_mid) if use_color else ""

    # Rotating clockwork highlight across inner cardinal facets when animate_live
    clock_idx = int(t * 6.0) % 4 if animate_live else -1
    ic_up = (C_GOLD if clock_idx == 0 and sem_mode != "ended" else inner_facet_col) if use_color else ""
    ic_rb = (C_GOLD if clock_idx == 1 and sem_mode != "ended" else inner_facet_col) if use_color else ""
    ic_dn = (C_GOLD if clock_idx == 2 and sem_mode != "ended" else inner_facet_col) if use_color else ""
    ic_lb = (C_GOLD if clock_idx == 3 and sem_mode != "ended" else inner_facet_col) if use_color else ""

    if core_level == 3:
        # Apex facets
        grid.put(cx, cy - 3, up, f_col_top)
        grid.put(cx, cy + 3, dn, f_col_bot)
        # Outer faceted crown
        grid.put(cx - 2, cy - 2, sl, f_col_top)
        grid.put(cx + 2, cy - 2, bs, f_col_top)
        grid.put(cx - 4, cy - 1, sl, f_col_mid)
        grid.put(cx + 4, cy - 1, bs, f_col_mid)
        grid.put(cx - 6, cy, lb, f_col_mid)
        grid.put(cx + 6, cy, rb, f_col_mid)
        grid.put(cx - 4, cy + 1, bs, f_col_bot)
        grid.put(cx + 4, cy + 1, sl, f_col_bot)
        grid.put(cx - 2, cy + 2, bs, f_col_bot)
        grid.put(cx + 2, cy + 2, sl, f_col_bot)
        # Coronal glints when active or crystallized
        if sem_mode in ("attending", "refracting", "branching", "resolved") or offer:
            c_glint_ch = g_glint if (animate_live and int(t * 4) % 2 == 0) else g_spark
            grid.put(cx - 3, cy, c_glint_ch, f_col_top)
            grid.put(cx + 3, cy, c_glint_ch, f_col_top)
        # Inner facets
        grid.put(cx, cy - 1, up, ic_up)
        grid.put(cx, cy + 1, dn, ic_dn)
        grid.put(cx - 2, cy, lb, ic_lb)
        grid.put(cx + 2, cy, rb, ic_rb)
        grid.put(cx, cy, g_core, core_center_col if use_color else "")
    elif core_level == 2:
        # Outer diamond crown
        grid.put(cx, cy - 2, up, f_col_top)
        grid.put(cx, cy + 2, dn, f_col_bot)
        grid.put(cx - 2, cy - 1, sl, f_col_top)
        grid.put(cx + 2, cy - 1, bs, f_col_top)
        grid.put(cx - 4, cy, lb, f_col_mid)
        grid.put(cx + 4, cy, rb, f_col_mid)
        grid.put(cx - 2, cy + 1, bs, f_col_bot)
        grid.put(cx + 2, cy + 1, sl, f_col_bot)
        # Inner jewel cradle (preserves ⟨ ⟐ ⟩ and < o > symmetry at the core)
        grid.put(cx, cy - 1, up, ic_up)
        grid.put(cx, cy + 1, dn, ic_dn)
        grid.put(cx - 2, cy, lb, ic_lb)
        grid.put(cx + 2, cy, rb, ic_rb)
        grid.put(cx, cy, g_core, core_center_col if use_color else "")
    else:
        grid.put(cx - 2, cy, lb, facet_col if use_color else "")
        grid.put(cx + 2, cy, rb, facet_col if use_color else "")
        grid.put(cx, cy - 1, up, facet_col if use_color else "")
        grid.put(cx, cy + 1, dn, facet_col if use_color else "")
        grid.put(cx, cy, g_core, core_center_col if use_color else "")

    # 5. Cyclops Link: Spark and Keeper in their own looks at their seats, and the threads they declare
    hud_y = height - 2
    if link_state is not None and link_view is not None:
        link_view.draw(grid, link_state, link_sheets or {}, centre=(cx, cy), hud_y=hud_y, t=t,
                       unicode_mode=unicode_mode, use_color=use_color, reduced_motion=reduced_motion or ended)

    # 6. Status Banner & Personal Crystalline Voice
    display_hover = hover if unicode_mode else hover.replace("·", "-")
    status_bar = f" {g_core}  {display_hover} "
    sx = max(1, (width - len(status_bar)) // 2)
    if use_color:
        # Render status bar with bright sigil, luminous "Prism", gold separator, and vivid state color
        grid.put_str(sx, hud_y, status_bar, facet_col)
        grid.put(sx + 1, hud_y, g_core, C_WHITE if sem_mode != "approval" else C_GOLD)
        prism_idx = status_bar.find("Prism")
        if prism_idx >= 0:
            grid.put_str(sx + prism_idx, hud_y, "Prism", C_WHITE if sem_mode not in ("ended", "halted") else C_DIM)
        for idx_ch, ch_s in enumerate(status_bar):
            if ch_s in ("·", "-") and idx_ch > 2:
                grid.put(sx + idx_ch, hud_y, ch_s, C_GOLD if sem_mode not in ("ended", "halted") else C_DIM)
    else:
        grid.put_str(sx, hud_y, status_bar, "")

    def _put_luminous_voice(y_row: int, text: str) -> None:
        x0 = max(1, (width - len(text)) // 2)
        if not use_color:
            grid.put_str(x0, y_row, text, "")
            return
        rgb_orchid = (196, 140, 255)
        rgb_silver = (176, 190, 210)
        if sem_mode in ("ended", "halted"):
            v_stops = [rgb_silver, (140, 155, 175), rgb_silver]
        elif sem_mode == "approval":
            v_stops = [RGB_RED, RGB_GOLD, RGB_WHITE, RGB_GOLD]
        elif offer or sem_mode == "resolved":
            v_stops = [RGB_WHITE, RGB_GOLD, RGB_CYAN, RGB_TEAL, RGB_WHITE]
        elif sem_mode == "branching":
            v_stops = [rgb_orchid, RGB_CYAN, RGB_WHITE, RGB_GOLD]
        elif sem_mode == "refracting":
            if primary_kind == "change":
                v_stops = [RGB_GOLD, RGB_WHITE, RGB_AMBER, RGB_CYAN]
            elif primary_kind == "execute":
                v_stops = [rgb_orchid, RGB_WHITE, RGB_CYAN, rgb_orchid]
            elif primary_kind == "service":
                v_stops = [RGB_TEAL, RGB_WHITE, RGB_CYAN, RGB_GOLD]
            else:
                v_stops = [RGB_CYAN, RGB_TEAL, RGB_WHITE, RGB_GOLD]
        elif sem_mode == "attending":
            v_stops = [RGB_GOLD, RGB_WHITE, RGB_CYAN, RGB_TEAL]
        else:
            v_stops = [RGB_CYAN, RGB_TEAL, RGB_WHITE, rgb_orchid, RGB_CYAN]

        n_chars = max(1, len(text))
        for i_ch, ch_v in enumerate(text):
            if ch_v in ("✧", "✦", "~"):
                col_v = C_GOLD if sem_mode not in ("ended", "halted") else "\033[38;2;176;190;210m"
            elif ch_v == "·":
                col_v = C_WHITE
            else:
                pos_v = ((i_ch / n_chars) - (t * 0.22 if not reduced_motion else 0.0)) % 1.0
                col_v = _sample_gradient(v_stops, pos_v)
            grid.put(x0 + i_ch, y_row, ch_v, col_v)

    voice_line = _get_prism_voice(sem_mode, offer, primary_kind, spectrum, t, unicode_mode)
    c_telemetry = "\033[38;2;150;215;240m" if use_color else ""
    if is_focus:
        # In focus mode, place Prism's personal voice just above the status banner when room permits
        if height >= 20 and not (link_state and link_state.get("peers")) and len(voice_line) < width - 2:
            _put_luminous_voice(hud_y - 1, voice_line)
        sub_info = f"Calls: {active_calls}  Branches: {active_branches}  Offer: {offer or 'none'}  Comp: {mode}"
        if link_state is not None and link_view is not None:
            sub_info += "  " + link_view.status(link_state)
        elif spectrum and sum(spectrum.values()) > 0:
            spec_parts = [f"{k}:{v}" for k, v in sorted(spectrum.items()) if v > 0]
            candidate = sub_info + "  Spectrum: " + " ".join(spec_parts)
            if len(candidate) <= width - 2:
                sub_info = candidate
        grid.put_str(max(1, (width - len(sub_info)) // 2), hud_y + 1, sub_info, c_telemetry)
    elif height >= 12 and not (t == 0.0 and reduced_motion and height <= 10):
        # In balanced mode, show Prism's living inner reflection on the whisper row below the banner
        if len(voice_line) > width - 2:
            voice_line = voice_line[: max(0, width - 2)]
        _put_luminous_voice(hud_y + 1, voice_line)

    return grid.render()


def load_feed_state(feed_dir: Path, now: Optional[float] = None) -> dict:
    """Read latest state from live.json or fallback to durable.json."""
    if not feed_dir or not feed_dir.is_dir():
        return {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "spectrum": {}, "hover": "Prism · ready"}

    now_ts = time.time() if now is None else now

    for filename in ["live.json", "durable.json"]:
        p = feed_dir / filename
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                events = data.get("events", [])
                if isinstance(events, list) and events:
                    active_calls = []
                    recent_impulses = []
                    spectrum: Dict[str, int] = {}
                    active_branches = 0
                    offer = None
                    latest = events[-1]
                    typ = latest.get("type", "turn.attend")

                    turn_closed = False
                    for ev in events:
                        t_name = ev.get("type")
                        ev_t = float(ev.get("t", 0.0))
                        ev_kind = ev.get("kind")
                        if t_name == "refract.start":
                            k = ev_kind or "inspect"
                            active_calls.append({"kind": k})
                            spectrum[k] = spectrum.get(k, 0) + 1
                        elif t_name in ("refract.resolve", "refract.halt"):
                            if active_calls:
                                active_calls.pop()
                            elif ev_kind:
                                spectrum[ev_kind] = spectrum.get(ev_kind, 0) + 1
                            if ev_kind and (0.0 <= now_ts - ev_t <= 2.8):
                                recent_impulses.append({"kind": ev_kind})
                        elif t_name == "branch.start":
                            active_branches += 1
                        elif t_name == "branch.resolve":
                            if active_branches > 0:
                                active_branches -= 1
                        # the reply is held out from its turn's resolve until a new turn, a halt, a copy or a wake
                        if t_name in ("turn.resolve", "reply.crystallize"):
                            offer = "crystallize"
                            recent_impulses.clear()
                            turn_closed = True
                        elif t_name in ("session.wake", "turn.attend", "turn.halt", "reply.copied"):
                            offer = None
                            if t_name in ("session.wake", "turn.halt"):
                                spectrum.clear()
                                recent_impulses.clear()
                                turn_closed = (t_name == "turn.halt")
                            elif t_name == "turn.attend" and turn_closed:
                                spectrum.clear()
                                recent_impulses.clear()
                                turn_closed = False

                    # Surface recent PostToolUse impulses (<2.8s) as live refraction rays during active turns
                    effective_calls = active_calls if active_calls else (
                        recent_impulses[-4:] if typ in ("refract.resolve", "refract.halt", "turn.attend") else []
                    )

                    if typ == "session.end":
                        sem_mode = "ended"
                    elif typ == "approval.request":
                        sem_mode = "approval"
                    elif effective_calls:
                        sem_mode = "refracting"
                    elif active_branches:
                        sem_mode = "branching"
                    elif typ in ("reply.crystallize", "turn.resolve"):
                        sem_mode = "resolved"
                    elif typ == "turn.halt":
                        sem_mode = "halted"
                    else:
                        sem_mode = "attending" if typ in ("turn.attend", "refract.resolve", "branch.resolve") else "idle"

                    if sem_mode == "idle":
                        hover_text = "Prism · ready"
                    else:
                        hover_text = f"Prism · {sem_mode}"
                    if sem_mode == "refracting" and effective_calls:
                        kinds = sorted({c["kind"] for c in effective_calls})
                        hover_text = f"Prism · refracting · {', '.join(kinds)}"
                    elif sem_mode == "branching":
                        hover_text = f"Prism · parallel synthesis · {active_branches} branches"
                    elif sem_mode == "approval":
                        hover_text = "Prism · awaiting consent"
                    elif sem_mode == "resolved" and offer:
                        hover_text = "Prism · crystallized · 1 ready"

                    return {
                        "mode": sem_mode,
                        "ended": typ == "session.end",
                        "offer": offer,
                        "activeCalls": len(effective_calls),
                        "activeBranches": active_branches,
                        "lanes": effective_calls,
                        "spectrum": spectrum,
                        "hover": hover_text,
                    }
            except Exception:
                pass

    return {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "spectrum": {}, "hover": "Prism · ready"}


def get_demo_state(t: float, forced_state: str = None) -> dict:
    """Generate cycling or forced demo states for standalone exploration."""
    states_sequence = [
        ("idle", None, 0, 0, []),
        ("attending", None, 0, 0, []),
        ("refracting", None, 2, 0, [{"kind": "inspect"}, {"kind": "change"}]),
        ("branching", None, 0, 2, []),
        ("approval", None, 1, 0, [{"kind": "execute"}]),
        ("resolved", "crystallize", 0, 0, []),
    ]

    if forced_state:
        selected_mode = forced_state
        offer = "crystallize" if selected_mode == "crystallize" or selected_mode == "resolved" else None
        active_calls = 2 if selected_mode == "refracting" else (1 if selected_mode == "approval" else 0)
        active_branches = 2 if selected_mode == "branching" else 0
        lanes = [{"kind": "inspect"}, {"kind": "change"}] if selected_mode == "refracting" else []
    else:
        # Cycle through states every 4 seconds
        idx = int((t // 4.0) % len(states_sequence))
        selected_mode, offer, active_calls, active_branches, lanes = states_sequence[idx]

    hover_desc = {
        "idle": "Prism · ready",
        "attending": "Prism · attending",
        "refracting": "Prism · refracting · change, inspect",
        "branching": "Prism · parallel synthesis · 2 branches",
        "approval": "Prism · awaiting consent",
        "resolved": "Prism · crystallized · 1 ready",
        "crystallize": "Prism · crystallized · 1 ready",
        "ended": "Prism · ended",
    }.get(selected_mode, f"Prism · {selected_mode}")

    return {
        "mode": "resolved" if selected_mode == "crystallize" else selected_mode,
        "ended": selected_mode == "ended",
        "offer": offer,
        "activeCalls": active_calls,
        "activeBranches": active_branches,
        "lanes": lanes,
        "hover": hover_desc,
    }


def handle_tmux(subcmd: str = "split") -> None:
    """Manage Prism inside tmux (split pane, status line, or standalone)."""
    tmux_bin = shutil.which("tmux")
    if not tmux_bin:
        print("Notice: tmux is not found in PATH.")
        print("To install tmux on Ubuntu/Debian: sudo apt install tmux")
        sys.exit(1)

    in_tmux = bool(os.environ.get("TMUX"))
    launcher = shutil.which("prism") or str(Path(__file__).resolve().parent.parent / "bin" / "prism")

    if subcmd == "status":
        status_expr = f"#({launcher} once --plain | grep -o 'Prism.*' | head -n 1) | %H:%M "
        subprocess.run([tmux_bin, "set", "-g", "status-interval", "2"], check=False)
        subprocess.run([tmux_bin, "set", "-g", "status-right", status_expr], check=False)
        print("✓ Prism status line configured in tmux status-right.")
        return

    if subcmd in ("top", "prismtop"):
        if in_tmux:
            subprocess.run([tmux_bin, "set", "-g", "mouse", "on"], check=False)
            subprocess.run([tmux_bin, "split-window", "-b", "-v", "-l", "14", launcher], check=False)
            subprocess.run([tmux_bin, "select-pane", "-D"], check=False)
            print("✓ Prism companion opened in top pane.")
        else:
            print("Notice: Not currently inside a tmux session.")
            print("Start a new tmux session with Prism on top using:")
            print(f"  tmux new-session \\; set -g mouse on \\; split-window -b -v -l 14 '{launcher}' \\; select-pane -D")
        return

    if subcmd in ("split", "side", "open", "launch", ""):
        if in_tmux:
            subprocess.run([tmux_bin, "set", "-g", "mouse", "on"], check=False)
            subprocess.run([tmux_bin, "split-window", "-h", "-l", "35", launcher], check=False)
            subprocess.run([tmux_bin, "select-pane", "-L"], check=False)
            print("✓ Prism companion opened in side pane.")
        else:
            print("Notice: Not currently inside a tmux session.")
            print("Start a new tmux session with Prism side-by-side using:")
            print(f"  tmux new-session \\; set -g mouse on \\; split-window -h -l 35 '{launcher}' \\; select-pane -L")
        return

    if subcmd == "kill":
        if in_tmux:
            p = subprocess.run([tmux_bin, "list-panes", "-F", "#{pane_id} #{pane_current_command}"], capture_output=True, text=True)
            killed = False
            for line in p.stdout.splitlines():
                if "prism" in line or "python" in line:
                    pane_id = line.split()[0]
                    subprocess.run([tmux_bin, "kill-pane", "-t", pane_id], check=False)
                    killed = True
            if killed:
                print("✓ Prism pane closed.")
            else:
                print("No active Prism pane found.")
        else:
            print("Not inside tmux.")
        return


def handle_link(subcmd: str = "status") -> None:
    """prism link on | off | status: Prism's own Cyclops Link switch (off until you turn it on)."""
    if link is None:
        print("Cyclops Link is not available in this install.")
        sys.exit(1)
    if subcmd in ("on", "off"):
        path = link.set_enabled(subcmd == "on")
        if subcmd == "on":
            print("✓ Prism Link on: she shares her coarse state and sees Spark and Keeper working in the same folder.")
            print("  Nothing else is shared: no prompts, commands, paths or names. Off again: prism link off")
        else:
            print("✓ Prism Link off. Her record says she has ended and is removed a minute later.")
        print(f"  (switch: {path})")
        return
    on = link.enabled()
    print(f"Prism Link: {'on' if on else 'off'}" + ("  (PRISM_LINK overrides the switch)" if os.environ.get("PRISM_LINK") else ""))
    if not on:
        print("  Turn on: prism link on")
        return
    watch = link_view.Watch()
    feed = presence_feed.find_active_feed() if presence_feed else None
    view = watch.view(feed)
    print("  " + link_view.status(view))
    for peer in (view or {}).get("peers", []):
        print(f"  · {peer['presence']} {peer['state']}  tools {peer['tools']}  branches {peer['branches']}")
    for th in (view or {}).get("threads", []):
        print(f"  · thread {th['from']} → {th['to']}")


def main():
    parser = argparse.ArgumentParser(description="Prism Terminal Presence Observer")
    parser.add_argument("--feed", type=Path, default=None, help="Path to presence feed directory (containing live.json)")
    parser.add_argument("--mode", choices=["balanced", "focus"], default="balanced", help="Composition layout")
    parser.add_argument("--plain", action="store_true", help="Render pure ASCII without Unicode")
    parser.add_argument("--no-color", action="store_true", help="Suppress ANSI color escape sequences")
    parser.add_argument("--once", action="store_true", help="Render a single frame and exit (tmux/statusbar)")
    parser.add_argument("--demo", action="store_true", help="Continuously cycle through demonstration states")
    parser.add_argument("--demo-state", choices=["idle", "attending", "refracting", "branching", "approval", "crystallize", "resolved", "ended"], default=None, help="Force demo to specific state")
    parser.add_argument("--calm", action="store_true", help="Slower ambient rotation")
    parser.add_argument("--reduced-motion", action="store_true", help="Disable ring rotation animation")

    # Positional sugar: prism tmux, prism focus, prism once, prism demo, prism plain
    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] == "tmux":
        subaction = raw_args[1] if len(raw_args) > 1 else "split"
        handle_tmux(subaction)
        sys.exit(0)
    if raw_args and raw_args[0] == "link":
        handle_link(raw_args[1] if len(raw_args) > 1 else "status")
        sys.exit(0)

    normalized_args = []
    skip_next = False
    for arg in raw_args:
        if skip_next:
            skip_next = False
            normalized_args.append(arg)
            continue
        if arg in ("--mode", "--feed", "--demo-state"):
            normalized_args.append(arg)
            skip_next = True
            continue
        if arg == "focus":
            normalized_args.extend(["--mode", "focus"])
        elif arg == "once":
            normalized_args.append("--once")
        elif arg == "demo":
            normalized_args.append("--demo")
        elif arg == "plain":
            normalized_args.append("--plain")
        else:
            normalized_args.append(arg)

    args = parser.parse_args(normalized_args)

    use_color = not (args.no_color or "NO_COLOR" in os.environ)
    unicode_mode = not args.plain

    # Resolve feed path
    feed_dir = args.feed
    if not feed_dir and not args.demo and not args.demo_state and presence_feed and hasattr(presence_feed, "find_active_feed"):
        feed_dir = presence_feed.find_active_feed()

    # Cyclops Link: only drawn while Prism is linked; demos never show live peers
    watch = link_view.Watch() if (link_view is not None and not args.demo and not args.demo_state) else None

    # One-shot rendering (--once)
    if args.once:
        cols, rows = shutil.get_terminal_size((80, 24))
        if feed_dir and feed_dir.is_dir():
            state = load_feed_state(feed_dir)
        elif args.demo or args.demo_state:
            state = get_demo_state(0.0, forced_state=args.demo_state)
        else:
            state = get_demo_state(0.0, forced_state="idle")

        frame = render_prism_frame(
            state,
            cols,
            rows,
            t=0.0,
            mode=args.mode,
            unicode_mode=unicode_mode,
            use_color=use_color,
            reduced_motion=args.reduced_motion,
            calm=args.calm,
            link_state=watch.view(feed_dir) if watch else None,
            link_sheets=watch.sheets if watch else None,
        )
        print(frame)
        sys.exit(0)

    explicit_feed = args.feed is not None

    # Interactive live animation loop
    def restore_and_exit(signum=None, frame=None):
        sys.stdout.write("\033[?25h\033[?12h\033[0m\033[?1049l\n")  # Show cursor, restore blink, reset color, exit alternate screen
        if os.environ.get("TMUX"):
            sys.stdout.write("\033Ptmux;\033\033[?25h\033\\\033Ptmux;\033\033[?12h\033\\")
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, restore_and_exit)
    signal.signal(signal.SIGTERM, restore_and_exit)

    # Enter alternate screen buffer, hide cursor & disable blinking
    sys.stdout.write("\033[?1049h\033[?25l\033[?12l\033[2J\033[H")
    if os.environ.get("TMUX"):
        sys.stdout.write("\033Ptmux;\033\033[?25l\033\\\033Ptmux;\033\033[?12h\033\\")
    sys.stdout.flush()

    try:
        t0 = time.time()
        last_feed_check = 0.0
        prev_size = None
        while True:
            try:
                t = time.time() - t0
                cols, rows = shutil.get_terminal_size((80, 24))

                # Auto-recheck feed dynamically every 0.5s if running in auto mode
                if not explicit_feed and not args.demo and not args.demo_state and presence_feed and (t - last_feed_check >= 0.5):
                    last_feed_check = t
                    discovered = presence_feed.find_active_feed()
                    if discovered and discovered != feed_dir:
                        feed_dir = discovered

                if feed_dir and feed_dir.is_dir():
                    state = load_feed_state(feed_dir)
                elif args.demo or args.demo_state:
                    state = get_demo_state(t, forced_state=args.demo_state)
                else:
                    state = get_demo_state(t, forced_state="idle")

                link_st = None
                link_sh = None
                if watch:
                    try:
                        link_st = watch.view(feed_dir)
                        link_sh = watch.sheets
                    except Exception:
                        pass

                frame = render_prism_frame(
                    state,
                    cols,
                    rows,
                    t=t,
                    mode=args.mode,
                    unicode_mode=unicode_mode,
                    use_color=use_color,
                    reduced_motion=args.reduced_motion,
                    calm=args.calm,
                    link_state=link_st,
                    link_sheets=link_sh,
                )

                # Atomic redraw with cursor hide & bottom-right parking
                clear_seq = "\033[2J" if (cols, rows) != prev_size else ""
                prev_size = (cols, rows)

                sys.stdout.write(f"\033[?25l\033[?12l{clear_seq}\033[H{frame}\033[{rows};{cols}H\033[?25l")
                sys.stdout.flush()
            except Exception:
                pass
            time.sleep(0.05)
    except (KeyboardInterrupt, SystemExit):
        restore_and_exit()


if __name__ == "__main__":
    main()
