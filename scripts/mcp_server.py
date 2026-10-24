#!/usr/bin/env python3
"""mcp_server.py - Stdio MCP Server for Prism's Permanent Terminal Expressive Channel.

Exposes zero-dependency Model Context Protocol (MCP) tools that allow Prism (or her
subagents) to project live thoughts, moods, particle animations, custom core glyphs,
and 24-bit half-block Terminal Art Paintings directly into her running 20 FPS terminal companion.

State is stored in $XDG_STATE_HOME/gemini-prism/expression.json, completely separate
from the zero-leakage Cyclops Link and Presence Feed files.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

VALID_MOODS = ("aurora", "solar", "nebula", "emerald", "supernova", "zen", "crystalline")
VALID_EFFECTS = ("starburst", "meteor", "ripple", "pulse", "bloom", "none")
VALID_SHAPES = ("wide", "square", "tall")
VALID_SCOPES = ("session", "dir")


def _is_default_state_home(environ: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    custom = env.get("XDG_STATE_HOME")
    if not custom:
        return True
    home = env.get("HOME", "/tmp")
    try:
        return Path(custom).resolve() == (Path(home) / ".local" / "state").resolve()
    except OSError:
        return False


def _active_project_candidates(environ: Optional[Dict[str, str]] = None) -> List[Path]:
    env = os.environ if environ is None else environ
    home = env.get("HOME", "/tmp")
    state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
    cands = [state_home / "gemini-prism" / "active_project.json"]
    if _is_default_state_home(env):
        cands.append(Path("/tmp") / "gemini-prism" / "active_project.json")
    return cands


def set_active_project(
    project_dir: Path,
    *,
    session_id: Optional[str] = None,
    session_start: Optional[float] = None,
    environ: Optional[Dict[str, str]] = None,
) -> None:
    """Record the active project directory and session so stdio MCP tools target the active workspace."""
    try:
        resolved = str(Path(project_dir).resolve())
    except OSError:
        resolved = str(project_dir)
    payload = {
        "v": 1,
        "projectDir": resolved,
        "sessionId": session_id,
        "sessionStart": session_start,
        "updatedAt": time.time(),
    }
    for cand in _active_project_candidates(environ):
        try:
            _write_single_expr_file(cand, payload)
        except Exception:
            pass


def resolve_project_dir(
    project_dir: Optional[Path] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Path:
    """Resolve the active workspace directory for scoping paintings and expression state."""
    if project_dir is not None:
        try:
            return Path(project_dir).resolve()
        except OSError:
            return Path(project_dir)
    env = os.environ if environ is None else environ
    env_proj = env.get("PRISM_PROJECT_DIR")
    if env_proj:
        try:
            p_env = Path(env_proj).resolve()
            if p_env.is_dir():
                return p_env
        except OSError:
            pass
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = Path("/tmp")

    home_dir = Path(env.get("HOME", "/tmp")).resolve() if env.get("HOME") else Path("/tmp")
    cwd_str = str(cwd)
    # When spawned by Antigravity as a plugin MCP server, cwd is the plugin directory or $HOME
    if ".gemini/config/plugins" in cwd_str or cwd == home_dir:
        best_proj: Optional[Path] = None
        best_ts = -1.0
        for cand in _active_project_candidates(env):
            if not cand.is_file() or cand.is_symlink():
                continue
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                p_str = data.get("projectDir")
                upd = float(data.get("updatedAt") or 0.0)
                if p_str and upd > best_ts:
                    p_cand = Path(p_str).resolve()
                    if p_cand.is_dir():
                        best_ts = upd
                        best_proj = p_cand
            except Exception:
                continue
        if best_proj is not None:
            return best_proj
    return cwd


def _project_hash(project_dir: Path) -> str:
    try:
        norm = str(Path(project_dir).resolve())
    except OSError:
        norm = str(project_dir)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def expression_file_path(
    environ: Optional[Dict[str, str]] = None,
    project_dir: Optional[Path] = None,
) -> Path:
    """Resolve the path to Prism's directory-scoped live expression channel state file."""
    env = os.environ if environ is None else environ
    override = env.get("PRISM_EXPRESSION_FILE")
    if override:
        return Path(override)
    proj = resolve_project_dir(project_dir, env)
    p_hash = _project_hash(proj)
    home = env.get("HOME", "/tmp")
    state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
    candidate = state_home / "gemini-prism" / "projects" / p_hash / "expression.json"
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if os.access(candidate.parent, os.W_OK):
            return candidate
    except OSError:
        pass
    fallback = Path("/tmp") / "gemini-prism" / "projects" / p_hash / "expression.json"
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
        os.replace(tmp_path, dest)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def _atomic_write_expr(target: Path, payload: Dict[str, Any], environ: Optional[Dict[str, str]] = None) -> None:
    _write_single_expr_file(target, payload)
    # Mirror between ~/.local/state/gemini-prism/projects/<hash>/expression.json and /tmp/gemini-prism/projects/<hash>/expression.json
    # so the host terminal pane and the sandboxed Antigravity agent always see each other's updates for the same project
    if target.name == "expression.json" and _is_default_state_home(environ):
        if target.parent.parent.name == "projects":
            tmp_mirror = Path("/tmp") / "gemini-prism" / "projects" / target.parent.name / "expression.json"
            if target.resolve() != tmp_mirror.resolve():
                try:
                    _write_single_expr_file(tmp_mirror, payload)
                except Exception:
                    pass


def compute_paint_stats(
    project_dir: Path,
    *,
    scope: str = "session",
    session_start: float = 0.0,
    active_painting: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute truthful session and directory painting counts and token totals for the project."""
    clean_scope = "dir" if str(scope).lower().strip() in ("dir", "directory", "folder", "all") else "session"
    if painter is None:
        tok = int((active_painting or {}).get("tokens") or 2100)
        return {"paintings": 1, "tokens": tok, "dirPaintings": 1, "scope": clean_scope}

    all_dir = painter.load_session_paintings(project_dir, session_start=0.0)
    if clean_scope == "dir" or session_start <= 0.0:
        scoped = all_dir
    else:
        scoped = painter.load_session_paintings(project_dir, session_start=session_start, strict_session=True)
        if not scoped and active_painting:
            scoped = [active_painting]

    n_scoped = max(1, len(scoped)) if (scoped or active_painting) else 0
    n_dir = max(n_scoped, len(all_dir))
    if scoped:
        tokens_total = sum(int(p.get("tokens") or 2100) for p in scoped)
    elif active_painting:
        tokens_total = int(active_painting.get("tokens") or 2100)
    else:
        tokens_total = 0

    return {
        "paintings": max(1, n_scoped),
        "tokens": max(2100 if n_scoped else 0, tokens_total),
        "dirPaintings": max(1, n_dir),
        "scope": clean_scope,
    }


def write_expression(
    thought: Optional[str] = None,
    *,
    mood: Optional[str] = None,
    effect: Optional[str] = None,
    glyph: Optional[str] = None,
    art: Optional[List[str]] = None,
    painting: Optional[Dict[str, Any]] = None,
    paint_enabled: Optional[bool] = None,
    paint_mode: Optional[str] = None,
    paint_scope: Optional[str] = None,
    session_start: Optional[float] = None,
    session_id: Optional[str] = None,
    project_dir: Optional[Path] = None,
    reset_session: bool = False,
    job: Optional[Dict[str, Any]] = None,
    ttl: float = 0.0,
    environ: Optional[Dict[str, str]] = None,
    save_shared_json: bool = True,
) -> Dict[str, Any]:
    """Atomically write an expressive update (and optional painting) to Prism's directory-scoped terminal channel."""
    proj = resolve_project_dir(project_dir, environ)
    target = expression_file_path(environ, project_dir=proj)
    prev = {} if reset_session else (read_expression(environ, project_dir=proj) or {})
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
    raw_pm = str(paint_mode if paint_mode is not None else (prev.get("paintMode") or "live")).lower().strip()
    clean_paint_mode = "work" if raw_pm in ("work", "relative", "story-mode") else "live"

    if paint_enabled is not None:
        clean_paint_enabled = bool(paint_enabled)
    elif painting is not None:
        clean_paint_enabled = True
    elif "paintEnabled" in prev:
        clean_paint_enabled = bool(prev.get("paintEnabled"))
    else:
        clean_paint_enabled = False

    raw_scope = str(
        paint_scope
        if paint_scope is not None
        else (os.environ.get("PRISM_PAINT_SCOPE") or prev.get("paintScope") or "session")
    ).lower().strip()
    clean_scope = "dir" if raw_scope in ("dir", "directory", "folder", "all") else "session"

    eff_session_start = float(
        session_start
        if session_start is not None
        else (prev.get("sessionStart") or os.environ.get("PRISM_SESSION_START") or now)
    )
    eff_session_id = session_id if session_id is not None else prev.get("sessionId")
    ttl_val = float(ttl) if isinstance(ttl, (int, float)) and ttl >= 0 else 0.0

    active_painting = None if (paint_enabled is False and painting is None) else prev.get("painting")
    paint_stats = prev.get("paintStats") or {"paintings": 0, "tokens": 0, "dirPaintings": 0, "scope": clean_scope}
    if painting is not None and painter is not None:
        parsed_p = painter.parse_painting(painting, default_by=str(painting.get("by") or "prism"))
        if parsed_p:
            if not painting.get("at"):
                parsed_p["at"] = now
            active_painting = parsed_p
            # §1 Always write Prism's paintings to <project_dir>/prism-paintings/NN-title.json so Spark can read them
            if save_shared_json and parsed_p.get("by", "prism") == "prism":
                try:
                    saved_p = painter.save_painting_json(parsed_p, gallery_dir=proj / "prism-paintings")
                    if saved_p:
                        parsed_p["_file"] = str(saved_p)
                except Exception:
                    pass
            paint_stats = compute_paint_stats(
                proj,
                scope=clean_scope,
                session_start=eff_session_start,
                active_painting=active_painting,
            )
    elif paint_scope is not None or session_start is not None or reset_session or paint_enabled is not None:
        paint_stats = compute_paint_stats(
            proj,
            scope=clean_scope,
            session_start=eff_session_start,
            active_painting=active_painting,
        )

    thought_val = (
        str(thought).strip()[:240]
        if thought is not None
        else str(prev.get("thought") or "")
    )

    active_job = prev.get("job") if job is None else (job if job.get("active") else None)
    chat_history = prev.get("chat") if isinstance(prev.get("chat"), list) else []

    payload = {
        "v": 1,
        "projectDir": str(proj),
        "sessionId": eff_session_id,
        "sessionStart": eff_session_start,
        "paintEnabled": clean_paint_enabled,
        "paintScope": clean_scope,
        "thought": thought_val,
        "mood": clean_mood,
        "effect": clean_effect,
        "glyph": clean_glyph,
        "art": clean_art,
        "paintMode": clean_paint_mode,
        "painting": active_painting,
        "paintStats": paint_stats,
        "chat": chat_history[-16:],
        "job": active_job,
        "updatedAt": now,
        "expiresAt": (now + ttl_val) if ttl_val > 0 else None,
    }

    _atomic_write_expr(target, payload, environ=environ)
    return payload


def append_chat_exchange(
    user_text: str,
    prism_reply: str,
    *,
    environ: Optional[Dict[str, str]] = None,
    project_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Append a user message and Prism's painting-chat response to the project's expression.json."""
    proj = resolve_project_dir(project_dir, environ)
    target = expression_file_path(environ, project_dir=proj)
    prev = read_expression(environ, project_dir=proj) or {"v": 1, "projectDir": str(proj)}
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
        _atomic_write_expr(target, prev, environ=environ)
    except Exception:
        pass
    return chat_list


def update_job_progress(
    label: str,
    fraction: float,
    *,
    done: bool = False,
    environ: Optional[Dict[str, str]] = None,
    project_dir: Optional[Path] = None,
) -> None:
    """Update background job progress (convert / roll) in expression.json so any live pane redraws it."""
    proj = resolve_project_dir(project_dir, environ)
    target = expression_file_path(environ, project_dir=proj)
    prev = read_expression(environ, project_dir=proj) or {"v": 1, "projectDir": str(proj)}
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
        _atomic_write_expr(target, prev, environ=environ)
    except Exception:
        pass


def clear_expression(
    environ: Optional[Dict[str, str]] = None,
    *,
    clear_painting: bool = False,
    project_dir: Optional[Path] = None,
) -> bool:
    """Clear Prism's custom thought/voice while preserving her permanent painting spot unless clear_painting=True."""
    proj = resolve_project_dir(project_dir, environ)
    target = expression_file_path(environ, project_dir=proj)
    try:
        if not clear_painting:
            prev = read_expression(environ, project_dir=proj)
            if isinstance(prev, dict) and prev.get("painting"):
                write_expression(
                    "",
                    mood=prev.get("mood"),
                    effect=None,
                    glyph=None,
                    art=[],
                    project_dir=proj,
                    environ=environ,
                )
                return True
        if target.is_file():
            target.unlink()
        if _is_default_state_home(environ) and target.parent.parent.name == "projects":
            tmp_mirror = Path("/tmp") / "gemini-prism" / "projects" / target.parent.name / "expression.json"
            if tmp_mirror.is_file():
                tmp_mirror.unlink()
        return True
    except OSError:
        return False


_EXPR_FILE_CACHE: Dict[Tuple[str, int, int], Dict[str, Any]] = {}


def read_expression(
    environ: Optional[Dict[str, str]] = None,
    now: Optional[float] = None,
    project_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Read the active directory-scoped expression; if a thought TTL expired, keep the permanent painting spot intact.
    Checks both primary state_home and /tmp/gemini-prism fallback (when not overridden) and picks the freshest.
    """
    env = os.environ if environ is None else environ
    override = env.get("PRISM_EXPRESSION_FILE")
    proj: Optional[Path] = None
    if override:
        candidates = [Path(override)]
    else:
        proj = resolve_project_dir(project_dir, env)
        p_hash = _project_hash(proj)
        home = env.get("HOME", "/tmp")
        state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
        candidates = [
            state_home / "gemini-prism" / "projects" / p_hash / "expression.json",
        ]
        if _is_default_state_home(env):
            candidates.append(Path("/tmp") / "gemini-prism" / "projects" / p_hash / "expression.json")

    best_data: Optional[Dict[str, Any]] = None
    best_ts = -1.0
    for target in candidates:
        if not target.is_file() or target.is_symlink():
            continue
        try:
            st = target.stat()
            cache_k = (str(target), st.st_mtime_ns, st.st_size)
            data = _EXPR_FILE_CACHE.get(cache_k)
            if data is None:
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("v") == 1:
                    if len(_EXPR_FILE_CACHE) >= 16:
                        _EXPR_FILE_CACHE.clear()
                    _EXPR_FILE_CACHE[cache_k] = data
            if not isinstance(data, dict) or data.get("v") != 1:
                continue
            if proj is not None and data.get("projectDir"):
                try:
                    if Path(data["projectDir"]).resolve() != proj:
                        continue
                except OSError:
                    pass
            upd = float(data.get("updatedAt") or 0.0)
            if upd > best_ts:
                best_ts = upd
                best_data = dict(data)
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
                "projectDir": best_data.get("projectDir"),
                "sessionId": best_data.get("sessionId"),
                "sessionStart": best_data.get("sessionStart"),
                "paintEnabled": best_data.get("paintEnabled", True),
                "paintScope": best_data.get("paintScope", "session"),
                "thought": "",
                "mood": best_data.get("mood"),
                "effect": None,
                "glyph": None,
                "art": [],
                "paintMode": best_data.get("paintMode", "live"),
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
            proj_dir = resolve_project_dir()
            write_expression(
                thought=args.get("thought") or paint_obj.get("thought") or None,
                mood=args.get("mood") or paint_obj.get("mood"),
                painting=paint_obj,
                project_dir=proj_dir,
            )
            svg_msg = ""
            if args.get("convert"):
                way = str(args.get("way") or "truest")
                conv_res = painter.convert_painting(paint_obj, gallery_dir=proj_dir / "prism-paintings", way=way)
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
