#!/usr/bin/env python3
"""Prism's Cyclops Link mark sheet: Prism's own crystalline form, drawn by her own terminal
renderer (scripts/terminal.py render_prism_frame), small, one frame per Link state.

Other presences carry a copy of link-mark/prism.json and place it at Prism's seat;
they never draw Prism themselves.
    python3 tools/export-link-mark.py        writes link-mark/prism.json
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
from terminal import render_prism_frame  # noqa: E402  Prism's own renderer

WIDTH, HEIGHT = 26, 10          # the smallest canvas her renderer draws whole (rings need 23 columns)
BANNER_ROWS = 2                 # her status banner and the row under it are not part of the mark

def state(mode, offer=None, calls=0, branches=0, ended=False):
    return {"mode": mode, "offer": offer, "activeCalls": calls, "activeBranches": branches,
            "lanes": [], "ended": ended, "hover": ""}

# Link state -> Prism's own composition for it.
STATES = {
    "idle": state("idle"),
    "working": state("attending"),
    "tool": state("refracting", calls=1),
    "waiting": state("approval", calls=1),
    "stopped": state("resolved", offer="crystallize"),
    "interrupted": state("halted"),
    "ended": state("ended", ended=True),
}
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def cells(name):
    text = render_prism_frame(STATES[name], WIDTH, HEIGHT, t=0.0, mode="balanced",
                              unicode_mode=True, use_color=True, reduced_motion=True)
    grid = []
    for line in text.split("\n"):
        row, fg, i = [], None, 0
        while i < len(line):
            m = SGR.match(line, i)
            if m:
                codes = m.group(1).split(";")
                fg = [int(v) for v in codes[2:5]] if codes[:2] == ["38", "2"] else None
                i = m.end()
                continue
            ch = line[i]
            row.append([ch, fg if ch != " " else None, None])
            i += 1
        grid.append(row)
    return grid[:HEIGHT - BANNER_ROWS]


def crop(all_frames):
    """Trim the blank margin every frame shares, so the sheet is only Prism."""
    inked = [(x, y) for f in all_frames.values() for y, row in enumerate(f)
             for x, c in enumerate(row) if c[0] != " "]
    x0, x1 = min(x for x, _ in inked), max(x for x, _ in inked) + 1
    y0, y1 = min(y for _, y in inked), max(y for _, y in inked) + 1
    return {n: [row[x0:x1] for row in f[y0:y1]] for n, f in all_frames.items()}


frames = crop({name: cells(name) for name in STATES})
COLS, ROWS = len(frames["idle"][0]), len(frames["idle"])
# Where hosts with little room may cut: the faceted core alone (the column of the core glyph +-3).
mid = next(x for x, c in enumerate(frames["idle"][ROWS // 2]) if c[0] == "⟐")
CORE = [mid - 3, ROWS // 2 - 1, mid + 4, ROWS // 2 + 2]
ascii_frames = {name: ["".join("." if c[0] != " " else " " for c in row) for row in frames[name]]
                for name in frames}
sheet = {
    "v": 1, "presence": "prism", "cols": COLS, "rows": ROWS, "core": CORE,
    "note": "Prism's own crystalline form, rendered by her own terminal renderer (scripts/terminal.py). "
            "A host draws it at Prism's seat; it never redraws Prism itself.",
    "core_note": "x0, y0, x1, y1 inside each frame: the faceted core alone, for hosts too small for the rings.",
    "states_map": {"listening": "idle", "thinking": "working", "compacting": "working"},
    "frames": frames, "ascii": ascii_frames,
}
out = ROOT / "link-mark" / "prism.json"
out.write_text(json.dumps(sheet, ensure_ascii=False) + "\n", encoding="utf-8")
print(out.relative_to(ROOT), " ".join(frames))
