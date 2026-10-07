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


# Cyclops Link (off unless the person turned it on): the observed event's phase, never its content
LINK_PHASE = {"session.wake": "wake", "turn.attend": "attending", "turn.resolve": "resolved",
              "turn.halt": "halted", "session.end": "ended"}


def _host_folder() -> str:
    """The Antigravity process's own working folder: the project this session belongs to."""
    host = presence_feed.find_host_identity()
    try:
        if host and host.get("pid"):
            return os.readlink(f"/proc/{host['pid']}/cwd")
    except OSError:
        pass
    return os.getcwd()


def _link_publish(record: dict, event: dict, session_id: str) -> None:
    try:
        import link
        if not link.enabled():
            return
        state = record.get("link") if isinstance(record.get("link"), dict) else {}
        folder = _host_folder()
        word = link.coarse_state(LINK_PHASE.get(event.get("type"), ""), state.get("state"))
        if word is None:
            return
        writer = link.Writer(session_id, folder)
        if word == "ended":
            ok = writer.publish("working") and writer.end()
        else:
            ok = writer.publish(word)
        if ok:
            record["link"] = {"state": word}
    except Exception:
        pass  # Link is decoration: it never disturbs Antigravity


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
                _link_publish(record, event, session_id)
                presence_feed._atomic_json(state_path, record)

                # Ensure detached heartbeat daemon is running
                if not os.environ.get("PRISM_NO_DAEMON"):
                    presence_feed.start_daemon(data_root, session_id, presence_root)
        except Exception:
            pass


def main() -> None:
    event_name = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--event" and idx + 1 < len(sys.argv):
            event_name = sys.argv[idx + 1]
            break

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
                    if event_name:
                        payload["hookEvent"] = event_name
                    handle_event(payload)
                break
            except (ValueError, UnicodeError):
                continue
    except Exception:
        pass

    # Antigravity observer hooks expect empty JSON object on stdout
    print("{}")


if __name__ == "__main__":
    main()
