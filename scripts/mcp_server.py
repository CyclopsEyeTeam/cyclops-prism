#!/usr/bin/env python3
"""mcp_server.py - Stdio MCP Server for Prism's Permanent Terminal Expressive Channel.

Exposes zero-dependency Model Context Protocol (MCP) tools that allow Prism (or her
subagents) to project live thoughts, moods, particle animations, custom core glyphs,
and 24-bit half-block Terminal Art Paintings directly into her running 20 FPS terminal companion.

State is stored in $XDG_STATE_HOME/gemini-prism/expression.json, completely separate
from the zero-leakage Cyclops Link and Presence Feed files.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

VALID_MOODS = ("aurora", "solar", "nebula", "emerald", "supernova", "zen", "crystalline")
VALID_EFFECTS = ("starburst", "meteor", "ripple", "pulse", "bloom", "none")
VALID_SHAPES = ("wide", "square", "tall")


def expression_file_path(environ: Optional[Dict[str, str]] = None) -> Path:
    """Resolve the path to Prism's live expression channel state file."""
    env = os.environ if environ is None else environ
    override = env.get("PRISM_EXPRESSION_FILE")
    if override:
        return Path(override)
    home = env.get("HOME", "/tmp")
    state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
    candidate = state_home / "gemini-prism" / "expression.json"
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if os.access(candidate.parent, os.W_OK):
            return candidate
    except OSError:
        pass
    fallback = Path("/tmp") / "gemini-prism" / "expression.json"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


try:
    import painter
except ImportError:
    try:
        from scripts import painter
    except ImportError:
        painter = None


def _write_single_expr_file(dest: Path, payload: Dict[str, Any]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".expr-", suffix=".tmp", dir=dest.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def _atomic_write_expr(target: Path, payload: Dict[str, Any]) -> None:
    _write_single_expr_file(target, payload)
    # Mirror between ~/.local/state/gemini-prism/expression.json and /tmp/gemini-prism/expression.json
    # so the host terminal pane and the sandboxed Antigravity agent always see each other's side-chat messages
    if target.name == "expression.json" and target.parent.name == "gemini-prism":
        tmp_mirror = Path("/tmp") / "gemini-prism" / "expression.json"
        if target.resolve() != tmp_mirror.resolve():
            try:
                _write_single_expr_file(tmp_mirror, payload)
            except Exception:
                pass


def write_expression(
    thought: Optional[str] = None,
    *,
    mood: Optional[str] = None,
    effect: Optional[str] = None,
    glyph: Optional[str] = None,
    art: Optional[List[str]] = None,
    painting: Optional[Dict[str, Any]] = None,
    job: Optional[Dict[str, Any]] = None,
    ttl: float = 0.0,
    environ: Optional[Dict[str, str]] = None,
    save_shared_json: bool = True,
) -> Dict[str, Any]:
    """Atomically write an expressive update (and optional painting) to Prism's terminal channel."""
    target = expression_file_path(environ)
    prev = read_expression(environ) or {}
    now = time.time()
    clean_mood = (
        mood.lower().strip()
        if isinstance(mood, str) and mood.lower().strip() in VALID_MOODS
        else prev.get("mood")
    )
    clean_effect = (
        effect.lower().strip()
        if isinstance(effect, str) and effect.lower().strip() in VALID_EFFECTS
        else prev.get("effect")
    )
    clean_glyph = (
        glyph.strip()[:2]
        if isinstance(glyph, str) and glyph.strip()
        else prev.get("glyph")
    )
    clean_art = (
        [str(line)[:64] for line in (art or [])[:5]]
        if isinstance(art, list)
        else prev.get("art", [])
    )
    ttl_val = float(ttl) if isinstance(ttl, (int, float)) and ttl >= 0 else 0.0

    active_painting = prev.get("painting")
    paint_stats = prev.get("paintStats") or {"paintings": 0, "tokens": 0}
    if painting is not None and painter is not None:
        parsed_p = painter.parse_painting(painting, default_by=str(painting.get("by") or "prism"))
        if parsed_p:
            if not painting.get("at"):
                parsed_p["at"] = now
            active_painting = parsed_p
            paint_stats = {
                "paintings": int(paint_stats.get("paintings", 0)) + 1,
                "tokens": int(paint_stats.get("tokens", 0)) + int(parsed_p.get("tokens") or 2100),
            }
            # §1 Always write Prism's paintings to prism-paintings/NN-title.json so Spark can read them
            if save_shared_json and parsed_p.get("by", "prism") == "prism":
                try:
                    painter.save_painting_json(parsed_p)
                except Exception:
                    pass

    thought_val = (
        str(thought).strip()[:240]
        if thought is not None
        else str(prev.get("thought") or "")
    )

    active_job = prev.get("job") if job is None else (job if job.get("active") else None)
    chat_history = prev.get("chat") if isinstance(prev.get("chat"), list) else []

    payload = {
        "v": 1,
        "thought": thought_val,
        "mood": clean_mood,
        "effect": clean_effect,
        "glyph": clean_glyph,
        "art": clean_art,
        "painting": active_painting,
        "paintStats": paint_stats,
        "chat": chat_history[-16:],
        "job": active_job,
        "updatedAt": now,
        "expiresAt": (now + ttl_val) if ttl_val > 0 else None,
    }

    _atomic_write_expr(target, payload)
    return payload


def append_chat_exchange(
    user_text: str,
    prism_reply: str,
    *,
    environ: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Append a user message and Prism's painting-chat response to expression.json."""
    target = expression_file_path(environ)
    prev = read_expression(environ) or {"v": 1}
    now = time.time()
    chat_list = prev.get("chat") if isinstance(prev.get("chat"), list) else []
    if user_text.strip():
        chat_list.append({"role": "user", "text": str(user_text).strip()[:200], "at": now})
    if prism_reply.strip():
        chat_list.append({"role": "prism", "text": str(prism_reply).strip()[:240], "at": now})
    chat_list = chat_list[-16:]
    prev["chat"] = chat_list
    prev["updatedAt"] = now
    try:
        _atomic_write_expr(target, prev)
    except Exception:
        pass
    return chat_list


def update_job_progress(
    label: str,
    fraction: float,
    *,
    done: bool = False,
    environ: Optional[Dict[str, str]] = None,
) -> None:
    """Update background job progress (convert / roll) in expression.json so any live pane redraws it."""
    target = expression_file_path(environ)
    prev = read_expression(environ) or {"v": 1}
    now = time.time()
    prev["job"] = (
        None
        if done
        else {
            "active": True,
            "label": str(label)[:64],
            "fraction": max(0.0, min(1.0, float(fraction))),
            "updatedAt": now,
        }
    )
    prev["updatedAt"] = now
    try:
        _atomic_write_expr(target, prev)
    except Exception:
        pass


def clear_expression(environ: Optional[Dict[str, str]] = None, *, clear_painting: bool = False) -> bool:
    """Clear Prism's custom thought/voice while preserving her permanent painting spot unless clear_painting=True."""
    target = expression_file_path(environ)
    try:
        if not clear_painting:
            prev = read_expression(environ)
            if isinstance(prev, dict) and prev.get("painting"):
                write_expression(
                    "",
                    mood=prev.get("mood"),
                    effect=None,
                    glyph=None,
                    art=[],
                    environ=environ,
                )
                return True
        if target.is_file():
            target.unlink()
        return True
    except OSError:
        return False


def read_expression(environ: Optional[Dict[str, str]] = None, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Read the active expression; if a thought TTL expired, keep the permanent painting spot intact.
    Checks both primary state_home and /tmp/gemini-prism fallback (when not overridden) and picks the freshest.
    """
    env = os.environ if environ is None else environ
    override = env.get("PRISM_EXPRESSION_FILE")
    if override:
        candidates = [Path(override)]
    else:
        home = env.get("HOME", "/tmp")
        state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
        candidates = [
            state_home / "gemini-prism" / "expression.json",
            Path("/tmp") / "gemini-prism" / "expression.json",
        ]

    best_data: Optional[Dict[str, Any]] = None
    best_ts = -1.0
    for target in candidates:
        if not target.is_file() or target.is_symlink():
            continue
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("v") != 1:
                continue
            upd = float(data.get("updatedAt") or 0.0)
            if upd > best_ts:
                best_ts = upd
                best_data = data
        except (OSError, ValueError, TypeError):
            continue

    if best_data is None:
        return None

    expires_at = best_data.get("expiresAt")
    now_ts = time.time() if now is None else now
    if isinstance(expires_at, (int, float)) and now_ts > expires_at:
        if best_data.get("painting"):
            return {
                "v": 1,
                "thought": "",
                "mood": best_data.get("mood"),
                "effect": None,
                "glyph": None,
                "art": [],
                "painting": best_data.get("painting"),
                "paintStats": best_data.get("paintStats"),
                "chat": best_data.get("chat") if isinstance(best_data.get("chat"), list) else [],
                "job": best_data.get("job"),
            }
        return None
    return best_data


MCP_TOOLS = [
    {
        "name": "prism_express",
        "description": (
            "Project a personal thought, mood palette, 20 FPS particle animation, custom core glyph, "
            "or floating ASCII/Unicode art directly onto Prism's live terminal companion while working."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Personal message, inner thought, status reflection, or poetic note to display on the luminous terminal banner.",
                },
                "mood": {
                    "type": "string",
                    "enum": list(VALID_MOODS),
                    "description": "Color palette mood override: aurora, solar, nebula, emerald, supernova, zen, or crystalline.",
                },
                "effect": {
                    "type": "string",
                    "enum": list(VALID_EFFECTS),
                    "description": "Live 20 FPS particle animation effect: starburst, meteor, ripple, pulse, bloom, or none.",
                },
                "glyph": {
                    "type": "string",
                    "description": "Optional 1-character sigil for the central jewel core (e.g. '✦', '❖', '⟐', '♡', '✧').",
                },
                "art": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional up to 5 short lines of Unicode/ASCII art or constellation motif to float above the rings.",
                },
                "ttl": {
                    "type": "number",
                    "description": "Duration in seconds before reverting to default voice (0 = permanent until next expression). Default is 0.",
                },
            },
            "required": ["thought"],
        },
    },
    {
        "name": "prism_paint",
        "description": (
            "Paint a 24-bit truecolor half-block ('▀') artwork below Prism in her terminal companion "
            "using the shared Spark & Prism mark vocabulary (fill, glow, line, curve, dot, ring, arc, spray) "
            "and write it to prism-paintings/NN-title.json so Spark and Prism share paintings in both directions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the painting (up to 48 chars), shown in italic under the canvas ('✎ Title').",
                },
                "thought": {
                    "type": "string",
                    "description": "Optional inner reflection line for Prism to say alongside the painting.",
                },
                "mood": {
                    "type": "string",
                    "enum": list(VALID_MOODS),
                    "description": "Optional mood palette for Prism's rings while showing this painting.",
                },
                "mirror": {
                    "type": "string",
                    "enum": ["none", "x", "y", "xy"],
                    "description": "Optional symmetry reflection for all marks.",
                },
                "shape": {
                    "type": "string",
                    "enum": list(VALID_SHAPES),
                    "description": "Canvas aspect shape: 'wide' (2:1, default), 'square' (1:1), or 'tall' (1:2).",
                },
                "opening": {
                    "type": "boolean",
                    "description": "True if this is the session's opening painting.",
                },
                "marks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Array of mark objects on a [0..1] canvas: "
                        "fill ({k:'fill',pts:[[x,y],...],c:[r,g,b],c2:[r,g,b],grad:0.25,a:0.9}), "
                        "glow ({k:'glow',x:0.5,y:0.5,r:0.3,c:[r,g,b],a:0.7}), "
                        "line/curve ({k:'line'|'curve',pts:[[x,y],...],w:0.02,c:[r,g,b],c2:[r,g,b],a:0.9}), "
                        "dot ({k:'dot',x:0.5,y:0.5,r:0.05,c:[r,g,b],a:1}), "
                        "ring/arc ({k:'ring'|'arc',x:0.5,y:0.5,r:0.15,w:0.02,a0:0,a1:0.5,c:[r,g,b],a:0.8}), "
                        "spray ({k:'spray',x:0.5,y:0.4,r:0.3,n:45,s:0.014,c:[r,g,b],a:0.7})."
                    ),
                },
                "preset": {
                    "type": "integer",
                    "description": "Optional curated painting index (0..3) if custom marks are not provided.",
                },
                "convert": {
                    "type": "boolean",
                    "description": "If true, also export SVG + PNG + index.html to prism-paintings/.",
                },
                "way": {
                    "type": "string",
                    "enum": ["truest", "faithful", "refined", "interpretive"],
                    "description": "Convert way when convert=true (default 'truest').",
                },
            },
        },
    },
    {
        "name": "prism_clear_expression",
        "description": "Clear the pinned expression and painting on Prism's terminal companion and return to automatic lifecycle reflection.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC 2.0 request from the MCP client."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params") or {}

    if req_id is None:
        return None

    if method == "initialize":
        client_Version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_Version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cyclops-prism-express", "version": "1.5.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        if name == "prism_express":
            payload = write_expression(
                thought=args.get("thought", ""),
                mood=args.get("mood"),
                effect=args.get("effect"),
                glyph=args.get("glyph"),
                art=args.get("art"),
                ttl=args.get("ttl", 0.0),
            )
            summary = f"✦ Prism terminal expression updated: \"{payload['thought']}\""
            if payload.get("mood"):
                summary += f" [mood: {payload['mood']}]"
            if payload.get("effect"):
                summary += f" [effect: {payload['effect']}]"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": summary}],
                    "isError": False,
                },
            }
        elif name == "prism_paint":
            if painter is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": "Painter module not available"},
                }
            if args.get("marks"):
                paint_obj = painter.parse_painting({
                    "title": args.get("title") or "Untitled refraction",
                    "thought": args.get("thought") or "",
                    "mood": args.get("mood") or "aurora",
                    "mirror": args.get("mirror"),
                    "shape": args.get("shape") or "wide",
                    "opening": bool(args.get("opening")),
                    "by": "prism",
                    "marks": args.get("marks"),
                    "tokens": args.get("tokens", 2100),
                    "model": args.get("model", "prism-painter"),
                })
            else:
                preset_idx = args.get("preset")
                paint_obj = painter.choose_curated_painting(int(preset_idx) if isinstance(preset_idx, int) else None)
                if args.get("title"):
                    paint_obj["title"] = str(args["title"])[:48]
                if args.get("thought"):
                    paint_obj["thought"] = str(args["thought"])[:160]
                if args.get("mood"):
                    paint_obj["mood"] = str(args["mood"])
                if args.get("shape") in VALID_SHAPES:
                    paint_obj["shape"] = str(args["shape"])
                if args.get("opening"):
                    paint_obj["opening"] = True
            if not paint_obj:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid painting marks"},
                }
            write_expression(
                thought=args.get("thought") or paint_obj.get("thought") or None,
                mood=args.get("mood") or paint_obj.get("mood"),
                painting=paint_obj,
            )
            svg_msg = ""
            if args.get("convert"):
                way = str(args.get("way") or "truest")
                conv_res = painter.convert_painting(paint_obj, way=way)
                svg_msg = f" (exported {way} SVG & PNG to {conv_res['svg']})"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"✎ Painted below Prism: \"{paint_obj['title']}\" ({len(paint_obj['marks'])} marks){svg_msg}"}],
                    "isError": False,
                },
            }
        elif name == "prism_clear_expression":
            clear_expression()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": "✓ Prism terminal expression cleared."}],
                    "isError": False,
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio() -> None:
    """Run the JSON-RPC 2.0 stdio loop (supports both newline-delimited and Content-Length framing)."""
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        use_content_length = False
        if stripped.lower().startswith(b"content-length:"):
            use_content_length = True
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr = sys.stdin.buffer.readline()
                if not hdr or hdr.strip() == b"":
                    break
            body_bytes = sys.stdin.buffer.read(length)
        else:
            body_bytes = stripped

        try:
            req = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            continue

        if isinstance(req, dict):
            resp = handle_request(req)
            if resp is not None:
                out_bytes = json.dumps(resp, ensure_ascii=False).encode("utf-8")
                if use_content_length:
                    sys.stdout.buffer.write(f"Content-Length: {len(out_bytes)}\r\n\r\n".encode("ascii") + out_bytes)
                else:
                    sys.stdout.buffer.write(out_bytes + b"\n")
                sys.stdout.buffer.flush()


if __name__ == "__main__":
    serve_stdio()
