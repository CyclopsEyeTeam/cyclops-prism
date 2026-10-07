#!/usr/bin/env python3
"""link_view.py - what Prism shows of the other presences when Cyclops Link is on.

Prism never draws Spark or Keeper herself. Each of them exported her own small look from
her own renderer (link-mark/spark.json, link-mark/keeper.json, vendored here with their
SOURCE note); Prism places that look at the peer's seat in the canonical triangle and
draws the handoff threads their own records declare. Nothing here reads anything but
the Link records (state, counts, reaching) and those mark sheets.

Seats (SPEC §11): Prism sees Spark to the lower left (240 deg) and Keeper to the lower right (300 deg).
"""

import json
import math
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

import link

ROOT = Path(__file__).resolve().parent.parent
MARKS = ROOT / "link-mark"
MAX_SHEET_BYTES = 256 * 1024
NAMES = {"spark": "Spark", "keeper": "Keeper", "prism": "Prism"}


# ---------------------------------------------------------------- mark sheets (display only)

def _rgb(v: Any) -> Optional[Tuple[int, int, int]]:
    if v is None:
        return None
    if (isinstance(v, list) and len(v) == 3 and all(isinstance(c, int) and not isinstance(c, bool)
                                                       and 0 <= c <= 255 for c in v)):
        return (v[0], v[1], v[2])
    raise ValueError("colour")


def load_sheet(presence: str, directory: Path = MARKS) -> Optional[Dict[str, Any]]:
    """A peer's own mark sheet, validated; None when it is missing or malformed (then no mark is invented)."""
    path = directory / f"{presence}.json"
    try:
        if path.is_symlink() or path.stat().st_size > MAX_SHEET_BYTES:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("v") != 1 or raw.get("presence") != presence:
            return None
        cols, rows = raw["cols"], raw["rows"]
        if not (isinstance(cols, int) and isinstance(rows, int) and 0 < cols <= 64 and 0 < rows <= 32):
            return None
        frames = {}
        for state, grid in raw["frames"].items():
            if state not in link.STATES or len(grid) != rows:
                return None
            out = []
            for row in grid:
                if len(row) != cols:
                    return None
                out.append([(c[0] if isinstance(c[0], str) and len(c[0]) == 1 else " ", _rgb(c[1]), _rgb(c[2]))
                            for c in row])
            frames[state] = out
        if "idle" not in frames:
            return None
        states_map = {k: v for k, v in (raw.get("states_map") or {}).items()
                      if k in link.STATES and v in frames}
        ascii_frames = {}
        for state, lines in (raw.get("ascii") or {}).items():
            if state in frames and isinstance(lines, list) and len(lines) == rows:
                ascii_frames[state] = [str(line)[:cols].ljust(cols) for line in lines]
        core = raw.get("core")
        if not (isinstance(core, list) and len(core) == 4 and all(isinstance(v, int) for v in core)
                and 0 <= core[0] < core[2] <= cols and 0 <= core[1] < core[3] <= rows):
            core = None
        return {"presence": presence, "cols": cols, "rows": rows, "frames": frames,
                "states_map": states_map, "ascii": ascii_frames, "core": core}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        return None


def frame_for(sheet: Dict[str, Any], state: str) -> str:
    """The frame a peer's sheet names for a Link state (its own mapping), else her idle look."""
    if state in sheet["frames"]:
        return state
    mapped = sheet["states_map"].get(state)
    return mapped if mapped in sheet["frames"] else "idle"


def accent(sheet: Dict[str, Any]) -> Tuple[int, int, int]:
    """The brightest colour in the peer's own idle look: her threads carry it."""
    best, score = (200, 200, 200), -1
    for row in sheet["frames"]["idle"]:
        for _, fg, _ in row:
            if fg and sum(fg) > score:
                best, score = fg, sum(fg)
    return best


def _sgr(fg: Optional[Tuple[int, int, int]], bg: Optional[Tuple[int, int, int]] = None, dim: float = 1.0) -> str:
    s = ""
    if fg:
        s += "\033[38;2;%d;%d;%dm" % tuple(int(c * dim) for c in fg)
    if bg:
        s += "\033[48;2;%d;%d;%dm" % tuple(int(c * dim) for c in bg)
    return s


# ---------------------------------------------------------------- reading the room

class Watch:
    """Prism's Link reader for her terminal: off unless she is linked, at most one poll a second."""

    def __init__(self, environ: Optional[Dict[str, str]] = None):
        self.environ = os.environ if environ is None else environ
        self.reader = link.Reader(self.environ)
        self.checked = -1e9
        self.on = False
        self.sheets = {p: load_sheet(p) for p in ("spark", "keeper")}

    def view(self, feed_dir: Optional[Path], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        mono = time.monotonic()
        if mono - self.checked >= 1.0:
            self.checked = mono
            self.on = link.enabled(self.environ)
        if not self.on:
            return None
        now = time.time() if now is None else now
        records = self.reader.poll(mono)
        if self.reader.salt is None:
            return {"peers": [], "threads": []}
        # Prism's own session: the feed she is showing lives at <root>/<session>/prism
        session = feed_dir.parent.name if feed_dir and feed_dir.name == "prism" else None
        own = None
        if session:
            mine = self.reader.own_instance(session)
            own = next((r for r in records if r["presence"] == "prism" and r["instance"] == mine), None)
        if own is None:
            try:
                folder = os.path.realpath(os.getcwd())
            except OSError:
                return {"peers": [], "threads": []}
            own = {"presence": "prism", "instance": "0" * 16, "room": self.reader.own_room(folder),
                   "reaching": [], "ended": False}
        return link.compose(own, records, now)


# ---------------------------------------------------------------- drawing into Prism's grid

def _blank(grid, x: int, y: int) -> bool:
    return 0 <= y < grid.height and 0 <= x < grid.width and grid.chars[y][x] == " "


def _stamp(grid, sheet, state: str, x0: int, y0: int, *, unicode_mode: bool, use_color: bool,
           crop: Optional[List[int]] = None) -> None:
    name = frame_for(sheet, state)
    rows = sheet["frames"][name]
    cx0, cy0, cx1, cy1 = crop or (0, 0, sheet["cols"], sheet["rows"])
    ascii_rows = sheet["ascii"].get(name)
    for yy in range(cy0, cy1):
        for xx in range(cx0, cx1):
            ch, fg, bg = rows[yy][xx]
            if not unicode_mode:
                ch = ascii_rows[yy][xx] if ascii_rows else ("." if ch != " " else " ")
                bg = None
            if ch == " " and not bg:
                continue
            grid.put(x0 + xx - cx0, y0 + yy - cy0, ch, _sgr(fg, bg) if use_color else "")


def _path(a: Tuple[float, float], b: Tuple[float, float]) -> List[Tuple[int, int]]:
    n = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1]) * 2)))
    pts, seen = [], set()
    for i in range(n + 1):
        u = i / n
        p = (round(a[0] + (b[0] - a[0]) * u), round(a[1] + (b[1] - a[1]) * u))
        if p not in seen:
            seen.add(p)
            pts.append(p)
    return pts


def _thread(grid, a, b, colour, *, t: float, unicode_mode: bool, use_color: bool, reduced_motion: bool,
            solid=frozenset()) -> None:
    """A handoff thread from a to b: a dotted strand on empty cells, and a bead that travels a -> b."""
    pts = [p for p in _path(a, b) if _blank(grid, *p) and p not in solid]
    if not pts:
        return
    dot, bead = ("·", "•") if unicode_mode else (".", "o")
    dim = _sgr(colour, dim=0.55) if use_color else ""
    for x, y in pts[::1]:
        grid.put(x, y, dot, dim)
    if not reduced_motion:
        x, y = pts[int((t * 6.0) % len(pts))]
        grid.put(x, y, bead, _sgr(colour) if use_color else "")


def draw(grid, view: Optional[Dict[str, Any]], sheets: Dict[str, Optional[Dict[str, Any]]], *,
         centre: Tuple[int, int], hud_y: int, t: float = 0.0, unicode_mode: bool = True,
         use_color: bool = True, reduced_motion: bool = False) -> Dict[str, Tuple[float, float]]:
    """Place each present peer's own mark at her seat and draw the threads the records declare.

    Returns the anchor (centre cell) of every presence drawn, Prism's own included.
    """
    anchors: Dict[str, Tuple[float, float]] = {"prism": (centre[0], centre[1])}
    if not view or not view["peers"]:
        return anchors
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for peer in view["peers"]:
        by_class.setdefault(peer["presence"], []).append(peer)
    width = grid.width
    solid = set()
    for presence, peers in sorted(by_class.items()):
        if presence == "prism":
            continue
        b = peer_bearing(presence)
        if b is None:
            continue
        side = 1 if 90 < b < 270 else -1   # 1: her seat is to Prism's left
        first = peers[0]
        label = f"{NAMES.get(presence, presence).lower()} · {first['state']}" + (f" ×{len(peers)}" if len(peers) > 1 else "")
        sheet = sheets.get(presence)
        if sheet:
            crop = None
            cols, rows = sheet["cols"], sheet["rows"]
            if cols > width // 2 - 1 and sheet.get("core"):
                crop = sheet["core"]
                cols, rows = crop[2] - crop[0], crop[3] - crop[1]
            y0 = max(1, hud_y - rows)
            x0 = 1 if side > 0 else width - cols - 1
            _stamp(grid, sheet, first["state"], x0, y0, unicode_mode=unicode_mode, use_color=use_color, crop=crop)
            anchors[presence] = (x0 + cols / 2, y0 + rows / 2)
            label_y, mark_w, mark_x = y0 - 1, cols, x0
            colour = accent(sheet)
        else:
            # No sheet from her: her name only, never an invented look
            y0 = max(1, hud_y - 1)
            name = NAMES.get(presence, presence.title())
            x0 = 1 if side > 0 else width - len(name) - 1
            grid.put_str(x0, y0, name, "\033[38;2;200;200;200m" if use_color else "")
            anchors[presence] = (x0 + len(name) / 2, y0)
            label_y, mark_w, mark_x = y0 - 1, len(name), x0
            colour = (200, 200, 200)
        text = label if unicode_mode else label.replace("·", "-").replace("×", "x")
        lx = mark_x if side > 0 else max(0, mark_x + mark_w - len(text))
        text = text[: max(0, width - lx)]
        grid.put_str(lx, label_y, text, _sgr(colour, dim=0.8) if use_color else "")
        solid.update((lx + i, label_y) for i in range(len(text)))   # no thread runs through a label's gaps
    for th in view["threads"]:
        a, b = anchors.get(th["from"]), anchors.get(th["to"])
        if a and b:
            src = sheets.get(th["from"])
            colour = accent(src) if src else (0, 242, 254)
            _thread(grid, a, b, colour, t=t, unicode_mode=unicode_mode, use_color=use_color,
                    reduced_motion=reduced_motion, solid=solid)
    return anchors


def peer_bearing(presence: str) -> Optional[int]:
    return link.bearing("prism", presence)


def status(view: Optional[Dict[str, Any]]) -> str:
    """One truthful line for Prism's focus telemetry."""
    if view is None:
        return "Link: off"
    peers = [p for p in view["peers"] if p["presence"] != "prism"]
    if not peers:
        return "Link: on · alone here"
    names = sorted({NAMES.get(p["presence"], p["presence"].title()) for p in peers})
    return "Link: on · " + ", ".join(names)
