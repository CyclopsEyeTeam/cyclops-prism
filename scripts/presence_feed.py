"""presence_feed.py - Feed publisher, atomic writer, process identity tracker & heartbeat daemon for Gemini Prism."""

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import feed_state


def resolve_target(environ: Optional[Dict[str, str]] = None, payload: Optional[Dict[str, Any]] = None) -> Tuple[Path, str]:
    """Resolve (presence_root, session_id) from environment or hook payload."""
    env = os.environ if environ is None else environ
    home = env.get("HOME", "/tmp")

    # 1. Cyclops Studio environment
    cyclops_session = env.get("CYCLOPS_SESSION_ID")
    if isinstance(cyclops_session, str) and feed_state.SESSION_ID.fullmatch(cyclops_session):
        override = env.get("CYCLOPS_PRESENCE_ROOT")
        if override:
            root = Path(override)
        else:
            state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
            root = state_home / "cyclops-presence"
        return root, cyclops_session

    # 2. Antigravity conversationId from hook payload
    session_id = "default"
    if isinstance(payload, dict):
        conv_id = payload.get("conversationId")
        if isinstance(conv_id, str) and conv_id:
            # Clean conversation ID to meet SESSION_ID regex
            cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", conv_id)[:80]
            if feed_state.SESSION_ID.fullmatch(cleaned):
                session_id = cleaned
            else:
                session_id = hashlib.sha256(conv_id.encode("utf-8")).hexdigest()[:32]

    # 3. Environment override or default standalone state root
    override = env.get("PRISM_PRESENCE_ROOT")
    if override:
        root = Path(override)
    else:
        state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
        root = state_home / "gemini-prism" / "presence"

    return root, session_id


def find_active_feed(environ: Optional[Dict[str, str]] = None) -> Optional[Path]:
    """Auto-discover the most recent active presence feed directory."""
    env = os.environ if environ is None else environ
    home = env.get("HOME", "/tmp")

    # 1. Check explicit environment override
    for env_var in ["PRISM_FEED_DIR", "CYCLOPS_PRESENCE_DIR"]:
        val = env.get(env_var)
        if val:
            p = Path(val)
            if p.is_dir() and (p / "live.json").is_file():
                return p

    # 2. Search candidates
    state_home = Path(env.get("XDG_STATE_HOME") or (Path(home) / ".local" / "state"))
    candidate_roots = []
    if env.get("PRISM_PRESENCE_ROOT"):
        candidate_roots.append(Path(env["PRISM_PRESENCE_ROOT"]))
    if env.get("CYCLOPS_PRESENCE_ROOT"):
        candidate_roots.append(Path(env["CYCLOPS_PRESENCE_ROOT"]))
    candidate_roots.extend([
        state_home / "gemini-prism" / "presence",
        state_home / "cyclops-presence",
    ])

    best_path = None
    best_mtime = -1.0

    for root in candidate_roots:
        if not root.is_dir():
            continue
        try:
            for item in root.iterdir():
                if not item.is_dir():
                    continue
                # Could be root/session/live.json or root/session/prism/live.json
                direct_live = item / "live.json"
                nested_live = item / feed_state.ENTITY / "live.json"
                if nested_live.is_file():
                    mt = nested_live.stat().st_mtime
                    if mt > best_mtime:
                        best_mtime = mt
                        best_path = nested_live.parent
                elif direct_live.is_file():
                    mt = direct_live.stat().st_mtime
                    if mt > best_mtime:
                        best_mtime = mt
                        best_path = item
        except (OSError, PermissionError):
            continue

    return best_path


def _safe_mkdir(path: Path) -> None:
    """Create directory tree safely, rejecting any symbolic link in the path hierarchy."""
    path = Path(path)
    chain = list(reversed((path, *path.parents)))
    for item in chain:
        if item.exists() and item.is_symlink():
            raise OSError("presence path contains an unsafe symbolic link")
        if not item.exists():
            item.mkdir(mode=0o700)


def _atomic_json(path: Path, value: Any) -> None:
    """Write JSON atomically via mkstemp + fsync + os.replace + parent directory fsync."""
    path = Path(path)
    if path.is_symlink():
        raise OSError("presence target is a symbolic link")
    _safe_mkdir(path.parent)

    fd, temporary = tempfile.mkstemp(prefix=".prism-", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, separators=(",", ":"), ensure_ascii=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)

        # Fsync parent directory to commit rename to disk
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        dir_fd = os.open(path.parent, dir_flags)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def process_identity(pid: Any) -> Optional[Dict[str, int]]:
    """Capture Linux process identity using PID and starttime ticks from /proc/<pid>/stat."""
    try:
        pid = int(pid)
        if pid < 1:
            return None
        stat_text = Path(f"/proc/{pid}/stat").read_text()
        fields = stat_text.rsplit(")", 1)[1].split()
        state = fields[0]
        if state in {"Z", "X"}:  # Zombie or dead
            return None
        start_ticks = int(fields[19])  # Field 22 in /proc/[pid]/stat, index 19 after ') '
        return {"pid": pid, "startTicks": start_ticks}
    except (OSError, ValueError, IndexError, TypeError):
        return None


def producer_alive(identity: Optional[Dict[str, Any]]) -> bool:
    """Check if the recorded process identity is still alive and has not been replaced."""
    if not isinstance(identity, dict) or "pid" not in identity or "startTicks" not in identity:
        return False
    current = process_identity(identity["pid"])
    return current is not None and current == identity


def find_host_identity() -> Optional[Dict[str, int]]:
    """Identify the nearest ancestor host process (e.g. agy, antigravity) or session leader."""
    pid = os.getppid()
    for _ in range(16):
        try:
            stat_text = Path(f"/proc/{pid}/stat").read_text()
            fields = stat_text.rsplit(")", 1)[1].split()
            comm = Path(f"/proc/{pid}/comm").read_text().strip().lower()
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\x00")
            cmd = b" ".join(argv).lower()

            if any(k in comm or k.encode() in cmd for k in ["agy", "antigravity", "cortex"]):
                return process_identity(pid)

            parent = int(fields[1])
            if parent <= 1 or parent == pid:
                break
            pid = parent
        except (OSError, ValueError, IndexError):
            break
    return process_identity(os.getppid())


def new_record(session_id: str, *, run: Optional[str] = None, started_at: Optional[float] = None, host_identity: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Create a new in-memory feed record for a session."""
    if not isinstance(session_id, str) or not feed_state.SESSION_ID.fullmatch(session_id):
        raise ValueError("invalid session ID")
    now = time.time() if started_at is None else started_at
    if not feed_state.is_finite_number(now):
        raise ValueError("invalid start time")

    return {
        "v": feed_state.VERSION,
        "owner": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
        "run": run or uuid.uuid4().hex,
        "startedAt": float(now),
        "seq": 0,
        "checkpoint": feed_state.empty_checkpoint(),
        "pendingEvents": [],
        "liveEvents": [],
        "ended": False,
        "producer": host_identity,
        "durableAt": None,
        "liveAt": None,
        "aliveAt": None,
        "durableDirty": False,
        "liveDirty": False,
    }


def _safe_event(ev: Any) -> Optional[Dict[str, Any]]:
    """Validate and clean an event for feed storage."""
    if not isinstance(ev, dict) or "type" not in ev or "seq" not in ev or "t" not in ev:
        return None
    if ev["type"] not in feed_state.EVENT_TYPES:
        return None
    if not isinstance(ev["seq"], int) or ev["seq"] < 1:
        return None
    if not feed_state.is_finite_number(ev["t"]):
        return None

    res = {"seq": ev["seq"], "t": float(ev["t"]), "type": ev["type"]}
    if "kind" in ev and ev["kind"] in feed_state.KINDS:
        res["kind"] = ev["kind"]
    if "key" in ev and feed_state.is_valid_key(ev["key"]):
        res["key"] = ev["key"]
    return res


def append_event(record: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """Append a validated Presence event to the record, assigning sequence monotonically."""
    if not isinstance(record, dict) or record.get("v") != feed_state.VERSION:
        return record
    clean_ev = _safe_event(event)
    if clean_ev is None:
        return record

    next_seq = record.get("seq", 0) + 1
    if clean_ev["seq"] < next_seq:
        clean_ev["seq"] = next_seq
    record["seq"] = clean_ev["seq"]

    # Append to pending durable queue
    pending = record.setdefault("pendingEvents", [])
    pending.append(clean_ev)
    if len(pending) > feed_state.PENDING_LIMIT:
        dropped = pending[:-feed_state.PENDING_LIMIT]
        record["checkpoint"] = feed_state.advance(record.get("checkpoint", feed_state.empty_checkpoint()), dropped)
        record["pendingEvents"] = pending[-feed_state.PENDING_LIMIT:]

    # Append to live queue (60s sliding window)
    live = record.setdefault("liveEvents", [])
    live.append(clean_ev)
    cutoff = clean_ev["t"] - feed_state.LIVE_WINDOW
    live = [e for e in live if e.get("t", 0.0) >= cutoff]
    if not live or live[-1] != clean_ev:
        live.append(clean_ev)
    record["liveEvents"] = live[-feed_state.LIVE_LIMIT:]

    record["durableDirty"] = True
    record["liveDirty"] = True

    if clean_ev["type"] == "session.end":
        record["ended"] = True

    return record


def _durable_header(path: Path) -> Optional[Dict[str, Any]]:
    """Read durable feed header without loading entire event history."""
    if not path.exists() or path.is_symlink() or path.stat().st_size > feed_state.MAX_RECORD_BYTES:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            chunk = f.read(4096)
        marker = chunk.find(',"checkpoint":')
        if marker < 0:
            marker = chunk.find(',"events":[')
        if marker < 0:
            return None
        header = json.loads(chunk[:marker] + "}")
        if (
            isinstance(header, dict)
            and header.get("v") == feed_state.VERSION
            and isinstance(header.get("run"), str)
            and isinstance(header.get("seq"), int)
        ):
            return header
    except (OSError, ValueError):
        return None
    return None


def _load_durable(path: Path, expected_run: str) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
    """Safely load existing durable events and checkpoint."""
    header = _durable_header(path)
    if not header or header.get("run") != expected_run:
        return [], 0, feed_state.empty_checkpoint()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            return [], 0, feed_state.empty_checkpoint()
        events = [e for item in data["events"] if (e := _safe_event(item)) is not None]
        checkpoint = feed_state.safe_checkpoint(data.get("checkpoint"))
        return events, header["seq"], checkpoint
    except (OSError, ValueError):
        return [], 0, feed_state.empty_checkpoint()


def flush(
    record: Dict[str, Any],
    presence_root: Path,
    *,
    session_id: str,
    now: Optional[float] = None,
    force: bool = False,
    force_live: bool = False,
) -> bool:
    """Flush durable.json and live.json within documented cadences."""
    if not isinstance(record, dict) or record.get("v") != feed_state.VERSION:
        return False
    stamp = float(time.time() if now is None else now)
    if not feed_state.is_finite_number(stamp):
        return False
    if not isinstance(session_id, str) or not feed_state.SESSION_ID.fullmatch(session_id):
        return False
    if hashlib.sha256(session_id.encode("utf-8")).hexdigest() != record.get("owner"):
        return False

    target_dir = Path(presence_root) / session_id / feed_state.ENTITY
    first = record.get("durableAt") is None or record.get("liveAt") is None
    durable_due = force or first or (
        record.get("durableDirty") and (stamp - (record.get("durableAt") or -math.inf) >= feed_state.DURABLE_INTERVAL)
    )
    heartbeat_due = (
        record.get("aliveAt") is None or (stamp - (record.get("aliveAt") or -math.inf) >= feed_state.HEARTBEAT_INTERVAL)
    )
    live_due = force or force_live or first or heartbeat_due or (
        record.get("liveDirty") and (stamp - (record.get("liveAt") or -math.inf) >= feed_state.LIVE_INTERVAL)
    )

    if not durable_due and not live_due:
        return False

    _safe_mkdir(target_dir)

    # 1. Flush durable.json
    if durable_due:
        durable_path = target_dir / "durable.json"
        prev_events, persisted_seq, checkpoint = _load_durable(durable_path, record["run"])
        pending = record.get("pendingEvents", [])
        additions = [e for e in pending if e["seq"] > persisted_seq]

        local_checkpoint = record.get("checkpoint", feed_state.empty_checkpoint())
        if local_checkpoint["seq"] >= checkpoint["seq"]:
            checkpoint = local_checkpoint

        all_events = [e for e in (prev_events + additions) if e["seq"] > checkpoint["seq"]]
        if len(all_events) > feed_state.DURABLE_LIMIT:
            checkpoint = feed_state.advance(checkpoint, all_events[:-feed_state.DURABLE_LIMIT])
            all_events = all_events[-feed_state.DURABLE_LIMIT:]

        record["checkpoint"] = checkpoint
        latest_seq = max([record.get("seq", 0), persisted_seq, *(e["seq"] for e in additions)])
        record["seq"] = latest_seq

        durable_payload = {
            "v": feed_state.VERSION,
            "run": record["run"],
            "startedAt": record["startedAt"],
            "seq": record["seq"],
            "checkpoint": checkpoint,
            "events": all_events,
        }
        try:
            _atomic_json(durable_path, durable_payload)
            record["pendingEvents"] = [e for e in pending if e["seq"] > latest_seq]
            record["durableAt"] = stamp
            record["durableDirty"] = bool(record["pendingEvents"])
        except OSError:
            return False

    # 2. Flush live.json
    if live_due:
        live_path = target_dir / "live.json"
        live_events = [
            e for e in record.get("liveEvents", []) if e.get("t", 0.0) >= stamp - feed_state.LIVE_WINDOW
        ]
        latest = record.get("liveEvents", [])[-1] if record.get("liveEvents") else None
        if latest and latest not in live_events:
            live_events.append(latest)
        record["liveEvents"] = live_events[-feed_state.LIVE_LIMIT:]

        live_payload = {
            "v": feed_state.VERSION,
            "run": record["run"],
            "startedAt": record["startedAt"],
            "seq": record["seq"],
            "checkpoint": record.get("checkpoint", feed_state.empty_checkpoint()),
            "events": record["liveEvents"],
            "aliveAt": stamp,
            "ended": bool(record.get("ended")),
        }
        try:
            _atomic_json(live_path, live_payload)
            record["liveAt"] = stamp
            record["aliveAt"] = stamp
            record["liveDirty"] = False
        except OSError:
            return False

    return True


def start_daemon(data_root: Path, session_id: str, presence_root: Path) -> None:
    """Spawn detached background heartbeat daemon if not already running."""
    if not isinstance(session_id, str) or not feed_state.SESSION_ID.fullmatch(session_id):
        return
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    sessions_dir = Path(data_root) / "sessions"
    _safe_mkdir(sessions_dir)

    pid_path = sessions_dir / f"{session_hash}.daemon.pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            return  # Daemon is running and healthy
        except (OSError, ValueError):
            pass  # Stale pid file

    lock_path = sessions_dir / f"{session_hash}.daemon.lock"
    probe_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(probe_fd, "r+") as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # Another daemon holds the lock

        child_env = dict(os.environ)
        child_env["PRISM_PRESENCE_ROOT"] = str(Path(presence_root))
        proc = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--daemon",
                str(Path(data_root)),
                session_id,
                str(Path(presence_root)),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            env=child_env,
        )
        try:
            pid_path.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            pass
        fcntl.flock(probe, fcntl.LOCK_UN)


def run_daemon(data_root: Path, session_id: str, presence_root: Path) -> None:
    """Background heartbeat loop and truthful host liveness monitor."""
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    sessions_dir = Path(data_root) / "sessions"
    state_path = sessions_dir / f"{session_hash}.state.json"
    state_lock_path = sessions_dir / f"{session_hash}.state.lock"
    daemon_lock_path = sessions_dir / f"{session_hash}.daemon.lock"
    pid_path = sessions_dir / f"{session_hash}.daemon.pid"

    _safe_mkdir(sessions_dir)
    daemon_fd = os.open(daemon_lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(daemon_fd, "r+") as daemon_lock:
        try:
            fcntl.flock(daemon_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # Single instance enforcement

        try:
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

        try:
            while True:
                flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                lock_fd = os.open(state_lock_path, flags, 0o600)
                with os.fdopen(lock_fd, "r+") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        time.sleep(0.05)
                        continue

                    try:
                        if not state_path.exists() or state_path.is_symlink() or state_path.stat().st_size > feed_state.MAX_RECORD_BYTES:
                            return
                        record = json.loads(state_path.read_text(encoding="utf-8"))
                        if not isinstance(record, dict) or record.get("v") != feed_state.VERSION:
                            return

                        # Never resurrect an already ended session
                        if record.get("ended") and not record.get("durableDirty"):
                            return

                        # Verify host process liveness
                        producer = record.get("producer")
                        is_alive = producer_alive(producer)

                        if not is_alive:
                            # Truthful session termination strictly on host process death
                            record["ended"] = True
                            append_event(record, {"seq": record.get("seq", 0) + 1, "t": time.time(), "type": "session.end"})
                            flush(record, presence_root, session_id=session_id, force=True)
                            _atomic_json(state_path, record)
                            return

                        # Host is alive: flush dirty feeds or periodic heartbeat
                        published = flush(record, presence_root, session_id=session_id)
                        if published:
                            _atomic_json(state_path, record)

                    except (OSError, ValueError, TypeError, KeyError):
                        return

                time.sleep(0.2)
        finally:
            try:
                pid_path.unlink()
            except OSError:
                pass


if __name__ == "__main__" and len(sys.argv) == 5 and sys.argv[1] == "--daemon":
    run_daemon(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
