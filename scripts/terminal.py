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

KIND_COLOR_MAP = {
    "inspect": C_CYAN,
    "change": C_GOLD,
    "execute": C_VIOLET,
    "service": C_TEAL,
    "other": C_AMBER,
}


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
    hover = state_data.get("hover", "Prism · ready")

    # Glyph sets
    if unicode_mode:
        g_core = "⟐"
        if ended:
            g_core = "·"
        elif sem_mode == "approval":
            g_core = "!"
        elif offer:
            g_core = "✦"
        elif sem_mode == "synthesizing":
            g_core = "◈"
        elif sem_mode == "refracting":
            g_core = "❖"
        elif sem_mode == "branching":
            g_core = "◇"

        g_sat = "◆"
        g_ring1 = "╱"
        g_ring2 = "╲"
        g_node = "○"
    else:
        g_core = "." if ended else ("!" if sem_mode == "approval" else ("*" if offer else "o"))
        g_sat = "#"
        g_ring1 = "/"
        g_ring2 = "\\"
        g_node = "o"

    # Mode colors
    if sem_mode == "approval":
        core_col = C_RED
        ring1_col = C_GOLD
        ring2_col = C_RED
    elif offer:
        core_col = C_WHITE
        ring1_col = C_CYAN
        ring2_col = C_WHITE
    elif sem_mode == "halted":
        core_col = C_DARK
        ring1_col = C_DIM
        ring2_col = C_DIM
    elif ended:
        core_col = C_DARK
        ring1_col = C_DARK
        ring2_col = C_DARK
    else:
        core_col = C_CYAN
        ring1_col = C_CYAN
        ring2_col = C_VIOLET

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

    # Animation angle
    speed = 0.0 if (reduced_motion or ended) else (0.4 if calm else 0.8)
    theta = t * speed

    # 1. Outer Polarized Rings
    for i in range(steps):
        phi = (i / steps) * (2.0 * math.pi)
        # Ring 1
        rx1 = cx + int(math.cos(phi + theta) * ring_radius_x)
        ry1 = cy + int(math.sin(phi + theta) * ring_radius_y * 0.7 - math.cos(phi + theta) * 1.5)
        grid.put(rx1, ry1, g_ring1, ring1_col)

        # Ring 2 (counter-angle)
        rx2 = cx + int(math.cos(phi - theta) * ring_radius_x)
        ry2 = cy + int(math.sin(phi - theta) * ring_radius_y * 0.7 + math.cos(phi - theta) * 1.5)
        grid.put(rx2, ry2, g_ring2, ring2_col)

    # 2. Refraction rays for active calls
    if lanes:
        for idx, lane in enumerate(lanes[:6]):
            kind = lane.get("kind", "other")
            col = KIND_COLOR_MAP.get(kind, C_CYAN)
            side = 1 if (idx % 2 == 0) else -1
            row_offset = (idx // 2) - 1
            max_reach = max(8, (width // 2) - len(kind) - 4)
            reach = min(ring_radius_x + 6, max_reach) * side
            tx = cx + reach
            ty = cy + row_offset * 2

            # Ray connector
            dash = "─" if unicode_mode else "-"
            start_x = cx + (side * 4)
            for x_pos in range(min(start_x, tx), max(start_x, tx) + 1):
                grid.put(x_pos, ty, dash, col)
            grid.put(tx, ty, g_node, col)
            grid.put_str(tx + (1 if side > 0 else -len(kind) - 1), ty, f"[{kind}]", col)

    # 3. Subagent branch satellites
    if active_branches > 0:
        for b_idx in range(min(4, active_branches)):
            b_angle = (theta * 0.8) + (b_idx * math.pi / 2.0)
            bx = cx + int(math.cos(b_angle) * (ring_radius_x + 3))
            by = cy + int(math.sin(b_angle) * (ring_radius_y + 2))
            grid.put(bx, by, g_sat, C_VIOLET)

    # 4. Central Faceted Core
    if ring_radius_x >= 24 and ring_radius_y >= 9 and height >= 28:
        core_level = 3
    elif ring_radius_x >= 16 and ring_radius_y >= 6 and height >= 20:
        core_level = 2
    else:
        core_level = 1

    clear_w = 7 if core_level == 3 else (5 if core_level == 2 else 3)
    clear_h = 4 if core_level == 3 else (3 if core_level == 2 else 2)
    for dy in range(-clear_h, clear_h + 1):
        for dx in range(-clear_w, clear_w + 1):
            if (abs(dx) / (clear_w + 0.1) + abs(dy) / (clear_h + 0.1)) <= 1.05:
                grid.put(cx + dx, cy + dy, " ", C_RESET)

    # Core facets
    if unicode_mode:
        up, dn = "▲", "▼"
        lb, rb = "⟨", "⟩"
        sl, bs = "╱", "╲"
    else:
        up, dn = "^", "v"
        lb, rb = "<", ">"
        sl, bs = "/", "\\"

    if core_level == 3:
        # Apex facets
        grid.put(cx, cy - 3, up, core_col)
        grid.put(cx, cy + 3, dn, core_col)
        # Outer faceted crown
        grid.put(cx - 2, cy - 2, sl, core_col)
        grid.put(cx + 2, cy - 2, bs, core_col)
        grid.put(cx - 4, cy - 1, sl, core_col)
        grid.put(cx + 4, cy - 1, bs, core_col)
        grid.put(cx - 6, cy, lb, core_col)
        grid.put(cx + 6, cy, rb, core_col)
        grid.put(cx - 4, cy + 1, bs, core_col)
        grid.put(cx + 4, cy + 1, sl, core_col)
        grid.put(cx - 2, cy + 2, bs, core_col)
        grid.put(cx + 2, cy + 2, sl, core_col)
        # Inner facets
        grid.put(cx, cy - 1, up, core_col)
        grid.put(cx, cy + 1, dn, core_col)
        grid.put(cx - 2, cy, lb, core_col)
        grid.put(cx + 2, cy, rb, core_col)
        grid.put(cx, cy, g_core, C_WHITE if offer else core_col)
    elif core_level == 2:
        grid.put(cx, cy - 2, up, core_col)
        grid.put(cx, cy + 2, dn, core_col)
        grid.put(cx - 2, cy - 1, sl, core_col)
        grid.put(cx + 2, cy - 1, bs, core_col)
        grid.put(cx - 4, cy, lb, core_col)
        grid.put(cx + 4, cy, rb, core_col)
        grid.put(cx - 2, cy + 1, bs, core_col)
        grid.put(cx + 2, cy + 1, sl, core_col)
        grid.put(cx, cy, g_core, C_WHITE if offer else core_col)
    else:
        grid.put(cx - 2, cy, lb, core_col)
        grid.put(cx + 2, cy, rb, core_col)
        grid.put(cx, cy - 1, up, core_col)
        grid.put(cx, cy + 1, dn, core_col)
        grid.put(cx, cy, g_core, C_WHITE if offer else core_col)

    # 5. Cyclops Link: Spark and Keeper in their own looks at their seats, and the threads they declare
    hud_y = height - 2
    if link_state is not None and link_view is not None:
        link_view.draw(grid, link_state, link_sheets or {}, centre=(cx, cy), hud_y=hud_y, t=t,
                       unicode_mode=unicode_mode, use_color=use_color, reduced_motion=reduced_motion or ended)

    # 6. Status Banner
    display_hover = hover if unicode_mode else hover.replace("·", "-")
    status_bar = f" {g_core}  {display_hover} "
    grid.put_str(max(1, (width - len(status_bar)) // 2), hud_y, status_bar, core_col)

    if is_focus:
        sub_info = f"Calls: {active_calls}  Branches: {active_branches}  Offer: {offer or 'none'}  Comp: {mode}"
        if link_state is not None and link_view is not None:
            sub_info += "  " + link_view.status(link_state)
        grid.put_str(max(1, (width - len(sub_info)) // 2), hud_y + 1, sub_info, C_DIM)

    return grid.render()


def load_feed_state(feed_dir: Path) -> dict:
    """Read latest state from live.json or fallback to durable.json."""
    if not feed_dir or not feed_dir.is_dir():
        return {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "hover": "Prism · ready"}

    for filename in ["live.json", "durable.json"]:
        p = feed_dir / filename
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                events = data.get("events", [])
                if isinstance(events, list) and events:
                    active_calls = []
                    active_branches = 0
                    offer = None
                    latest = events[-1]
                    typ = latest.get("type", "turn.attend")

                    for ev in events:
                        t_name = ev.get("type")
                        if t_name == "refract.start":
                            active_calls.append({"kind": ev.get("kind", "inspect")})
                        elif t_name in ("refract.resolve", "refract.halt") and active_calls:
                            active_calls.pop()
                        elif t_name == "branch.start":
                            active_branches += 1
                        elif t_name == "branch.resolve" and active_branches > 0:
                            active_branches -= 1
                        # the reply is held out from its turn's resolve until a new turn, a halt, a copy or a wake
                        if t_name in ("turn.resolve", "reply.crystallize"):
                            offer = "crystallize"
                        elif t_name in ("session.wake", "turn.attend", "turn.halt", "reply.copied"):
                            offer = None

                    if typ == "session.end":
                        sem_mode = "ended"
                    elif typ == "approval.request":
                        sem_mode = "approval"
                    elif active_calls:
                        sem_mode = "refracting"
                    elif active_branches:
                        sem_mode = "branching"
                    elif typ in ("reply.crystallize", "turn.resolve"):
                        sem_mode = "resolved"
                    elif typ == "turn.halt":
                        sem_mode = "halted"
                    else:
                        sem_mode = "attending" if typ == "turn.attend" else "idle"

                    if sem_mode == "idle":
                        hover_text = "Prism · ready"
                    else:
                        hover_text = f"Prism · {sem_mode}"
                    if sem_mode == "refracting" and active_calls:
                        kinds = sorted({c["kind"] for c in active_calls})
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
                        "activeCalls": len(active_calls),
                        "activeBranches": active_branches,
                        "lanes": active_calls,
                        "hover": hover_text,
                    }
            except Exception:
                pass

    return {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "hover": "Prism · ready"}


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
            subprocess.run([tmux_bin, "split-window", "-b", "-v", "-l", "14", launcher], check=False)
            subprocess.run([tmux_bin, "select-pane", "-D"], check=False)
            print("✓ Prism companion opened in top pane.")
        else:
            print("Notice: Not currently inside a tmux session.")
            print("Start a new tmux session with Prism on top using:")
            print(f"  tmux new-session \\; split-window -b -v -l 14 '{launcher}' \\; select-pane -D")
        return

    if subcmd in ("split", "side", "open", "launch", ""):
        if in_tmux:
            subprocess.run([tmux_bin, "split-window", "-h", "-l", "35", launcher], check=False)
            subprocess.run([tmux_bin, "select-pane", "-L"], check=False)
            print("✓ Prism companion opened in side pane.")
        else:
            print("Notice: Not currently inside a tmux session.")
            print("Start a new tmux session with Prism side-by-side using:")
            print(f"  tmux new-session \\; split-window -h -l 35 '{launcher}' \\; select-pane -L")
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
    for arg in raw_args:
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
    if not feed_dir and not args.demo and not args.demo_state and presence_feed:
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

    # Interactive live animation loop
    def restore_and_exit(signum=None, frame=None):
        sys.stdout.write("\033[?25h\033[0m\033[?1049l\n")  # Show cursor, reset color, exit alternate screen
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, restore_and_exit)
    signal.signal(signal.SIGTERM, restore_and_exit)

    # Enter alternate screen buffer & hide cursor
    sys.stdout.write("\033[?1049h\033[?25l\033[2J\033[H")
    sys.stdout.flush()

    try:
        t0 = time.time()
        prev_size = None
        while True:
            t = time.time() - t0
            cols, rows = shutil.get_terminal_size((80, 24))

            # Auto-recheck feed if none was found initially
            if not feed_dir and not args.demo and not args.demo_state and presence_feed and int(t) % 2 == 0:
                feed_dir = presence_feed.find_active_feed()

            if feed_dir and feed_dir.is_dir():
                state = load_feed_state(feed_dir)
            elif args.demo or args.demo_state:
                state = get_demo_state(t, forced_state=args.demo_state)
            else:
                state = get_demo_state(t, forced_state="idle")

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
                link_state=watch.view(feed_dir) if watch else None,
                link_sheets=watch.sheets if watch else None,
            )

            # Atomic synchronized redraw with cursor hide & cursor park
            clear_seq = "\033[2J" if (cols, rows) != prev_size else ""
            prev_size = (cols, rows)

            # \033[?2026h: Begin synchronized update (atomic frame render)
            # \033[?25l: Re-assert cursor hide
            # \033[H: Cursor home
            # frame: Artwork
            # \033[1;1H: Park cursor at top-left
            # \033[?2026l: End synchronized update
            sys.stdout.write(f"\033[?2026h\033[?25l{clear_seq}\033[H{frame}\033[1;1H\033[?2026l")
            sys.stdout.flush()
            time.sleep(0.05)
    except (KeyboardInterrupt, SystemExit):
        restore_and_exit()


if __name__ == "__main__":
    main()
