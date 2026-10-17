#!/usr/bin/env python3
"""mcp_server.py - Stdio MCP Server for Prism's Permanent Terminal Expressive Channel.

Exposes zero-dependency Model Context Protocol (MCP) tools that allow Prism (or her
subagents) to project live thoughts, moods, particle animations, custom core glyphs,
and holographic ASCII/Unicode art directly into her running 20 FPS terminal companion.

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


def expression_file_path(environ: Optional[Dict[str, str]] = None) -> Path:
    """Resolve the path to Prism's live expression channel state file."""
    env = os.environ if environ is None else environ
    override = env.get("PRISM_EXPRESSION_FILE")
    if override:
        return Path(override)
    home = env.get("HOME", "/tmp")
    state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
    return state_home / "gemini-prism" / "expression.json"


try:
    import painter
except ImportError:
    try:
        from scripts import painter
    except ImportError:
        painter = None


def write_expression(
    thought: Optional[str] = None,
    *,
    mood: Optional[str] = None,
    effect: Optional[str] = None,
    glyph: Optional[str] = None,
    art: Optional[List[str]] = None,
    painting: Optional[Dict[str, Any]] = None,
    ttl: float = 0.0,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Atomically write an expressive update (and optional painting) to Prism's terminal channel."""
    target = expression_file_path(environ)
    target.parent.mkdir(parents=True, exist_ok=True)

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
        parsed_p = painter.parse_painting(painting)
        if parsed_p:
            parsed_p["at"] = now
            active_painting = parsed_p
            paint_stats = {
                "paintings": int(paint_stats.get("paintings", 0)) + 1,
                "tokens": int(paint_stats.get("tokens", 0)) + int(parsed_p.get("tokens") or 2100),
            }

    thought_val = (
        str(thought).strip()[:240]
        if thought is not None
        else str(prev.get("thought") or "")
    )

    payload = {
        "v": 1,
        "thought": thought_val,
        "mood": clean_mood,
        "effect": clean_effect,
        "glyph": clean_glyph,
        "art": clean_art,
        "painting": active_painting,
        "paintStats": paint_stats,
        "updatedAt": now,
        "expiresAt": (now + ttl_val) if ttl_val > 0 else None,
    }

    fd, tmp_path = tempfile.mkstemp(prefix=".expr-", suffix=".tmp", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    return payload


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
    """Read the active expression; if a thought TTL expired, keep the permanent painting spot intact."""
    target = expression_file_path(environ)
    if not target.is_file() or target.is_symlink():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("v") != 1:
            return None
        expires_at = data.get("expiresAt")
        now_ts = time.time() if now is None else now
        if isinstance(expires_at, (int, float)) and now_ts > expires_at:
            if data.get("painting"):
                return {
                    "v": 1,
                    "thought": "",
                    "mood": data.get("mood"),
                    "effect": None,
                    "glyph": None,
                    "art": [],
                    "painting": data.get("painting"),
                    "paintStats": data.get("paintStats"),
                }
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


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
            "using the Cyclops/Spark mark vocabulary (fill, glow, line, curve, dot, ring, arc, spray) "
            "or a curated painting preset, with optional SVG export to prism-paintings/."
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
                "marks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Array of mark objects on a [0..1] canvas: "
                        "fill ({k:'fill',pts:[[x,y],...],c:'#rrggbb',c2:'#rrggbb',grad:0.25,a:0.9}), "
                        "glow ({k:'glow',x:0.5,y:0.5,r:0.3,c:'#rrggbb',a:0.7}), "
                        "line/curve ({k:'line'|'curve',pts:[[x,y],...],w:0.02,c:'#rrggbb',c2:'#rrggbb',a:0.9}), "
                        "dot ({k:'dot',x:0.5,y:0.5,r:0.05,c:'#rrggbb',a:1}), "
                        "ring/arc ({k:'ring'|'arc',x:0.5,y:0.5,r:0.15,w:0.02,a0:0,a1:0.5,c:'#rrggbb',a:0.8}), "
                        "spray ({k:'spray',x:0.5,y:0.4,r:0.3,n:45,s:0.014,c:'#rrggbb',a:0.7})."
                    ),
                },
                "preset": {
                    "type": "integer",
                    "description": "Optional curated painting index (0..3) if custom marks are not provided.",
                },
                "convert": {
                    "type": "boolean",
                    "description": "If true, also export a 1920x1100 bloom SVG + index.html to prism-paintings/.",
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

    # Notifications (no id) require no response
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
                "serverInfo": {"name": "cyclops-prism-express", "version": "1.4.0"},
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
            if not paint_obj:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid painting marks"},
                }
            payload = write_expression(
                thought=args.get("thought") or paint_obj.get("thought") or None,
                mood=args.get("mood") or paint_obj.get("mood"),
                painting=paint_obj,
            )
            svg_msg = ""
            if args.get("convert"):
                svg_path = painter.save_painting_to_gallery(paint_obj)
                svg_msg = f" (saved SVG to {svg_path})"
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
            # Consume remaining headers until blank line
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
