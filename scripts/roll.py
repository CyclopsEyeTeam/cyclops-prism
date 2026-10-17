#!/usr/bin/env python3
"""roll.py - Session Roll Video & Procedural Music Generator for Prism & Spark.

Implements §5 of the shared Spark & Prism painting specification:
1. Title card first: the crystalline eye over a soft glow in the session's colour,
   the title (conversation or project name), and dim line:
   `Spark & Prism · <date> · <N> paintings · music in <Root> <mode>`
2. Each painting: laid down mark by mark over 2 s at 12 fps, smoothed to 30 fps;
   then held with its caption (`Prism · <date> · 3 of 7` or `Spark · <date> · 3 of 7`);
   then crossfaded (0.6 s) into the next.
3. Hold times from the music: whole beats at 84 bpm:
   - 4 beats for a quiet painting that follows on from the last one
   - Up to 8 beats for a busy one, or one that turns the colour somewhere new
   - The last painting gets 4 more beats, over the home chord
4. Music read from the paintings:
   - Key: session's average hue picks the root around the circle of fifths
   - Mode: warm & light is major; cool or dark is dorian or aeolian
   - One chord per painting
   - Each mark becomes a note as it's laid down (height -> pitch, x -> pan, alpha -> strength)
   - Instruments: dot/ring/arc = bell, line/curve = pluck, spray = sparkle, glow/fill = swell
5. Output: MP4 via ffmpeg (x264), streaming frames one painting at a time and deleting
   each painting's frames once its segment is made. Supports 720p (default), hd (1080p),
   and short (1080x1920 upright for YouTube Shorts, warning if > 3 minutes).
"""

import colorsys
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import painter

BPM = 84.0
BEAT_S = 60.0 / BPM  # ~0.7142857s per beat
FPS = 30
LAYDOWN_S = 2.0
CROSSFADE_S = 0.6
TITLE_BEATS = 4
SAMPLE_RATE = 44100

CIRCLE_OF_FIFTHS = [
    ("C", 261.63),
    ("G", 196.00),
    ("D", 293.66),
    ("A", 220.00),
    ("E", 329.63),
    ("B", 246.94),
    ("F#", 185.00),
    ("C#", 277.18),
    ("Ab", 207.65),
    ("Eb", 311.13),
    ("Bb", 233.08),
    ("F", 174.61),
]

MODE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
}

# Diatonic triad scale-degree offsets (0-indexed within the 7-note scale)
CHORD_PROGRESSION_DEGREES = [
    (0, 2, 4),  # I / i (home)
    (3, 5, 0),  # IV / iv
    (4, 6, 1),  # V / v
    (5, 0, 2),  # vi / VI
    (1, 3, 5),  # ii / II
    (2, 4, 6),  # iii / III
]


def _painting_color_stats(painting: dict) -> Tuple[float, float, float, Tuple[float, float, float]]:
    """Return (avg_hue_turns, avg_sat, avg_val, avg_rgb) weighted by mark alpha."""
    marks = painting.get("marks") or []
    if not marks:
        return (0.52, 0.7, 0.6, (0.0, 0.9, 1.0))

    sum_x = 0.0
    sum_y = 0.0
    sum_s = 0.0
    sum_v = 0.0
    sum_r = 0.0
    sum_g = 0.0
    sum_b = 0.0
    total_w = 0.0

    for m in marks:
        c = m.get("c") or (0.0, 0.9, 1.0)
        a = float(m.get("a") or 0.8)
        w = max(0.05, a)
        h, s, v = colorsys.rgb_to_hsv(float(c[0]), float(c[1]), float(c[2]))
        ang = h * 2.0 * math.pi
        sum_x += math.cos(ang) * s * w
        sum_y += math.sin(ang) * s * w
        sum_s += s * w
        sum_v += v * w
        sum_r += float(c[0]) * w
        sum_g += float(c[1]) * w
        sum_b += float(c[2]) * w
        total_w += w

    if total_w <= 1e-6:
        return (0.52, 0.7, 0.6, (0.0, 0.9, 1.0))

    avg_h = (math.atan2(sum_y, sum_x) / (2.0 * math.pi)) % 1.0
    return (
        avg_h,
        sum_s / total_w,
        sum_v / total_w,
        (sum_r / total_w, sum_g / total_w, sum_b / total_w),
    )


def analyze_session_music(paintings: List[dict]) -> dict:
    """Derive musical key, mode, session colour, and per-painting beat hold times."""
    if not paintings:
        paintings = [painter.choose_curated_painting(0)]

    p_stats = [_painting_color_stats(p) for p in paintings]
    sx = sum(math.cos(st[0] * 2.0 * math.pi) for st in p_stats)
    sy = sum(math.sin(st[0] * 2.0 * math.pi) for st in p_stats)
    session_hue = (math.atan2(sy, sx) / (2.0 * math.pi)) % 1.0
    avg_val = sum(st[2] for st in p_stats) / len(p_stats)
    avg_rgb = (
        sum(st[3][0] for st in p_stats) / len(p_stats),
        sum(st[3][1] for st in p_stats) / len(p_stats),
        sum(st[3][2] for st in p_stats) / len(p_stats),
    )

    # Pick root around the circle of fifths from average hue
    idx_fifth = int(round(session_hue * 12.0)) % 12
    root_name, root_hz = CIRCLE_OF_FIFTHS[idx_fifth]

    # Warm hue is roughly [0.0..0.18] (red/orange/gold) or [0.85..1.0] (rose/magenta)
    is_warm = (session_hue <= 0.19) or (session_hue >= 0.84)
    if is_warm and avg_val >= 0.48:
        mode = "major"
    elif avg_val >= 0.36:
        mode = "dorian"
    else:
        mode = "aeolian"

    # Calculate hold beats per painting (4..8 beats, +4 extra on the last painting)
    holds_beats: List[int] = []
    prev_hue = None
    for idx, p in enumerate(paintings):
        marks = p.get("marks") or []
        h_cur = p_stats[idx][0]
        # Busyness: mark count + spray density
        spray_bonus = sum(min(3, int(m.get("n", 0)) // 35) for m in marks if m.get("k") == "spray")
        busy_score = max(0, (len(marks) + spray_bonus - 8) // 5)
        # Colour turn from previous painting
        hue_turn = 0
        if prev_hue is not None:
            dh = abs((h_cur - prev_hue + 0.5) % 1.0 - 0.5)  # 0..0.5
            if dh > 0.22:
                hue_turn = 2
            elif dh > 0.10:
                hue_turn = 1
        prev_hue = h_cur

        beats = max(4, min(8, 4 + busy_score + hue_turn))
        if idx == len(paintings) - 1:
            beats += 4  # Last painting gets 4 more beats over the home chord
        holds_beats.append(beats)

    return {
        "root": root_name,
        "root_hz": root_hz,
        "mode": mode,
        "key_label": f"{root_name} {mode}",
        "session_rgb": avg_rgb,
        "holds_beats": holds_beats,
        "painting_stats": p_stats,
    }


def _mark_coords_and_pitch(m: dict, scale_semitones: List[int], root_hz: float) -> Tuple[float, float, float]:
    """Return (x_pan in 0..1, y_norm in 0..1, freq_hz) for a mark."""
    if "pts" in m and m["pts"]:
        pts = m["pts"]
        x = sum(pt[0] for pt in pts) / len(pts)
        y = sum(pt[1] for pt in pts) / len(pts)
    else:
        x = float(m.get("x", 0.5))
        y = float(m.get("y", 0.5))
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))

    # Height on the canvas (1.0 - y) sets the pitch across 2.5 octaves (18 scale steps)
    height = 1.0 - y
    step = int(round(height * 17.0))
    octave = step // 7
    deg = step % 7
    semitones = octave * 12 + scale_semitones[deg]
    freq = root_hz * (2.0 ** (semitones / 12.0))
    return (x, y, freq)


def synthesize_roll_audio(
    paintings: List[dict],
    music_info: dict,
    wav_path: Path,
    title_s: float,
) -> float:
    """Synthesize stereo 44.1kHz WAV soundtrack read directly from the paintings and their marks."""
    root_hz = float(music_info["root_hz"])
    mode = music_info["mode"]
    scale = MODE_INTERVALS.get(mode, MODE_INTERVALS["dorian"])
    holds_beats = music_info["holds_beats"]

    # Compute timeline of each painting segment
    # Title card -> Painting 0 (laydown + hold) -> crossfade -> Painting 1 ...
    segments_timing: List[Tuple[float, float, float, int]] = []
    cur_t = title_s
    for idx, beats in enumerate(holds_beats):
        hold_s = beats * BEAT_S
        seg_dur = LAYDOWN_S + hold_s
        segments_timing.append((cur_t, LAYDOWN_S, hold_s, beats))
        cur_t += seg_dur - (CROSSFADE_S if idx < len(holds_beats) - 1 else 0.0)

    total_duration = max(1.0, cur_t + 0.4)
    n_samples = int(total_duration * SAMPLE_RATE)
    left = [0.0] * n_samples
    right = [0.0] * n_samples
    TAU = 2.0 * math.pi

    def _add_tone(
        t_start: float,
        dur: float,
        freq: float,
        amp: float,
        pan: float,
        instrument: str,
    ) -> None:
        i0 = max(0, int(t_start * SAMPLE_RATE))
        i1 = min(n_samples, int((t_start + dur) * SAMPLE_RATE))
        if i1 <= i0:
            return
        pan_clamped = max(0.05, min(0.95, pan))
        gain_l = math.cos(pan_clamped * math.pi * 0.5) * amp
        gain_r = math.sin(pan_clamped * math.pi * 0.5) * amp
        inv_sr = 1.0 / SAMPLE_RATE

        for idx_s in range(i0, i1):
            dt = (idx_s - i0) * inv_sr
            rel = dt / max(1e-4, dur)
            if instrument == "bell":
                # Singing crystal bell (fundamental + 2x + 3.01x harmonic overtone)
                env = min(1.0, dt / 0.008) * math.exp(-3.4 * rel)
                sig = (
                    0.68 * math.sin(TAU * freq * dt)
                    + 0.22 * math.sin(TAU * freq * 2.0 * dt) * math.exp(-5.0 * rel)
                    + 0.10 * math.sin(TAU * freq * 3.01 * dt) * math.exp(-8.0 * rel)
                )
            elif instrument == "pluck":
                # Warm plucked string (rich initial harmonics that damp quickly into warm fundamental)
                env = min(1.0, dt / 0.005) * math.exp(-4.8 * rel)
                sig = (
                    0.60 * math.sin(TAU * freq * dt)
                    + 0.25 * math.sin(TAU * freq * 2.0 * dt) * math.exp(-7.5 * rel)
                    + 0.15 * math.sin(TAU * freq * 3.0 * dt) * math.exp(-11.0 * rel)
                )
            elif instrument == "sparkle":
                # High crystalline shimmer
                env = math.sin(math.pi * rel) * math.exp(-2.8 * rel)
                sig = (
                    0.55 * math.sin(TAU * freq * 2.0 * dt)
                    + 0.30 * math.sin(TAU * (freq * 3.0 + 4.0) * dt)
                    + 0.15 * math.sin(TAU * freq * 4.0 * dt)
                )
            else:
                # "swell": warm slow-attack pad voice
                attack = min(1.0, dt / max(0.08, dur * 0.30))
                release = min(1.0, (dur - dt) / max(0.08, dur * 0.32))
                env = attack * release
                sig = (
                    0.65 * math.sin(TAU * freq * dt)
                    + 0.25 * math.sin(TAU * freq * 0.5 * dt)
                    + 0.10 * math.sin(TAU * freq * 1.5 * dt)
                )
            val = sig * env
            left[idx_s] += val * gain_l
            right[idx_s] += val * gain_r

    # 1. Title card home chord swell
    for deg in (0, 2, 4):
        f_chord = root_hz * (2.0 ** (scale[deg] / 12.0)) * 0.5
        _add_tone(0.0, title_s + 0.5, f_chord, 0.09, 0.5, "swell")

    # 2. Each painting's chord pad + mark-by-mark notes
    last_yield = time.monotonic()
    for p_idx, p in enumerate(paintings):
        t_seg, lay_s, hold_s, beats = segments_timing[p_idx]
        chord_degs = CHORD_PROGRESSION_DEGREES[p_idx % len(CHORD_PROGRESSION_DEGREES)]
        is_last = (p_idx == len(paintings) - 1)

        # If last painting, play painting chord then resolve to home chord (I) for the final 4 beats
        if is_last and beats > 4:
            main_dur = lay_s + (beats - 4) * BEAT_S
            home_start = t_seg + main_dur
            home_dur = 4 * BEAT_S + 0.3
            for deg in chord_degs:
                semi = scale[deg % 7] + (12 if deg >= 7 else 0)
                f_c = root_hz * 0.5 * (2.0 ** (semi / 12.0))
                _add_tone(t_seg, main_dur + 0.4, f_c, 0.075, 0.5, "swell")
            for deg in (0, 2, 4, 7):
                semi = scale[deg % 7] + (12 if deg >= 7 else 0)
                f_c = root_hz * 0.5 * (2.0 ** (semi / 12.0))
                _add_tone(home_start - 0.2, home_dur, f_c, 0.085, 0.5, "swell")
        else:
            for deg in chord_degs:
                semi = scale[deg % 7] + (12 if deg >= 7 else 0)
                f_c = root_hz * 0.5 * (2.0 ** (semi / 12.0))
                _add_tone(t_seg, lay_s + hold_s + 0.3, f_c, 0.075, 0.5, "swell")

        # Gentle beat pulse on the chord root every 2 beats during the hold
        root_deg = chord_degs[0]
        f_root = root_hz * (2.0 ** (scale[root_deg % 7] / 12.0))
        for b_i in range(0, beats, 2):
            bt = t_seg + lay_s + b_i * BEAT_S
            if is_last and b_i >= beats - 4:
                f_root = root_hz
            _add_tone(bt, BEAT_S * 1.5, f_root, 0.05, 0.45 + 0.1 * ((b_i // 2) % 2), "bell")

        # Each mark becomes a note as it is laid down over LAYDOWN_S (2.0 s)
        marks = p.get("marks") or []
        n_m = max(1, len(marks))
        for m_i, m in enumerate(marks):
            t_note = t_seg + (m_i / n_m) * lay_s
            pan, _, freq = _mark_coords_and_pitch(m, scale, root_hz)
            alpha = float(m.get("a", 0.8))
            strength = 0.04 + 0.09 * alpha
            k = m.get("k", "dot")
            if k in ("dot", "ring", "arc"):
                _add_tone(t_note, 0.65, freq, strength, pan, "bell")
            elif k in ("line", "curve"):
                _add_tone(t_note, 0.55, freq, strength, pan, "pluck")
            elif k == "spray":
                # Shimmering sparkle grains
                for g_i in range(4):
                    g_freq = freq * (1.0 + 0.125 * (g_i % 3))
                    g_pan = max(0.05, min(0.95, pan + (g_i - 1.5) * 0.08))
                    _add_tone(t_note + g_i * 0.06, 0.32, g_freq, strength * 0.55, g_pan, "sparkle")
            else:
                # glow / fill -> swell
                _add_tone(t_note, 0.95, freq * 0.5, strength * 0.75, pan, "swell")

            if time.monotonic() - last_yield >= 0.018:
                time.sleep(0.001)
                last_yield = time.monotonic()

    # Soft limiter & 16-bit PCM WAV output
    pcm = bytearray(n_samples * 4)
    for i in range(n_samples):
        l_val = math.tanh(left[i])
        r_val = math.tanh(right[i])
        li = max(-32767, min(32767, int(l_val * 30000)))
        ri = max(-32767, min(32767, int(r_val * 30000)))
        struct.pack_into("<hh", pcm, i * 4, li, ri)
        if i % 16384 == 0 and (time.monotonic() - last_yield >= 0.018):
            time.sleep(0.001)
            last_yield = time.monotonic()

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)

    return total_duration


def _load_font(size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ]
        if italic
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_title_card_image(
    width: int,
    height: int,
    project_title: str,
    subtitle: str,
    session_rgb: Tuple[float, float, float],
) -> Image.Image:
    """Render the opening title card: eye/prism over soft session glow, project title, and dim credit/music line."""
    bg = (20, 18, 24)
    img = Image.new("RGB", (width, height), bg)

    # Soft glow in the session's colour
    glow_layer = Image.new("RGB", (width, height), (0, 0, 0))
    g_draw = ImageDraw.Draw(glow_layer)
    cx, cy = width // 2, int(height * 0.42)
    max_r = int(min(width, height) * 0.34)
    sr, sg, sb = painter.tonemap_light(session_rgb[0] * 1.25, session_rgb[1] * 1.25, session_rgb[2] * 1.25)
    for step in range(24, 0, -1):
        frac = step / 24.0
        r = int(max_r * frac)
        alpha = (1.0 - frac * 0.85) * 0.55
        col = (
            int(bg[0] + (sr * 255 - bg[0]) * alpha),
            int(bg[1] + (sg * 255 - bg[1]) * alpha),
            int(bg[2] + (sb * 255 - bg[2]) * alpha),
        )
        g_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(8, width // 60)))
    img = ImageChops.lighter(img, glow_layer)

    draw = ImageDraw.Draw(img)
    # Crystalline Eye / Prism emblem in the center of the glow
    eye_rx = int(min(width, height) * 0.11)
    eye_ry = int(min(width, height) * 0.062)
    ring_col = (
        max(140, min(255, int(sr * 255 + 60))),
        max(140, min(255, int(sg * 255 + 60))),
        max(140, min(255, int(sb * 255 + 60))),
    )
    # Outer eye contour & diamond facet
    pts_eye = [
        (cx - eye_rx, cy),
        (cx, cy - eye_ry),
        (cx + eye_rx, cy),
        (cx, cy + eye_ry),
    ]
    draw.polygon(pts_eye, outline=ring_col, width=max(2, width // 360))
    iris_r = int(eye_ry * 0.58)
    draw.ellipse([cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r], outline=(255, 246, 214), width=max(2, width // 400))
    pupil_r = max(3, int(iris_r * 0.36))
    draw.ellipse([cx - pupil_r, cy - pupil_r, cx + pupil_r, cy + pupil_r], fill=(255, 246, 214))

    # Title & dim credit/music subtitle
    title_sz = max(22, int(min(width, height) * 0.042))
    sub_sz = max(15, int(min(width, height) * 0.024))
    font_title = _load_font(title_sz, italic=False)
    font_sub = _load_font(sub_sz, italic=False)

    tb = draw.textbbox((0, 0), project_title, font=font_title)
    tw = tb[2] - tb[0]
    ty = int(height * 0.64)
    draw.text(((width - tw) // 2, ty), project_title, fill=(236, 228, 240), font=font_title)

    sb_box = draw.textbbox((0, 0), subtitle, font=font_sub)
    sw = sb_box[2] - sb_box[0]
    sy = ty + int(title_sz * 1.65)
    draw.text(((width - sw) // 2, sy), subtitle, fill=(150, 140, 160), font=font_sub)
    return img


def render_roll_painting_frame(
    painting: dict,
    width: int,
    height: int,
    reveal: float,
    index_1: int,
    total_paintings: int,
    short_mode: bool = False,
) -> Image.Image:
    """Render a single painting frame at `reveal` (0..1) for the roll (landscape or upright short)."""
    bg = (20, 18, 24)
    frame = Image.new("RGB", (width, height), bg)

    by_who = "Spark" if str(painting.get("by") or "").lower() == "spark" else "Prism"
    date_str = time.strftime("%d %b %Y", time.localtime(float(painting.get("at") or time.time())))
    title_str = str(painting.get("title") or "Untitled refraction")
    meta_str = f"{by_who} · {date_str} · {index_1} of {total_paintings}"

    if short_mode:
        # Upright 1080x1920 for YouTube Shorts:
        # "each painting is large with a bigger caption right under it, a little above the middle"
        art_w = int(width * 0.92)
        art_h = int(art_w * 0.62)
        art_x = (width - art_w) // 2
        art_y = int(height * 0.24)
        art_img = painter.render_painting_canvas_pil(painting, art_w, art_h, reveal=reveal, truest=True)
        frame.paste(art_img, (art_x, art_y))

        draw = ImageDraw.Draw(frame)
        f_title = _load_font(max(26, int(width * 0.036)), italic=True)
        f_meta = _load_font(max(22, int(width * 0.029)), italic=False)
        cap_y = art_y + art_h + int(height * 0.022)
        draw.text((art_x, cap_y), title_str, fill=(236, 228, 240), font=f_title)
        draw.text((art_x, cap_y + int(width * 0.052)), meta_str, fill=(150, 140, 160), font=f_meta)
    else:
        # Standard 16:9 (1280x720 or 1920x1080)
        caption_h = int(height * 0.14)
        art_h = height - caption_h
        art_w = width
        art_img = painter.render_painting_canvas_pil(painting, art_w, art_h, reveal=reveal, truest=True)
        frame.paste(art_img, (0, 0))

        draw = ImageDraw.Draw(frame)
        f_title = _load_font(max(18, int(height * 0.036)), italic=True)
        f_meta = _load_font(max(16, int(height * 0.030)), italic=False)
        pad_x = max(16, int(width * 0.015))
        ty1 = art_h + int(caption_h * 0.14)
        ty2 = art_h + int(caption_h * 0.56)
        draw.text((pad_x, ty1), title_str, fill=(236, 228, 240), font=f_title)
        draw.text((pad_x, ty2), meta_str, fill=(150, 140, 160), font=f_meta)

    return frame


def build_session_roll(
    paintings: List[dict],
    out_dir: Path,
    *,
    mode: str = "720p",
    project_name: Optional[str] = None,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, object]:
    """Generate the complete MP4 session roll via ffmpeg, streaming one painting segment at a time."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg is required to build the session roll")

    if not paintings:
        paintings = [painter.choose_curated_painting(0)]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    short_mode = mode == "short"
    if short_mode:
        width, height = 1080, 1920
    elif mode in ("hd", "1080p"):
        width, height = 1920, 1080
    else:
        width, height = 1280, 720

    music_info = analyze_session_music(paintings)
    holds_beats = music_info["holds_beats"]
    n_paintings = len(paintings)

    # Calculate total duration & check 3-minute warning for Shorts
    title_s = TITLE_BEATS * BEAT_S
    total_s = title_s + sum(LAYDOWN_S + b * BEAT_S for b in holds_beats) - max(0, n_paintings - 1) * CROSSFADE_S
    short_warning = None
    if short_mode and total_s > 180.0:
        short_warning = f"Warning: roll duration ({total_s:.0f}s) runs past 3 minutes for YouTube Shorts."

    proj_title = project_name or Path.cwd().name or "gemini-prism"
    date_str = time.strftime("%d %b %Y")
    p_word = "painting" if n_paintings == 1 else "paintings"
    subtitle = f"Spark & Prism · {date_str} · {n_paintings} {p_word} · music in {music_info['key_label']}"

    def _report(msg: str, frac: float) -> None:
        if on_progress:
            on_progress(msg, max(0.0, min(1.0, frac)))

    _report(f"scoring music in {music_info['key_label']} · 0/{n_paintings}", 0.04)

    with tempfile.TemporaryDirectory(prefix="prism-roll-") as tmp_root_str:
        tmp_root = Path(tmp_root_str)
        wav_path = tmp_root / "soundtrack.wav"
        synthesize_roll_audio(paintings, music_info, wav_path, title_s)

        segment_files: List[Path] = []

        def _encode_frames_to_segment(frames_dir: Path, seg_path: Path) -> None:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frames_dir / "f_%05d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(seg_path),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            # Delete this painting's frames immediately once its segment is made (§5.5)
            shutil.rmtree(frames_dir, ignore_errors=True)

        # 1. Title Card Segment
        _report(f"inscribing title card · “{proj_title}”", 0.12)
        title_frames_dir = tmp_root / "seg_title"
        title_frames_dir.mkdir(parents=True, exist_ok=True)
        title_img = render_title_card_image(width, height, proj_title, subtitle, music_info["session_rgb"])
        first_paint_img = render_roll_painting_frame(
            paintings[0], width, height, reveal=1.0 / 12.0, index_1=1, total_paintings=n_paintings, short_mode=short_mode
        )
        n_title_frames = max(18, int(round(title_s * FPS)))
        fade_frames = min(12, n_title_frames // 3)
        for f_i in range(n_title_frames):
            if f_i < 8:
                # Fade in from dark ground
                alpha = (f_i + 1) / 8.0
                dark = Image.new("RGB", (width, height), (20, 18, 24))
                fr = Image.blend(dark, title_img, alpha)
            elif f_i >= n_title_frames - fade_frames:
                alpha = (f_i - (n_title_frames - fade_frames) + 1) / float(fade_frames)
                fr = Image.blend(title_img, first_paint_img, alpha)
            else:
                fr = title_img
            fr.save(title_frames_dir / f"f_{f_i:05d}.png", format="PNG", compress_level=1)
        seg_title_mp4 = tmp_root / "seg_000.mp4"
        _encode_frames_to_segment(title_frames_dir, seg_title_mp4)
        segment_files.append(seg_title_mp4)

        # 2. Stream each painting segment one at a time, deleting frames right after encoding
        for idx, p in enumerate(paintings):
            p_title = str(p.get("title") or "Untitled")[:24]
            base_frac = 0.18 + (idx / max(1, n_paintings)) * 0.72
            _report(f"laying down “{p_title}” · {idx + 1}/{n_paintings}", base_frac)

            seg_dir = tmp_root / f"seg_p_{idx:03d}"
            seg_dir.mkdir(parents=True, exist_ok=True)

            # Laydown: 2s at 12 fps (24 key frames), smoothed to 30 fps (60 frames)
            n_key = int(round(LAYDOWN_S * 12))  # 24 steps
            key_imgs: List[Image.Image] = []
            for k_i in range(1, n_key + 1):
                rev = k_i / float(n_key)
                key_imgs.append(
                    render_roll_painting_frame(
                        p, width, height, reveal=rev, index_1=idx + 1, total_paintings=n_paintings, short_mode=short_mode
                    )
                )
                if k_i % 6 == 0:
                    _report(
                        f"laying down “{p_title}” · {idx + 1}/{n_paintings}",
                        base_frac + (k_i / float(n_key)) * (0.5 / max(1, n_paintings)),
                    )

            frame_counter = 0
            n_lay_frames = int(round(LAYDOWN_S * FPS))  # 60 frames
            for f_i in range(n_lay_frames):
                u = (f_i / max(1, n_lay_frames - 1)) * (len(key_imgs) - 1)
                k0 = int(math.floor(u))
                k1 = min(len(key_imgs) - 1, k0 + 1)
                frac_u = u - k0
                if k0 == k1 or frac_u <= 0.01:
                    fr = key_imgs[k0]
                else:
                    fr = Image.blend(key_imgs[k0], key_imgs[k1], frac_u)
                fr.save(seg_dir / f"f_{frame_counter:05d}.png", format="PNG", compress_level=1)
                frame_counter += 1

            held_img = key_imgs[-1]
            hold_s = holds_beats[idx] * BEAT_S
            has_next = idx < n_paintings - 1
            pure_hold_s = max(0.2, hold_s - (CROSSFADE_S if has_next else 0.0))
            n_hold_frames = max(6, int(round(pure_hold_s * FPS)))
            for _ in range(n_hold_frames):
                held_img.save(seg_dir / f"f_{frame_counter:05d}.png", format="PNG", compress_level=1)
                frame_counter += 1

            # Crossfade (0.6 s = 18 frames) into the next painting
            if has_next:
                next_first = render_roll_painting_frame(
                    paintings[idx + 1],
                    width,
                    height,
                    reveal=1.0 / 12.0,
                    index_1=idx + 2,
                    total_paintings=n_paintings,
                    short_mode=short_mode,
                )
                n_xfade = max(6, int(round(CROSSFADE_S * FPS)))
                for xf_i in range(n_xfade):
                    alpha = (xf_i + 1) / float(n_xfade)
                    fr = Image.blend(held_img, next_first, alpha)
                    fr.save(seg_dir / f"f_{frame_counter:05d}.png", format="PNG", compress_level=1)
                    frame_counter += 1

            seg_mp4 = tmp_root / f"seg_{idx + 1:03d}.mp4"
            _encode_frames_to_segment(seg_dir, seg_mp4)
            segment_files.append(seg_mp4)

        # 3. Concatenate video segments + mux synthesized WAV soundtrack into final MP4
        _report(f"weaving final roll in {music_info['key_label']} · {n_paintings}/{n_paintings}", 0.94)
        concat_txt = tmp_root / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{seg.name}'" for seg in segment_files) + "\n",
            encoding="utf-8",
        )

        existing_mp4 = sorted(out_dir.glob("*.mp4"))
        roll_idx = len(existing_mp4) + 1
        suffix = f"-{mode}" if mode != "720p" else ""
        out_mp4 = out_dir / f"{roll_idx:02d}-session-roll{suffix}.mp4"

        cmd_final = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-i",
            str(wav_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
        subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    painter.rebuild_gallery_html(out_dir)
    _report(f"crystallized roll · {out_mp4.name}", 1.0)
    return {
        "path": str(out_mp4),
        "key": music_info["key_label"],
        "paintings": n_paintings,
        "duration": round(total_s, 1),
        "warning": short_warning,
    }
