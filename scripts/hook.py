#!/usr/bin/env python3
"""hook.py - Fast, synchronous Antigravity hook observer for Gemini Prism.

Completes in < 15ms. Ingests lifecycle events, enforces privacy, updates session
record, and delegates background heartbeats & flushes to the detached daemon.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import sys
import time

sys.dont_write_bytecode = True

# Add scripts directory to path if needed
sys.path.insert(0, str(Path(__file__).resolve().parent))

import activity
import feed_state
import presence_feed


def handle_event(payload: dict) -> None:
    """Process a single hook payload safely and update session state."""
    presence_root, session_id = presence_feed.resolve_target(payload=payload)
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    home = os.environ.get("HOME", "/tmp")
    data_root = Path(os.environ.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state")) / "gemini-prism"
    sessions_dir = data_root / "sessions"
    presence_feed._safe_mkdir(sessions_dir)

    state_path = sessions_dir / f"{session_hash}.state.json"
    state_lock_path = sessions_dir / f"{session_hash}.state.lock"

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(state_lock_path, flags, 0o600)

    # Acquire lock with a tight 20ms deadline to never block agent loop
    deadline = time.monotonic() + 0.02
    acquired = False
    with os.fdopen(lock_fd, "r+") as lock:
        while time.monotonic() < deadline:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(0.002)

        if not acquired:
            return  # Lock contention timeout - fail open immediately

        try:
            record = None
            if state_path.exists() and not state_path.is_symlink() and state_path.stat().st_size <= feed_state.MAX_RECORD_BYTES:
                try:
                    record = json.loads(state_path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    record = None

            if not isinstance(record, dict) or record.get("v") != feed_state.VERSION:
                host_identity = presence_feed.find_host_identity()
                record = presence_feed.new_record(session_id, host_identity=host_identity)

            # Adapt Antigravity hook payload to normalized Presence event
            next_seq = record.get("seq", 0) + 1
            event = activity.adapt_hook_event(payload, sequence=next_seq)
            if event:
                presence_feed.append_event(record, event)
                presence_feed.flush(record, presence_root, session_id=session_id)
                presence_feed._atomic_json(state_path, record)

                # Ensure detached heartbeat daemon is running
                presence_feed.start_daemon(data_root, session_id, presence_root)
        except Exception:
            pass


def main() -> None:
    payload = {}
    try:
        # Read bounded payload from stdin (max 2MB, short timeout)
        raw = bytearray()
        deadline = time.monotonic() + 0.3
        while len(raw) <= feed_state.MAX_RECORD_BYTES:
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            r, _, _ = select.select([sys.stdin], [], [], rem)
            if not r:
                break
            chunk = os.read(sys.stdin.fileno(), 16384)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > feed_state.MAX_RECORD_BYTES:
                break
            try:
                p = json.loads(raw)
                if isinstance(p, dict):
                    payload = p
                    handle_event(payload)
                break
            except (ValueError, UnicodeError):
                continue
    except Exception:
        pass

    # Antigravity hooks expect valid JSON on stdout per event contract
    cli_event = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--event" and i + 1 < len(sys.argv):
            cli_event = sys.argv[i + 1]
            break

    hook_event = cli_event or payload.get("hookEvent") or payload.get("hook_event_name", "")
    if not hook_event:
        if "toolCall" in payload and "toolResult" not in payload and "error" not in payload:
            hook_event = "PreToolUse"
        elif "toolResult" in payload or "error" in payload:
            hook_event = "PostToolUse"
        elif "terminationReason" in payload:
            hook_event = "Stop"

    if hook_event == "PreToolUse":
        print('{"decision": "allow"}')
    else:
        print("{}")


if __name__ == "__main__":
    main()
