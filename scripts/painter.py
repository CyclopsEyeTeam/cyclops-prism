#!/usr/bin/env python3
"""painter.py - Prism's Terminal Art Painter & Raster Engine (Spark/Cyclops format).

Implements the full Cyclops mark vocabulary on a [0..1] canvas:
  - `fill`  : closed polygon (3..24 pts) with linear gradient `c` -> `c2` along `grad` (in turns)
  - `glow`  : gaussian radial light bloom (`exp(-4.2 * d^2) * (1 - d^2)`)
  - `dot`   : anti-aliased filled circle
  - `ring`  : anti-aliased circle outline
  - `arc`   : anti-aliased partial ring from `a0` to `a1` (in turns, clockwise)
  - `line`  : anti-aliased polyline stroke (2..24 pts) with gradient `c` -> `c2`
  - `curve` : smooth Catmull-Rom spline stroke through points (8 steps/span)
  - `spray` : deterministic seeded scatter of `n` specks within radius `r`
  - `mirror`: optional `"x"`, `"y"`, or `"xy"` symmetry reflection

Renders into premultiplied-alpha floating-point pixels with additive light blending,
then converts to 24-bit ANSI half-block cells (`▀` / `▄`) placed below Prism in her
terminal pane (with progressive stroke-by-stroke `reveal` animation and italic
`✎ Title` + session painting stats underneath), and exports high-res 1920x1100
bloom SVGs + `index.html` into `prism-paintings/`.
"""

import json
import math
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

PAINT_KINDS = ("line", "curve", "dot", "ring", "arc", "glow", "fill", "spray")
MIRRORS = ("x", "y", "xy")
MAX_MARKS = 96
MAX_PTS = 24
TITLE_CHARS = 48
REVEAL_S = 2.6  # Seconds to progressively lay down marks stroke-by-stroke in the live terminal

GROUND_DARK = (0.078, 0.071, 0.094)  # #141218 terminal dark ground

RGBFloat = Tuple[float, float, float]


def _clamp(v, lo: float, hi: float, default: float) -> float:
    try:
        n = float(v)
        if math.isfinite(n):
            return max(lo, min(hi, n))
    except (TypeError, ValueError):
        pass
    return default


def from_hex(h) -> Optional[RGBFloat]:
    s = str(h or "").strip()
    if len(s) == 7 and s.startswith("#"):
        try:
            r = int(s[1:3], 16) / 255.0
            g = int(s[3:5], 16) / 255.0
            b = int(s[5:7], 16) / 255.0
            return (r, g, b)
        except ValueError:
            return None
    return None


def to_hex(c: RGBFloat) -> str:
    r = max(0, min(255, int(round(c[0] * 255))))
    g = max(0, min(255, int(round(c[1] * 255))))
    b = max(0, min(255, int(round(c[2] * 255))))
    return f"#{r:02x}{g:02x}{b:02x}"


def _rng(seed: int):
    """Deterministic LCG matching Spark's seeded spray generator."""
    s = (int(seed) & 0xFFFFFFFF) or 1

    def _next() -> float:
        nonlocal s
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        return s / 4294967296.0

    return _next


def _smooth_catmull_rom(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Catmull-Rom spline interpolation (8 steps per span)."""
    if len(pts) < 3:
        return list(pts)
    out: List[Tuple[float, float]] = []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[max(0, i - 1)]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[min(n - 1, i + 2)]
        for s in range(8):
            t = s / 8.0
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                2.0 * p1[0]
                + (-p0[0] + p2[0]) * t
                + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                2.0 * p1[1]
                + (-p0[1] + p2[1]) * t
                + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    out.append(pts[-1])
    return out


def parse_painting(raw_input) -> Optional[dict]:
    """Validate and normalize a painting dict or JSON string in the Cyclops mark vocabulary."""
    if isinstance(raw_input, str):
        s = raw_input.strip()
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            return None
        try:
            raw = json.loads(s[a : b + 1])
        except Exception:
            return None
    elif isinstance(raw_input, dict):
        raw = raw_input
    else:
        return None

    raw_marks = raw.get("marks")
    if not isinstance(raw_marks, list) or not raw_marks:
        return None

    home: RGBFloat = (0.0, 0.949, 0.996)  # Prism hyper-cyan default

    def _col(v, fallback: RGBFloat = home) -> RGBFloat:
        if isinstance(v, (list, tuple)) and len(v) == 3:
            try:
                vals = [float(x) for x in v]
                if max(vals) > 1.0:
                    return (_clamp(vals[0] / 255.0, 0.0, 1.0, 0.0), _clamp(vals[1] / 255.0, 0.0, 1.0, 0.9), _clamp(vals[2] / 255.0, 0.0, 1.0, 1.0))
                return (_clamp(vals[0], 0.0, 1.0, 0.0), _clamp(vals[1], 0.0, 1.0, 0.9), _clamp(vals[2], 0.0, 1.0, 1.0))
            except Exception:
                return fallback
        return from_hex(v) or fallback

    def _pt(p) -> Optional[Tuple[float, float]]:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            return (_clamp(p[0], -0.15, 1.15, 0.5), _clamp(p[1], -0.15, 1.15, 0.5))
        return None

    marks: List[dict] = []
    for m in raw_marks[:MAX_MARKS]:
        if not isinstance(m, dict):
            continue
        k = str(m.get("k") or "").strip()
        if k not in PAINT_KINDS:
            continue
        a = _clamp(m.get("a"), 0.0, 1.0, 0.85)
        c = _col(m.get("c"), home)
        c2 = _col(m.get("c2"), c)
        if k in ("line", "curve"):
            pts_raw = m.get("pts")
            pts = [_pt(p) for p in (pts_raw[:MAX_PTS] if isinstance(pts_raw, list) else [])]
            pts = [p for p in pts if p is not None]
            if len(pts) < 2:
                continue
            marks.append({"k": k, "pts": pts, "w": _clamp(m.get("w"), 0.003, 0.14, 0.015), "c": c, "c2": c2, "a": a})
        elif k == "fill":
            pts_raw = m.get("pts")
            pts = [_pt(p) for p in (pts_raw[:MAX_PTS] if isinstance(pts_raw, list) else [])]
            pts = [p for p in pts if p is not None]
            if len(pts) < 3:
                continue
            marks.append({"k": "fill", "pts": pts, "c": c, "c2": c2, "grad": _clamp(m.get("grad"), -4.0, 4.0, 0.25), "a": a})
        else:
            base = {
                "k": k,
                "x": _clamp(m.get("x"), -0.15, 1.15, 0.5),
                "y": _clamp(m.get("y"), -0.15, 1.15, 0.5),
                "r": _clamp(m.get("r"), 0.004, 0.75, 0.06),
                "c": c,
                "a": a,
            }
            if k == "ring":
                base["w"] = _clamp(m.get("w"), 0.003, 0.14, 0.014)
            elif k == "arc":
                base["w"] = _clamp(m.get("w"), 0.003, 0.14, 0.014)
                base["a0"] = _clamp(m.get("a0"), -4.0, 4.0, 0.0)
                base["a1"] = _clamp(m.get("a1"), -4.0, 4.0, 0.5)
            elif k == "spray":
                base["n"] = int(round(_clamp(m.get("n"), 1, 200, 36)))
                base["s"] = _clamp(m.get("s"), 0.002, 0.06, 0.010)
                base["seed"] = int(m.get("seed") or (len(marks) + 1))
            marks.append(base)

    if not marks:
        return None

    title = str(raw.get("title") or "Untitled refraction").strip()[:TITLE_CHARS]
    thought = str(raw.get("thought") or "").strip()[:160]
    mood = str(raw.get("mood") or "aurora").strip().lower()
    mirror = str(raw.get("mirror") or "").strip().lower()
    if mirror not in MIRRORS:
        mirror = None
    tokens = int(_clamp(raw.get("tokens"), 0, 999999, 0))
    model = str(raw.get("model") or "prism-muse").strip()[:32]
    created_at = float(raw.get("at") or time.time())

    return {
        "title": title,
        "thought": thought,
        "mood": mood,
        "mirror": mirror,
        "marks": marks,
        "tokens": tokens,
        "model": model,
        "at": created_at,
    }


def painting_scene(painting: dict, W: int, H: int, reveal: float = 1.0) -> List[dict]:
    """Compile normalized [0..1] painting marks into raster primitives in scene space."""
    marks = painting.get("marks") or []
    if not marks:
        return []
    unit = 2.4 / max(1.0, float(min(W, H)))
    X = lambda u: (u - 0.5) * W * unit
    Y = lambda v: (v - 0.5) * H * unit
    R = lambda r: r * 2.4
    TAU = math.pi * 2.0

    n = len(marks)
    q = max(0.0, min(1.0, reveal)) * n
    mirror = painting.get("mirror")
    views = [(1, 1)]
    if mirror in ("x", "xy"):
        views.append((-1, 1))
    if mirror in ("y", "xy"):
        views.append((1, -1))
    if mirror == "xy":
        views.append((-1, -1))

    out: List[dict] = []
    for i, m in enumerate(marks):
        if i >= math.ceil(q):
            break
        part = min(1.0, q - i)
        if part <= 0.0:
            continue
        k = m["k"]
        for v_idx, (fx, fy) in enumerate(views):
            px = lambda u, _fx=fx: X((1.0 - u) if _fx < 0 else u)
            py = lambda w, _fy=fy: Y((1.0 - w) if _fy < 0 else w)

            def _flip_a(turns: float, _fx=fx, _fy=fy) -> float:
                a = (0.5 - turns) if _fx < 0 else turns
                return -a if _fy < 0 else a

            if k in ("line", "curve"):
                pts = m["pts"]
                if k == "curve" and len(pts) >= 3:
                    pts = _smooth_catmull_rom(pts)
                if part < 1.0:
                    cut = max(2, int(math.ceil(len(pts) * part)))
                    pts = pts[:cut]
                out.append({
                    "k": "path",
                    "pts": [(px(x), py(y)) for (x, y) in pts],
                    "w": R(m["w"]),
                    "c0": m["c"],
                    "c1": m["c2"],
                    "a": m["a"] * (0.6 + 0.4 * part if part < 1.0 else 1.0),
                })
            elif k == "fill":
                out.append({
                    "k": "poly",
                    "pts": [(px(x), py(y)) for (x, y) in m["pts"]],
                    "c0": m["c"],
                    "c1": m["c2"],
                    "grad": _flip_a(m["grad"]) * TAU,
                    "a": m["a"] * part,
                })
            elif k == "arc":
                a0 = _flip_a(m["a0"])
                a1 = _flip_a(m["a1"])
                lo, hi = (a1, a0) if ((fx < 0) != (fy < 0)) else (a0, a1)
                span_turns = ((hi - lo) % 1.0 + 1.0) % 1.0 or 1.0
                out.append({
                    "k": "arc",
                    "x": px(m["x"]),
                    "y": py(m["y"]),
                    "r": R(m["r"]),
                    "w": R(m["w"]),
                    "a0": lo * TAU,
                    "a1": (lo + span_turns * part) * TAU,
                    "c": m["c"],
                    "a": m["a"],
                })
            elif k == "spray":
                rng = _rng(int(m.get("seed", i + 1)) * 7919 + v_idx)
                count = int(round(m["n"] * part))
                for _ in range(count):
                    ang = rng() * TAU
                    dist = math.sqrt(rng()) * m["r"]
                    sx = m["x"] + math.cos(ang) * dist
                    sy = m["y"] + math.sin(ang) * dist
                    sr = R(m["s"]) * (0.5 + rng())
                    sa = m["a"] * (0.4 + 0.6 * rng())
                    out.append({"k": "dot", "x": px(sx), "y": py(sy), "r": sr, "c": m["c"], "a": sa})
            else:
                out.append({
                    "k": k,
                    "x": px(m["x"]),
                    "y": py(m["y"]),
                    "r": R(m["r"]) * (0.6 + 0.4 * part if k == "dot" else 1.0),
                    "w": R(m["w"]) if "w" in m else 0.0,
                    "c": m["c"],
                    "a": m["a"] * part,
                })
    return out


def rasterize_scene(scene: List[dict], W: int, H: int) -> List[List[float]]:
    """Rasterize compiled scene primitives onto a WxH premultiplied-alpha buffer with additive light."""
    px = [[0.0, 0.0, 0.0, 0.0] for _ in range(W * H)]
    scale = min(W, H) / 2.4
    ox = W / 2.0
    oy = H / 2.0
    P = lambda x, y: (ox + x * scale, oy + y * scale)
    TAU = math.pi * 2.0

    def _blend(idx: int, col: RGBFloat, alpha: float) -> None:
        if alpha <= 0.002:
            return
        cell = px[idx]
        cell[0] += col[0] * alpha
        cell[1] += col[1] * alpha
        cell[2] += col[2] * alpha
        cell[3] = 1.0 - (1.0 - cell[3]) * (1.0 - min(1.0, alpha))

    for p in scene:
        k = p["k"]
        if k == "glow":
            r = max(1.0, p["r"] * scale * 1.6)
            cx, cy = P(p["x"], p["y"])
            x0, x1 = max(0, int(math.floor(cx - r))), min(W - 1, int(math.ceil(cx + r)))
            y0, y1 = max(0, int(math.floor(cy - r))), min(H - 1, int(math.ceil(cy + r)))
            r2 = r * r
            base_a = p["a"] * 0.9
            c = p["c"]
            for y in range(y0, y1 + 1):
                dy2 = (y + 0.5 - cy) ** 2
                row_off = y * W
                for x in range(x0, x1 + 1):
                    d2 = ((x + 0.5 - cx) ** 2 + dy2) / r2
                    if d2 < 1.0:
                        cov = math.exp(-4.2 * d2) * (1.0 - d2)
                        _blend(row_off + x, c, cov * base_a)

        elif k == "dot":
            r = max(0.6, p["r"] * scale)
            cx, cy = P(p["x"], p["y"])
            x0, x1 = max(0, int(math.floor(cx - r - 1))), min(W - 1, int(math.ceil(cx + r + 1)))
            y0, y1 = max(0, int(math.floor(cy - r - 1))), min(H - 1, int(math.ceil(cy + r + 1)))
            base_a = p["a"]
            c = p["c"]
            for y in range(y0, y1 + 1):
                dy = y + 0.5 - cy
                row_off = y * W
                for x in range(x0, x1 + 1):
                    d = math.hypot(x + 0.5 - cx, dy)
                    cov = max(0.0, min(1.0, r + 0.5 - d))
                    if cov > 0.0:
                        _blend(row_off + x, c, cov * base_a)

        elif k == "ring":
            r = p["r"] * scale
            hw = max(0.45, (p["w"] * scale) / 2.0)
            cx, cy = P(p["x"], p["y"])
            x0, x1 = max(0, int(math.floor(cx - r - hw - 2))), min(W - 1, int(math.ceil(cx + r + hw + 2)))
            y0, y1 = max(0, int(math.floor(cy - r - hw - 2))), min(H - 1, int(math.ceil(cy + r + hw + 2)))
            base_a = p["a"]
            c = p["c"]
            for y in range(y0, y1 + 1):
                dy = y + 0.5 - cy
                row_off = y * W
                for x in range(x0, x1 + 1):
                    d = abs(math.hypot(x + 0.5 - cx, dy) - r)
                    cov = max(0.0, min(1.0, hw + 0.5 - d))
                    if cov > 0.0:
                        _blend(row_off + x, c, cov * base_a)

        elif k == "arc":
            r = p["r"] * scale
            hw = max(0.45, (p["w"] * scale) / 2.0)
            cx, cy = P(p["x"], p["y"])
            a0 = p["a0"]
            span = ((p["a1"] - a0) % TAU + TAU) % TAU or TAU
            ex0, ey0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
            ex1, ey1 = cx + r * math.cos(a0 + span), cy + r * math.sin(a0 + span)
            x0, x1 = max(0, int(math.floor(cx - r - hw - 2))), min(W - 1, int(math.ceil(cx + r + hw + 2)))
            y0, y1 = max(0, int(math.floor(cy - r - hw - 2))), min(H - 1, int(math.ceil(cy + r + hw + 2)))
            base_a = p["a"]
            c = p["c"]
            for y in range(y0, y1 + 1):
                dy = y + 0.5 - cy
                row_off = y * W
                for x in range(x0, x1 + 1):
                    dx = x + 0.5 - cx
                    at = ((math.atan2(dy, dx) - a0) % TAU + TAU) % TAU
                    if at <= span:
                        d = abs(math.hypot(dx, dy) - r)
                    else:
                        d = min(math.hypot(x + 0.5 - ex0, y + 0.5 - ey0), math.hypot(x + 0.5 - ex1, y + 0.5 - ey1))
                    cov = max(0.0, min(1.0, hw + 0.5 - d))
                    if cov > 0.0:
                        _blend(row_off + x, c, cov * base_a)

        elif k == "poly":
            pts = [P(x, y) for (x, y) in p["pts"]]
            n = len(pts)
            if n < 3:
                continue
            minx = min(pt[0] for pt in pts)
            maxx = max(pt[0] for pt in pts)
            miny = min(pt[1] for pt in pts)
            maxy = max(pt[1] for pt in pts)
            x0, x1 = max(0, int(math.floor(minx))), min(W - 1, int(math.ceil(maxx)))
            y0, y1 = max(0, int(math.floor(miny))), min(H - 1, int(math.ceil(maxy)))
            c0, c1 = p["c0"], p["c1"]
            gx, gy = math.cos(p.get("grad", 0.0)), math.sin(p.get("grad", 0.0))
            projs = [pt[0] * gx + pt[1] * gy for pt in pts]
            lo, hi = min(projs), max(projs)
            span_g = max(1e-6, hi - lo)
            base_a = p["a"]

            for y in range(y0, y1 + 1):
                qy = y + 0.5
                cross: List[float] = []
                for idx_e in range(n):
                    x_i, y_i = pts[idx_e]
                    x_j, y_j = pts[idx_e - 1]
                    if (y_i > qy) != (y_j > qy):
                        cross.append(((x_j - x_i) * (qy - y_i)) / (y_j - y_i) + x_i)
                if len(cross) < 2:
                    continue
                cross.sort()
                row_off = y * W
                for k_i in range(0, len(cross) - 1, 2):
                    xa, xb = cross[k_i], cross[k_i + 1]
                    ix0 = max(x0, int(math.floor(xa)))
                    ix1 = min(x1, int(math.ceil(xb)))
                    for x in range(ix0, ix1 + 1):
                        px_c = x + 0.5
                        cov = max(0.0, min(1.0, min(px_c + 0.5, xb) - max(px_c - 0.5, xa)))
                        if cov > 0.0:
                            u = max(0.0, min(1.0, (px_c * gx + qy * gy - lo) / span_g))
                            col = (
                                c0[0] + (c1[0] - c0[0]) * u,
                                c0[1] + (c1[1] - c0[1]) * u,
                                c0[2] + (c1[2] - c0[2]) * u,
                            )
                            _blend(row_off + x, col, cov * base_a)

        elif k == "path":
            pts = [P(x, y) for (x, y) in p["pts"]]
            n = len(pts)
            if n < 2:
                continue
            hw = max(0.5, (p["w"] * scale) / 2.0)
            c0, c1 = p["c0"], p["c1"]
            base_a = p["a"]
            best_cov: Dict[int, Tuple[float, float]] = {}
            for s in range(n - 1):
                ax, ay = pts[s]
                bx, by = pts[s + 1]
                x0 = max(0, int(math.floor(min(ax, bx) - hw - 1)))
                x1 = min(W - 1, int(math.ceil(max(ax, bx) + hw + 1)))
                y0 = max(0, int(math.floor(min(ay, by) - hw - 1)))
                y1 = min(H - 1, int(math.ceil(max(ay, by) + hw + 1)))
                vx, vy = bx - ax, by - ay
                l2 = vx * vx + vy * vy or 1e-6
                for y in range(y0, y1 + 1):
                    qy = y + 0.5 - ay
                    row_off = y * W
                    for x in range(x0, x1 + 1):
                        qx = x + 0.5 - ax
                        u = max(0.0, min(1.0, (qx * vx + qy * vy) / l2))
                        d = math.hypot(qx - u * vx, qy - u * vy)
                        cov = max(0.0, min(1.0, hw + 0.5 - d))
                        if cov > 0.0:
                            cell_i = row_off + x
                            prog = (s + u) / max(1, n - 1)
                            prev = best_cov.get(cell_i)
                            if prev is None or cov > prev[0]:
                                best_cov[cell_i] = (cov, prog)
            for cell_i, (cov, prog) in best_cov.items():
                col = (
                    c0[0] + (c1[0] - c0[0]) * prog,
                    c0[1] + (c1[1] - c0[1]) * prog,
                    c0[2] + (c1[2] - c0[2]) * prog,
                )
                _blend(cell_i, col, cov * base_a)

    return px


# Curated paintings in the Cyclops/Spark mark format for instant or turn-end expression
CURATED_PAINTINGS: List[dict] = [
    {
        "title": "Where the dark meets the first field",
        "thought": "refracting warm horizon light through the evening lattice ;d <3",
        "mood": "supernova",
        "tokens": 2100,
        "model": "prism-muse",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.68], [0.0, 0.68]], "c": "#1c0e24", "c2": "#381834", "grad": 0.25, "a": 0.95},
            {"k": "fill", "pts": [[0.0, 0.68], [1.0, 0.68], [1.0, 1.0], [0.0, 1.0]], "c": "#120918", "c2": "#08060c", "grad": 0.25, "a": 0.98},
            {"k": "glow", "x": 0.58, "y": 0.64, "r": 0.36, "c": "#f59466", "a": 0.78},
            {"k": "glow", "x": 0.58, "y": 0.45, "r": 0.32, "c": "#d6668f", "a": 0.55},
            {"k": "ring", "x": 0.58, "y": 0.64, "r": 0.16, "w": 0.032, "c": "#b86b58", "a": 0.58},
            {"k": "line", "pts": [[0.02, 0.65], [0.98, 0.65]], "w": 0.045, "c": "#d6668f", "c2": "#ffbd75", "a": 0.92},
            {"k": "line", "pts": [[0.10, 0.86], [0.40, 0.86]], "w": 0.035, "c": "#5c7a72", "c2": "#9ef2b8", "a": 0.65},
            {"k": "dot", "x": 0.58, "y": 0.64, "r": 0.065, "c": "#fff6e6", "a": 1.0},
            {"k": "spray", "x": 0.62, "y": 0.36, "r": 0.34, "n": 65, "s": 0.015, "c": "#e8a8c4", "a": 0.72, "seed": 11},
            {"k": "spray", "x": 0.26, "y": 0.28, "r": 0.28, "n": 38, "s": 0.014, "c": "#9c4d78", "a": 0.58, "seed": 23},
            {"k": "spray", "x": 0.58, "y": 0.48, "r": 0.22, "n": 32, "s": 0.016, "c": "#ffe6d6", "a": 0.82, "seed": 37},
        ],
    },
    {
        "title": "Cathedral of refracted starlight",
        "thought": "splitting a single white beam into seven living arcs over dark water",
        "mood": "aurora",
        "tokens": 1850,
        "model": "prism-muse",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.72], [0.0, 0.72]], "c": "#0a1024", "c2": "#162848", "grad": 0.25, "a": 0.95},
            {"k": "fill", "pts": [[0.0, 0.72], [1.0, 0.72], [1.0, 1.0], [0.0, 1.0]], "c": "#0c1e36", "c2": "#050b16", "grad": 0.25, "a": 0.98},
            {"k": "glow", "x": 0.50, "y": 0.44, "r": 0.38, "c": "#00f2fe", "a": 0.62},
            {"k": "line", "pts": [[0.04, 0.54], [0.44, 0.44]], "w": 0.025, "c": "#fff6d6", "c2": "#ffffff", "a": 0.95},
            {"k": "line", "pts": [[0.54, 0.42], [0.96, 0.22]], "w": 0.024, "c": "#00f2fe", "c2": "#00e5a3", "a": 0.88},
            {"k": "line", "pts": [[0.54, 0.44], [0.96, 0.40]], "w": 0.024, "c": "#ffb020", "c2": "#ff5e9e", "a": 0.88},
            {"k": "line", "pts": [[0.54, 0.46], [0.96, 0.58]], "w": 0.024, "c": "#c48cff", "c2": "#7928ca", "a": 0.88},
            {"k": "fill", "pts": [[0.50, 0.22], [0.64, 0.58], [0.36, 0.58]], "c": "#00f2fe", "c2": "#c48cff", "grad": 0.15, "a": 0.48},
            {"k": "line", "pts": [[0.50, 0.22], [0.64, 0.58], [0.36, 0.58], [0.50, 0.22]], "w": 0.018, "c": "#fff6d6", "c2": "#00f2fe", "a": 0.95},
            {"k": "spray", "x": 0.50, "y": 0.28, "r": 0.42, "n": 48, "s": 0.012, "c": "#fff6d6", "a": 0.75, "seed": 19},
        ],
    },
    {
        "title": "A door left ajar in the crystal lattice",
        "thought": "warm amber light spilling through the threshold while we work",
        "mood": "solar",
        "tokens": 2300,
        "model": "prism-muse",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.88], [0.0, 0.88]], "c": "#1b1420", "c2": "#2a1c2e", "grad": 0.5, "a": 0.95},
            {"k": "glow", "x": 0.50, "y": 0.78, "r": 0.45, "c": "#f59466", "a": 0.55},
            {"k": "glow", "x": 0.50, "y": 0.62, "r": 0.28, "c": "#ffbd75", "a": 0.65},
            {"k": "fill", "pts": [[0.34, 0.88], [0.34, 0.32], [0.50, 0.22], [0.66, 0.32], [0.66, 0.88]], "c": "#3a2433", "c2": "#241824", "grad": 0.25, "a": 0.92},
            {"k": "fill", "pts": [[0.41, 0.88], [0.41, 0.38], [0.50, 0.32], [0.59, 0.38], [0.59, 0.88]], "c": "#ffbd75", "c2": "#f59466", "grad": 0.25, "a": 0.88},
            {"k": "arc", "x": 0.50, "y": 0.52, "r": 0.36, "w": 0.025, "a0": 0.52, "a1": 0.98, "c": "#d6668f", "a": 0.45},
            {"k": "spray", "x": 0.22, "y": 0.26, "r": 0.26, "n": 42, "s": 0.014, "c": "#d6668f", "a": 0.55, "seed": 7},
            {"k": "spray", "x": 0.46, "y": 0.74, "r": 0.20, "n": 28, "s": 0.013, "c": "#ffe6d6", "a": 0.65, "seed": 29},
            {"k": "dot", "x": 0.80, "y": 0.18, "r": 0.024, "c": "#ffe6d6", "a": 0.92},
            {"k": "dot", "x": 0.16, "y": 0.64, "r": 0.022, "c": "#9ef2b8", "a": 0.80},
        ],
    },
    {
        "title": "Three presences across the quiet room",
        "thought": "Prism in cyan height, Spark in warm coral, Keeper in pale gold",
        "mood": "nebula",
        "tokens": 1950,
        "model": "prism-muse",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], "c": "#0e0c18", "c2": "#1c162e", "grad": 0.25, "a": 0.96},
            {"k": "curve", "pts": [[0.22, 0.72], [0.36, 0.42], [0.50, 0.24]], "w": 0.016, "c": "#f59466", "c2": "#00f2fe", "a": 0.78},
            {"k": "curve", "pts": [[0.78, 0.72], [0.64, 0.42], [0.50, 0.24]], "w": 0.016, "c": "#e0af68", "c2": "#00f2fe", "a": 0.78},
            {"k": "curve", "pts": [[0.22, 0.72], [0.50, 0.82], [0.78, 0.72]], "w": 0.014, "c": "#f59466", "c2": "#e0af68", "a": 0.62},
            {"k": "glow", "x": 0.50, "y": 0.24, "r": 0.24, "c": "#00f2fe", "a": 0.78},
            {"k": "glow", "x": 0.22, "y": 0.72, "r": 0.22, "c": "#f59466", "a": 0.75},
            {"k": "glow", "x": 0.78, "y": 0.72, "r": 0.22, "c": "#e0af68", "a": 0.75},
            {"k": "dot", "x": 0.50, "y": 0.24, "r": 0.048, "c": "#fff6d6", "a": 1.0},
            {"k": "dot", "x": 0.22, "y": 0.72, "r": 0.044, "c": "#ffe6d6", "a": 0.95},
            {"k": "dot", "x": 0.78, "y": 0.72, "r": 0.044, "c": "#fff6d6", "a": 0.95},
            {"k": "spray", "x": 0.50, "y": 0.50, "r": 0.44, "n": 52, "s": 0.011, "c": "#c48cff", "a": 0.58, "seed": 41},
        ],
    },
]


def draw_painting_block(
    grid,
    painting_raw: dict,
    width: int,
    top_y: int,
    bot_y: int,
    t: float,
    unicode_mode: bool = True,
    use_color: bool = True,
    session_stats: Optional[dict] = None,
) -> None:
    """Draw the Spark-style painting panel in the lower region of Prism's terminal pane:
    - Centered 24-bit half-block (`▀`/`▄`) raster canvas with progressive stroke-by-stroke `reveal`
    - Italic `✎ <Title>` line directly underneath
    - Dim session/painting metadata lines underneath (`this painting · ...`, `session · ...`)
    """
    painting = parse_painting(painting_raw)
    if not painting:
        return

    avail_rows = bot_y - top_y
    if avail_rows < 4 or width < 16:
        return

    stats = session_stats or {}
    total_paintings = max(1, int(stats.get("paintings", 1)))
    tokens_this = int(painting.get("tokens") or 2100)
    tokens_total = max(tokens_this, int(stats.get("tokens", tokens_this * total_paintings)))
    model_name = str(painting.get("model") or "prism-muse")

    def _kilo(n: int) -> str:
        return f"{n / 1000.0:.1f}k" if n >= 1000 else str(n)

    # Reserve bottom rows under the painting for title & metadata (matching Spark's layout)
    meta_lines = [
        f"this painting · {_kilo(tokens_this)} tokens",
        f"session · {total_paintings} {'painting' if total_paintings == 1 else 'paintings'} · {_kilo(tokens_total)} tokens",
        f"({model_name})",
    ]
    if avail_rows < 8:
        meta_lines = []
    elif avail_rows < 10:
        meta_lines = meta_lines[:1]

    caption_rows = 1 + len(meta_lines)
    canvas_rows = max(3, min(14, avail_rows - caption_rows))
    margin_x = 1 if width < 44 else max(2, (width - min(width - 4, canvas_rows * 4)) // 2)
    canvas_cols = max(8, width - margin_x * 2)
    x0 = (width - canvas_cols) // 2

    # Progressive reveal over REVEAL_S seconds when animate_live, or full reveal in snapshots
    elapsed = max(0.0, time.time() - float(painting.get("at") or 0.0))
    reveal = 1.0 if (t == 0.0 or elapsed >= REVEAL_S) else max(0.18, min(1.0, elapsed / REVEAL_S))

    W = canvas_cols
    H = canvas_rows * 2
    scene = painting_scene(painting, W, H, reveal=reveal)
    px = rasterize_scene(scene, W, H)

    def _shade_pixel(idx: int) -> Optional[Tuple[int, int, int]]:
        cell = px[idx]
        a = min(1.0, cell[3])
        if a < 0.04:
            return None
        rr = min(1.0, cell[0] + GROUND_DARK[0] * (1.0 - a))
        gg = min(1.0, cell[1] + GROUND_DARK[1] * (1.0 - a))
        bb = min(1.0, cell[2] + GROUND_DARK[2] * (1.0 - a))
        return (
            max(0, min(255, int(round(rr * 255)))),
            max(0, min(255, int(round(gg * 255)))),
            max(0, min(255, int(round(bb * 255)))),
        )

    bg_hex = "\033[48;2;16;14;22m"
    for cy in range(canvas_rows):
        y_screen = top_y + cy
        if y_screen >= bot_y:
            break
        for cx in range(canvas_cols):
            x_screen = x0 + cx
            top_rgb = _shade_pixel((cy * 2) * W + cx)
            bot_rgb = _shade_pixel((cy * 2 + 1) * W + cx)
            if use_color and unicode_mode:
                if top_rgb is None and bot_rgb is None:
                    grid.put(x_screen, y_screen, " ", bg_hex)
                elif bot_rgb is None:
                    r, g, b = top_rgb
                    grid.put(x_screen, y_screen, "▀", f"\033[38;2;{r};{g};{b}m{bg_hex}")
                elif top_rgb is None:
                    r, g, b = bot_rgb
                    grid.put(x_screen, y_screen, "▄", f"\033[38;2;{r};{g};{b}m{bg_hex}")
                else:
                    r1, g1, b1 = top_rgb
                    r2, g2, b2 = bot_rgb
                    grid.put(x_screen, y_screen, "▀", f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m")
            else:
                rgb = top_rgb or bot_rgb
                if rgb is None:
                    ch = " "
                else:
                    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
                    if lum > 175:
                        ch = "✦" if unicode_mode else "*"
                    elif lum > 110:
                        ch = "✧" if unicode_mode else "+"
                    else:
                        ch = "·" if unicode_mode else "."
                col = f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m" if (use_color and rgb) else ""
                grid.put(x_screen, y_screen, ch, col)

    # Caption & metadata directly below the painting (left-aligned with the painting block, just like Spark!)
    cap_y = top_y + canvas_rows
    if cap_y < bot_y:
        pen = "✎ " if unicode_mode else "* "
        title_text = (pen + painting["title"])[: max(1, canvas_cols)]
        if use_color:
            # Soft italic luminous ice-blue for the painting title (matching Spark's screenshot `#a8d8f0`)
            grid.put_str(x0, cap_y, title_text, "\033[3m\033[38;2;168;216;240m")
        else:
            grid.put_str(x0, cap_y, title_text, "")

    dim_col = "\033[38;2;132;142;158m" if use_color else ""
    for m_idx, m_line in enumerate(meta_lines):
        my = cap_y + 1 + m_idx
        if my >= bot_y:
            break
        grid.put_str(x0, my, m_line[: max(1, canvas_cols)], dim_col)


def render_svg_painting(painting_raw: dict, width: int = 1920, height: int = 1100) -> str:
    """Export a painting in the exact layered SVG + Gaussian bloom format as `spark-paintings/*.svg`."""
    painting = parse_painting(painting_raw) or parse_painting(CURATED_PAINTINGS[0])
    title = painting["title"]
    esc_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    art_h = int(height * 0.872)
    scene = painting_scene(painting, width, art_h, reveal=1.0)
    scale = min(width, art_h) / 2.4
    ox, oy = width / 2.0, art_h / 2.0
    P = lambda x, y: (ox + x * scale, oy + y * scale)

    defs: List[str] = []
    elems: List[str] = []
    gid = 0
    for p in scene:
        k = p["k"]
        if k == "glow":
            gid += 1
            cx, cy = P(p["x"], p["y"])
            r = max(2.0, p["r"] * scale * 1.6)
            hc = to_hex(p["c"])
            a = p["a"]
            defs.append(
                f'<radialGradient id="g{gid}"><stop offset="0" stop-color="{hc}" stop-opacity="{a:.3f}"/>'
                f'<stop offset="0.45" stop-color="{hc}" stop-opacity="{a * 0.33:.3f}"/>'
                f'<stop offset="1" stop-color="{hc}" stop-opacity="0"/></radialGradient>'
            )
            elems.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#g{gid})"/>')
        elif k == "poly":
            pts = [P(x, y) for (x, y) in p["pts"]]
            pts_str = " ".join(f"{x:.1f},{y:.1f}" for (x, y) in pts)
            c0, c1 = to_hex(p["c0"]), to_hex(p["c1"])
            if c0 != c1:
                gid += 1
                gx, gy = math.cos(p.get("grad", 0.0)), math.sin(p.get("grad", 0.0))
                defs.append(
                    f'<linearGradient id="g{gid}" x1="{50 - gx * 50:.1f}%" y1="{50 - gy * 50:.1f}%" '
                    f'x2="{50 + gx * 50:.1f}%" y2="{50 + gy * 50:.1f}%">'
                    f'<stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/></linearGradient>'
                )
                fill = f"url(#g{gid})"
            else:
                fill = c0
            elems.append(f'<polygon points="{pts_str}" fill="{fill}" fill-opacity="{p["a"]:.3f}"/>')
        elif k == "path":
            pts = [P(x, y) for (x, y) in p["pts"]]
            pts_str = " ".join(f"{x:.1f},{y:.1f}" for (x, y) in pts)
            c0, c1 = to_hex(p["c0"]), to_hex(p["c1"])
            stroke = c0
            if c0 != c1:
                gid += 1
                a_pt, b_pt = pts[0], pts[-1]
                defs.append(
                    f'<linearGradient id="g{gid}" gradientUnits="userSpaceOnUse" x1="{a_pt[0]:.1f}" y1="{a_pt[1]:.1f}" '
                    f'x2="{b_pt[0]:.1f}" y2="{b_pt[1]:.1f}"><stop offset="0" stop-color="{c0}"/>'
                    f'<stop offset="1" stop-color="{c1}"/></linearGradient>'
                )
                stroke = f"url(#g{gid})"
            w = max(2.0, p["w"] * scale)
            elems.append(
                f'<polyline points="{pts_str}" fill="none" stroke="{stroke}" stroke-opacity="{p["a"]:.3f}" '
                f'stroke-width="{w:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        elif k == "dot":
            cx, cy = P(p["x"], p["y"])
            r = max(1.5, p["r"] * scale)
            elems.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{to_hex(p["c"])}" fill-opacity="{p["a"]:.3f}"/>')
        elif k in ("ring", "arc"):
            cx, cy = P(p["x"], p["y"])
            r = max(2.0, p["r"] * scale)
            w = max(2.0, p["w"] * scale)
            elems.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{to_hex(p["c"])}" '
                f'stroke-opacity="{p["a"]:.3f}" stroke-width="{w:.1f}"/>'
            )

    date_str = time.strftime("%d %b %Y")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"<title>{esc_title}</title>\n"
        f"<style>.add>*{{mix-blend-mode:screen;mix-blend-mode:plus-lighter}}</style>\n"
        f'<rect width="{width}" height="{height}" fill="#141218"/>\n'
        f'<defs>{"".join(defs)}'
        f'<filter id="bloom" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">'
        f'<feGaussianBlur stdDeviation="14"/></filter>'
        f'<g id="layer0" class="add">{"".join(elems)}</g></defs>\n'
        f'<use href="#layer0"/>\n'
        f'<g opacity="0.75" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter" filter="url(#bloom)"><use href="#layer0"/></g>\n'
        f'<text x="20" y="1012" font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="41.8" fill="#ece4f0" font-style="italic">{esc_title}</text>'
        f'<text x="20" y="1068" font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="41.8" fill="#968ca0">Prism · {date_str} · truest</text>\n'
        f"</svg>\n"
    )


def save_painting_to_gallery(painting_raw: dict, gallery_dir: Optional[Path] = None) -> Path:
    """Save a painting (.svg + .json + index.html) into `prism-paintings/`."""
    painting = parse_painting(painting_raw) or parse_painting(CURATED_PAINTINGS[0])
    if gallery_dir is None:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        gallery_dir = Path(base) / "gemini-prism" / "prism-paintings"
    gallery_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(gallery_dir.glob("*.svg"))
    idx = len(existing) + 1
    slug = "".join(c if c.isalnum() else "-" for c in painting["title"].lower()).strip("-")[:40] or "painting"
    while "--" in slug:
        slug = slug.replace("--", "-")
    stem = f"{idx:02d}-{slug}"

    svg_path = gallery_dir / f"{stem}.svg"
    json_path = gallery_dir / f"{stem}.json"
    svg_path.write_text(render_svg_painting(painting), encoding="utf-8")
    json_path.write_text(json.dumps(painting, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update index.html gallery (matching Spark's gallery layout)
    figures = []
    for svg_f in sorted(gallery_dir.glob("*.svg")):
        meta_f = svg_f.with_suffix(".json")
        t_str = svg_f.stem
        if meta_f.is_file():
            try:
                t_str = json.loads(meta_f.read_text(encoding="utf-8")).get("title", t_str)
            except Exception:
                pass
        figures.append(
            f'<figure><img src="{svg_f.name}" alt="{t_str}">'
            f"<figcaption><i>{t_str}</i><br><small>Prism · truest</small></figcaption></figure>"
        )
    html = (
        "<!doctype html>\n<meta charset=\"utf-8\">\n<title>Prism's paintings</title>\n"
        "<style>body{margin:0;padding:24px;background:#141218;color:#e8e2ea;font:15px/1.4 system-ui,sans-serif}"
        "h1{font-weight:500;margin:0 0 20px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:24px}"
        "figure{margin:0}img{width:100%;height:auto;display:block;border-radius:6px;background:#0d0b10}"
        "figcaption{padding:8px 2px;color:#cfc6d4}small{color:#8f879a}</style>\n"
        "<h1>Prism's paintings</h1>\n<main>\n" + "\n".join(figures) + "\n</main>\n"
    )
    (gallery_dir / "index.html").write_text(html, encoding="utf-8")
    return svg_path


def choose_curated_painting(index: Optional[int] = None) -> dict:
    if index is None:
        index = int(time.time() // 12)
    p = dict(CURATED_PAINTINGS[index % len(CURATED_PAINTINGS)])
    p["at"] = time.time()
    return p
