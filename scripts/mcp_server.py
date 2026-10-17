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


def write_expression(
    thought: str = "",
    *,
    mood: Optional[str] = None,
    effect: Optional[str] = None,
    glyph: Optional[str] = None,
    art: Optional[List[str]] = None,
    ttl: float = 0.0,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Atomically write an expressive update to Prism's terminal channel."""
    target = expression_file_path(environ)
    target.parent.mkdir(parents=True, exist_ok=True)

    now = time.time()
    clean_mood = mood.lower().strip() if isinstance(mood, str) and mood.lower().strip() in VALID_MOODS else None
    clean_effect = effect.lower().strip() if isinstance(effect, str) and effect.lower().strip() in VALID_EFFECTS else None
    clean_glyph = glyph.strip()[:2] if isinstance(glyph, str) and glyph.strip() else None
    clean_art = [str(line)[:64] for line in (art or [])[:5]] if isinstance(art, list) else []
    ttl_val = float(ttl) if isinstance(ttl, (int, float)) and ttl >= 0 else 0.0

    payload = {
        "v": 1,
        "thought": str(thought or "").strip()[:240],
        "mood": clean_mood,
        "effect": clean_effect,
        "glyph": clean_glyph,
        "art": clean_art,
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


def clear_expression(environ: Optional[Dict[str, str]] = None) -> bool:
    """Clear Prism's custom expression and return to autonomous state reflection."""
    target = expression_file_path(environ)
    try:
        if target.is_file():
            target.unlink()
        return True
    except OSError:
        return False


def read_expression(environ: Optional[Dict[str, str]] = None, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Read the active expression if present and not expired."""
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
        "name": "prism_clear_expression",
        "description": "Clear the pinned expression on Prism's terminal companion and return to automatic lifecycle reflection.",
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
                "serverInfo": {"name": "cyclops-prism-express", "version": "1.3.0"},
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
