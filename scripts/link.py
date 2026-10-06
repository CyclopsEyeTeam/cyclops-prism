#!/usr/bin/env python3
"""link.py - Cyclops Link v1 implementation for Prism.

A lightweight, local, content-free presence protocol enabling Spark (Claude Code),
Keeper (Codex), and Prism (Antigravity) to observe each other peer-to-peer.

Specifications:
- Location: ${CYCLOPS_LINK_DIR:-${XDG_STATE_HOME:-~/.local/state}/cyclops-link}/
- Mode 0700 directory, mode 0600 atomic JSON files (<presence>-<instance>.json)
- Off by default (enabled via --link flag or CYCLOPS_LINK=1 / PRISM_LINK=1)
- Zero-leakage: session hash, canonical room hash, status vocabulary, active counts.
"""

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Dict, List, Optional, Set

VERSION = 1
MAX_LINK_FILE_BYTES = 4096
STALE_THRESHOLD_SECONDS = 15.0
SHARED_STATES = {
    "idle",
    "listening",
    "thinking",
    "working",
    "tool",
    "waiting",
    "compacting",
    "stopped",
    "interrupted",
    "ended",
}
KNOWN_PRESENCES = {"spark", "keeper", "prism"}
KNOWN_HOSTS = {"claude-code", "codex", "antigravity"}

STATE_MAP = {
    "idle": "idle",
    "ready": "idle",
    "attending": "thinking",
    "refracting": "tool",
    "branching": "working",
    "approval": "waiting",
    "crystallized": "idle",
    "ended": "ended",
}

PEER_MARKS = {
    "prism": "⟐",
    "spark": "✶",
    "keeper": "⬡",
}

PEER_MARKS_ASCII = {
    "prism": "<>",
    "spark": "*",
    "keeper": "#",
}


def is_link_enabled(environ: Optional[Dict[str, str]] = None, flag: bool = False) -> bool:
    """Check if Cyclops Link is enabled. Off by default."""
    if flag:
        return True
    env = os.environ if environ is None else environ
    return env.get("CYCLOPS_LINK", "").strip() in ("1", "true", "yes", "on") or \
           env.get("PRISM_LINK", "").strip() in ("1", "true", "yes", "on")


def resolve_link_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    """Return the Cyclops Link state directory."""
    env = os.environ if environ is None else environ
    override = env.get("CYCLOPS_LINK_DIR")
    if override:
        return Path(override)
    state_home = env.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cyclops-link"
    home = env.get("HOME", "/tmp")
    return Path(home) / ".local" / "state" / "cyclops-link"


def compute_instance(session_id: str) -> str:
    """Compute 16-hex instance hash from host session id."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]


def compute_room(cwd: Optional[str] = None) -> str:
    """Compute 16-hex room hash from canonical working folder."""
    target = cwd or os.getcwd()
    try:
        real_path = os.path.realpath(target)
    except Exception:
        real_path = target
    return hashlib.sha256(real_path.encode("utf-8")).hexdigest()[:16]


def map_to_shared_state(internal_state: str) -> str:
    """Map Prism's internal state to Cyclops Link shared state vocabulary."""
    norm = internal_state.lower().strip()
    return STATE_MAP.get(norm, "idle" if norm not in SHARED_STATES else norm)


def write_link_file(
    session_id: str,
    state: str,
    *,
    tools: int = 0,
    branches: int = 0,
    reaching: Optional[List[str]] = None,
    ended: bool = False,
    cwd: Optional[str] = None,
    environ: Optional[Dict[str, str]] = None,
    link_enabled: bool = False,
) -> Optional[Path]:
    """Write this session's Cyclops Link presence file atomically."""
    if not is_link_enabled(environ, flag=link_enabled):
        return None

    link_dir = resolve_link_dir(environ)
    try:
        link_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(link_dir, 0o700)
    except OSError:
        return None

    instance = compute_instance(session_id)
    room = compute_room(cwd)
    shared_st = map_to_shared_state(state)
    reach = [r for r in (reaching or []) if r in KNOWN_PRESENCES]

    payload = {
        "v": VERSION,
        "presence": "prism",
        "host": "antigravity",
        "instance": instance,
        "room": room,
        "state": shared_st,
        "tools": max(0, int(tools)),
        "branches": max(0, int(branches)),
        "reaching": reach,
        "updated_at": round(time.time(), 3),
        "ended": bool(ended),
    }

    target_file = link_dir / f"prism-{instance}.json"
    content = json.dumps(payload, separators=(",", ":"))

    try:
        fd, tmp_path = tempfile.mkstemp(dir=link_dir, prefix=f".prism-{instance}-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, target_file)
        return target_file
    except OSError:
        return None


def clean_link_file(session_id: str, environ: Optional[Dict[str, str]] = None) -> None:
    """Mark session as ended or delete link file upon exit."""
    link_dir = resolve_link_dir(environ)
    instance = compute_instance(session_id)
    target_file = link_dir / f"prism-{instance}.json"
    if target_file.is_file():
        try:
            target_file.unlink(missing_ok=True)
        except OSError:
            pass


class PeerLinkReader:
    """Reads peer presence links with 1-second caching and stat checking."""

    def __init__(self, link_dir: Optional[Path] = None):
        self.link_dir = link_dir
        self.last_scan_time = 0.0
        self.cached_peers: List[Dict[str, Any]] = []
        self._file_mtimes: Dict[str, float] = {}

    def read_peers(
        self,
        current_session_id: str,
        current_room: Optional[str] = None,
        *,
        everywhere: bool = False,
        now: Optional[float] = None,
        environ: Optional[Dict[str, str]] = None,
        link_enabled: bool = False,
    ) -> List[Dict[str, Any]]:
        """Read and validate active peer presence records."""
        if not is_link_enabled(environ, flag=link_enabled):
            return []

        cur_time = time.time() if now is None else now
        if cur_time - self.last_scan_time < 1.0:
            return self.cached_peers

        self.last_scan_time = cur_time
        target_dir = self.link_dir or resolve_link_dir(environ)
        if not target_dir.is_dir():
            self.cached_peers = []
            return []

        my_instance = compute_instance(current_session_id)
        room_filter = current_room or compute_room()
        active: List[Dict[str, Any]] = []

        try:
            entries = os.scandir(target_dir)
        except OSError:
            return []

        for entry in entries:
            try:
                name = entry.name
                if not name.endswith(".json") or entry.name.startswith("."):
                    continue
                # Skip own file
                if name == f"prism-{my_instance}.json":
                    continue

                # Presence name check from filename: <presence>-<instance>.json
                parts = name[:-5].split("-", 1)
                if len(parts) != 2 or parts[0] not in KNOWN_PRESENCES:
                    continue

                st = entry.stat()
                if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_LINK_FILE_BYTES:
                    continue

                text = Path(entry.path).read_text(encoding="utf-8")
                data = json.loads(text)
                if not isinstance(data, dict) or data.get("v") != VERSION:
                    continue

                presence = data.get("presence")
                peer_state = data.get("state")
                if presence not in KNOWN_PRESENCES or peer_state not in SHARED_STATES:
                    continue

                if data.get("ended", False):
                    continue

                updated_at = float(data.get("updated_at", 0.0))
                if (cur_time - updated_at) > STALE_THRESHOLD_SECONDS:
                    continue

                if not everywhere:
                    peer_room = data.get("room")
                    if peer_room != room_filter:
                        continue

                active.append(data)
            except (OSError, ValueError, KeyError):
                continue

        self.cached_peers = active
        return active
