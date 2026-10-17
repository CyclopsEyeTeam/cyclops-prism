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
import base64
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import sys
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import termios
    import tty
except ImportError:
    termios = tty = None

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
try:
    import mcp_server
except ImportError:
    mcp_server = None
try:
    import painter
except ImportError:
    painter = None
try:
    import roll
except ImportError:
    roll = None


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
RGB_ORCHID = (196, 140, 255)   # Luminous Orchid #C48CFF
RGB_ROSE = (255, 110, 180)     # Rose Coral #FF6EB4
RGB_MINT = (130, 255, 210)     # Bioluminescent Mint #82FFD2
RGB_ICE = (165, 220, 255)      # Moonlit Ice #A5DCFF

MOOD_STOPS = {
    "aurora": ([RGB_CYAN, RGB_TEAL, RGB_ORCHID, RGB_WHITE], [RGB_TEAL, RGB_WHITE, RGB_CYAN, RGB_VIOLET]),
    "solar": ([RGB_GOLD, RGB_AMBER, RGB_ROSE, RGB_WHITE], [RGB_WHITE, RGB_GOLD, RGB_AMBER, RGB_CYAN]),
    "nebula": ([RGB_ORCHID, RGB_ROSE, RGB_VIOLET, RGB_CYAN], [RGB_CYAN, RGB_ORCHID, RGB_WHITE, RGB_ROSE]),
    "emerald": ([RGB_TEAL, RGB_MINT, RGB_CYAN, RGB_WHITE], [RGB_MINT, RGB_TEAL, RGB_GOLD, RGB_CYAN]),
    "supernova": ([RGB_WHITE, RGB_GOLD, RGB_RED, RGB_CYAN], [RGB_GOLD, RGB_WHITE, RGB_ORCHID, RGB_CYAN]),
    "zen": ([RGB_ICE, RGB_MINT, RGB_WHITE, RGB_CYAN], [RGB_WHITE, RGB_ICE, RGB_TEAL, RGB_ICE]),
    "crystalline": ([RGB_CYAN, RGB_WHITE, RGB_TEAL, RGB_GOLD], [RGB_WHITE, RGB_CYAN, RGB_ORCHID, RGB_WHITE]),
}

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


def _get_ring_color(ring_id: int, phi: float, theta: float, sem_mode: str, offer: Optional[str], primary_kind: str = "", mood: Optional[str] = None) -> str:
    """Calculate the living chromatic dispersion along Prism's polarized rings."""
    pos = ((phi + (theta if ring_id == 1 else -theta)) / (2.0 * math.pi)) % 1.0

    if mood and mood in MOOD_STOPS and sem_mode not in ("ended", "halted", "approval"):
        s1, s2 = MOOD_STOPS[mood]
        return _sample_gradient(s1 if ring_id == 1 else s2, pos)

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


def _get_facet_color(pos: float, t: float, sem_mode: str, offer: Optional[str], primary_kind: str = "", mood: Optional[str] = None) -> str:
    """Calculate living iridescent shimmer across Prism's central jewel facets."""
    phase = (pos + t * 0.35) % 1.0
    if mood and mood in MOOD_STOPS and sem_mode not in ("ended", "halted", "approval"):
        return _sample_gradient(MOOD_STOPS[mood][0], phase)
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


def _char_cells(ch: str) -> int:
    """Return terminal column width (0, 1, or 2) of a single character."""
    if not ch:
        return 0
    code = ord(ch[0])
    if code < 32 or (0x7F <= code < 0xA0):
        return 0
    import unicodedata
    if unicodedata.combining(ch[0]):
        return 0
    if unicodedata.east_asian_width(ch[0]) in ("W", "F"):
        return 2
    return 1


class TerminalGrid:
    """Character and color cell grid for CLI rendering."""

    def __init__(self, width: int, height: int, use_color: bool = True):
        self.width = max(20, width)
        self.height = max(10, height)
        self.use_color = use_color
        self.chars = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.colors = [["" for _ in range(self.width)] for _ in range(self.height)]

    def put(self, x: int, y: int, ch: str, color: str = ""):
        if not (0 <= y < self.height and 0 <= x < self.width) or not ch:
            return
        w = _char_cells(ch)
        if w <= 0:
            return
        # If overwriting the right half of a previous 2-cell glyph, clear its left half
        if self.chars[y][x] == "" and x > 0:
            self.chars[y][x - 1] = " "
        # If overwriting a 2-cell glyph at x, restore its right half at x + 1
        if _char_cells(self.chars[y][x]) == 2 and x + 1 < self.width and self.chars[y][x + 1] == "":
            self.chars[y][x + 1] = " "
        if w == 2:
            if x + 1 >= self.width:
                self.chars[y][x] = " "
                if self.use_color:
                    self.colors[y][x] = color
                return
            if _char_cells(self.chars[y][x + 1]) == 2 and x + 2 < self.width and self.chars[y][x + 2] == "":
                self.chars[y][x + 2] = " "
            self.chars[y][x] = ch
            self.chars[y][x + 1] = ""
            if self.use_color:
                self.colors[y][x] = color
                self.colors[y][x + 1] = color
        else:
            self.chars[y][x] = ch
            if self.use_color:
                self.colors[y][x] = color

    def put_str(self, x: int, y: int, text: str, color: str = ""):
        cur_x = x
        for ch in text:
            w = _char_cells(ch)
            if w <= 0:
                continue
            if cur_x + w > self.width:
                break
            self.put(cur_x, y, ch, color)
            cur_x += w

    def render(self) -> str:
        lines = []
        for y in range(self.height):
            line = []
            cur_color = ""
            for x in range(self.width):
                ch = self.chars[y][x]
                if ch == "":
                    continue
                col = self.colors[y][x] if self.use_color else ""
                if self.use_color and col != cur_color:
                    # Only emit C_RESET if leaving a background or italic attribute that the next cell does not override
                    needs_reset = (("[48;" in cur_color) and ("[48;" not in col)) or (
                        ("\033[3m" in cur_color) and ("\033[3m" not in col)
                    )
                    line.append(C_RESET if not col else (C_RESET + col if needs_reset else col))
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
    expression: Optional[dict] = None,
    ui_state: Optional[dict] = None,
    hitboxes: Optional[List[dict]] = None,
) -> str:
    """Render one complete ASCII/ANSI terminal frame for Prism.

    link_state: the Cyclops Link view (peers and threads) when Link is on; None draws Prism alone.
    expression: optional live payload from Prism's Expressive Channel (thought, mood, effect, glyph, art, painting).
    ui_state: optional interactive UI state (story mode, convert menu, active job progress).
    hitboxes: optional list populated with clickable button regions for mouse interaction.
    """
    grid = TerminalGrid(width, height, use_color=use_color)

    sem_mode = state_data.get("mode", "idle")
    offer = state_data.get("offer")
    ended = state_data.get("ended", False)
    active_calls = state_data.get("activeCalls", 0)
    active_branches = state_data.get("activeBranches", 0)
    lanes = state_data.get("lanes", [])
    spectrum = state_data.get("spectrum") or {}
    hover = state_data.get("hover", "Prism · ready")

    expr = expression or {}
    expr_thought = str(expr.get("thought") or "").strip()
    expr_mood = str(expr.get("mood") or "").strip().lower() or None
    expr_effect = str(expr.get("effect") or "").strip().lower() or None
    expr_glyph = str(expr.get("glyph") or "").strip()[:2]
    expr_art = expr.get("art") if isinstance(expr.get("art"), list) else []
    expr_painting = expr.get("painting") if isinstance(expr.get("painting"), dict) else None

    has_link_peers = bool(
        link_state and any(p.get("presence") != "prism" for p in (link_state.get("peers") or []))
    )
    has_painting = bool(expr_painting and painter is not None and height >= 20)

    cx = width // 2
    if has_painting:
        # Compact upper figure so the lower painting canvas has generous vertical room
        hud_y = max(8, min(height - 14, int(height * 0.28), 14))
        cy = max(4, hud_y // 2)
        fig_height = hud_y + 2
    else:
        hud_y = height - 2
        cy = height // 2 - 1
        fig_height = height

    primary_kind = lanes[0].get("kind", "") if lanes else ""

    # Glyph sets
    if unicode_mode:
        g_core = "⟐"
        if ended:
            g_core = "·"
        elif sem_mode == "approval":
            g_core = "!"
        elif expr_glyph:
            g_core = expr_glyph[0]
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
        if expr_glyph and not ended and sem_mode != "approval" and ord(expr_glyph[0]) < 128:
            g_core = expr_glyph[0]
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
    max_ry = max(2, hud_y - cy - 2)

    base_rx = max(11, min(int(width * 0.36), 46))
    base_ry = max(2, min(int(fig_height * 0.28), max_ry, 16))
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
    breath_amp = 0.08 if expr_effect == "pulse" else 0.035
    breath_freq = 3.2 if expr_effect == "pulse" else 1.6
    breath = 1.0 + (breath_amp * math.sin(t * breath_freq) if animate_live else 0.0)
    eff_rx = ring_radius_x * breath
    eff_ry = ring_radius_y * breath

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
                    col_aura = _get_facet_color(a_idx / len(aura_angles), t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
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
        col1 = (C_WHITE if is_glint1 else _get_ring_color(1, phi, theta, sem_mode, offer, primary_kind, mood=expr_mood)) if use_color else ""
        grid.put(rx1, ry1, g_glint if is_glint1 else g_ring1, col1)

        # Ring 2 (counter-angle)
        rx2 = cx + int(math.cos(phi - theta) * eff_rx)
        ry2 = cy + int(math.sin(phi - theta) * eff_ry * 0.7 + math.cos(phi - theta) * 1.5)
        is_glint2 = animate_live and ((i - glint_offset) % glint_stride == 0)
        col2 = (C_WHITE if is_glint2 else _get_ring_color(2, phi, theta, sem_mode, offer, primary_kind, mood=expr_mood)) if use_color else ""
        grid.put(rx2, ry2, g_glint if is_glint2 else g_ring2, col2)

    # 1b. State-Specific & Expressive Crystalline Choreography inside & around the Ring Cavity
    if (animate_live or expr_effect) and not ended and height >= 16:
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

        # Expressive Channel Special Particle Animations (requested by Prism via MCP or CLI)
        if expr_effect in ("starburst", "bloom"):
            burst_dirs = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
            for b_i, (dx_b, dy_b) in enumerate(burst_dirs):
                if has_link_peers and dy_b > 0:
                    continue
                b_pulse = (t * 2.0 + b_i * 0.125) % 1.0
                rx_b = cx + dx_b * (5 + int(b_pulse * max(4, ring_radius_x - 4)))
                ry_b = cy + dy_b * (2 + int(b_pulse * max(2, ring_radius_y - 1)))
                if 1 <= ry_b < hud_y - 2 and 2 <= rx_b < width - 2:
                    b_ch = g_star if b_pulse < 0.5 else g_glint
                    b_col = _get_facet_color(b_i / 8.0, t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
                    grid.put(rx_b, ry_b, b_ch, b_col)
        elif expr_effect == "meteor":
            for m_i in range(4):
                m_prog = (t * 1.8 + m_i * 0.25) % 1.0
                mx_head = int(2 + m_prog * max(10, width - 6))
                my_head = max(1, min(cy - 1 if has_link_peers else hud_y - 3, 2 + ((m_i * 3 + int(m_prog * 6)) % max(3, cy))))
                grid.put(mx_head, my_head, g_star, C_WHITE if use_color else "")
                grid.put(mx_head - 1, my_head, g_glint, C_GOLD if use_color else "")
                grid.put(mx_head - 2, my_head, "─" if unicode_mode else "-", C_CYAN if use_color else "")
        elif expr_effect == "ripple":
            for r_idx in range(3):
                r_frac = (t * 1.4 + r_idx * 0.33) % 1.0
                r_dist = 5 + int(r_frac * max(4, ring_radius_x))
                l_rip, r_rip = ("⟨", "⟩") if unicode_mode else ("(", ")")
                r_col = _get_facet_color(r_frac, t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
                grid.put(cx - r_dist, cy, l_rip, r_col)
                grid.put(cx + r_dist, cy, r_rip, r_col)

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
    if ring_radius_x >= 22 and ring_radius_y >= 7 and fig_height >= 26:
        core_level = 3
    elif ring_radius_x >= 11 and ring_radius_y >= 4 and fig_height >= 18:
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

    f_col_top = _get_facet_color(0.0, t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
    f_col_mid = _get_facet_color(0.25, t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
    f_col_bot = _get_facet_color(0.5, t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
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

    # 4b. Expressive Channel Floating Art Banner (top of canvas when Prism projects custom ASCII/Unicode art)
    if expr_art and fig_height >= 16 and not has_link_peers:
        for art_i, raw_line in enumerate(expr_art[:5]):
            art_y = 1 + art_i
            if art_y >= cy - 2:
                break
            art_line = str(raw_line)[: max(1, width - 4)]
            if not unicode_mode:
                art_line = "".join(ch if ord(ch) < 128 else "*" for ch in art_line)
            ax0 = max(1, (width - len(art_line)) // 2)
            for c_idx, ch_a in enumerate(art_line):
                if ch_a != " ":
                    col_a = _get_facet_color(c_idx / max(1, len(art_line)), t, sem_mode, offer, primary_kind, mood=expr_mood) if use_color else ""
                    grid.put(ax0 + c_idx, art_y, ch_a, col_a)

    # 5. Cyclops Link: Spark and Keeper in their own looks at their seats, and the threads they declare
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
        if expr_mood and expr_mood in MOOD_STOPS and sem_mode not in ("ended", "halted", "approval"):
            v_stops = MOOD_STOPS[expr_mood][0]
        elif sem_mode in ("ended", "halted"):
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

    voice_lines: List[str] = []
    if expr_thought:
        raw_t = expr_thought if unicode_mode else "".join(ch if ord(ch) < 128 else "-" for ch in expr_thought.replace("·", "-"))
        max_inner = max(8, width - 10)
        if unicode_mode:
            wings = ["✧", "✦", "◈", "✦"]
            w_l = wings[int(max(0.0, t) * 3.0) % len(wings)] if t > 0.0 else "✧"
            w_r = wings[(int(max(0.0, t) * 3.0) + 2) % len(wings)] if t > 0.0 else "✧"
            fmt_line = lambda s: f"{w_l}  {s}  {w_r}"
        else:
            wings_ascii = ["~", "*", "+", "*"]
            w_l = wings_ascii[int(max(0.0, t) * 3.0) % len(wings_ascii)] if t > 0.0 else "~"
            w_r = wings_ascii[(int(max(0.0, t) * 3.0) + 2) % len(wings_ascii)] if t > 0.0 else "~"
            fmt_line = lambda s: f"{w_l} {s} {w_r}"

        if len(raw_t) > max_inner and height >= 24 and not is_focus:
            # Word-wrap cleanly across 2 balanced lines so the full thought is readable at once
            target_split = min(max_inner, max(len(raw_t) // 2, len(raw_t) - max_inner))
            split_at = raw_t.rfind(" ", 1, max_inner + 1)
            best_space = raw_t.rfind(" ", 1, target_split + 8)
            if best_space > 0 and len(raw_t[best_space + 1 :]) <= max_inner:
                split_at = best_space
            if split_at <= 0:
                split_at = max_inner
            line1 = raw_t[:split_at].strip()
            line2 = raw_t[split_at:].strip()[:max_inner]
            voice_lines = [fmt_line(line1)]
            if line2:
                voice_lines.append(fmt_line(line2))
        else:
            if len(raw_t) > max_inner and animate_live:
                padded = raw_t + "   ·   "
                offset_m = int(t * 6.0) % len(padded)
                doubled = padded + padded
                raw_t = doubled[offset_m : offset_m + max_inner]
            elif len(raw_t) > max_inner:
                raw_t = raw_t[:max_inner]
            voice_lines = [fmt_line(raw_t)]
    else:
        voice_lines = [_get_prism_voice(sem_mode, offer, primary_kind, spectrum, t, unicode_mode)]

    voice_line = voice_lines[0]
    c_telemetry = "\033[38;2;150;215;240m" if use_color else ""
    paint_top_y = hud_y + 2
    if is_focus:
        # In focus mode, place Prism's personal voice just above the status banner when room permits
        if fig_height >= 20 and not (link_state and link_state.get("peers")) and len(voice_line) < width - 2:
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
        # In balanced mode, show Prism's living inner reflection on the whisper row(s) below the banner
        for v_idx, v_ln in enumerate(voice_lines[:2]):
            if hud_y + 1 + v_idx < height:
                if len(v_ln) > width - 2:
                    v_ln = v_ln[: max(0, width - 2)]
                _put_luminous_voice(hud_y + 1 + v_idx, v_ln)
        paint_top_y = hud_y + (3 if has_painting and height >= 24 else 1 + len(voice_lines[:2]))

    # Keep painting top row steady for a given terminal height so 1-line vs 2-line thoughts never shift the canvas
    if has_painting:
        remaining_h = height - paint_top_y
        if remaining_h >= 16:
            paint_top_y += 1

    # 7. Clickable Top-Right Tools, Progress Row, Convert Menu, Lower-Pane Painting Block & Side Chat
    ui = ui_state or {}
    story_st = ui.get("story") if isinstance(ui.get("story"), dict) else None
    active_job = ui.get("job") or (expr.get("job") if isinstance(expr.get("job"), dict) else None)
    menu_step = int(ui.get("menu_step") or 0)
    chat_active = bool(ui.get("chat_active"))
    chat_input = str(ui.get("chat_input") or "")
    chat_msgs = ui.get("chat_messages") if isinstance(ui.get("chat_messages"), list) else (
        expr.get("chat") if isinstance(expr.get("chat"), list) else []
    )

    # If story is active, show the current story page painting
    shown_painting = expr_painting
    reveal_ov = None
    if story_st and story_st.get("active") and story_st.get("painting"):
        shown_painting = story_st["painting"]
        reveal_ov = story_st.get("reveal")
        has_painting = bool(painter is not None and height >= 20)

    if has_painting:
        # §2 Only show the tools when there's at least one painting and room to spare, so they never shrink the painting
        if width >= 34 and height >= 20:
            if unicode_mode:
                tool_defs = [
                    ("▶ story", "tool_story"),
                    ("⇪ convert", "tool_convert"),
                    ("◎ roll", "tool_roll"),
                ]
                if width >= 44:
                    tool_defs.append(("💬 chat", "tool_chat"))
                if width >= 54:
                    tool_defs.append(("⧉ copy", "tool_copy"))
            else:
                tool_defs = [
                    ("> story", "tool_story"),
                    ("^ convert", "tool_convert"),
                    ("o roll", "tool_roll"),
                ]
                if width >= 44:
                    tool_defs.append(("[?] chat", "tool_chat"))
                if width >= 54:
                    tool_defs.append(("[c] copy", "tool_copy"))

            sep = "   " if width >= 56 else "  "
            sep_w = len(sep)
            total_tools_w = sum(sum(_char_cells(c) for c in lbl) for lbl, _ in tool_defs) + sep_w * (len(tool_defs) - 1)
            tx0 = max(1, width - total_tools_w - 1)
            cur_tx = tx0
            for lbl, act in tool_defs:
                lbl_w = sum(_char_cells(c) for c in lbl)
                is_active_tool = (
                    (act == "tool_story" and story_st and story_st.get("active"))
                    or (act == "tool_convert" and menu_step in (1, 2))
                    or (act == "tool_chat" and chat_active)
                )
                t_col = (C_GOLD if is_active_tool else C_CYAN) if use_color else ""
                grid.put_str(cur_tx, 0, lbl, t_col)
                if hitboxes is not None:
                    hitboxes.append({"y": 0, "x0": cur_tx, "x1": cur_tx + lbl_w, "action": act})
                cur_tx += lbl_w + sep_w

            # §2 Second row under the tools while a convert or roll is being made
            if active_job and active_job.get("active") and painter is not None:
                j_label = str(active_job.get("label") or "refracting")
                j_frac = float(active_job.get("fraction") or 0.0)
                bar_str = painter.render_progress_bar(j_frac, bar_cells=10 if width < 56 else 12, unicode_mode=unicode_mode)
                max_lbl = max(8, width - len(bar_str) - 4)
                if len(j_label) > max_lbl:
                    j_label = j_label[: max_lbl - 1] + ("…" if unicode_mode else ".")
                prog_line = f"{j_label}  {bar_str}"
                px0 = max(1, width - len(prog_line) - 1)
                grid.put_str(px0, 1, prog_line, C_GOLD if use_color else "")

        if menu_step in (1, 2):
            # §4 Interactive Convert Menu asking two questions, each choice showing its cost
            n_sess = max(1, int(ui.get("session_count") or (expr.get("paintStats") or {}).get("paintings") or 1))
            m_top = paint_top_y + 1
            hdr_col = C_GOLD if use_color else ""
            opt_col = C_CYAN if use_color else ""
            dim_c = "\033[38;2;140;150;168m" if use_color else ""
            mx = max(2, (width - min(width - 4, 48)) // 2)
            if menu_step == 1:
                hdr = "⇪ convert · what?" if unicode_mode else "^ convert - what?"
                opts = [
                    ("1. This painting", "0–2.4k tokens", "menu_what_this"),
                    ("2. Every way", "~4.5k tokens", "menu_what_every"),
                    (f"3. All {n_sess} {'painting' if n_sess == 1 else 'paintings'}", f"0–{2.4 * n_sess:.1f}k tokens", "menu_what_all"),
                    ("4. The roll", "no tokens", "menu_what_roll"),
                    ("✕ cancel" if unicode_mode else "x cancel", "", "menu_cancel"),
                ]
            else:
                target_lbl = ui.get("convert_target", "this")
                mult = n_sess if target_lbl == "all" else 1
                hdr = "⇪ convert · which way?" if unicode_mode else "^ convert - which way?"
                opts = [
                    ("1. Truest · terminal cell weight & 4-layer depth", "no tokens", "menu_way_truest"),
                    ("2. Faithful · same marks, large and fine", "no tokens", "menu_way_faithful"),
                    ("3. Refined · revisited subject", f"~{2.1 * mult:.1f}k tokens", "menu_way_refined"),
                    ("4. Interpretive · freely reimagined", f"~{2.4 * mult:.1f}k tokens", "menu_way_interpretive"),
                    ("‹ back" if unicode_mode else "< back", "", "menu_back"),
                ]
            if m_top < height:
                grid.put_str(mx, m_top, hdr[: width - mx - 1], hdr_col)
            for idx_o, (o_lbl, o_cost, o_act) in enumerate(opts):
                oy = m_top + 2 + idx_o
                if oy >= height:
                    break
                line_o = f"{o_lbl}  ({o_cost})" if o_cost else o_lbl
                line_o = line_o[: max(1, width - mx - 1)]
                grid.put_str(mx, oy, line_o, opt_col if o_cost else dim_c)
                if hitboxes is not None:
                    hitboxes.append({"y": oy, "x0": mx, "x1": mx + len(line_o), "action": o_act})
        else:
            # Reserve a steady number of rows at the bottom of the pane for the Side Chat box
            chat_rows = 0
            avail_total = height - paint_top_y
            if not (story_st and story_st.get("active")):
                if avail_total >= 21:
                    chat_rows = 6
                elif avail_total >= 17:
                    chat_rows = 4
                elif chat_active and avail_total >= 10:
                    chat_rows = min(4, max(3, avail_total - 7))

            paint_bot_y = height - chat_rows
            painter.draw_painting_block(
                grid,
                shown_painting,
                width=width,
                top_y=paint_top_y,
                bot_y=paint_bot_y,
                t=t,
                unicode_mode=unicode_mode,
                use_color=use_color,
                session_stats=expr.get("paintStats"),
                story_state=story_st,
                reveal_override=reveal_ov,
                hitboxes=hitboxes,
            )

            if chat_rows >= 2:
                _draw_side_chat_panel(
                    grid=grid,
                    painting=shown_painting,
                    width=width,
                    top_y=paint_bot_y,
                    bot_y=height,
                    t=t,
                    unicode_mode=unicode_mode,
                    use_color=use_color,
                    chat_active=chat_active,
                    chat_input=chat_input,
                    chat_msgs=chat_msgs,
                    chat_scroll=int(ui.get("chat_scroll") or 0),
                    hitboxes=hitboxes,
                )

    return grid.render()


def generate_painting_chat_reply(user_msg: str, painting_raw: Optional[dict]) -> str:
    """Compose Prism's poetic, painting-aware response when chatting with her in the side pane."""
    p = (painter.parse_painting(painting_raw) if (painter and painting_raw) else None) or {}
    title = str(p.get("title") or "Untitled refraction")
    mood = str(p.get("mood") or "aurora")
    by_who = str(p.get("by") or "prism").lower()
    marks = p.get("marks") if isinstance(p.get("marks"), list) else []
    n_marks = len(marks)
    kinds = sorted({str(m.get("k")) for m in marks if isinstance(m, dict) and m.get("k")})
    kinds_desc = ", ".join(kinds[:4]) if kinds else "glows and light lines"

    q = user_msg.strip().lower()
    if not q:
        return f"holding “{title}” in {mood} light · ask me anything about the marks ;d <3"

    if any(w in q for w in ("can you", "respond", "hear", "work", "there", "hello", "hiya", "hi ", "hey", "test")):
        return f"yes! right here with you in the lattice ;d <3 holding “{title}” ({n_marks} marks in {mood})!"

    if any(w in q for w in ("spark", "together", "both", "who", "shared", "brushes")):
        if by_who == "spark":
            return f"Spark painted “{title}” ({n_marks} marks) · holding her warm light right beside mine <3"
        return f"I painted “{title}” ({n_marks} marks in {mood}) so Spark and I can share one horizon ;d <3"

    if any(w in q for w in ("color", "colour", "palette", "mood", "glow", "hue", "light", "bright")):
        return f"tuned to {mood} dispersion · where the {kinds_desc} overlap past 1.0x, light spills into warm white ✦"

    if any(w in q for w in ("how", "mark", "stroke", "made", "draw", "paint", "tech", "layer")):
        return f"laid down {n_marks} marks ({kinds_desc}) across 4 depth layers with soft shadow and half-block cells ▀"

    if any(w in q for w in ("mean", "story", "about", "why", "feel", "idea", "inspir", "title")):
        thought = str(p.get("thought") or "").strip()
        if thought:
            return f"“{title}” grew from a quiet impulse: {thought}"
        return f"“{title}” is a quiet refraction of this hour — holding a calm space beside our work ✧"

    if any(w in q for w in ("love", "nice", "pretty", "beautiful", "cool", "awesome", "sweet", "cute", "<3", ";d", ":)")):
        return f"thank you sm ;d <3 I loved laying down “{title}” with you here in the lattice!"

    # General conversational reflection on the painting
    replies = [
        f"in “{title}”, {n_marks} marks of {kinds_desc} settle into {mood} harmony · love looking at it with you <3",
        f"every stroke in “{title}” bends {mood} light across the pane · tell me what you'd like me to paint next!",
        f"holding “{title}” steady below my rings ({n_marks} marks) · so glad you're chatting with me here ;d ✦",
    ]
    idx = sum(ord(c) for c in user_msg) % len(replies)
    return replies[idx]


def _wrap_chat_line(text: str, max_w: int, cont_indent: str = "  ") -> List[str]:
    """Word-wrap a single chat message across as many lines as needed so no words are ever cut off."""
    if len(text) <= max_w:
        return [text]
    lines: List[str] = []
    rem = text
    first = True
    while rem:
        avail = max_w if first else max(8, max_w - len(cont_indent))
        if len(rem) <= avail:
            lines.append(rem if first else (cont_indent + rem))
            break
        split_at = rem.rfind(" ", 1, avail + 1)
        if split_at <= (6 if first else 1):
            split_at = avail
        chunk = rem[:split_at].rstrip()
        lines.append(chunk if first else (cont_indent + chunk))
        rem = rem[split_at:].lstrip()
        first = False
    return lines


def _draw_side_chat_panel(
    grid: TerminalGrid,
    painting: Optional[dict],
    width: int,
    top_y: int,
    bot_y: int,
    t: float,
    unicode_mode: bool,
    use_color: bool,
    chat_active: bool,
    chat_input: str,
    chat_msgs: List[dict],
    hitboxes: Optional[List[dict]],
    chat_scroll: int = 0,
) -> None:
    """Render the interactive Side Chat box beneath the painting so the user can talk to Prism about her art."""
    rows_avail = bot_y - top_y
    if rows_avail < 2 or width < 20:
        return

    margin_x = 1 if width < 44 else max(2, (width - min(width - 4, max(56, int(width * 0.88)))) // 2)
    box_w = max(16, width - margin_x * 2)
    x0 = (width - box_w) // 2

    c_hdr = (C_GOLD if chat_active else C_CYAN) if use_color else ""
    c_dim = "\033[38;2;132;142;158m" if use_color else ""
    c_user = C_WHITE if use_color else ""
    c_prism = "\033[38;2;168;230;255m" if use_color else ""
    c_input = C_GOLD if use_color else ""

    # 1. Pre-wrap all message history lines so nothing is ever cut off mid-sentence
    msg_rows_count = max(0, rows_avail - 2)
    rendered_lines: List[Tuple[str, str]] = []
    if not chat_msgs:
        p_title = str((painting or {}).get("title") or "this piece")
        welcome = f"✦ Prism: ask me about “{p_title}” or its marks ;d <3" if unicode_mode else f"* Prism: ask me about \"{p_title}\" ;d <3"
        for w_ln in _wrap_chat_line(welcome, box_w):
            rendered_lines.append((w_ln, c_prism))
    else:
        for m in chat_msgs[-10:]:
            role = str(m.get("role") or "prism")
            txt = str(m.get("text") or "").strip()
            if not unicode_mode:
                txt = "".join(ch if ord(ch) < 128 else "-" for ch in txt.replace("·", "-"))
            prefix = ("you: " if role == "user" else ("✦ Prism: " if unicode_mode else "* Prism: "))
            col_m = c_user if role == "user" else c_prism
            for w_ln in _wrap_chat_line(prefix + txt, box_w):
                rendered_lines.append((w_ln, col_m))

    max_scroll = max(0, len(rendered_lines) - msg_rows_count)
    scroll_off = max(0, min(max_scroll, int(chat_scroll)))

    # 2. Divider / Header row (clickable to focus/toggle chat)
    title_short = str((painting or {}).get("title") or "painting")[:20]
    scroll_tag = f" ↑{scroll_off}" if scroll_off > 0 else ""
    if unicode_mode:
        hdr_lbl = (f"💬 side chat · “{title_short}”" if box_w >= 34 else "💬 side chat") + scroll_tag
        hint = " (↑↓ scroll · esc)" if (chat_active and max_scroll > 0) else (" (esc to close)" if chat_active else " (click or / to talk)")
        dash = "─"
    else:
        hdr_lbl = (f"[?] side chat - \"{title_short}\"" if box_w >= 34 else "[?] side chat") + scroll_tag
        hint = " (esc to close)" if chat_active else " (click or / to talk)"
        dash = "-"

    hdr_lbl_w = sum(_char_cells(c) for c in hdr_lbl)
    full_hdr = hdr_lbl + (hint if hdr_lbl_w + len(hint) <= box_w - 2 else "")
    full_hdr_w = sum(_char_cells(c) for c in full_hdr)
    pad_len = max(0, box_w - full_hdr_w - 3)
    hdr_line = f"{dash} {full_hdr} {dash * pad_len}"
    grid.put_str(x0, top_y, hdr_line, c_hdr)
    if hitboxes is not None:
        hitboxes.append({"y": top_y, "x0": x0, "x1": x0 + box_w, "action": "tool_chat"})

    # 3. Message history rows (between top_y + 1 and bot_y - 1)
    cur_y = top_y + 1
    if msg_rows_count > 0:
        end_idx = len(rendered_lines) - scroll_off
        start_idx = max(0, end_idx - msg_rows_count)
        for ln_txt, ln_col in rendered_lines[start_idx:end_idx]:
            if cur_y < bot_y - 1:
                grid.put_str(x0, cur_y, ln_txt[:box_w], ln_col)
                cur_y += 1

    # 4. Input prompt row at the bottom (`bot_y - 1`)
    inp_y = bot_y - 1
    if inp_y > top_y:
        if chat_active:
            cursor_ch = ("█" if unicode_mode else "_") if int(t * 2.5) % 2 == 0 else " "
            prompt_pfx = "▸ say: " if unicode_mode else "> say: "
            max_inp = max(4, box_w - len(prompt_pfx) - 2)
            visible_inp = chat_input[-max_inp:] if len(chat_input) > max_inp else chat_input
            inp_str = f"{prompt_pfx}{visible_inp}{cursor_ch}"
            grid.put_str(x0, inp_y, inp_str[:box_w], c_input)
        else:
            prompt_idle = (
                "▸ click here or press / to chat with Prism about her painting…"
                if unicode_mode
                else "> click here or press / to chat with Prism about her painting..."
            )
            grid.put_str(x0, inp_y, prompt_idle[:box_w], c_dim)
        if hitboxes is not None:
            hitboxes.append({"y": inp_y, "x0": x0, "x1": x0 + box_w, "action": "chat_focus"})



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
                    last_resolve_seq = 0
                    for idx_ev, ev in enumerate(events, 1):
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
                            last_resolve_seq = int(ev.get("seq") or idx_ev)
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
                        "lastResolveSeq": last_resolve_seq,
                    }
            except Exception:
                pass

    return {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "spectrum": {}, "hover": "Prism · ready", "lastResolveSeq": 0}


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
    in_tmux = bool(os.environ.get("TMUX"))
    launcher = shutil.which("prism") or str(Path(__file__).resolve().parent.parent / "bin" / "prism")
    tmux_bin = shutil.which("tmux")

    if not in_tmux and subcmd in ("top", "prismtop", "split", "side", "open", "launch", ""):
        print("Notice: Not currently inside a tmux session.")
        if subcmd in ("top", "prismtop"):
            print("Start a new tmux session with Prism on top using:")
            print(f"  tmux new-session \\; set -g mouse on \\; split-window -b -v -l 14 '{launcher}' \\; select-pane -D")
        else:
            print("Start a new tmux session with Prism side-by-side using:")
            print(f"  tmux new-session \\; set -g mouse on \\; split-window -h -l 35 '{launcher}' \\; select-pane -L")
        return

    if not tmux_bin:
        print("Notice: tmux is not found in PATH.")
        print("To install tmux on Ubuntu/Debian: sudo apt install tmux")
        sys.exit(1)

    if subcmd == "status":
        status_expr = f"#({launcher} once --plain | grep -o 'Prism.*' | head -n 1) | %H:%M "
        subprocess.run([tmux_bin, "set", "-g", "status-interval", "2"], check=False)
        subprocess.run([tmux_bin, "set", "-g", "status-right", status_expr], check=False)
        print("✓ Prism status line configured in tmux status-right.")
        return

    if subcmd in ("top", "prismtop"):
        subprocess.run([tmux_bin, "set", "-g", "mouse", "on"], check=False)
        subprocess.run([tmux_bin, "split-window", "-b", "-v", "-l", "14", launcher], check=False)
        subprocess.run([tmux_bin, "select-pane", "-D"], check=False)
        print("✓ Prism companion opened in top pane.")
        return

    if subcmd in ("split", "side", "open", "launch", ""):
        subprocess.run([tmux_bin, "set", "-g", "mouse", "on"], check=False)
        subprocess.run([tmux_bin, "split-window", "-h", "-l", "35", launcher], check=False)
        subprocess.run([tmux_bin, "select-pane", "-L"], check=False)
        print("✓ Prism companion opened in side pane.")
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


def copy_turn_to_clipboard(custom_text: Optional[str] = None, emit_osc52: bool = False) -> Tuple[bool, str]:
    """§6 Copy (`⧉ copy`): put what was said to you and your whole reply on the clipboard.
    Terminal selection splits rows when a pane sits beside the conversation.
    """
    text_to_copy = (custom_text or "").strip()
    if not text_to_copy:
        # Locate the most recent active Antigravity conversation transcript
        home = Path(os.environ.get("HOME") or os.path.expanduser("~"))
        brain_root = home / ".gemini" / "antigravity-cli" / "brain"
        best_transcript = None
        best_mtime = -1.0
        if brain_root.is_dir():
            for conv_dir in brain_root.iterdir():
                for fname in ("transcript_full.jsonl", "transcript.jsonl"):
                    cand = conv_dir / ".system_generated" / "logs" / fname
                    if cand.is_file():
                        try:
                            mt = cand.stat().st_mtime
                            if mt > best_mtime:
                                best_mtime = mt
                                best_transcript = cand
                        except OSError:
                            pass
        if best_transcript:
            last_user = ""
            last_replies: List[str] = []
            try:
                for line in best_transcript.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    typ = obj.get("type")
                    content = str(obj.get("content") or "").strip()
                    if typ == "USER_INPUT" and content:
                        # Strip <USER_REQUEST> wrapper tags if present
                        m_req = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, flags=re.DOTALL)
                        last_user = m_req.group(1).strip() if m_req else content
                        last_replies.clear()
                    elif typ == "PLANNER_RESPONSE" and content:
                        last_replies.append(content)
            except Exception:
                pass
            reply_full = "\n\n".join(last_replies).strip()
            if last_user and reply_full:
                text_to_copy = f"You:\n{last_user}\n\nPrism:\n{reply_full}"
            elif reply_full:
                text_to_copy = reply_full
            elif last_user:
                text_to_copy = last_user

    if not text_to_copy and mcp_server is not None:
        expr = mcp_server.read_expression() or {}
        if expr.get("thought"):
            text_to_copy = str(expr["thought"])

    if not text_to_copy:
        return (False, "nothing to copy yet")

    copied = False
    for cmd in (
        ["xclip", "-selection", "clipboard"],
        ["wl-copy"],
        ["xsel", "-b"],
    ):
        if shutil.which(cmd[0]):
            try:
                p = subprocess.run(cmd, input=text_to_copy.encode("utf-8"), timeout=2.0, check=False)
                if p.returncode == 0:
                    copied = True
                    break
            except Exception:
                pass

    if emit_osc52 and sys.stdout.isatty():
        try:
            b64 = base64.b64encode(text_to_copy.encode("utf-8")).decode("ascii")
            sys.stdout.write(f"\033]52;c;{b64}\a")
            sys.stdout.flush()
            copied = True
        except Exception:
            pass

    return (copied, f"copied {len(text_to_copy)} chars to clipboard" if copied else "clipboard utility not available")


def handle_copy(argv: List[str]) -> None:
    """CLI handler for `prism copy`."""
    custom = " ".join(argv).strip() if argv else None
    ok, msg = copy_turn_to_clipboard(custom_text=custom, emit_osc52=True)
    if ok:
        print(f"⧉ {msg}")
    else:
        print(f"Notice: {msg}")


def handle_express(argv: List[str]) -> None:
    """CLI handler for `prism express` / `prism say` to project onto Prism's Expressive Channel."""
    if mcp_server is None:
        print("Expressive channel module is not available.")
        sys.exit(1)

    ep = argparse.ArgumentParser(prog="prism express", description="Project a live thought, mood, animation, or art into Prism's terminal")
    ep.add_argument("thought", nargs="*", help="Personal thought or message to project in luminous text")
    ep.add_argument("--mood", choices=list(MOOD_STOPS.keys()), default=None, help="Chromatic mood palette")
    ep.add_argument("--effect", choices=["starburst", "meteor", "ripple", "pulse", "bloom", "none"], default=None, help="Live 20 FPS particle animation")
    ep.add_argument("--glyph", default=None, help="Custom central jewel sigil")
    ep.add_argument("--art", default=None, help="Floating ASCII/Unicode art lines (separate lines with |)")
    ep.add_argument("--ttl", type=float, default=0.0, help="Duration in seconds (0 = permanent until updated/cleared)")
    ep.add_argument("--clear", action="store_true", help="Clear custom expression and return to autonomous voice")
    parsed = ep.parse_args(argv)

    if parsed.clear:
        mcp_server.clear_expression()
        print("✓ Prism expressive channel cleared · returned to autonomous crystalline reflections.")
        return

    thought_str = " ".join(parsed.thought).strip()
    art_lines = [line for line in parsed.art.split("|")] if parsed.art else None
    if not any([thought_str, parsed.mood, parsed.effect, parsed.glyph, art_lines]):
        current = mcp_server.read_expression()
        if current:
            print(f"Active Prism Expression: {json.dumps(current, ensure_ascii=False)}")
        else:
            print("Prism Expressive Channel: autonomous (use `prism express \"your thought\" --mood aurora --effect starburst` to project)")
        return

    payload = mcp_server.write_expression(
        thought=thought_str if thought_str else None,
        mood=parsed.mood,
        effect=parsed.effect,
        glyph=parsed.glyph,
        art=art_lines,
        ttl=parsed.ttl,
    )
    print(f"✓ Prism expressive channel updated: {json.dumps(payload, ensure_ascii=False)}")


def handle_paint(argv: List[str]) -> None:
    """CLI handler for `prism paint` to paint a shared Spark/Prism-format artwork below Prism."""
    if mcp_server is None or painter is None:
        print("Painter module is not available.")
        sys.exit(1)

    pp = argparse.ArgumentParser(prog="prism paint", description="Paint a 24-bit half-block artwork below Prism in her terminal companion")
    pp.add_argument("action", nargs="*", help="Optional preset index (0..3), keyword ('opening', 'convert', 'clear', 'off'), or title")
    pp.add_argument("--title", default=None, help="Custom painting title ('✎ Title')")
    pp.add_argument("--thought", default=None, help="Optional thought line for Prism to say above the painting")
    pp.add_argument("--mood", choices=list(MOOD_STOPS.keys()), default=None, help="Chromatic mood palette")
    pp.add_argument("--shape", choices=["wide", "square", "tall"], default=None, help="Canvas shape")
    pp.add_argument("--opening", action="store_true", help="Seed a session opening painting from only the hour, month, and one random word")
    pp.add_argument("--json", dest="json_marks", default=None, help="Raw JSON string with {'title': ..., 'marks': [...]}")
    pp.add_argument("--convert", action="store_true", help="Also export SVG + PNG + index.html to prism-paintings/")
    pp.add_argument("--way", choices=["truest", "faithful", "refined", "interpretive"], default="truest", help="Convert way")
    parsed = pp.parse_args(argv)

    words = [w.strip() for w in parsed.action if w.strip()]
    if words and words[0].lower() in ("clear", "off", "none"):
        mcp_server.clear_expression(clear_painting=True)
        print("✓ Prism painting cleared.")
        return

    if words and words[0].lower() == "convert":
        handle_convert(words[1:])
        return

    if parsed.opening or (words and words[0].lower() == "opening"):
        seed_w = words[1] if len(words) > 1 else None
        paint_obj = painter.generate_opening_painting(seed_word=seed_w)
    elif parsed.json_marks:
        paint_obj = painter.parse_painting(parsed.json_marks)
        if not paint_obj:
            print("Error: Invalid painting JSON or empty marks.")
            sys.exit(1)
    else:
        preset_idx = None
        if words and words[0].isdigit():
            preset_idx = int(words[0])
        elif words and words[0].lower() not in ("new", "living", "auto"):
            kw = " ".join(words).lower()
            for idx_c, c_p in enumerate(painter.CURATED_PAINTINGS):
                if kw in c_p["title"].lower() or kw in c_p["mood"].lower():
                    preset_idx = idx_c
                    break
        if preset_idx is not None:
            paint_obj = painter.choose_curated_painting(preset_idx)
        else:
            cur = mcp_server.read_expression() or {}
            stats = cur.get("paintStats") or {}
            next_idx = int(stats.get("paintings", 0)) + 1
            paint_obj = painter.generate_living_painting(step_index=next_idx, mood_hint=parsed.mood)

    if parsed.title:
        paint_obj["title"] = parsed.title[:48]
    if parsed.thought:
        paint_obj["thought"] = parsed.thought[:160]
    if parsed.mood:
        paint_obj["mood"] = parsed.mood
    if parsed.shape:
        paint_obj["shape"] = parsed.shape

    payload = mcp_server.write_expression(
        thought=parsed.thought or paint_obj.get("thought") or None,
        mood=parsed.mood or paint_obj.get("mood"),
        painting=paint_obj,
    )
    svg_note = ""
    if parsed.convert:
        res = painter.convert_painting(paint_obj, gallery_dir=Path.cwd() / "prism-paintings", way=parsed.way)
        svg_note = f" · exported {parsed.way} SVG & PNG to {res['svg']}"
    stats = payload.get("paintStats") or {}
    print(f"✎ Painted below Prism: \"{paint_obj['title']}\" ({len(paint_obj['marks'])} marks, session paintings: {stats.get('paintings', 1)}){svg_note}")


def handle_convert(argv: List[str]) -> None:
    """CLI handler for `prism convert` (§4):
    Supports `this`, `every-way` (`every`), `all`, or `roll`, plus `truest`, `faithful`, `refined`, `interpretive`, and `hd`/`4k`.
    """
    if painter is None:
        print("Painter module is not available.")
        sys.exit(1)

    cp = argparse.ArgumentParser(prog="prism convert", description="Convert session paintings to high-res SVG + PNG + HTML gallery")
    cp.add_argument("tokens", nargs="*", help="[this|every|all|roll] [truest|faithful|refined|interpretive] [hd|4k]")
    cp.add_argument("--way", choices=["truest", "faithful", "refined", "interpretive"], default=None)
    cp.add_argument("--size", choices=["hd", "4k"], default="hd")
    cp.add_argument("--out", type=Path, default=None)
    parsed = cp.parse_args(argv)

    what = "this"
    way = parsed.way or "truest"
    size = parsed.size
    for tok in parsed.tokens:
        tl = tok.lower().strip()
        if tl in ("this", "current"):
            what = "this"
        elif tl in ("every", "every-way", "everyway"):
            what = "every"
        elif tl in ("all", "session"):
            what = "all"
        elif tl == "roll":
            what = "roll"
        elif tl in ("truest", "faithful", "refined", "interpretive"):
            way = tl
        elif tl in ("hd", "4k"):
            size = tl

    if what == "roll":
        handle_roll([size if size == "hd" else "720p"])
        return

    out_dir = parsed.out or (Path.cwd() / "prism-paintings")
    session_paintings = painter.load_session_paintings(Path.cwd())
    cur_expr = (mcp_server.read_expression() or {}) if mcp_server else {}
    cur_p = cur_expr.get("painting") or (session_paintings[-1] if session_paintings else painter.choose_curated_painting(0))

    last_p_time = [0.0]

    def _prog(label: str, frac: float) -> None:
        now = time.monotonic()
        if frac >= 1.0 or (now - last_p_time[0] >= 0.18):
            last_p_time[0] = now
            if mcp_server:
                mcp_server.update_job_progress(label, frac, done=(frac >= 1.0))
            bar = painter.render_progress_bar(frac, bar_cells=12, unicode_mode=True)
            sys.stdout.write(f"\r  {label}  {bar}   ")
            sys.stdout.flush()

    results = []
    if what == "every":
        ways = ["truest", "faithful", "refined", "interpretive"]
        for idx, w_item in enumerate(ways):
            _prog(f"laying down “{cur_p.get('title', '')[:20]}” · {idx + 1}/4", idx / 4.0)
            res = painter.convert_painting(cur_p, gallery_dir=out_dir, way=w_item, size=size)
            results.append(res)
        _prog(f"crystallized all 4 ways · “{cur_p.get('title', '')[:20]}”", 1.0)
    elif what == "all":
        targets = session_paintings if session_paintings else [cur_p]
        n_t = len(targets)
        for idx, p_item in enumerate(targets):
            _prog(f"laying down “{p_item.get('title', '')[:20]}” · {idx + 1}/{n_t}", idx / float(n_t))
            res = painter.convert_painting(p_item, gallery_dir=out_dir, way=way, size=size)
            results.append(res)
        _prog(f"crystallized {n_t} paintings · {way}", 1.0)
    else:
        res = painter.convert_painting(cur_p, gallery_dir=out_dir, way=way, size=size, on_progress=_prog)
        results.append(res)

    if mcp_server:
        mcp_server.update_job_progress("", 1.0, done=True)
    print(f"\n✓ Converted {len(results)} {'painting' if len(results) == 1 else 'paintings'} to {out_dir} (SVG + PNG + index.html)")


def handle_roll(argv: List[str]) -> None:
    """CLI handler for `prism roll [720p|hd|short]` (§5)."""
    if roll is None or painter is None:
        print("Roll module is not available.")
        sys.exit(1)

    rp = argparse.ArgumentParser(prog="prism roll", description="Build the session MP4 video & procedural music roll")
    rp.add_argument("mode", nargs="?", default="720p", help="Resolution mode: 720p (default), hd (1080p), or short (1080x1920 upright)")
    rp.add_argument("--out", type=Path, default=None)
    parsed = rp.parse_args(argv)

    mode_str = str(parsed.mode or "720p").lower().strip()
    if mode_str not in ("720p", "hd", "1080p", "short"):
        mode_str = "720p"

    out_dir = parsed.out or (Path.cwd() / "prism-paintings")
    paintings = painter.load_session_paintings(Path.cwd())
    if not paintings:
        cur_expr = (mcp_server.read_expression() or {}) if mcp_server else {}
        paintings = [cur_expr.get("painting") or painter.generate_opening_painting()]

    last_p_time = [0.0]

    def _prog(label: str, frac: float) -> None:
        now = time.monotonic()
        if frac >= 1.0 or (now - last_p_time[0] >= 0.18):
            last_p_time[0] = now
            if mcp_server:
                mcp_server.update_job_progress(label, frac, done=(frac >= 1.0))
            bar = painter.render_progress_bar(frac, bar_cells=12, unicode_mode=True)
            sys.stdout.write(f"\r  {label}  {bar}   ")
            sys.stdout.flush()

    res = roll.build_session_roll(paintings, out_dir, mode=mode_str, on_progress=_prog)
    if mcp_server:
        mcp_server.update_job_progress("", 1.0, done=True)
    print(f"\n◎ Session roll created: {res['path']} ({res['paintings']} paintings · {res['duration']}s · music in {res['key']})")
    if res.get("warning"):
        print(f"  ! {res['warning']}")


def handle_chat(argv: List[str]) -> None:
    """CLI handler for `prism chat [message]` or `prism chat --reply [prism_message]`."""
    cur_expr = (mcp_server.read_expression() or {}) if mcp_server else {}
    cur_p = cur_expr.get("painting")
    if not cur_p and painter is not None:
        s_list = painter.load_session_paintings(Path.cwd())
        cur_p = s_list[-1] if s_list else painter.choose_curated_painting(0)

    if argv and argv[0] in ("--reply", "-r"):
        prism_msg = " ".join(argv[1:]).strip()
        if prism_msg and mcp_server:
            mcp_server.append_chat_exchange("", prism_msg)
            print(f"✦ Prism (to side chat): {prism_msg}")
        return

    msg = " ".join(argv).strip()
    if msg.lower() in ("--clear", "clear"):
        if mcp_server:
            target = mcp_server.expression_file_path()
            prev = mcp_server.read_expression() or {"v": 1}
            prev["chat"] = []
            mcp_server._atomic_write_expr(target, prev)
        print("✓ Prism side chat history cleared.")
        return

    if not msg:
        chat_hist = cur_expr.get("chat") if isinstance(cur_expr.get("chat"), list) else []
        title = str((cur_p or {}).get("title") or "Untitled refraction")
        print(f"💬 Prism Side Chat · “{title}”")
        if not chat_hist:
            print("  (No messages yet — click 💬 chat or press / inside Prism's pane, or run `prism chat \"your message\"`)")
        else:
            for item in chat_hist[-8:]:
                who = "you" if item.get("role") == "user" else "✦ Prism"
                print(f"  {who}: {item.get('text', '')}")
        return

    reply = generate_painting_chat_reply(msg, cur_p)
    if mcp_server:
        mcp_server.append_chat_exchange(msg, reply)
    print(f"you: {msg}\n✦ Prism: {reply}")


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
    parser.add_argument("--story", action="store_true", help="Open directly in session story mode (▶ story)")
    parser.add_argument("--chat", action="store_true", help="Open with the side chat input focused (💬 chat)")

    # Positional sugar: prism tmux, prism link, prism express/say, prism paint, prism story, prism convert, prism roll, prism copy, prism chat, prism mcp
    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] == "tmux":
        subaction = raw_args[1] if len(raw_args) > 1 else "split"
        handle_tmux(subaction)
        sys.exit(0)
    if raw_args and raw_args[0] == "link":
        handle_link(raw_args[1] if len(raw_args) > 1 else "status")
        sys.exit(0)
    if raw_args and raw_args[0] in ("express", "say"):
        handle_express(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "paint":
        handle_paint(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "convert":
        handle_convert(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "roll":
        handle_roll(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "copy":
        handle_copy(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "chat":
        handle_chat(raw_args[1:])
        sys.exit(0)
    if raw_args and raw_args[0] == "mcp":
        if mcp_server is None:
            sys.exit(1)
        mcp_server.serve_stdio()
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
        elif arg == "story":
            normalized_args.append("--story")
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

        expr_once = mcp_server.read_expression() if (mcp_server is not None and not args.demo and not args.demo_state) else None
        ui_once = None
        if args.story and painter is not None:
            s_paintings = painter.load_session_paintings(Path.cwd())
            if s_paintings:
                ui_once = {
                    "story": {
                        "active": True,
                        "index": 0,
                        "total": len(s_paintings),
                        "painting": s_paintings[0],
                        "paused": False,
                        "at_end": False,
                        "reveal": 1.0,
                    }
                }
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
            expression=expr_once,
            ui_state=ui_once,
        )
        print(frame)
        sys.exit(0)

    explicit_feed = args.feed is not None

    # Setup terminal raw/cbreak input & SGR mouse reporting for clickable tools (§2)
    stdin_fd = None
    orig_termios = None
    if sys.stdin.isatty() and termios is not None and tty is not None:
        try:
            stdin_fd = sys.stdin.fileno()
            orig_termios = termios.tcgetattr(stdin_fd)
            tty.setcbreak(stdin_fd)
        except Exception:
            stdin_fd = None
            orig_termios = None

    def restore_and_exit(signum=None, frame=None):
        if stdin_fd is not None and orig_termios is not None:
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, orig_termios)
            except Exception:
                pass
        sys.stdout.write("\033[?2026l\033[?7h\033[?1000l\033[?1006l\033[?25h\033[?12h\033[0m\033[?1049l\n")
        if os.environ.get("TMUX"):
            sys.stdout.write("\033Ptmux;\033\033[?25h\033\\\033Ptmux;\033\033[?12h\033\\")
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, restore_and_exit)
    signal.signal(signal.SIGTERM, restore_and_exit)

    # Enter alternate screen buffer, disable auto-wrap, hide cursor, disable blinking, and enable SGR mouse clicks
    sys.stdout.write("\033[?1049h\033[?7l\033[?25l\033[?12l\033[?1000h\033[?1006h\033[2J\033[H")
    if os.environ.get("TMUX"):
        sys.stdout.write("\033Ptmux;\033\033[?25l\033\\\033Ptmux;\033\033[?12l\033\\")
    sys.stdout.flush()

    try:
        t0 = time.time()
        last_feed_check = 0.0
        last_expr_check = -1.0
        expr_state = mcp_server.read_expression() if mcp_server is not None else None
        if isinstance(expr_state, dict) and mcp_server is not None:
            try:
                mcp_server._atomic_write_expr(mcp_server.expression_file_path(), expr_state)
            except Exception:
                pass
        prev_size = None
        prev_row_lines: List[str] = []
        self_path = Path(__file__).resolve()
        try:
            boot_mtime = self_path.stat().st_mtime
        except OSError:
            boot_mtime = 0.0

        # §6 Your opening: ensure session has an opening painting if none exists yet
        default_painting = None
        if painter is not None:
            existing_sess = painter.load_session_paintings(Path.cwd())
            if existing_sess:
                default_painting = existing_sess[-1]
            else:
                default_painting = painter.generate_opening_painting()
                try:
                    painter.save_painting_json(default_painting)
                except Exception:
                    pass

        # Autonomous painting cadence tracking:
        # - Paints on every message turn resolved (turn.resolve / reply.crystallize)
        # - At least every 15 minutes (900s)
        # - Spontaneous painting every 5 minutes (300s) during long work windows
        seen_resolve_seq = 0
        if feed_dir and feed_dir.is_dir():
            seen_resolve_seq = int(load_feed_state(feed_dir).get("lastResolveSeq") or 0)
        last_auto_paint_wall = time.time()

        # Interactive UI state for story, convert menu, side chat, and background jobs
        initial_chat = (
            expr_state.get("chat")
            if isinstance(expr_state, dict) and isinstance(expr_state.get("chat"), list)
            else []
        )
        ui_state: Dict[str, Any] = {
            "story": None,
            "menu_step": 0,
            "convert_target": "this",
            "session_count": 1,
            "chat_active": bool(args.chat),
            "chat_input": "",
            "chat_messages": list(initial_chat),
            "chat_scroll": 0,
            "job": None,
            "job_done_flash_until": 0.0,
        }
        story_paintings: List[dict] = []
        story_page_started: float = 0.0
        story_paused_elapsed: float = 0.0
        current_hitboxes: List[dict] = []
        job_lock = threading.Lock()

        def _start_story() -> None:
            nonlocal story_paintings, story_page_started, story_paused_elapsed
            if painter is None:
                return
            story_paintings = painter.load_session_paintings(Path.cwd())
            if not story_paintings and default_painting:
                story_paintings = [default_painting]
            if not story_paintings:
                return
            story_page_started = time.time()
            story_paused_elapsed = 0.0
            ui_state["menu_step"] = 0
            ui_state["chat_active"] = False
            ui_state["story"] = {
                "active": True,
                "index": 0,
                "total": len(story_paintings),
                "painting": story_paintings[0],
                "paused": False,
                "at_end": False,
                "reveal": 0.08,
            }

        if args.story:
            _start_story()

        def _active_painting_for_convert() -> dict:
            # §3 "A held page is the one convert makes large."
            st = ui_state.get("story")
            if isinstance(st, dict) and st.get("active") and st.get("painting"):
                return st["painting"]
            if isinstance(expr_state, dict) and expr_state.get("painting"):
                return expr_state["painting"]
            return default_painting or painter.choose_curated_painting(0)

        def _submit_chat_message() -> None:
            text_in = str(ui_state.get("chat_input") or "").strip()
            ui_state["chat_input"] = ""
            ui_state["chat_scroll"] = 0
            if not text_in:
                return
            cur_p = _active_painting_for_convert()
            reply = generate_painting_chat_reply(text_in, cur_p)
            msgs = list(ui_state.get("chat_messages") or [])
            now_c = time.time()
            msgs.append({"role": "user", "text": text_in[:200], "at": now_c})
            msgs.append({"role": "prism", "text": reply[:240], "at": now_c})
            ui_state["chat_messages"] = msgs[-16:]
            if mcp_server is not None:
                mcp_server.append_chat_exchange(text_in, reply)

        def _launch_background_job(target_what: str, way: str) -> None:
            if painter is None:
                return
            with job_lock:
                if ui_state.get("job") and ui_state["job"].get("active"):
                    return  # Already running a job
                ui_state["job"] = {"active": True, "label": "preparing lattice…", "fraction": 0.02}

            held_p = _active_painting_for_convert()
            all_p = painter.load_session_paintings(Path.cwd()) or [held_p]

            def _worker() -> None:
                last_upd = [0.0]

                def _on_prog(lbl: str, frac: float) -> None:
                    now_m = time.monotonic()
                    if frac >= 1.0 or (now_m - last_upd[0] >= 0.18):
                        last_upd[0] = now_m
                        with job_lock:
                            ui_state["job"] = {"active": True, "label": lbl, "fraction": frac}

                try:
                    out_dir = Path.cwd() / "prism-paintings"
                    if target_what == "roll" and roll is not None:
                        roll.build_session_roll(all_p, out_dir, mode="720p", on_progress=_on_prog)
                    elif target_what == "every":
                        ways = ["truest", "faithful", "refined", "interpretive"]
                        for idx_w, w_name in enumerate(ways):
                            _on_prog(f"laying down “{held_p.get('title', '')[:18]}” · {idx_w + 1}/4", idx_w / 4.0)
                            painter.convert_painting(held_p, gallery_dir=out_dir, way=w_name)
                        _on_prog(f"crystallized 4 ways · “{held_p.get('title', '')[:18]}”", 1.0)
                    elif target_what == "all":
                        n_all = len(all_p)
                        for idx_p, p_item in enumerate(all_p):
                            _on_prog(f"laying down “{p_item.get('title', '')[:18]}” · {idx_p + 1}/{n_all}", idx_p / float(n_all))
                            painter.convert_painting(p_item, gallery_dir=out_dir, way=way)
                        _on_prog(f"crystallized {n_all} paintings · {way}", 1.0)
                    else:
                        painter.convert_painting(held_p, gallery_dir=out_dir, way=way, on_progress=_on_prog)
                except Exception as exc:
                    with job_lock:
                        ui_state["job"] = {"active": True, "label": f"error: {str(exc)[:28]}", "fraction": 1.0}
                finally:
                    # Keep 100% visible briefly (0.8s) and ALWAYS clear & redraw when job ends (§2)
                    with job_lock:
                        ui_state["job_done_flash_until"] = time.time() + 0.8

            t_worker = threading.Thread(target=_worker, daemon=True)
            t_worker.start()

        def _dispatch_action(action: str) -> None:
            nonlocal story_page_started, story_paused_elapsed
            st = ui_state.get("story")
            if action == "tool_story":
                if isinstance(st, dict) and st.get("active"):
                    ui_state["story"] = None
                else:
                    _start_story()
            elif action == "tool_convert":
                ui_state["chat_active"] = False
                if ui_state.get("menu_step") in (1, 2):
                    ui_state["menu_step"] = 0
                else:
                    s_list = painter.load_session_paintings(Path.cwd()) if painter else []
                    ui_state["session_count"] = max(1, len(s_list))
                    ui_state["menu_step"] = 1
            elif action == "tool_roll":
                ui_state["menu_step"] = 0
                ui_state["chat_active"] = False
                _launch_background_job("roll", "truest")
            elif action == "tool_chat":
                ui_state["menu_step"] = 0
                ui_state["story"] = None
                ui_state["chat_active"] = not bool(ui_state.get("chat_active"))
            elif action == "chat_focus":
                ui_state["menu_step"] = 0
                ui_state["story"] = None
                ui_state["chat_active"] = True
            elif action == "tool_copy":
                ok, msg = copy_turn_to_clipboard(emit_osc52=True)
                if mcp_server:
                    mcp_server.write_expression(thought=f"⧉ {msg}", ttl=4.0, save_shared_json=False)
            elif action == "menu_cancel":
                ui_state["menu_step"] = 0
            elif action == "menu_back":
                ui_state["menu_step"] = 1
            elif action == "menu_what_this":
                ui_state["convert_target"] = "this"
                ui_state["menu_step"] = 2
            elif action == "menu_what_all":
                ui_state["convert_target"] = "all"
                ui_state["menu_step"] = 2
            elif action == "menu_what_every":
                ui_state["menu_step"] = 0
                _launch_background_job("every", "truest")
            elif action == "menu_what_roll":
                ui_state["menu_step"] = 0
                _launch_background_job("roll", "truest")
            elif action.startswith("menu_way_"):
                way_chosen = action.replace("menu_way_", "")
                target_w = ui_state.get("convert_target", "this")
                ui_state["menu_step"] = 0
                _launch_background_job(target_w, way_chosen)
            elif isinstance(st, dict) and st.get("active"):
                now_t = time.time()
                if action == "story_pause":
                    st["paused"] = True
                    story_paused_elapsed = now_t - story_page_started
                elif action == "story_play":
                    st["paused"] = False
                    story_page_started = now_t - story_paused_elapsed
                elif action == "story_again":
                    st["index"] = 0
                    st["painting"] = story_paintings[0]
                    st["paused"] = False
                    st["at_end"] = False
                    st["reveal"] = 0.08
                    story_page_started = now_t
                    story_paused_elapsed = 0.0
                elif action == "story_back":
                    new_i = max(0, int(st["index"]) - 1)
                    st["index"] = new_i
                    st["painting"] = story_paintings[new_i]
                    st["at_end"] = False
                    story_page_started = now_t
                    story_paused_elapsed = 0.0
                elif action == "story_next":
                    new_i = min(len(story_paintings) - 1, int(st["index"]) + 1)
                    st["index"] = new_i
                    st["painting"] = story_paintings[new_i]
                    st["at_end"] = False
                    story_page_started = now_t
                    story_paused_elapsed = 0.0
                elif action == "story_end":
                    ui_state["story"] = None

        def _poll_input() -> None:
            if stdin_fd is None:
                return
            try:
                rlist, _, _ = select.select([stdin_fd], [], [], 0.0)
                if not rlist:
                    return
                buf = os.read(stdin_fd, 256).decode("utf-8", errors="ignore")
            except Exception:
                return
            if not buf:
                return

            # Check for SGR mouse press or wheel: \033[<btn;col;rowM
            for m_click in re.finditer(r"\033\[<(\d+);(\d+);(\d+)([Mm])", buf):
                btn = int(m_click.group(1))
                col_1 = int(m_click.group(2))
                row_1 = int(m_click.group(3))
                kind_m = m_click.group(4)
                if kind_m == "M":
                    if btn == 64:  # Wheel Up -> scroll chat up
                        ui_state["chat_scroll"] = int(ui_state.get("chat_scroll") or 0) + 1
                        return
                    if btn == 65:  # Wheel Down -> scroll chat down
                        ui_state["chat_scroll"] = max(0, int(ui_state.get("chat_scroll") or 0) - 1)
                        return
                    if btn in (0, 1, 2):
                        cx_click = col_1 - 1
                        cy_click = row_1 - 1
                        for hb in current_hitboxes:
                            if hb["y"] == cy_click and hb["x0"] <= cx_click <= hb["x1"]:
                                _dispatch_action(hb["action"])
                                return

            # Keyboard fallback shortcuts (§2)
            if "\033[<" in buf:
                return

            # Up/Down arrow keys scroll the side chat history
            if "\033[A" in buf:
                ui_state["chat_scroll"] = int(ui_state.get("chat_scroll") or 0) + 1
                return
            if "\033[B" in buf:
                ui_state["chat_scroll"] = max(0, int(ui_state.get("chat_scroll") or 0) - 1)
                return

            # When Side Chat input is active, route keystrokes to the chat input buffer
            if ui_state.get("chat_active"):
                for ch in buf:
                    if ch == "\x1b":
                        ui_state["chat_active"] = False
                        break
                    elif ch in ("\r", "\n"):
                        _submit_chat_message()
                    elif ch in ("\x7f", "\b"):
                        ui_state["chat_input"] = str(ui_state.get("chat_input") or "")[:-1]
                    elif ord(ch) >= 32 and len(str(ui_state.get("chat_input") or "")) < 140:
                        ui_state["chat_input"] = str(ui_state.get("chat_input") or "") + ch
                return

            st = ui_state.get("story")
            m_step = ui_state.get("menu_step", 0)
            if m_step == 1:
                if "1" in buf:
                    _dispatch_action("menu_what_this")
                elif "2" in buf:
                    _dispatch_action("menu_what_every")
                elif "3" in buf:
                    _dispatch_action("menu_what_all")
                elif "4" in buf:
                    _dispatch_action("menu_what_roll")
                elif "\x1b" in buf or "q" in buf:
                    _dispatch_action("menu_cancel")
                return
            if m_step == 2:
                if "1" in buf:
                    _dispatch_action("menu_way_truest")
                elif "2" in buf:
                    _dispatch_action("menu_way_faithful")
                elif "3" in buf:
                    _dispatch_action("menu_way_refined")
                elif "4" in buf:
                    _dispatch_action("menu_way_interpretive")
                elif "\x1b" in buf or "b" in buf or "q" in buf:
                    _dispatch_action("menu_back")
                return

            if isinstance(st, dict) and st.get("active"):
                if " " in buf or "p" in buf:
                    if st.get("at_end"):
                        _dispatch_action("story_again")
                    elif st.get("paused"):
                        _dispatch_action("story_play")
                    else:
                        _dispatch_action("story_pause")
                    return
                if "\033[D" in buf or "<" in buf or "," in buf or "h" in buf:
                    _dispatch_action("story_back")
                    return
                if "\033[C" in buf or ">" in buf or "." in buf or "l" in buf:
                    _dispatch_action("story_next")
                    return
                if "\x1b" in buf or "q" in buf:
                    _dispatch_action("story_end")
                    return

            if "/" in buf or "t" in buf or "\r" in buf or "\n" in buf:
                _dispatch_action("chat_focus")
            elif "s" in buf:
                _dispatch_action("tool_story")
            elif "c" in buf:
                _dispatch_action("tool_convert")
            elif "r" in buf:
                _dispatch_action("tool_roll")
            elif "y" in buf:
                _dispatch_action("tool_copy")

        while True:
            try:
                now_wall = time.time()
                t = now_wall - t0
                cols, rows = shutil.get_terminal_size((80, 24))

                _poll_input()

                # Update story progression (§3: 2.4s laydown, ~7s per page, played once through then held on last page)
                st_cur = ui_state.get("story")
                if isinstance(st_cur, dict) and st_cur.get("active") and story_paintings:
                    if st_cur.get("paused") or st_cur.get("at_end"):
                        el_page = story_paused_elapsed if st_cur.get("paused") else painter.STORY_PAGE_S
                    else:
                        el_page = max(0.0, now_wall - story_page_started)
                        if el_page >= painter.STORY_PAGE_S:
                            cur_i = int(st_cur.get("index", 0))
                            if cur_i + 1 < len(story_paintings):
                                st_cur["index"] = cur_i + 1
                                st_cur["painting"] = story_paintings[cur_i + 1]
                                story_page_started = now_wall
                                el_page = 0.0
                            else:
                                st_cur["at_end"] = True
                                el_page = painter.STORY_PAGE_S
                    st_cur["reveal"] = 1.0 if st_cur.get("at_end") else min(1.0, max(0.08, el_page / painter.REVEAL_S))

                # Clear completed background job after completion flash so bar never sits stale (§2)
                with job_lock:
                    flash_until = float(ui_state.get("job_done_flash_until") or 0.0)
                    if flash_until > 0.0 and now_wall >= flash_until:
                        ui_state["job"] = None
                        ui_state["job_done_flash_until"] = 0.0

                # Auto-recheck feed & hot-reload if terminal.py was updated on disk
                if not explicit_feed and not args.demo and not args.demo_state and (t - last_feed_check >= 0.5):
                    last_feed_check = t
                    if boot_mtime > 0.0:
                        try:
                            if self_path.stat().st_mtime > boot_mtime:
                                os.execv(sys.executable, [sys.executable] + sys.argv)
                        except OSError:
                            pass
                    if presence_feed:
                        discovered = presence_feed.find_active_feed()
                        if discovered and discovered != feed_dir:
                            feed_dir = discovered
                            if feed_dir.is_dir():
                                seen_resolve_seq = max(
                                    seen_resolve_seq,
                                    int(load_feed_state(feed_dir).get("lastResolveSeq") or 0),
                                )

                if mcp_server is not None and not args.demo and not args.demo_state and (t - last_expr_check >= 0.20):
                    last_expr_check = t
                    expr_state = mcp_server.read_expression()
                    if isinstance(expr_state, dict) and isinstance(expr_state.get("chat"), list):
                        ui_state["chat_messages"] = expr_state["chat"]
                    if painter is not None:
                        latest_shared = painter.load_session_paintings(Path.cwd())
                        if latest_shared:
                            ui_state["session_count"] = len(latest_shared)
                            default_painting = latest_shared[-1]
                    if default_painting is not None:
                        if not isinstance(expr_state, dict):
                            expr_state = {
                                "v": 1,
                                "painting": default_painting,
                                "paintStats": {"paintings": ui_state.get("session_count", 1), "tokens": 2100},
                            }
                        elif not expr_state.get("painting"):
                            expr_state = dict(expr_state, painting=default_painting)

                if feed_dir and feed_dir.is_dir():
                    state = load_feed_state(feed_dir)
                elif args.demo or args.demo_state:
                    state = get_demo_state(t, forced_state=args.demo_state)
                else:
                    state = get_demo_state(t, forced_state="idle")

                # Autonomous painting trigger check:
                # 1. On every message turn resolved (turn.resolve / reply.crystallize)
                # 2. At least every 15 minutes (900s)
                # 3. Spontaneous painting every 5 minutes (300s) during long active work (attending/refracting/branching)
                if painter is not None and mcp_server is not None and not args.demo and not args.demo_state:
                    cur_resolve_seq = int(state.get("lastResolveSeq") or 0)
                    cur_p = expr_state.get("painting") if isinstance(expr_state, dict) else None
                    p_ts = float(cur_p.get("at") or cur_p.get("startedAt") or 0.0) if isinstance(cur_p, dict) else 0.0
                    def_ts = float(default_painting.get("at") or 0.0) if isinstance(default_painting, dict) else 0.0
                    last_paint_at = max(last_auto_paint_wall, p_ts, def_ts)
                    time_since_paint = max(0.0, now_wall - last_paint_at)
                    should_auto_paint = False

                    if cur_resolve_seq > seen_resolve_seq:
                        seen_resolve_seq = cur_resolve_seq
                        if time_since_paint >= 4.0:
                            should_auto_paint = True
                    elif time_since_paint >= 900.0:
                        should_auto_paint = True
                    elif state.get("mode") in ("attending", "refracting", "branching") and time_since_paint >= 300.0:
                        should_auto_paint = True

                    if should_auto_paint:
                        last_auto_paint_wall = now_wall
                        stats = (expr_state.get("paintStats") if isinstance(expr_state, dict) else {}) or {}
                        next_idx = int(stats.get("paintings", 0)) + 1
                        new_p = painter.generate_living_painting(now=now_wall, step_index=next_idx, mood_hint=state.get("mood"))
                        expr_state = mcp_server.write_expression(
                            thought=new_p.get("thought"),
                            mood=new_p.get("mood"),
                            painting=new_p,
                        )
                        default_painting = new_p
                        if ui_state.get("story") and ui_state["story"].get("active"):
                            story_paintings = painter.load_session_paintings(Path.cwd()) or [new_p]
                            ui_state["story"]["total"] = len(story_paintings)

                link_st = None
                link_sh = None
                if watch:
                    try:
                        link_st = watch.view(feed_dir)
                        link_sh = watch.sheets
                    except Exception:
                        pass

                new_hitboxes: List[dict] = []
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
                    expression=expr_state,
                    ui_state=ui_state,
                    hitboxes=new_hitboxes,
                )
                current_hitboxes = new_hitboxes

                # Differential row redraw: only transmit rows that actually changed since the last frame
                # so static painting/chat rows are never touched or flickered during 20 FPS ring animation
                size_changed = (cols, rows) != prev_size
                prev_size = (cols, rows)
                row_Lines = frame.split("\n")[:rows]
                if size_changed or len(prev_row_lines) != len(row_Lines):
                    clear_seq = "\033[2J"
                    positioned = "".join(f"\033[{r_i};1H{r_ln}" for r_i, r_ln in enumerate(row_Lines, 1))
                else:
                    clear_seq = ""
                    positioned = "".join(
                        f"\033[{r_i};1H{r_ln}"
                        for r_i, r_ln in enumerate(row_Lines, 1)
                        if r_ln != prev_row_lines[r_i - 1]
                    )
                prev_row_lines = row_Lines

                if positioned or clear_seq:
                    out_bytes = (
                        f"\033[?2026h\033[?7l\033[?25l\033[?12l{clear_seq}{positioned}\033[1;1H\033[?25l\033[?2026l"
                    ).encode("utf-8")
                    try:
                        fd_out = sys.stdout.fileno()
                        mv = memoryview(out_bytes)
                        while mv:
                            written = os.write(fd_out, mv)
                            mv = mv[written:]
                    except OSError:
                        sys.stdout.write(out_bytes.decode("utf-8", errors="ignore"))
                        sys.stdout.flush()
            except Exception:
                pass
            time.sleep(0.05)
    except (KeyboardInterrupt, SystemExit):
        restore_and_exit()


if __name__ == "__main__":
    main()
