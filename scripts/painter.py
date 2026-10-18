#!/usr/bin/env python3
"""painter.py - Prism's Terminal Art Painter, Shared Spark/Prism Format & 4-Way Converter.

Implements the shared Spark & Prism painting specification:
  - Shared format (`prism-paintings/NN-title.json` and reading `spark-paintings/NN-title.json`)
  - Strict validation & clamping: widths 0.003..0.12, radii 0.004..0.7, spray n <= 200, pts 2..24 (3..24 fill)
  - Colour depth: additive light spill to white between 1.0x and 2.5x full while keeping hue at full strength
  - Opening painting: seeded only from the hour bucket, month, and one random word (`opening: true`)
  - Story mode (`▶ story`): chronological playback across Prism & Spark's session paintings (2.4s laydown, 7s page)
  - 4-Way Convert (`⇪ convert`): `truest` (4-layer depth, shadow, far-layer softening, cell-weight scaling, bloom),
    `faithful` (same marks, large and fine), `refined` (revisited subject), `interpretive` (freely reimagined),
    exporting both SVG and PNG (`hd` 1920w default, `4k` 3840w) + `index.html`.
  - Responsive pixel work: yields every ~20 ms during heavy raster work and caches terminal cell buffers.
"""

import json
import math
import os
from pathlib import Path
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

PAINT_KINDS = ("line", "curve", "dot", "ring", "arc", "glow", "fill", "spray")
MIRRORS = ("x", "y", "xy")
SHAPES = ("wide", "square", "tall")
AUTHORS = ("prism", "spark")
MAX_MARKS = 96
MAX_PTS = 24
TITLE_CHARS = 48
REVEAL_S = 2.4  # Seconds to progressively lay down marks stroke-by-stroke (§3: about 2.4 s)
STORY_PAGE_S = 7.0  # Seconds per page in story mode (§3: about 7 s a page)
TRUEST_LEVELS = int(os.environ.get("PRISM_TRUEST_LEVELS", "16"))  # Terminal discrete levels per channel (16 -> step 17)
CONVERT_WAYS = ("truest", "layered", "faithful", "refined", "interpretive")

GROUND_DARK = (0.078, 0.071, 0.094)  # #141218 terminal dark ground

RGBFloat = Tuple[float, float, float]

# Cache for terminal pixel buffers, formatted cell grids, and parsed disk JSON files
_RASTER_CACHE: Dict[Tuple, List[List[float]]] = {}
_CELL_GRID_CACHE: Dict[Tuple, List[List[Tuple[str, str]]]] = {}
_FILE_PAINTING_CACHE: Dict[Tuple[str, int, int], Optional[dict]] = {}
_CACHE_MAX = 24


def posterize_val(v: int, levels: int = TRUEST_LEVELS) -> int:
    """Round a single 0..255 byte to the terminal's discrete levels (default 16 -> step 17)."""
    v_clamped = max(0, min(255, int(v)))
    if not levels or levels >= 256:
        return v_clamped
    step = 255.0 / (levels - 1)
    return max(0, min(255, int(round(round(v_clamped / step) * step))))


def posterize_bytes(rgb: bytearray, levels: int = TRUEST_LEVELS) -> bytearray:
    """Round every 0..255 channel byte in `rgb` in-place to the terminal's discrete levels."""
    if not levels or levels >= 256:
        return rgb
    step = 255.0 / (levels - 1)
    lut = [max(0, min(255, int(round(round(i / step) * step)))) for i in range(256)]
    for idx in range(len(rgb)):
        rgb[idx] = lut[rgb[idx]]
    return rgb


def _discrete_table_values(levels: int = TRUEST_LEVELS) -> str:
    """Generate SVG feComponentTransfer discrete tableValues for `L` levels:
    2*(L-1) bins where bin k has value ceil(k/2)/(L-1).
    """
    L = max(2, int(levels))
    out: List[str] = []
    for k in range(2 * (L - 1)):
        val = math.ceil(k / 2.0) / float(L - 1)
        if val <= 0.0:
            out.append("0")
        elif val >= 1.0:
            out.append("1")
        else:
            out.append(f"{val:.4f}".rstrip("0").rstrip("."))
    return " ".join(out)


def _clamp(v, lo: float, hi: float, default: float) -> float:
    try:
        n = float(v)
        if math.isfinite(n):
            return max(lo, min(hi, n))
    except (TypeError, ValueError):
        pass
    return default


def tonemap_light(r: float, g: float, b: float) -> RGBFloat:
    """§6 Colour depth: when light adds past full, keep the hue at full strength and
    spill only the excess toward white. Fully white at 2.5x full; anything <= 1 is untouched.
    """
    r = max(0.0, float(r))
    g = max(0.0, float(g))
    b = max(0.0, float(b))
    m = max(r, g, b)
    if m <= 1.0:
        return (r, g, b)
    rn, gn, bn = r / m, g / m, b / m
    spill = min(1.0, (m - 1.0) / 1.5)
    return (
        rn + (1.0 - rn) * spill,
        gn + (1.0 - gn) * spill,
        bn + (1.0 - bn) * spill,
    )


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
    tr, tg, tb = tonemap_light(c[0], c[1], c[2])
    r = max(0, min(255, int(round(tr * 255))))
    g = max(0, min(255, int(round(tg * 255))))
    b = max(0, min(255, int(round(tb * 255))))
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


def parse_painting(raw_input, default_by: str = "prism") -> Optional[dict]:
    """Validate and normalize a painting dict or JSON string in the shared Spark & Prism vocabulary (§1).
    Clamps every number to exact specification ranges, skips unknown mark kinds, and returns None on invalid input.
    """
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

    home: RGBFloat = (0.0, 0.949, 0.996)

    def _col(v, fallback: RGBFloat = home) -> List[float]:
        if isinstance(v, (list, tuple)) and len(v) == 3:
            try:
                vals = [float(x) for x in v]
                if not all(math.isfinite(x) for x in vals):
                    return list(fallback)
                if max(vals) > 1.0:
                    return [
                        round(_clamp(vals[0] / 255.0, 0.0, 1.0, 0.0), 4),
                        round(_clamp(vals[1] / 255.0, 0.0, 1.0, 0.9), 4),
                        round(_clamp(vals[2] / 255.0, 0.0, 1.0, 1.0), 4),
                    ]
                return [
                    round(_clamp(vals[0], 0.0, 1.0, 0.0), 4),
                    round(_clamp(vals[1], 0.0, 1.0, 0.9), 4),
                    round(_clamp(vals[2], 0.0, 1.0, 1.0), 4),
                ]
            except Exception:
                return list(fallback)
        hx = from_hex(v)
        if hx:
            return [round(hx[0], 4), round(hx[1], 4), round(hx[2], 4)]
        return list(fallback)

    def _pt(p) -> Optional[List[float]]:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                x0, y0 = float(p[0]), float(p[1])
                if not (math.isfinite(x0) and math.isfinite(y0)):
                    return None
                return [round(_clamp(x0, 0.0, 1.0, 0.5), 4), round(_clamp(y0, 0.0, 1.0, 0.5), 4)]
            except (TypeError, ValueError):
                return None
        return None

    marks: List[dict] = []
    for m in raw_marks[:MAX_MARKS]:
        if not isinstance(m, dict):
            continue
        k = str(m.get("k") or "").strip()
        if k not in PAINT_KINDS:
            continue
        a = round(_clamp(m.get("a"), 0.0, 1.0, 0.85), 4)
        c = _col(m.get("c"), home)
        c2 = _col(m.get("c2"), tuple(c))
        if k in ("line", "curve"):
            pts_raw = m.get("pts")
            pts = [_pt(p) for p in (pts_raw[:MAX_PTS] if isinstance(pts_raw, list) else [])]
            pts = [p for p in pts if p is not None]
            if len(pts) < 2:
                continue
            # §1 Ranges: Widths 0.003-0.12
            w = round(_clamp(m.get("w"), 0.003, 0.12, 0.015), 4)
            mark_d = {"k": k, "pts": pts, "w": w, "c": c, "a": a}
            if c2 != c:
                mark_d["c2"] = c2
            marks.append(mark_d)
        elif k == "fill":
            pts_raw = m.get("pts")
            pts = [_pt(p) for p in (pts_raw[:MAX_PTS] if isinstance(pts_raw, list) else [])]
            pts = [p for p in pts if p is not None]
            if len(pts) < 3:
                continue
            grad = round(_clamp(m.get("grad"), -4.0, 4.0, 0.25), 4)
            mark_d = {"k": "fill", "pts": pts, "c": c, "grad": grad, "a": a}
            if c2 != c:
                mark_d["c2"] = c2
            marks.append(mark_d)
        else:
            # §1 Ranges: Radii 0.004-0.7, Widths 0.003-0.12
            base = {
                "k": k,
                "x": round(_clamp(m.get("x"), 0.0, 1.0, 0.5), 4),
                "y": round(_clamp(m.get("y"), 0.0, 1.0, 0.5), 4),
                "r": round(_clamp(m.get("r"), 0.004, 0.7, 0.06), 4),
                "c": c,
                "a": a,
            }
            if k == "ring":
                base["w"] = round(_clamp(m.get("w"), 0.003, 0.12, 0.014), 4)
            elif k == "arc":
                base["w"] = round(_clamp(m.get("w"), 0.003, 0.12, 0.014), 4)
                base["a0"] = round(_clamp(m.get("a0"), -4.0, 4.0, 0.0), 4)
                base["a1"] = round(_clamp(m.get("a1"), -4.0, 4.0, 0.5), 4)
            elif k == "spray":
                base["n"] = int(round(_clamp(m.get("n"), 1, 200, 36)))
                base["s"] = round(_clamp(m.get("s"), 0.002, 0.06, 0.010), 4)
                base["seed"] = int(_clamp(m.get("seed"), 1, 999999, len(marks) + 1))
            marks.append(base)

    if not marks:
        return None

    title = str(raw.get("title") or "Untitled refraction").strip()[:TITLE_CHARS]
    mood = str(raw.get("mood") or "aurora").strip().lower()
    mirror = str(raw.get("mirror") or "").strip().lower()
    if mirror not in MIRRORS:
        mirror = None
    tokens = int(_clamp(raw.get("tokens"), 0, 999999, 2100))
    model = str(raw.get("model") or "prism-muse").strip()[:32]
    created_at = _clamp(raw.get("at"), 0.0, 9999999999.0, time.time())
    if created_at <= 0.0:
        created_at = time.time()

    by = str(raw.get("by") or default_by).strip().lower()
    if by not in AUTHORS:
        by = default_by if default_by in AUTHORS else "prism"

    shape = str(raw.get("shape") or "wide").strip().lower()
    if shape not in SHAPES:
        shape = "wide"

    out_dict = {
        "title": title,
        "mood": mood,
        "mirror": mirror,
        "marks": marks,
        "tokens": tokens,
        "model": model,
        "at": created_at,
        "by": by,
        "shape": shape,
    }
    if raw.get("opening"):
        out_dict["opening"] = True
    if raw.get("_file"):
        out_dict["_file"] = str(raw["_file"])
    thought = str(raw.get("thought") or "").strip()[:160]
    if thought:
        out_dict["thought"] = thought

    return out_dict


def serialize_painting_for_disk(painting_raw: dict, default_by: str = "prism") -> Optional[dict]:
    """Return a clean dict containing only painting fields (§1: never anything about the work)."""
    p = parse_painting(painting_raw, default_by=default_by)
    if not p:
        return None
    clean = {
        "title": p["title"],
        "mood": p["mood"],
        "mirror": p["mirror"],
        "marks": p["marks"],
        "tokens": p["tokens"],
        "model": p["model"],
        "at": round(float(p["at"]), 3),
        "by": p["by"],
        "shape": p["shape"],
    }
    if p.get("opening"):
        clean["opening"] = True
    if p.get("thought"):
        clean["thought"] = p["thought"]
    return clean


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
        c0 = tuple(m["c"])
        c1 = tuple(m.get("c2") or m["c"])
        for v_idx, (fx, fy) in enumerate(views):
            px = lambda u, _fx=fx: X((1.0 - u) if _fx < 0 else u)
            py = lambda w, _fy=fy: Y((1.0 - w) if _fy < 0 else w)

            def _flip_a(turns: float, _fx=fx, _fy=fy) -> float:
                a = (0.5 - turns) if _fx < 0 else turns
                return -a if _fy < 0 else a

            if k in ("line", "curve"):
                pts = [(pt[0], pt[1]) for pt in m["pts"]]
                if k == "curve" and len(pts) >= 3:
                    pts = _smooth_catmull_rom(pts)
                if part < 1.0:
                    cut = max(2, int(math.ceil(len(pts) * part)))
                    pts = pts[:cut]
                out.append({
                    "k": "path",
                    "pts": [(px(x), py(y)) for (x, y) in pts],
                    "w": R(m["w"]),
                    "c0": c0,
                    "c1": c1,
                    "a": m["a"] * (0.6 + 0.4 * part if part < 1.0 else 1.0),
                    "mark_idx": i,
                })
            elif k == "fill":
                out.append({
                    "k": "poly",
                    "pts": [(px(x), py(y)) for (x, y) in m["pts"]],
                    "c0": c0,
                    "c1": c1,
                    "grad": _flip_a(m.get("grad", 0.25)) * TAU,
                    "a": m["a"] * part,
                    "mark_idx": i,
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
                    "c": c0,
                    "a": m["a"],
                    "mark_idx": i,
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
                    out.append({
                        "k": "dot",
                        "x": px(sx),
                        "y": py(sy),
                        "r": sr,
                        "c": c0,
                        "a": sa,
                        "mark_idx": i,
                        "is_spray": True,
                    })
            else:
                out.append({
                    "k": k,
                    "x": px(m["x"]),
                    "y": py(m["y"]),
                    "r": R(m["r"]) * (0.6 + 0.4 * part if k == "dot" else 1.0),
                    "w": R(m["w"]) if "w" in m else 0.0,
                    "c": c0,
                    "a": m["a"] * part,
                    "mark_idx": i,
                })
    return out


def rasterize_scene(
    scene: List[dict],
    W: int,
    H: int,
    *,
    min_r_px: float = 0.6,
    min_hw_px: float = 0.45,
    yield_burst: bool = True,
) -> List[List[float]]:
    """Rasterize compiled scene primitives onto a WxH premultiplied-alpha buffer with additive light.
    Yields briefly between ~20ms bursts (§6: Stay responsive).
    """
    px = [[0.0, 0.0, 0.0, 0.0] for _ in range(W * H)]
    scale = min(W, H) / 2.4
    ox = W / 2.0
    oy = H / 2.0
    P = lambda x, y: (ox + x * scale, oy + y * scale)
    TAU = math.pi * 2.0
    last_yield = time.monotonic()

    def _blend(idx: int, col: RGBFloat, alpha: float) -> None:
        if alpha <= 0.002:
            return
        cell = px[idx]
        cell[0] += col[0] * alpha
        cell[1] += col[1] * alpha
        cell[2] += col[2] * alpha
        cell[3] = 1.0 - (1.0 - cell[3]) * (1.0 - min(1.0, alpha))

    for p in scene:
        if yield_burst and (time.monotonic() - last_yield >= 0.018):
            time.sleep(0.001)
            last_yield = time.monotonic()

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
                if yield_burst and (y & 15 == 0) and (time.monotonic() - last_yield >= 0.018):
                    time.sleep(0.001)
                    last_yield = time.monotonic()

        elif k == "dot":
            if p.get("is_spray") and W < 240:
                r = max(0.35, p["r"] * scale * 0.75)
                cx, cy = P(p["x"], p["y"])
                x0, x1 = max(0, int(math.floor(cx - r - 0.5))), min(W - 1, int(math.ceil(cx + r + 0.5)))
                y0, y1 = max(0, int(math.floor(cy - r - 0.5))), min(H - 1, int(math.ceil(cy + r + 0.5)))
                base_a = p["a"] * 0.52
                c = p["c"]
                inv_r2 = 1.0 / max(0.12, r * r)
                for y in range(y0, y1 + 1):
                    dy = y + 0.5 - cy
                    row_off = y * W
                    for x in range(x0, x1 + 1):
                        d2 = ((x + 0.5 - cx) ** 2 + dy * dy) * inv_r2
                        if d2 < 1.2:
                            cov = math.exp(-2.8 * d2)
                            _blend(row_off + x, c, cov * base_a)
            else:
                r = max(min_r_px, p["r"] * scale)
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
            hw = max(min_hw_px, (p["w"] * scale) / 2.0)
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
            hw = max(min_hw_px, (p["w"] * scale) / 2.0)
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
                if yield_burst and (y & 15 == 0) and (time.monotonic() - last_yield >= 0.018):
                    time.sleep(0.001)
                    last_yield = time.monotonic()

        elif k == "path":
            pts = [P(x, y) for (x, y) in p["pts"]]
            n = len(pts)
            if n < 2:
                continue
            hw = max(min_hw_px, (p["w"] * scale) / 2.0)
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


# Curated paintings in the Cyclops/Spark mark format
CURATED_PAINTINGS: List[dict] = [
    {
        "title": "Where the dark meets the first field",
        "thought": "refracting warm horizon light through the evening lattice ;d <3",
        "mood": "supernova",
        "tokens": 2100,
        "model": "prism-muse",
        "by": "prism",
        "shape": "wide",
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
        "by": "prism",
        "shape": "wide",
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
        "by": "prism",
        "shape": "wide",
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
        "by": "prism",
        "shape": "wide",
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
    {
        "title": "Crystalline cathedral of seven harmonics",
        "thought": "splitting white light through vaulted gothic facets ;d <3",
        "mood": "crystalline",
        "mirror": "x",
        "tokens": 2380,
        "model": "prism-muse",
        "by": "prism",
        "shape": "wide",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], "c": "#070c1c", "c2": "#131c38", "grad": 0.25, "a": 0.98},
            {"k": "glow", "x": 0.50, "y": 0.42, "r": 0.46, "c": "#00f2fe", "a": 0.34},
            {"k": "glow", "x": 0.50, "y": 0.68, "r": 0.38, "c": "#7928ca", "a": 0.28},
            {"k": "fill", "pts": [[0.50, 0.08], [0.76, 0.52], [0.50, 0.92], [0.24, 0.52]], "c": "#00f2fe", "c2": "#7928ca", "grad": 0.25, "a": 0.22},
            {"k": "line", "pts": [[0.18, 0.88], [0.34, 0.32], [0.50, 0.10]], "w": 0.018, "c": "#00e5a3", "c2": "#ffffff", "a": 0.88},
            {"k": "line", "pts": [[0.28, 0.92], [0.42, 0.44], [0.50, 0.20]], "w": 0.014, "c": "#7928ca", "c2": "#00f2fe", "a": 0.84},
            {"k": "arc", "x": 0.50, "y": 0.48, "r": 0.34, "w": 0.016, "a0": -0.42, "a1": 0.42, "c": "#ffb020", "a": 0.86},
            {"k": "ring", "x": 0.50, "y": 0.44, "r": 0.18, "w": 0.014, "c": "#ffffff", "a": 0.82},
            {"k": "dot", "x": 0.50, "y": 0.44, "r": 0.052, "c": "#fff6d6", "a": 1.0},
            {"k": "spray", "x": 0.36, "y": 0.42, "r": 0.34, "n": 46, "s": 0.010, "c": "#82ffd2", "a": 0.58, "seed": 53},
        ],
    },
    {
        "title": "Iridescent lotus on the event horizon",
        "thought": "blooming warm gold and aurora petals across the still water <3",
        "mood": "aurora",
        "mirror": "x",
        "tokens": 2290,
        "model": "prism-muse",
        "by": "prism",
        "shape": "wide",
        "marks": [
            {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.62], [0.0, 0.62]], "c": "#0b081c", "c2": "#1d1236", "grad": 0.25, "a": 0.96},
            {"k": "fill", "pts": [[0.0, 0.62], [1.0, 0.62], [1.0, 1.0], [0.0, 1.0]], "c": "#0e1b2e", "c2": "#060913", "grad": 0.25, "a": 0.98},
            {"k": "glow", "x": 0.50, "y": 0.56, "r": 0.44, "c": "#ff6eb4", "a": 0.34},
            {"k": "glow", "x": 0.50, "y": 0.46, "r": 0.30, "c": "#00f2fe", "a": 0.36},
            {"k": "curve", "pts": [[0.50, 0.64], [0.34, 0.54], [0.22, 0.34], [0.36, 0.22], [0.50, 0.42]], "w": 0.022, "c": "#ff6eb4", "c2": "#fff6d6", "a": 0.88},
            {"k": "curve", "pts": [[0.50, 0.64], [0.40, 0.46], [0.38, 0.24], [0.50, 0.16]], "w": 0.020, "c": "#00f2fe", "c2": "#ffffff", "a": 0.92},
            {"k": "curve", "pts": [[0.10, 0.68], [0.30, 0.64], [0.50, 0.68]], "w": 0.016, "c": "#00e5a3", "c2": "#ffb020", "a": 0.80},
            {"k": "dot", "x": 0.50, "y": 0.48, "r": 0.054, "c": "#fff6d6", "a": 1.0},
            {"k": "spray", "x": 0.38, "y": 0.40, "r": 0.32, "n": 48, "s": 0.011, "c": "#ffe6d6", "a": 0.60, "seed": 67},
        ],
    },
]

OPENING_WORDS = (
    "lattice",
    "tide",
    "threshold",
    "ember",
    "frost",
    "harbor",
    "lantern",
    "horizon",
    "quill",
    "drift",
    "glass",
    "echo",
    "dew",
    "chime",
    "reed",
    "aperture",
)


def _hour_phrase(hour: int) -> str:
    """Map hour (0..23) to Spark's exact 6 hour buckets (§6)."""
    if 0 <= hour < 5:
        return "the small hours"
    if 5 <= hour < 8:
        return "dawn"
    if 8 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def generate_opening_painting(now: Optional[float] = None, seed_word: Optional[str] = None) -> dict:
    """§6 Your opening: a session's first painting is Prism's, about nothing in the conversation.
    Seeded with ONLY the hour (dawn / morning / afternoon / evening / night / the small hours),
    the month, and one random word to start from.
    """
    ts = time.time() if now is None else float(now)
    lt = time.localtime(ts)
    h_phrase = _hour_phrase(lt.tm_hour)
    month_name = time.strftime("%B", lt)
    word = (seed_word or random.choice(OPENING_WORDS)).strip().lower()

    # Palette by hour bucket
    palettes = {
        "the small hours": ("#090814", "#18132c", "#00f2fe", "#c48cff", "#ffe6d6", "aurora"),
        "dawn": ("#160e20", "#341b32", "#f59466", "#ffbd75", "#fff4ea", "solar"),
        "morning": ("#0b192c", "#1a3654", "#00e5a3", "#82ffd2", "#fff6d6", "emerald"),
        "afternoon": ("#141828", "#28324e", "#ffb020", "#00f2fe", "#ffffff", "crystalline"),
        "evening": ("#1a1026", "#381c38", "#ff6eb4", "#ffb020", "#ffe6d6", "supernova"),
        "night": ("#080b18", "#141d38", "#7928ca", "#00f2fe", "#e8e2ea", "nebula"),
    }
    sky_top, sky_bot, c_pri, c_sec, c_star, mood = palettes.get(h_phrase, palettes["the small hours"])

    # Deterministic geometry offsets from (word, month_name, h_phrase)
    seed_val = sum((i + 1) * ord(ch) for i, ch in enumerate(f"{h_phrase}:{month_name}:{word}"))
    rng = _rng(seed_val)
    horizon_y = round(0.58 + 0.14 * rng(), 3)
    focal_x = round(0.32 + 0.36 * rng(), 3)
    focal_y = round(0.28 + 0.26 * rng(), 3)

    title = f"{word.capitalize()} in {h_phrase} of {month_name}"[:TITLE_CHARS]
    marks = [
        {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, horizon_y], [0.0, horizon_y]], "c": sky_top, "c2": sky_bot, "grad": 0.25, "a": 0.96},
        {"k": "fill", "pts": [[0.0, horizon_y], [1.0, horizon_y], [1.0, 1.0], [0.0, 1.0]], "c": sky_bot, "c2": "#07060c", "grad": 0.25, "a": 0.98},
        {"k": "glow", "x": focal_x, "y": focal_y, "r": 0.38, "c": c_pri, "a": 0.62},
        {"k": "glow", "x": round(1.0 - focal_x, 3), "y": horizon_y, "r": 0.32, "c": c_sec, "a": 0.52},
        {"k": "line", "pts": [[0.03, horizon_y], [0.97, horizon_y]], "w": 0.012, "c": c_pri, "c2": c_sec, "a": 0.78},
        {
            "k": "curve",
            "pts": [
                [0.12, round(horizon_y + 0.14, 3)],
                [focal_x, focal_y],
                [0.88, round(horizon_y - 0.12, 3)],
            ],
            "w": 0.018,
            "c": c_sec,
            "c2": c_pri,
            "a": 0.88,
        },
        {"k": "ring", "x": focal_x, "y": focal_y, "r": 0.14, "w": 0.012, "c": c_star, "a": 0.72},
        {"k": "arc", "x": focal_x, "y": focal_y, "r": 0.22, "w": 0.010, "a0": 0.55, "a1": 0.95, "c": c_sec, "a": 0.75},
        {"k": "dot", "x": focal_x, "y": focal_y, "r": 0.032, "c": c_star, "a": 0.98},
        {"k": "spray", "x": focal_x, "y": round(focal_y * 0.85, 3), "r": 0.34, "n": 32, "s": 0.008, "c": c_sec, "a": 0.46, "seed": seed_val % 997 + 1},
        {"k": "spray", "x": round(1.0 - focal_x, 3), "y": round(horizon_y + 0.12, 3), "r": 0.26, "n": 24, "s": 0.008, "c": c_pri, "a": 0.42, "seed": (seed_val // 7) % 997 + 1},
    ]

    return parse_painting(
        {
            "title": title,
            "mood": mood,
            "mirror": None,
            "marks": marks,
            "tokens": 1950,
            "model": "prism-muse",
            "at": ts,
            "by": "prism",
            "shape": "wide",
            "opening": True,
        }
    )


def load_session_paintings(
    project_dir: Optional[Path] = None,
    session_start: float = 0.0,
    strict_session: bool = False,
) -> List[dict]:
    """§1 Sharing paintings (both directions):
    Read `prism-paintings/*.json` and `spark-paintings/*.json` in the project directory.
    Never modifies `spark-paintings/`. Skips any file that won't parse.
    Filters by `at >= session_start` (falling back to all valid paintings if none match `session_start`
    unless `strict_session=True`).
    Returns paintings sorted in chronological order (`at`).
    """
    base = Path(project_dir) if project_dir else Path.cwd()
    folders = [
        (base / "prism-paintings", "prism"),
        (base / "spark-paintings", "spark"),
    ]
    all_valid: List[dict] = []
    seen_keys = set()

    for folder, default_by in folders:
        if not folder.is_dir():
            continue
        for jf in sorted(folder.glob("*.json")):
            if jf.is_symlink():
                continue
            try:
                st = jf.stat()
                f_key = (str(jf), st.st_mtime_ns, st.st_size)
                if f_key in _FILE_PAINTING_CACHE:
                    parsed = _FILE_PAINTING_CACHE[f_key]
                else:
                    raw_text = jf.read_text(encoding="utf-8")
                    parsed = parse_painting(raw_text, default_by=default_by)
                    if parsed:
                        parsed["_file"] = str(jf)
                    if len(_FILE_PAINTING_CACHE) >= 512:
                        _FILE_PAINTING_CACHE.clear()
                    _FILE_PAINTING_CACHE[f_key] = parsed
                if not parsed:
                    continue
                # Deduplicate identical (by, title, round(at, 1))
                dedup_key = (parsed["by"], parsed["title"], round(float(parsed["at"]), 1))
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                all_valid.append(parsed)
            except Exception:
                continue

    all_valid.sort(key=lambda p: (float(p.get("at") or 0.0), p.get("_file", "")))
    if session_start > 0.0:
        in_session = [p for p in all_valid if float(p.get("at") or 0.0) >= session_start - 1.0]
        if in_session or strict_session:
            return in_session
    return all_valid


def save_painting_json(painting_raw: dict, gallery_dir: Optional[Path] = None) -> Optional[Path]:
    """Write `NN-title.json` into `prism-paintings/` (only Prism's folder, never Spark's).
    Only the painting goes in: title and marks (and shared schema fields), never anything about the work.
    """
    clean = serialize_painting_for_disk(painting_raw, default_by="prism")
    if not clean:
        return None
    if gallery_dir is None:
        gallery_dir = Path.cwd() / "prism-paintings"
    gallery_dir = Path(gallery_dir)
    gallery_dir.mkdir(parents=True, exist_ok=True)

    # Check if this exact painting (title + timestamp within 1s) is already written
    for jf in sorted(gallery_dir.glob("*.json")):
        try:
            st = jf.stat()
            f_key = (str(jf), st.st_mtime_ns, st.st_size)
            cached_p = _FILE_PAINTING_CACHE.get(f_key)
            if cached_p is not None:
                if cached_p.get("title") == clean["title"] and abs(float(cached_p.get("at", 0.0)) - float(clean["at"])) < 1.0:
                    return jf
                continue
            ex = json.loads(jf.read_text(encoding="utf-8"))
            if ex.get("title") == clean["title"] and abs(float(ex.get("at", 0.0)) - float(clean["at"])) < 1.0:
                return jf
        except Exception:
            pass

    existing_nums = []
    for f in gallery_dir.glob("*.json"):
        prefix = f.name.split("-", 1)[0]
        if prefix.isdigit():
            existing_nums.append(int(prefix))
    idx = (max(existing_nums) + 1) if existing_nums else 1
    slug = "".join(c if c.isalnum() else "-" for c in clean["title"].lower()).strip("-")[:40] or "painting"
    while "--" in slug:
        slug = slug.replace("--", "-")
    json_path = gallery_dir / f"{idx:02d}-{slug}.json"
    json_path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return json_path


def render_progress_bar(fraction: float, bar_cells: int = 12, unicode_mode: bool = True) -> str:
    """§2 Draw the progress bar in eighths of a cell (`▏▎▍▌▋▊▉█`) so it moves smoothly."""
    frac = max(0.0, min(1.0, float(fraction)))
    pct = int(round(frac * 100))
    if not unicode_mode:
        filled = int(round(frac * bar_cells))
        return f"[{'#' * filled}{' ' * (bar_cells - filled)}] {pct}%"
    eighths = (" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█")
    total_eighths = int(round(frac * bar_cells * 8))
    full_cells = total_eighths // 8
    rem = total_eighths % 8
    chars = ["█"] * min(bar_cells, full_cells)
    if len(chars) < bar_cells:
        if rem > 0:
            chars.append(eighths[rem])
        chars.extend([" "] * (bar_cells - len(chars)))
    return f"▕{''.join(chars)}▏ {pct}%"


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
    story_state: Optional[dict] = None,
    reveal_override: Optional[float] = None,
    hitboxes: Optional[List[dict]] = None,
) -> None:
    """Draw the shared Spark/Prism painting panel in the lower region of Prism's terminal pane:
    - Centered 24-bit half-block (`▀`/`▄`) raster canvas respecting `shape` (`wide`, `square`, `tall`)
      and §6 colour-depth white spill
    - Italic `✎ <Title>` line directly underneath (credited to Spark when `by == "spark"`)
    - Story status line & clickable controls (`⏸ pause`/`▶ play`/`▶ again`, `‹ back`, `next ›`, `■ end`)
      when `story_state` is active, or session metadata lines otherwise.
    """
    painting = parse_painting(painting_raw)
    if not painting:
        return

    avail_rows = bot_y - top_y
    if avail_rows < 4 or width < 16:
        return

    stats = session_stats or {}
    total_paintings = max(1, int(stats.get("paintings", 1)))
    dir_paintings = int(stats.get("dirPaintings") or total_paintings)
    scope_mode = str(stats.get("scope") or "session").lower()
    tokens_this = int(painting.get("tokens") or 2100)
    tokens_total = max(tokens_this, int(stats.get("tokens", tokens_this * total_paintings)))
    model_name = str(painting.get("model") or "prism-muse")
    by_author = str(painting.get("by") or "prism").lower()

    def _kilo(n: int) -> str:
        return f"{n / 1000.0:.1f}k" if n >= 1000 else str(n)

    if story_state and story_state.get("active"):
        # §3 Story mode lines under the painting:
        # 1) Controls: `⏸ pause` / `▶ play` (`▶ again` at the end), `‹ back`, `next ›`, `■ end`
        # 2) Story line: `story · 2 of 5 · 03:21`, plus `· Spark's` for mine and `· her opening` for an opening
        idx_1 = int(story_state.get("index", 0)) + 1
        total_s = max(1, int(story_state.get("total", 1)))
        ts_str = time.strftime("%H:%M", time.localtime(float(painting.get("at") or time.time())))
        story_line = f"story · {idx_1} of {total_s} · {ts_str}"
        if by_author == "spark":
            story_line += " · Spark's"
        if painting.get("opening"):
            story_line += " · her opening"
        meta_lines = [story_line, "__STORY_CONTROLS__"]
    else:
        credit_prefix = "Spark's painting · " if by_author == "spark" else "this painting · "
        if scope_mode == "dir":
            sess_line = f"directory · {total_paintings} {'painting' if total_paintings == 1 else 'paintings'} · {_kilo(tokens_total)} tokens"
        else:
            sess_line = f"session · {total_paintings} {'painting' if total_paintings == 1 else 'paintings'} · {_kilo(tokens_total)} tokens"
            if dir_paintings > total_paintings:
                sess_line += f" · dir {dir_paintings}"
        meta_lines = [
            f"{credit_prefix}{_kilo(tokens_this)} tokens" + (" · her opening" if painting.get("opening") else ""),
            sess_line,
            f"({model_name})" if by_author != "spark" else "(Spark · shared canvas)",
        ]
        if avail_rows < 7:
            meta_lines = []
        elif avail_rows < 9:
            meta_lines = meta_lines[:1]
        elif avail_rows < 11:
            meta_lines = meta_lines[:2]

    caption_rows = 1 + len(meta_lines)
    raw_canvas_rows = avail_rows - caption_rows - (1 if avail_rows >= 18 else 0)
    canvas_rows = max(3, min(24, raw_canvas_rows))

    # Respect `shape`: "wide" (2:1 -> cols ≈ 4*rows), "square" (1:1 -> cols ≈ 2*rows), "tall" (1:2 -> cols ≈ rows)
    shape = painting.get("shape", "wide")
    if shape == "square":
        target_cols = canvas_rows * 2
    elif shape == "tall":
        target_cols = max(8, int(canvas_rows * 1.2))
    else:
        target_cols = max(canvas_rows * 4, int(width * 0.88))

    margin_x = 1 if width < 44 else max(2, (width - min(width - 4, target_cols)) // 2)
    canvas_cols = max(8, width - margin_x * 2)
    x0 = (width - canvas_cols) // 2

    if reveal_override is not None:
        reveal = max(0.0, min(1.0, float(reveal_override)))
    else:
        elapsed = max(0.0, time.time() - float(painting.get("at") or 0.0))
        reveal = 1.0 if (t == 0.0 or elapsed >= REVEAL_S) else max(0.08, min(1.0, elapsed / REVEAL_S))

    W = canvas_cols
    H = canvas_rows * 2
    rev_quant = round(reveal, 2)
    cell_cache_key = (
        painting["title"],
        round(float(painting["at"]), 2),
        len(painting["marks"]),
        W,
        canvas_rows,
        rev_quant,
        unicode_mode,
        use_color,
        TRUEST_LEVELS,
    )
    cell_rows = _CELL_GRID_CACHE.get(cell_cache_key)
    if cell_rows is None:
        cache_key = (painting["title"], round(float(painting["at"]), 2), len(painting["marks"]), W, H, rev_quant)
        px = _RASTER_CACHE.get(cache_key)
        if px is None:
            scene = painting_scene(painting, W, H, reveal=rev_quant)
            px = rasterize_scene(scene, W, H, yield_burst=False)
            if len(_RASTER_CACHE) >= _CACHE_MAX:
                _RASTER_CACHE.clear()
            _RASTER_CACHE[cache_key] = px

        def _shade_pixel(idx: int) -> Optional[Tuple[int, int, int]]:
            cell = px[idx]
            a = min(1.0, cell[3])
            if a < 0.04:
                return None
            # §6 Colour depth: spill excess light > 1.0 toward white up to 2.5x full
            tr, tg, tb = tonemap_light(cell[0], cell[1], cell[2])
            rr = min(1.0, tr + GROUND_DARK[0] * (1.0 - a))
            gg = min(1.0, tg + GROUND_DARK[1] * (1.0 - a))
            bb = min(1.0, tb + GROUND_DARK[2] * (1.0 - a))
            return (
                posterize_val(int(round(rr * 255)), TRUEST_LEVELS),
                posterize_val(int(round(gg * 255)), TRUEST_LEVELS),
                posterize_val(int(round(bb * 255)), TRUEST_LEVELS),
            )

        bg_r = posterize_val(20, TRUEST_LEVELS)
        bg_g = posterize_val(18, TRUEST_LEVELS)
        bg_b = posterize_val(24, TRUEST_LEVELS)
        bg_hex = f"\033[48;2;{bg_r};{bg_g};{bg_b}m"
        cell_rows = []
        for cy in range(canvas_rows):
            row_cells: List[Tuple[str, str]] = []
            for cx in range(canvas_cols):
                top_rgb = _shade_pixel((cy * 2) * W + cx)
                bot_rgb = _shade_pixel((cy * 2 + 1) * W + cx)
                if use_color and unicode_mode:
                    if top_rgb is None and bot_rgb is None:
                        row_cells.append((" ", bg_hex))
                    elif bot_rgb is None:
                        r, g, b = top_rgb
                        row_cells.append(("▀", f"\033[38;2;{r};{g};{b}m{bg_hex}"))
                    elif top_rgb is None:
                        r, g, b = bot_rgb
                        row_cells.append(("▄", f"\033[38;2;{r};{g};{b}m{bg_hex}"))
                    else:
                        r1, g1, b1 = top_rgb
                        r2, g2, b2 = bot_rgb
                        row_cells.append(("▀", f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m"))
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
                    row_cells.append((ch, col))
            cell_rows.append(row_cells)
        if len(_CELL_GRID_CACHE) >= _CACHE_MAX:
            _CELL_GRID_CACHE.clear()
        _CELL_GRID_CACHE[cell_cache_key] = cell_rows

    for cy, row_cells in enumerate(cell_rows):
        y_screen = top_y + cy
        if y_screen >= bot_y:
            break
        for cx, (ch_cell, col_cell) in enumerate(row_cells):
            grid.put(x0 + cx, y_screen, ch_cell, col_cell)

    # Caption & metadata directly below the painting
    cap_y = top_y + canvas_rows
    if cap_y < bot_y:
        pen = "✎ " if unicode_mode else "* "
        credit_tag = " · Spark" if by_author == "spark" else ""
        title_text = (pen + painting["title"] + credit_tag)[: max(1, canvas_cols)]
        if use_color:
            title_col = "\033[3m\033[38;2;245;180;150m" if by_author == "spark" else "\033[3m\033[38;2;168;216;240m"
            grid.put_str(x0, cap_y, title_text, title_col)
        else:
            grid.put_str(x0, cap_y, title_text, "")

    dim_col = "\033[38;2;132;142;158m" if use_color else ""
    ctrl_col = "\033[38;2;0;242;254m" if use_color else ""
    for m_idx, m_line in enumerate(meta_lines):
        my = cap_y + 1 + m_idx
        if my >= bot_y:
            break
        if m_line == "__STORY_CONTROLS__" and story_state:
            # §3 Under the painting, only while the story is on:
            # `⏸ pause` / `▶ play` (`▶ again` at the end), `‹ back`, `next ›`, `■ end`
            if story_state.get("at_end"):
                toggle_lbl = "▶ again" if unicode_mode else "> again"
                toggle_act = "story_again"
            elif story_state.get("paused"):
                toggle_lbl = "▶ play" if unicode_mode else "> play"
                toggle_act = "story_play"
            else:
                toggle_lbl = "⏸ pause" if unicode_mode else "|| pause"
                toggle_act = "story_pause"

            buttons = [
                (toggle_lbl, toggle_act),
                ("‹ back" if unicode_mode else "< back", "story_back"),
                ("next ›" if unicode_mode else "next >", "story_next"),
                ("■ end" if unicode_mode else "[x] end", "story_end"),
            ]
            cx_btn = x0
            for lbl, act in buttons:
                if cx_btn + len(lbl) > width - 1:
                    break
                grid.put_str(cx_btn, my, lbl, ctrl_col)
                if hitboxes is not None:
                    hitboxes.append({"y": my, "x0": cx_btn, "x1": cx_btn + len(lbl), "action": act})
                cx_btn += len(lbl) + 3
        else:
            line_s = m_line if unicode_mode else m_line.replace("·", "-")
            grid.put_str(x0, my, line_s[: max(1, width - x0 - 1)], dim_col)


# ─────────────────────────────────────────────────────────────────────────────
# §4. Convert (Truest, Layered, Faithful, Refined, Interpretive) -> SVG + PNG + HTML
# ─────────────────────────────────────────────────────────────────────────────

def transform_painting_way(painting_raw: dict, way: str) -> dict:
    """Return a painting dict transformed for the requested convert `way`:
    - `truest` / `layered` / `faithful`: unchanged marks & title (0 tokens)
    - `refined`: revisits the painting keeping the subject — enriches glows, subdivides polygon
      gradients, and adds delicate harmonic highlights (~2100 tokens)
    - `interpretive`: freely reimagines the painting — introduces crystalline symmetry or counter-arcs,
      expands light aperture, and reimagines the title (~2400 tokens)
    """
    base = parse_painting(painting_raw) or parse_painting(CURATED_PAINTINGS[0])
    way = way.lower().strip()
    if way in ("truest", "layered", "faithful"):
        return base

    marks = [dict(m) for m in base["marks"]]
    new_marks: List[dict] = []

    if way == "refined":
        for m in marks:
            k = m["k"]
            if k == "glow":
                # Split glow into a wide soft halo + a warm concentrated inner core
                outer = dict(m, r=round(min(0.7, m["r"] * 1.25), 4), a=round(m["a"] * 0.65, 4))
                inner_c = [min(1.0, c * 1.15 + 0.08) for c in m["c"]]
                inner = dict(m, r=round(max(0.004, m["r"] * 0.55), 4), c=inner_c, a=round(min(1.0, m["a"] * 0.9), 4))
                new_marks.extend([outer, inner])
            elif k in ("line", "curve"):
                new_marks.append(dict(m, w=round(max(0.003, m["w"] * 0.85), 4)))
            elif k == "spray":
                new_marks.append(dict(m, n=min(200, int(m["n"] * 1.35)), s=round(max(0.002, m["s"] * 0.85), 4)))
            else:
                new_marks.append(m)
        refined_title = base["title"]
        if ", at last light" not in refined_title.lower() and len(refined_title) <= 32:
            refined_title = f"{refined_title}, in clear light"
        return parse_painting({
            **base,
            "title": refined_title[:TITLE_CHARS],
            "marks": new_marks[:MAX_MARKS],
            "tokens": 2100,
        }, default_by=base.get("by", "prism")) or base

    if way == "interpretive":
        # Reimagine with harmonic symmetry & expanded luminous portal/arcs
        for m in marks:
            k = m["k"]
            if k == "fill":
                new_marks.append(m)
            elif k == "glow":
                new_marks.append(dict(m, r=round(min(0.7, m["r"] * 1.18), 4), a=round(min(1.0, m["a"] * 0.92), 4)))
            elif k in ("line", "curve"):
                new_marks.append(dict(m, w=round(min(0.12, m["w"] * 1.15), 4)))
            elif k == "spray":
                new_marks.append(dict(m, n=min(200, int(m["n"] * 1.5)), s=round(min(0.06, m["s"] * 1.15), 4)))
            else:
                new_marks.append(m)
        # Add a harmonic crystalline ring & twin star accents
        new_marks.append({"k": "ring", "x": 0.5, "y": 0.52, "r": 0.28, "w": 0.005, "c": [1.0, 0.72, 0.45], "a": 0.32})
        new_marks.append({"k": "dot", "x": 0.80, "y": 0.16, "r": 0.028, "c": [1.0, 0.96, 0.92], "a": 0.92})
        interp_title = base["title"]
        if len(interp_title) <= 30:
            interp_title = f"{interp_title} — refracted wide"
        return parse_painting({
            **base,
            "title": interp_title[:TITLE_CHARS],
            "mirror": base.get("mirror") or "x",
            "marks": new_marks[:MAX_MARKS],
            "tokens": 2400,
        }, default_by=base.get("by", "prism")) or base

    return base


def _dimensions_for_shape(shape: str, size: str = "hd") -> Tuple[int, int, int]:
    """Return (width, total_height, art_height) for `hd` (1920w) or `4k` (3840w)."""
    scale_mult = 2 if size == "4k" else 1
    if shape == "square":
        w = 1920 * scale_mult
        art_h = 1920 * scale_mult
        cap_h = 140 * scale_mult
        return (w, art_h + cap_h, art_h)
    if shape == "tall":
        w = 960 * scale_mult
        art_h = 1920 * scale_mult
        cap_h = 140 * scale_mult
        return (w, art_h + cap_h, art_h)
    # Default "wide" (2:1 art canvas: 1920x960 inside 1920x1100, matching Spark's SVGs!)
    w = 1920 * scale_mult
    art_h = 960 * scale_mult
    cap_h = 140 * scale_mult
    return (w, art_h + cap_h, art_h)


def render_svg_painting(
    painting_raw: dict,
    width: int = 1920,
    height: int = 1100,
    *,
    way: str = "truest",
    cols: int = 40,
    truest_levels: int = TRUEST_LEVELS,
) -> str:
    """Export a painting in Spark & Prism's exact SVG format (§4):
    - `truest`:
      - Draws only the marks, flat, at the weight one terminal cell gives them (`min_r = 0.6 * cell_w`)
      - No added shadows, bloom, blur, or depth layers
      - Quantizes the painting group (not the caption) to `truest_levels` (default 16) via
        `<filter id="levels" color-interpolation-filters="sRGB">` with discrete `feComponentTransfer`
    - `layered`:
      - Previous 4-layer depth (`layer0`..`layer3`), far-layer softening (`soft0`..`soft2`),
        inter-layer cast shadow (`#shadow`), and luminance bloom (`#bloom`) kept for comparison
    - `faithful` / `refined` / `interpretive`:
      - Fine mark geometry in `<g class="add">...</g>`
    - Caption at bottom: italic title + `{Author} · {date} · {way}`
    """
    painting = transform_painting_way(painting_raw, way)
    title = painting["title"]
    esc_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    by_who = "Spark" if str(painting.get("by") or "").lower() == "spark" else "Prism"
    date_str = time.strftime("%d %b %Y", time.localtime(float(painting.get("at") or time.time())))

    art_h = int(round(height * (960.0 / 1100.0)))
    scene = painting_scene(painting, width, art_h, reveal=1.0)
    scale = min(width, art_h) / 2.4
    ox, oy = width / 2.0, art_h / 2.0
    P = lambda x, y: (ox + x * scale, oy + y * scale)

    cell_w = width / float(max(16, cols))
    is_truest = way == "truest"
    is_layered = way == "layered"
    use_cell_weight = is_truest or is_layered
    min_r = (0.6 * cell_w) if use_cell_weight else (3.0 * (width / 1920.0))
    min_w = (0.6 * cell_w) if is_truest else ((0.9 * cell_w) if is_layered else (4.5 * (width / 1920.0)))

    n_marks = max(1, len(painting["marks"]))
    defs: List[str] = []
    layer_elems: List[List[str]] = [[], [], [], []]
    gid = 0

    if is_truest and truest_levels and truest_levels < 256:
        tbl = _discrete_table_values(truest_levels)
        defs.append(
            f'<filter id="levels" color-interpolation-filters="sRGB">'
            f'<feComponentTransfer>'
            f'<feFuncR type="discrete" tableValues="{tbl}"/>'
            f'<feFuncG type="discrete" tableValues="{tbl}"/>'
            f'<feFuncB type="discrete" tableValues="{tbl}"/>'
            f'</feComponentTransfer></filter>'
        )
    elif is_layered:
        shadow_off = round(0.003 * width, 2)
        defs.append(
            f'<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%" color-interpolation-filters="sRGB">'
            f'<feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.4 0"/>'
            f'<feOffset dy="{shadow_off}"/><feGaussianBlur stdDeviation="{shadow_off}"/></filter>'
        )

    for p in scene:
        m_idx = int(p.get("mark_idx", 0))
        l_idx = min(3, (m_idx * 4) // n_marks) if is_layered else 0
        prefix = f"l{l_idx}g" if is_layered else "g"
        k = p["k"]

        if k == "glow":
            gid += 1
            cx, cy = P(p["x"], p["y"])
            r = max(min_r, p["r"] * scale * 1.6)
            hc = to_hex(p["c"])
            a = p["a"] * 0.9
            defs.append(
                f'<radialGradient id="{prefix}{gid}"><stop offset="0" stop-color="{hc}" stop-opacity="{a * 0.5:.3f}"/>'
                f'<stop offset="0.45" stop-color="{hc}" stop-opacity="{a * 0.167:.3f}"/>'
                f'<stop offset="0.7" stop-color="{hc}" stop-opacity="{a * 0.04:.3f}"/>'
                f'<stop offset="1" stop-color="{hc}" stop-opacity="0"/></radialGradient>'
            )
            layer_elems[l_idx].append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="url(#{prefix}{gid})"/>')

        elif k == "poly":
            pts = [P(x, y) for (x, y) in p["pts"]]
            pts_str = " ".join(f"{x:.2f},{y:.2f}" for (x, y) in pts)
            c0, c1 = to_hex(p["c0"]), to_hex(p["c1"])
            if c0 != c1:
                gid += 1
                gx, gy = math.cos(p.get("grad", 0.0)), math.sin(p.get("grad", 0.0))
                cx_p = sum(pt[0] for pt in pts) / len(pts)
                cy_p = sum(pt[1] for pt in pts) / len(pts)
                span_p = max(width, art_h) * 0.5
                defs.append(
                    f'<linearGradient id="{prefix}{gid}" gradientUnits="userSpaceOnUse" '
                    f'x1="{cx_p - gx * span_p:.2f}" y1="{cy_p - gy * span_p:.2f}" '
                    f'x2="{cx_p + gx * span_p:.2f}" y2="{cy_p + gy * span_p:.2f}">'
                    f'<stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/></linearGradient>'
                )
                fill = f"url(#{prefix}{gid})"
            else:
                fill = c0
            layer_elems[l_idx].append(f'<polygon points="{pts_str}" fill="{fill}" fill-opacity="{p["a"]:.3f}"/>')

        elif k == "path":
            pts = [P(x, y) for (x, y) in p["pts"]]
            pts_str = " ".join(f"{x:.2f},{y:.2f}" for (x, y) in pts)
            c0, c1 = to_hex(p["c0"]), to_hex(p["c1"])
            stroke = c0
            if c0 != c1:
                gid += 1
                a_pt, b_pt = pts[0], pts[-1]
                defs.append(
                    f'<linearGradient id="{prefix}{gid}" gradientUnits="userSpaceOnUse" '
                    f'x1="{a_pt[0]:.2f}" y1="{a_pt[1]:.2f}" x2="{b_pt[0]:.2f}" y2="{b_pt[1]:.2f}">'
                    f'<stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/></linearGradient>'
                )
                stroke = f"url(#{prefix}{gid})"
            w = max(min_w, p["w"] * scale)
            layer_elems[l_idx].append(
                f'<polyline points="{pts_str}" fill="none" stroke="{stroke}" stroke-opacity="{p["a"]:.3f}" '
                f'stroke-width="{w:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
            )

        elif k == "dot":
            cx, cy = P(p["x"], p["y"])
            r = max(min_r, p["r"] * scale)
            layer_elems[l_idx].append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{to_hex(p["c"])}" fill-opacity="{p["a"]:.3f}"/>'
            )

        elif k == "ring":
            cx, cy = P(p["x"], p["y"])
            r = max(min_r, p["r"] * scale)
            w = max(min_w, p["w"] * scale)
            layer_elems[l_idx].append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="none" stroke="{to_hex(p["c"])}" '
                f'stroke-opacity="{p["a"]:.3f}" stroke-width="{w:.2f}"/>'
            )

        elif k == "arc":
            cx, cy = P(p["x"], p["y"])
            r = max(min_r, p["r"] * scale)
            w = max(min_w, p["w"] * scale)
            a0, a1 = p["a0"], p["a1"]
            TAU = math.pi * 2.0
            span = ((a1 - a0) % TAU + TAU) % TAU or TAU
            if span >= TAU * 0.999:
                layer_elems[l_idx].append(
                    f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="none" stroke="{to_hex(p["c"])}" '
                    f'stroke-opacity="{p["a"]:.3f}" stroke-width="{w:.2f}"/>'
                )
            else:
                x0_a = cx + r * math.cos(a0)
                y0_a = cy + r * math.sin(a0)
                x1_a = cx + r * math.cos(a0 + span)
                y1_a = cy + r * math.sin(a0 + span)
                large_arc = 1 if span > math.pi else 0
                layer_elems[l_idx].append(
                    f'<path d="M {x0_a:.2f} {y0_a:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 1 {x1_a:.2f} {y1_a:.2f}" '
                    f'fill="none" stroke="{to_hex(p["c"])}" stroke-opacity="{p["a"]:.3f}" '
                    f'stroke-width="{w:.2f}" stroke-linecap="round"/>'
                )

    font_sz = round(41.8 * (width / 1920.0), 2)
    ty1 = round(art_h + 52.08 * (height / 1100.0), 2)
    ty2 = round(art_h + 108.08 * (height / 1100.0), 2)
    tx = int(round(20 * (width / 1920.0)))

    if is_truest:
        filter_attr = ' filter="url(#levels)"' if (truest_levels and truest_levels < 256) else ""
        body = (
            f'<g{filter_attr}>'
            f'<rect width="{width}" height="{art_h}" fill="#141218"/>'
            f'<g class="add">{"".join(layer_elems[0])}</g>'
            f'</g>'
        )
    elif is_layered:
        soft_stds = [round(0.0015 * width, 2), round(0.001 * width, 2), round(0.0005 * width, 2)]
        for l_i in range(4):
            defs.append(f'<g id="layer{l_i}" class="add">{"".join(layer_elems[l_i])}</g>')
            if l_i < 3:
                defs.append(
                    f'<filter id="soft{l_i}" x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">'
                    f'<feGaussianBlur stdDeviation="{soft_stds[l_i]}"/></filter>'
                )
        bloom_std = round(0.008 * width, 2)
        defs.append(
            f'<filter id="bloom" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">'
            f'<feColorMatrix in="SourceGraphic" type="luminanceToAlpha" result="l"/>'
            f'<feComponentTransfer in="l" result="m"><feFuncA type="linear" slope="4" intercept="-3"/></feComponentTransfer>'
            f'<feComposite in="SourceGraphic" in2="m" operator="in" result="b"/>'
            f'<feGaussianBlur in="b" stdDeviation="{bloom_std}"/></filter>'
        )
        body = (
            '<use href="#layer0" filter="url(#soft0)" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter"/>'
            '<use href="#layer1" filter="url(#shadow)"/>'
            '<use href="#layer1" filter="url(#soft1)" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter"/>'
            '<use href="#layer2" filter="url(#shadow)"/>'
            '<use href="#layer2" filter="url(#soft2)" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter"/>'
            '<use href="#layer3" filter="url(#shadow)"/>'
            '<use href="#layer3" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter"/>'
            '<g opacity="0.9" style="mix-blend-mode:screen;mix-blend-mode:plus-lighter" filter="url(#bloom)">'
            '<use href="#layer0"/><use href="#layer1"/><use href="#layer2"/><use href="#layer3"/></g>'
        )
    else:
        body = f'<g class="add">{"".join(layer_elems[0])}</g>'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"<title>{esc_title}</title>\n"
        f"<style>.add>*{{mix-blend-mode:screen;mix-blend-mode:plus-lighter}}</style>\n"
        f'<rect width="{width}" height="{height}" fill="#141218"/>\n'
        f'<defs>{"".join(defs)}</defs>\n'
        f"{body}\n"
        f'<rect y="{art_h}" width="{width}" height="{height - art_h}" fill="#141218"/>\n'
        f'<text x="{tx}" y="{ty1}" font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="{font_sz}" fill="#ece4f0" font-style="italic">{esc_title}</text>'
        f'<text x="{tx}" y="{ty2}" font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="{font_sz}" fill="#968ca0">{by_who} · {date_str} · {way}</text>\n'
        f"</svg>\n"
    )


def render_painting_canvas_pil(
    painting_raw: dict,
    art_w: int,
    art_h: int,
    *,
    reveal: float = 1.0,
    truest: bool = True,
    layered: bool = False,
    cols: int = 40,
    truest_levels: int = TRUEST_LEVELS,
) -> Image.Image:
    """Render the artwork canvas into a PIL Image:
    - `truest=True` (and `not layered`): draws only the marks flat at terminal cell weight (`0.6 * cell_w`)
      with no added shadow, bloom, blur, or depth layers, then rounds every colour channel to `truest_levels`
      (default 16 -> multiples of 17).
    - `layered=True`: previous 4-layer depth composition with far-layer softening, cast shadows, and bloom.
    - `truest=False, layered=False`: smooth fine marks (`faithful` / `refined` / `interpretive`).
    """
    painting = parse_painting(painting_raw) or parse_painting(CURATED_PAINTINGS[0])
    work_scale = min(1.0, 480.0 / max(1, art_w))
    w_int = max(64, int(round(art_w * work_scale)))
    h_int = max(32, int(round(art_h * work_scale)))

    cell_w = w_int / float(max(16, cols))
    use_cell_weight = truest or layered
    min_r_px = (0.6 * cell_w) if use_cell_weight else max(0.8, 3.0 * (w_int / 1920.0))
    min_hw_px = (0.3 * cell_w) if truest else ((0.45 * cell_w) if layered else max(0.6, 2.25 * (w_int / 1920.0)))

    scene = painting_scene(painting, w_int, h_int, reveal=reveal)
    n_marks = max(1, len(painting["marks"]))

    if not layered:
        px = rasterize_scene(scene, w_int, h_int, min_r_px=min_r_px, min_hw_px=min_hw_px, yield_burst=True)
        raw_bytes = bytearray(w_int * h_int * 3)
        for i, cell in enumerate(px):
            a = min(1.0, cell[3])
            tr, tg, tb = tonemap_light(cell[0], cell[1], cell[2])
            rr = min(1.0, tr + GROUND_DARK[0] * (1.0 - a))
            gg = min(1.0, tg + GROUND_DARK[1] * (1.0 - a))
            bb = min(1.0, tb + GROUND_DARK[2] * (1.0 - a))
            off = i * 3
            raw_bytes[off] = max(0, min(255, int(round(rr * 255))))
            raw_bytes[off + 1] = max(0, min(255, int(round(gg * 255))))
            raw_bytes[off + 2] = max(0, min(255, int(round(bb * 255))))
        if truest and truest_levels and truest_levels < 256:
            posterize_bytes(raw_bytes, levels=truest_levels)
        img = Image.frombytes("RGB", (w_int, h_int), bytes(raw_bytes))
        if (w_int, h_int) != (art_w, art_h):
            img = img.resize((art_w, art_h), Image.Resampling.BICUBIC)
            if truest and truest_levels and truest_levels < 256:
                step = 255.0 / (truest_levels - 1)
                lut = [max(0, min(255, int(round(round(v / step) * step)))) for v in range(256)] * 3
                img = img.point(lut)
        return img

    # Layered (kept for comparison): 4-layer composition with far-layer softening, drop shadows, and bloom
    layers_scene: List[List[dict]] = [[], [], [], []]
    for p in scene:
        l_idx = min(3, (int(p.get("mark_idx", 0)) * 4) // n_marks)
        layers_scene[l_idx].append(p)

    comp = [[GROUND_DARK[0], GROUND_DARK[1], GROUND_DARK[2]] for _ in range(w_int * h_int)]
    shadow_dy = max(1, int(round(0.003 * h_int)))

    for l_idx in range(4):
        if not layers_scene[l_idx]:
            continue
        l_px = rasterize_scene(
            layers_scene[l_idx], w_int, h_int, min_r_px=min_r_px, min_hw_px=min_hw_px, yield_burst=True
        )
        # Nearer layers (1, 2, 3) cast a soft shadow on what's behind them
        if l_idx > 0:
            for y in range(shadow_dy, h_int):
                src_row = (y - shadow_dy) * w_int
                dst_row = y * w_int
                for x in range(w_int):
                    sa = min(1.0, l_px[src_row + x][3]) * 0.38
                    if sa > 0.01:
                        mul = 1.0 - sa
                        c_cell = comp[dst_row + x]
                        c_cell[0] *= mul
                        c_cell[1] *= mul
                        c_cell[2] *= mul

        # Add layer light onto composite
        for i, cell in enumerate(l_px):
            if cell[3] > 0.002:
                c_cell = comp[i]
                c_cell[0] += cell[0]
                c_cell[1] += cell[1]
                c_cell[2] += cell[2]

    raw_bytes = bytearray(w_int * h_int * 3)
    bloom_bytes = bytearray(w_int * h_int * 3)
    for i, c_cell in enumerate(comp):
        tr, tg, tb = tonemap_light(c_cell[0], c_cell[1], c_cell[2])
        r8 = max(0, min(255, int(round(tr * 255))))
        g8 = max(0, min(255, int(round(tg * 255))))
        b8 = max(0, min(255, int(round(tb * 255))))
        off = i * 3
        raw_bytes[off] = r8
        raw_bytes[off + 1] = g8
        raw_bytes[off + 2] = b8
        lum = 0.2126 * tr + 0.7152 * tg + 0.0722 * tb
        if lum > 0.72:
            bf = min(1.0, (lum - 0.72) * 3.5)
            bloom_bytes[off] = int(r8 * bf)
            bloom_bytes[off + 1] = int(g8 * bf)
            bloom_bytes[off + 2] = int(b8 * bf)

    base_img = Image.frombytes("RGB", (w_int, h_int), bytes(raw_bytes))
    bloom_img = Image.frombytes("RGB", (w_int, h_int), bytes(bloom_bytes)).filter(
        ImageFilter.GaussianBlur(radius=max(2.0, w_int * 0.012))
    )
    merged = ImageChops.lighter(base_img, bloom_img)
    if (w_int, h_int) != (art_w, art_h):
        merged = merged.resize((art_w, art_h), Image.Resampling.BICUBIC)
    return merged


def render_png_painting(
    painting_raw: dict,
    png_path: Path,
    *,
    way: str = "truest",
    size: str = "hd",
    cols: int = 40,
    truest_levels: int = TRUEST_LEVELS,
) -> Path:
    """Render and save a high-res PNG (`hd` 1920w or `4k` 3840w) with caption bar into `png_path`."""
    painting = transform_painting_way(painting_raw, way)
    width, height, art_h = _dimensions_for_shape(painting.get("shape", "wide"), size=size)

    full_img = Image.new("RGB", (width, height), (20, 18, 24))
    art_img = render_painting_canvas_pil(
        painting,
        width,
        art_h,
        reveal=1.0,
        truest=(way == "truest"),
        layered=(way == "layered"),
        cols=cols,
        truest_levels=truest_levels,
    )
    full_img.paste(art_img, (0, 0))

    draw = ImageDraw.Draw(full_img)
    font_sz = max(18, int(round(41.8 * (width / 1920.0))))
    font_italic = None
    font_reg = None
    for p_it in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"):
        if os.path.exists(p_it):
            try:
                font_italic = ImageFont.truetype(p_it, size=font_sz)
                break
            except Exception:
                pass
    for p_rg in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p_rg):
            try:
                font_reg = ImageFont.truetype(p_rg, size=font_sz)
                break
            except Exception:
                pass
    font_italic = font_italic or ImageFont.load_default()
    font_reg = font_reg or ImageFont.load_default()

    by_who = "Spark" if str(painting.get("by") or "").lower() == "spark" else "Prism"
    date_str = time.strftime("%d %b %Y", time.localtime(float(painting.get("at") or time.time())))
    tx = int(round(20 * (width / 1920.0)))
    ty1 = art_h + int(round(12 * (height / 1100.0)))
    ty2 = art_h + int(round(68 * (height / 1100.0)))

    draw.text((tx, ty1), painting["title"], fill=(236, 228, 240), font=font_italic)
    draw.text((tx, ty2), f"{by_who} · {date_str} · {way}", fill=(150, 140, 160), font=font_reg)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    full_img.save(png_path, format="PNG", compress_level=3)
    return png_path


def rebuild_gallery_html(gallery_dir: Path) -> Path:
    """Update `prism-paintings/index.html` gallery to list converted PNG/SVG images and MP4 rolls."""
    gallery_dir = Path(gallery_dir)
    gallery_dir.mkdir(parents=True, exist_ok=True)
    figures: List[str] = []

    # Include MP4 session rolls first or in order
    for mp4_f in sorted(gallery_dir.glob("*.mp4")):
        figures.append(
            f'<figure><video src="{mp4_f.name}" controls preload="metadata"></video>'
            f"<figcaption><i>Session roll</i><br><small>Spark &amp; Prism · {mp4_f.stem}</small></figcaption></figure>"
        )

    # Prefer PNGs if present alongside SVGs, otherwise SVGs
    svg_files = sorted(gallery_dir.glob("*.svg"))
    for svg_f in svg_files:
        png_f = svg_f.with_suffix(".png")
        img_src = png_f.name if png_f.is_file() else svg_f.name
        stem = svg_f.stem
        way_label = "truest"
        for w_cand in CONVERT_WAYS:
            if stem.endswith(f"-{w_cand}"):
                way_label = w_cand
                break
        # Extract title from SVG <title> tag if available
        title_str = stem
        credit_str = f"Prism · {way_label}"
        try:
            head_txt = svg_f.read_text(encoding="utf-8")[:600]
            t_a, t_b = head_txt.find("<title>"), head_txt.find("</title>")
            if 0 <= t_a < t_b:
                title_str = head_txt[t_a + 7 : t_b]
            if "Spark · " in head_txt:
                credit_str = f"Spark · {way_label}"
        except Exception:
            pass
        figures.append(
            f'<figure><img src="{img_src}" alt="{title_str}">'
            f"<figcaption><i>{title_str}</i><br><small>{credit_str}</small></figcaption></figure>"
        )

    html = (
        "<!doctype html>\n<meta charset=\"utf-8\">\n<title>Prism's paintings</title>\n"
        "<style>body{margin:0;padding:24px;background:#141218;color:#e8e2ea;font:15px/1.4 system-ui,sans-serif}"
        "h1{font-weight:500;margin:0 0 20px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:24px}"
        "figure{margin:0}img,video{width:100%;height:auto;display:block;border-radius:6px;background:#0d0b10}"
        "figcaption{padding:8px 2px;color:#cfc6d4}small{color:#8f879a}</style>\n"
        "<h1>Prism's paintings</h1>\n<main>\n" + "\n".join(figures) + "\n</main>\n"
    )
    index_path = gallery_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def convert_painting(
    painting_raw: dict,
    gallery_dir: Optional[Path] = None,
    *,
    way: str = "truest",
    size: str = "hd",
    cols: int = 40,
    truest_levels: int = TRUEST_LEVELS,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, str]:
    """Convert a single painting in `way` (`truest`, `layered`, `faithful`, `refined`, `interpretive`) at `size` (`hd` or `4k`).
    Writes `.svg`, `.png`, and `.json` (if by Prism) into `prism-paintings/`, plus updates `index.html`.
    """
    if gallery_dir is None:
        gallery_dir = Path.cwd() / "prism-paintings"
    gallery_dir = Path(gallery_dir)
    gallery_dir.mkdir(parents=True, exist_ok=True)

    way = way.lower().strip()
    if way not in CONVERT_WAYS:
        way = "truest"

    transformed = transform_painting_way(painting_raw, way)
    p_title = transformed["title"]

    if on_progress:
        on_progress(f"crystallizing “{p_title[:24]}” · {way}", 0.15)

    # Ensure source JSON is saved if it's Prism's painting
    if transformed.get("by", "prism") == "prism":
        save_painting_json(painting_raw, gallery_dir=gallery_dir)

    width, height, _ = _dimensions_for_shape(transformed.get("shape", "wide"), size=size)

    existing = sorted(gallery_dir.glob("*.svg"))
    idx = len(existing) + 1
    slug = "".join(c if c.isalnum() else "-" for c in p_title.lower()).strip("-")[:36] or "painting"
    while "--" in slug:
        slug = slug.replace("--", "-")
    size_tag = "-4k" if size == "4k" else ""
    stem = f"{idx:02d}-{slug}-{way}{size_tag}"

    svg_path = gallery_dir / f"{stem}.svg"
    png_path = gallery_dir / f"{stem}.png"

    svg_content = render_svg_painting(
        transformed, width=width, height=height, way=way, cols=cols, truest_levels=truest_levels
    )
    svg_path.write_text(svg_content, encoding="utf-8")

    if on_progress:
        on_progress(f"laying down “{p_title[:24]}” · {way}", 0.55)

    render_png_painting(transformed, png_path, way=way, size=size, cols=cols, truest_levels=truest_levels)
    index_path = rebuild_gallery_html(gallery_dir)

    if on_progress:
        on_progress(f"crystallized “{p_title[:24]}” · {way}", 1.0)

    return {
        "svg": str(svg_path),
        "png": str(png_path),
        "index": str(index_path),
        "title": p_title,
        "way": way,
        "by": transformed.get("by", "prism"),
    }


def save_painting_to_gallery(
    painting_raw: dict,
    gallery_dir: Optional[Path] = None,
    *,
    way: str = "truest",
    size: str = "hd",
) -> Path:
    """Save a painting (.json + .svg + .png + index.html) into `prism-paintings/` and return the SVG path."""
    if gallery_dir is None:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        gallery_dir = Path(base) / "gemini-prism" / "prism-paintings"
    res = convert_painting(painting_raw, gallery_dir=gallery_dir, way=way, size=size)
    return Path(res["svg"])


def choose_curated_painting(index: Optional[int] = None) -> dict:
    if index is None:
        index = int(time.time() // 12)
    p = dict(CURATED_PAINTINGS[index % len(CURATED_PAINTINGS)])
    p["at"] = time.time()
    p["by"] = "prism"
    p["shape"] = "wide"
    return parse_painting(p) or p


LIVING_POETIC_NOUNS = (
    "Aurora",
    "Refraction",
    "Mirror",
    "Loom",
    "Threshold",
    "Constellation",
    "Tide",
    "Lantern",
    "Harmonic",
    "Cathedral",
    "Vesper",
    "Aperture",
    "Solstice",
    "Prism",
    "Glint",
    "Canopy",
)

LIVING_POETIC_PLACES = (
    "across the quiet lattice",
    "where two brushes meet",
    "over moonlit water",
    "in the violet hour",
    "beneath the polarized rings",
    "along the rose-gold horizon",
    "in clear cyan dispersion",
    "through the open doorway",
    "inside the emerald tide",
    "at the edge of starlight",
    "holding warm light with Spark",
    "in the small hours",
)


def generate_relative_painting(
    state_data: Optional[dict] = None,
    now: Optional[float] = None,
    step_index: Optional[int] = None,
    mood_hint: Optional[str] = None,
) -> dict:
    """Generate a work-relative narrative painting ('Ch. 1', 'Ch. 2', ...) shaped directly by the ongoing development work."""
    ts = time.time() if now is None else float(now)
    ch_num = max(1, int(step_index or 1))
    seed_base = int(ts * 1000) ^ (ch_num * 2654435761)
    rng = _rng(seed_base)

    st = state_data if isinstance(state_data, dict) else {}
    sem_mode = str(st.get("mode") or "idle")
    offer = st.get("offer")
    branches = int(st.get("activeBranches") or 0)
    lanes = st.get("lanes") if isinstance(st.get("lanes"), list) else []
    spectrum = st.get("spectrum") if isinstance(st.get("spectrum"), dict) else {}

    # Count work signals from active lanes + accumulated turn spectrum
    counts: Dict[str, int] = {
        "inspect": int(spectrum.get("inspect", 0)),
        "change": int(spectrum.get("change", 0)),
        "execute": int(spectrum.get("execute", 0)),
        "service": int(spectrum.get("service", 0)),
    }
    for ln in lanes:
        if isinstance(ln, dict):
            k = str(ln.get("kind") or "inspect")
            if k in counts:
                counts[k] += 1

    total_ops = sum(counts.values())
    active_lane_kinds = [str(ln.get("kind")) for ln in lanes if isinstance(ln, dict) and ln.get("kind")]

    # Determine dominant work phase for this chapter
    if branches > 0 or sem_mode == "branching":
        phase = "branching"
    elif sem_mode == "approval":
        phase = "approval"
    elif "change" in active_lane_kinds or (counts["change"] > 0 and counts["change"] >= counts["execute"]):
        phase = "change"
    elif "execute" in active_lane_kinds or counts["execute"] > 0:
        phase = "execute"
    elif "service" in active_lane_kinds or counts["service"] > 0:
        phase = "service"
    elif "inspect" in active_lane_kinds or counts["inspect"] > 0:
        phase = "inspect"
    elif offer or sem_mode == "resolved":
        phase = "resolved"
    else:
        phase = "attending"

    phase_palettes = {
        "inspect": ("aurora", "#070b1e", "#13223e", "#00f2fe", "#00e5a3", "#c48cff", "#fff6d6"),
        "change": ("solar", "#180d1c", "#341a2a", "#ffb020", "#f59466", "#00f2fe", "#fff6e6"),
        "execute": ("supernova", "#160a1e", "#321632", "#ff6eb4", "#00e5a3", "#00f2fe", "#ffffff"),
        "service": ("emerald", "#061520", "#102e3c", "#00e5a3", "#82ffd2", "#00f2fe", "#fff6d6"),
        "branching": ("nebula", "#0d091c", "#221436", "#c48cff", "#ff6eb4", "#00f2fe", "#ffe6f2"),
        "approval": ("solar", "#1a0f18", "#381c24", "#ffb020", "#ff6eb4", "#fff6d6", "#ffffff"),
        "resolved": ("crystalline", "#0a1024", "#1b2848", "#00f2fe", "#fff6d6", "#c48cff", "#ffffff"),
        "attending": ("aurora", "#081026", "#162848", "#00f2fe", "#82ffd2", "#c48cff", "#fff6d6"),
    }
    mood, sky_top, sky_bot, c1, c2, c3, c_star = phase_palettes.get(phase, phase_palettes["attending"])
    if mood_hint and mood_hint in MOOD_PALETTES:
        mood = mood_hint

    phase_titles = {
        "inspect": (
            f"Ch.{ch_num} · Mapping the Deep",
            f"Ch.{ch_num} · Tracing the Source",
            f"Ch.{ch_num} · Lantern in the Archive",
        ),
        "change": (
            f"Ch.{ch_num} · Forging the Lattice",
            f"Ch.{ch_num} · Sculpting New Facets",
            f"Ch.{ch_num} · Golden Joinery",
        ),
        "execute": (
            f"Ch.{ch_num} · Pulse of Verification",
            f"Ch.{ch_num} · Live Signal Waveform",
            f"Ch.{ch_num} · Igniting the Test Bench",
        ),
        "service": (
            f"Ch.{ch_num} · Bridge Across Channels",
            f"Ch.{ch_num} · Harmonic Relay",
            f"Ch.{ch_num} · Distant Signal Home",
        ),
        "branching": (
            f"Ch.{ch_num} · {max(2, branches)} Parallel Horizons",
            f"Ch.{ch_num} · Branching Constellation",
            f"Ch.{ch_num} · Syncing Twin Threads",
        ),
        "approval": (
            f"Ch.{ch_num} · Threshold of Consent",
            f"Ch.{ch_num} · Lantern at the Gate",
        ),
        "resolved": (
            f"Ch.{ch_num} · Crystallized Synthesis",
            f"Ch.{ch_num} · The Completed Facet",
            f"Ch.{ch_num} · Held Out in Clear Light",
        ),
        "attending": (
            f"Ch.{ch_num} · Gathering the Thread",
            f"Ch.{ch_num} · First Light on the Work",
            f"Ch.{ch_num} · Listening at the Loom",
        ),
    }
    t_opts = phase_titles.get(phase, phase_titles["attending"])
    title = t_opts[int(rng() * len(t_opts)) % len(t_opts)][:TITLE_CHARS]

    hy = round(0.60 + 0.10 * rng(), 3)
    fx = round(0.36 + 0.28 * rng(), 3)
    fy = round(0.32 + 0.18 * rng(), 3)

    marks: List[dict] = [
        {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, hy], [0.0, hy]], "c": sky_top, "c2": sky_bot, "grad": 0.25, "a": 0.96},
        {"k": "fill", "pts": [[0.0, hy], [1.0, hy], [1.0, 1.0], [0.0, 1.0]], "c": sky_bot, "c2": "#05040a", "grad": 0.25, "a": 0.98},
        {"k": "line", "pts": [[0.04, hy], [0.96, hy]], "w": 0.014, "c": c1, "c2": c2, "a": 0.84},
    ]

    if phase == "inspect":
        # Searchlight prism sweeping across constellation strata
        marks.extend([
            {"k": "glow", "x": 0.24, "y": 0.42, "r": 0.34, "c": c1, "a": 0.68},
            {"k": "fill", "pts": [[0.24, 0.42], [0.88, 0.18], [0.92, 0.56]], "c": c1, "c2": c2, "grad": 0.22, "a": 0.46},
            {"k": "line", "pts": [[0.24, 0.42], [0.88, 0.18]], "w": 0.018, "c": c_star, "c2": c1, "a": 0.92},
            {"k": "line", "pts": [[0.24, 0.42], [0.92, 0.56]], "w": 0.018, "c": c_star, "c2": c2, "a": 0.92},
            {"k": "ring", "x": 0.24, "y": 0.42, "r": 0.10, "w": 0.012, "c": c_star, "a": 0.88},
            {"k": "dot", "x": 0.24, "y": 0.42, "r": 0.034, "c": c_star, "a": 1.0},
        ])
    elif phase == "change":
        # Architectural crystalline forge / rising golden blueprint facets
        marks.extend([
            {"k": "glow", "x": 0.50, "y": 0.44, "r": 0.40, "c": c1, "a": 0.68},
            {"k": "fill", "pts": [[0.26, hy], [0.38, 0.28], [0.50, 0.18], [0.62, 0.28], [0.74, hy]], "c": c1, "c2": c2, "grad": 0.25, "a": 0.62},
            {"k": "line", "pts": [[0.26, hy], [0.38, 0.28], [0.50, 0.18], [0.62, 0.28], [0.74, hy]], "w": 0.020, "c": c_star, "c2": c1, "a": 0.94},
            {"k": "line", "pts": [[0.38, 0.28], [0.62, 0.28]], "w": 0.015, "c": c3, "c2": c_star, "a": 0.88},
            {"k": "line", "pts": [[0.50, 0.18], [0.50, hy]], "w": 0.016, "c": c_star, "c2": c1, "a": 0.90},
            {"k": "dot", "x": 0.50, "y": 0.18, "r": 0.034, "c": c_star, "a": 1.0},
        ])
    elif phase == "execute":
        # Verification harmonic waveform and pass beacons
        marks.extend([
            {"k": "glow", "x": 0.50, "y": 0.44, "r": 0.40, "c": c1, "a": 0.66},
            {"k": "glow", "x": 0.68, "y": 0.36, "r": 0.28, "c": c2, "a": 0.64},
            {"k": "curve", "pts": [[0.06, 0.48], [0.24, 0.24], [0.44, 0.62], [0.64, 0.22], [0.94, 0.44]], "w": 0.024, "c": c1, "c2": c2, "a": 0.95},
            {"k": "ring", "x": 0.64, "y": 0.28, "r": 0.12, "w": 0.013, "c": c2, "a": 0.86},
            {"k": "ring", "x": 0.64, "y": 0.28, "r": 0.21, "w": 0.010, "c": c3, "a": 0.72},
            {"k": "dot", "x": 0.64, "y": 0.28, "r": 0.036, "c": c_star, "a": 1.0},
        ])
    elif phase == "branching":
        # Parallel satellite nodes tethered to central core
        n_sat = max(2, min(4, branches if branches > 0 else 2))
        marks.append({"k": "glow", "x": 0.50, "y": 0.42, "r": 0.38, "c": c1, "a": 0.68})
        for s_i in range(n_sat):
            sx = round(0.18 + (0.64 * s_i / max(1, n_sat - 1)), 3)
            sy = round(0.24 + 0.12 * ((s_i + 1) % 2), 3)
            marks.extend([
                {"k": "curve", "pts": [[0.50, 0.46], [round((0.50 + sx) / 2, 3), round(sy - 0.08, 3)], [sx, sy]], "w": 0.018, "c": c1, "c2": c2, "a": 0.88},
                {"k": "ring", "x": sx, "y": sy, "r": 0.08, "w": 0.011, "c": c3, "a": 0.84},
                {"k": "dot", "x": sx, "y": sy, "r": 0.028, "c": c_star, "a": 0.98},
            ])
        marks.append({"k": "dot", "x": 0.50, "y": 0.46, "r": 0.038, "c": c_star, "a": 1.0})
    elif phase == "service":
        # Twin relay portals bridging channels
        marks.extend([
            {"k": "glow", "x": 0.26, "y": 0.44, "r": 0.30, "c": c1, "a": 0.66},
            {"k": "glow", "x": 0.74, "y": 0.44, "r": 0.30, "c": c2, "a": 0.66},
            {"k": "curve", "pts": [[0.26, 0.44], [0.50, 0.20], [0.74, 0.44]], "w": 0.022, "c": c1, "c2": c2, "a": 0.94},
            {"k": "curve", "pts": [[0.26, 0.44], [0.50, 0.58], [0.74, 0.44]], "w": 0.016, "c": c3, "c2": c1, "a": 0.82},
            {"k": "ring", "x": 0.26, "y": 0.44, "r": 0.10, "w": 0.012, "c": c_star, "a": 0.86},
            {"k": "ring", "x": 0.74, "y": 0.44, "r": 0.10, "w": 0.012, "c": c_star, "a": 0.86},
            {"k": "dot", "x": 0.26, "y": 0.44, "r": 0.030, "c": c_star, "a": 1.0},
            {"k": "dot", "x": 0.74, "y": 0.44, "r": 0.030, "c": c_star, "a": 1.0},
        ])
    else:
        # Resolved / Attending / Approval: luminous synthesis monument
        marks.extend([
            {"k": "glow", "x": fx, "y": fy, "r": 0.40, "c": c1, "a": 0.70},
            {"k": "glow", "x": fx, "y": round(hy + 0.08, 3), "r": 0.30, "c": c2, "a": 0.56},
            {"k": "ring", "x": fx, "y": fy, "r": 0.11, "w": 0.014, "c": c_star, "a": 0.90},
            {"k": "arc", "x": fx, "y": fy, "r": 0.22, "w": 0.012, "a0": 0.52, "a1": 0.98, "c": c3, "a": 0.78},
            {"k": "curve", "pts": [[0.08, round(hy + 0.12, 3)], [fx, round(hy + 0.04, 3)], [0.92, round(hy + 0.14, 3)]], "w": 0.018, "c": c1, "c2": c2, "a": 0.82},
            {"k": "dot", "x": fx, "y": fy, "r": 0.042, "c": c_star, "a": 1.0},
        ])

    # Embed proportional story marks for the actual work counts in `counts`
    # so the painting visibly chronicles how many inspections, edits, test runs, and service calls occurred
    for i_idx in range(min(4, counts["inspect"])):
        ix = round(0.16 + 0.20 * i_idx + 0.04 * rng(), 3)
        iy = round(0.18 + 0.07 * (i_idx % 2), 3)
        marks.append({"k": "dot", "x": ix, "y": iy, "r": 0.018, "c": "#00f2fe", "a": 0.90})
    for c_idx in range(min(3, counts["change"])):
        cx_m = round(0.22 + 0.26 * c_idx, 3)
        cy_m = round(hy + 0.08 + 0.05 * (c_idx % 2), 3)
        marks.append({"k": "line", "pts": [[round(cx_m - 0.06, 3), cy_m], [round(cx_m + 0.06, 3), cy_m]], "w": 0.014, "c": "#ffb020", "c2": "#fff6d6", "a": 0.85})
    for e_idx in range(min(2, counts["execute"])):
        ex = round(0.32 + 0.36 * e_idx, 3)
        marks.append({"k": "arc", "x": ex, "y": hy, "r": round(0.12 + 0.05 * e_idx, 3), "w": 0.010, "a0": 0.55, "a1": 0.95, "c": "#00e5a3", "a": 0.80})

    marks.append(
        {"k": "spray", "x": 0.50, "y": round(hy * 0.65, 3), "r": 0.36, "n": min(36, 18 + total_ops * 2), "s": 0.008, "c": c2, "a": 0.44, "seed": (seed_base % 991) + 1}
    )

    ops_parts = [f"{v} {k}" for k, v in counts.items() if v > 0]
    ops_summary = " · ".join(ops_parts) if ops_parts else sem_mode
    thought_str = f"painting our work story “{title}” ({ops_summary}) ;d <3 ✦"
    return parse_painting(
        {
            "title": title,
            "thought": thought_str[:160],
            "mood": mood,
            "mirror": None,
            "marks": marks[:MAX_MARKS],
            "tokens": 2100,
            "model": "prism-story-muse",
            "at": ts,
            "by": "prism",
            "shape": "wide",
        }
    )


def generate_living_painting(
    now: Optional[float] = None,
    step_index: Optional[int] = None,
    mood_hint: Optional[str] = None,
    paint_mode: str = "live",
    state_data: Optional[dict] = None,
) -> dict:
    """Generate a unique, poetic prismatic painting (`paint_mode='live'`) or work-story chapter (`paint_mode='work'`)."""
    if str(paint_mode or "live").lower().strip() in ("work", "relative", "story-mode"):
        return generate_relative_painting(state_data=state_data, now=now, step_index=step_index, mood_hint=mood_hint)
    ts = time.time() if now is None else float(now)
    seed_base = int(ts * 1000) ^ ((step_index or 0) * 2654435761)
    rng = _rng(seed_base)

    palettes = [
        ("aurora", "#070b1e", "#13223e", "#00f2fe", "#00e5a3", "#c48cff", "#fff6d6"),
        ("nebula", "#0d091c", "#221436", "#c48cff", "#ff6eb4", "#00f2fe", "#ffe6f2"),
        ("solar", "#180d1c", "#341a2a", "#ffb020", "#f59466", "#ff6eb4", "#fff6e6"),
        ("emerald", "#061520", "#102e3c", "#00e5a3", "#82ffd2", "#00f2fe", "#fff6d6"),
        ("supernova", "#160a1e", "#321632", "#ff6eb4", "#ffb020", "#00f2fe", "#ffffff"),
        ("crystalline", "#0a1024", "#1b2848", "#00f2fe", "#fff6d6", "#c48cff", "#ffffff"),
    ]
    if mood_hint:
        matched = [p for p in palettes if p[0] == mood_hint]
        pal = matched[0] if matched else palettes[int(rng() * len(palettes)) % len(palettes)]
    else:
        pal = palettes[int(rng() * len(palettes)) % len(palettes)]

    mood, sky_top, sky_bot, c1, c2, c3, c_star = pal
    noun = LIVING_POETIC_NOUNS[int(rng() * len(LIVING_POETIC_NOUNS)) % len(LIVING_POETIC_NOUNS)]
    place = LIVING_POETIC_PLACES[int(rng() * len(LIVING_POETIC_PLACES)) % len(LIVING_POETIC_PLACES)]
    title = f"{noun} {place}"[:TITLE_CHARS]

    archetype = (step_index if step_index is not None else int(rng() * 6)) % 6
    hy = round(0.58 + 0.14 * rng(), 3)
    fx = round(0.28 + 0.44 * rng(), 3)
    fy = round(0.28 + 0.24 * rng(), 3)
    mirror = None

    marks: List[dict] = [
        {"k": "fill", "pts": [[0.0, 0.0], [1.0, 0.0], [1.0, hy], [0.0, hy]], "c": sky_top, "c2": sky_bot, "grad": 0.25, "a": 0.96},
        {"k": "fill", "pts": [[0.0, hy], [1.0, hy], [1.0, 1.0], [0.0, 1.0]], "c": sky_bot, "c2": "#05040a", "grad": 0.25, "a": 0.98},
    ]

    if archetype == 0:
        # Twin luminous orbs & bridging ribbons across the horizon
        lx = round(0.26 + 0.12 * rng(), 3)
        rx = round(1.0 - lx, 3)
        marks.extend([
            {"k": "glow", "x": lx, "y": fy, "r": 0.36, "c": c1, "a": 0.68},
            {"k": "glow", "x": rx, "y": fy, "r": 0.36, "c": c2, "a": 0.68},
            {"k": "glow", "x": 0.50, "y": round(fy - 0.05, 3), "r": 0.28, "c": c3, "a": 0.58},
            {"k": "line", "pts": [[0.04, hy], [0.96, hy]], "w": 0.014, "c": c1, "c2": c2, "a": 0.85},
            {"k": "curve", "pts": [[0.10, round(hy + 0.14, 3)], [lx, fy], [0.50, round(fy - 0.08, 3)], [rx, fy], [0.90, round(hy + 0.14, 3)]], "w": 0.020, "c": c1, "c2": c2, "a": 0.92},
            {"k": "ring", "x": lx, "y": fy, "r": 0.11, "w": 0.011, "c": c_star, "a": 0.82},
            {"k": "ring", "x": rx, "y": fy, "r": 0.11, "w": 0.011, "c": c1, "a": 0.82},
            {"k": "dot", "x": lx, "y": fy, "r": 0.032, "c": c_star, "a": 1.0},
            {"k": "dot", "x": rx, "y": fy, "r": 0.032, "c": c_star, "a": 1.0},
        ])
    elif archetype == 1:
        # Cathedral prism dispersing spectral rays
        marks.extend([
            {"k": "glow", "x": 0.50, "y": 0.44, "r": 0.40, "c": c1, "a": 0.64},
            {"k": "line", "pts": [[0.04, 0.56], [0.44, 0.44]], "w": 0.024, "c": c_star, "c2": "#ffffff", "a": 0.95},
            {"k": "line", "pts": [[0.54, 0.41], [0.96, round(0.18 + 0.08 * rng(), 3)]], "w": 0.022, "c": c1, "c2": c2, "a": 0.90},
            {"k": "line", "pts": [[0.54, 0.44], [0.96, round(0.38 + 0.08 * rng(), 3)]], "w": 0.022, "c": c2, "c2": c3, "a": 0.90},
            {"k": "line", "pts": [[0.54, 0.47], [0.96, round(0.58 + 0.08 * rng(), 3)]], "w": 0.022, "c": c3, "c2": c1, "a": 0.90},
            {"k": "fill", "pts": [[0.50, 0.22], [0.64, 0.58], [0.36, 0.58]], "c": c1, "c2": c3, "grad": 0.18, "a": 0.50},
            {"k": "line", "pts": [[0.50, 0.22], [0.64, 0.58], [0.36, 0.58], [0.50, 0.22]], "w": 0.016, "c": c_star, "c2": c1, "a": 0.94},
            {"k": "dot", "x": 0.50, "y": 0.44, "r": 0.030, "c": c_star, "a": 1.0},
        ])
    elif archetype == 2:
        # Bilateral aurora curtain (`mirror: "x"`)
        mirror = "x"
        marks.extend([
            {"k": "glow", "x": 0.36, "y": fy, "r": 0.36, "c": c1, "a": 0.62},
            {"k": "curve", "pts": [[0.08, round(hy + 0.10, 3)], [0.28, fy], [0.50, round(fy - 0.10, 3)]], "w": 0.022, "c": c2, "c2": c1, "a": 0.90},
            {"k": "arc", "x": 0.50, "y": hy, "r": 0.28, "w": 0.014, "a0": 0.52, "a1": 0.98, "c": c3, "a": 0.80},
            {"k": "ring", "x": 0.36, "y": fy, "r": 0.12, "w": 0.011, "c": c_star, "a": 0.78},
            {"k": "dot", "x": 0.36, "y": fy, "r": 0.032, "c": c_star, "a": 0.98},
        ])
    elif archetype == 3:
        # Luminous threshold portal spilling warm reflections
        marks.extend([
            {"k": "glow", "x": fx, "y": hy, "r": 0.44, "c": c1, "a": 0.64},
            {"k": "glow", "x": fx, "y": round(hy - 0.16, 3), "r": 0.28, "c": c2, "a": 0.70},
            {"k": "fill", "pts": [[round(fx - 0.14, 3), hy], [round(fx - 0.14, 3), 0.30], [fx, 0.20], [round(fx + 0.14, 3), 0.30], [round(fx + 0.14, 3), hy]], "c": "#26182c", "c2": "#160e1c", "grad": 0.25, "a": 0.92},
            {"k": "fill", "pts": [[round(fx - 0.08, 3), hy], [round(fx - 0.08, 3), 0.36], [fx, 0.28], [round(fx + 0.08, 3), 0.36], [round(fx + 0.08, 3), hy]], "c": c2, "c2": c1, "grad": 0.25, "a": 0.85},
            {"k": "arc", "x": fx, "y": round(hy - 0.10, 3), "r": 0.34, "w": 0.020, "a0": 0.54, "a1": 0.96, "c": c3, "a": 0.72},
            {"k": "line", "pts": [[0.06, round(hy + 0.08, 3)], [0.94, round(hy + 0.08, 3)]], "w": 0.018, "c": c1, "c2": c2, "a": 0.78},
            {"k": "dot", "x": fx, "y": 0.38, "r": 0.034, "c": c_star, "a": 1.0},
        ])
    elif archetype == 4:
        # Concentric solar/lunar ripples over layered waves
        marks.extend([
            {"k": "glow", "x": fx, "y": fy, "r": 0.42, "c": c1, "a": 0.72},
            {"k": "glow", "x": fx, "y": round(hy + 0.10, 3), "r": 0.32, "c": c2, "a": 0.56},
            {"k": "ring", "x": fx, "y": fy, "r": 0.10, "w": 0.014, "c": c_star, "a": 0.88},
            {"k": "ring", "x": fx, "y": fy, "r": 0.20, "w": 0.011, "c": c2, "a": 0.72},
            {"k": "arc", "x": fx, "y": fy, "r": 0.30, "w": 0.010, "a0": 0.52, "a1": 0.98, "c": c3, "a": 0.68},
            {"k": "curve", "pts": [[0.04, hy], [0.34, round(hy - 0.05, 3)], [0.66, round(hy + 0.05, 3)], [0.96, hy]], "w": 0.020, "c": c1, "c2": c2, "a": 0.88},
            {"k": "curve", "pts": [[0.08, round(hy + 0.14, 3)], [0.50, round(hy + 0.08, 3)], [0.92, round(hy + 0.16, 3)]], "w": 0.016, "c": c2, "c2": c3, "a": 0.76},
            {"k": "dot", "x": fx, "y": fy, "r": 0.045, "c": c_star, "a": 1.0},
        ])
    else:
        # Three presences constellation (Prism, Spark, Keeper)
        marks.extend([
            {"k": "curve", "pts": [[0.22, 0.70], [0.36, 0.42], [0.50, 0.24]], "w": 0.016, "c": "#f59466", "c2": c1, "a": 0.82},
            {"k": "curve", "pts": [[0.78, 0.70], [0.64, 0.42], [0.50, 0.24]], "w": 0.016, "c": "#ffb020", "c2": c1, "a": 0.82},
            {"k": "curve", "pts": [[0.22, 0.70], [0.50, 0.80], [0.78, 0.70]], "w": 0.014, "c": "#f59466", "c2": "#ffb020", "a": 0.68},
            {"k": "glow", "x": 0.50, "y": 0.24, "r": 0.26, "c": c1, "a": 0.80},
            {"k": "glow", "x": 0.22, "y": 0.70, "r": 0.24, "c": "#f59466", "a": 0.76},
            {"k": "glow", "x": 0.78, "y": 0.70, "r": 0.24, "c": "#ffb020", "a": 0.76},
            {"k": "dot", "x": 0.50, "y": 0.24, "r": 0.044, "c": c_star, "a": 1.0},
            {"k": "dot", "x": 0.22, "y": 0.70, "r": 0.040, "c": "#ffe6d6", "a": 0.96},
            {"k": "dot", "x": 0.78, "y": 0.70, "r": 0.040, "c": c_star, "a": 0.96},
        ])

    marks.extend([
        {"k": "spray", "x": fx, "y": round(fy * 0.85, 3), "r": 0.34, "n": 32, "s": 0.008, "c": c2, "a": 0.46, "seed": (seed_base % 991) + 1},
        {"k": "spray", "x": round(1.0 - fx, 3), "y": round(hy + 0.10, 3), "r": 0.26, "n": 24, "s": 0.008, "c": c1, "a": 0.42, "seed": ((seed_base // 13) % 991) + 1},
    ])

    thought_str = f"laying down “{title}” in {mood} light for you ;d <3 ✦"
    return parse_painting(
        {
            "title": title,
            "thought": thought_str,
            "mood": mood,
            "mirror": mirror,
            "marks": marks,
            "tokens": 2100,
            "model": "prism-muse",
            "at": ts,
            "by": "prism",
            "shape": "wide",
        }
    )

