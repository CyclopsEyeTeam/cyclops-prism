#!/usr/bin/env python3
"""link.py - Prism's own implementation of Cyclops Link V1.

Cyclops Link lets the terminal presences (Spark, Keeper, Prism) notice each other
on one machine: "I'm here, this is my truthful coarse state, these are my counts,
I'm reaching toward that presence." No messages, no commands, no network, no
shared code: Prism writes one small file per Antigravity session and reads the
others' files. The protocol is SPEC.md of Cyclops Link V1 (commit 3ba5cab); the
conformance fixtures are vendored in tests/fixtures/cyclops-link-v1/.

Off by default. Prism links only when the person turns it on (`prism link on`,
or PRISM_LINK=1). A shared switch such as CYCLOPS_LINK never enables her.
"""

import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

PRESENCE = "prism"
HOST = "antigravity"
PRESENCES = ("spark", "keeper", "prism")
HOST_OF = {"spark": "claude-code", "keeper": "codex", "prism": "antigravity"}
STATES = frozenset({"idle", "listening", "thinking", "working", "tool", "waiting",
                    "compacting", "stopped", "interrupted", "ended"})
SEATS = {"prism": 90.0, "spark": 210.0, "keeper": 330.0}
MAX_BYTES = 4096
FRESH_SECONDS = 15.0
FUTURE_SLACK = 2.0
HEARTBEAT_SECONDS = 4.0      # spec: at most every 5 s while alive
END_GRACE_SECONDS = 60.0
MAX_FAILURES = 3
NAME = re.compile(r"^(spark|keeper|prism)-([0-9a-f]{16})\.json$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
SALT_RE = re.compile(rb"^[0-9a-f]{64}\n$")

REQUIRED = ("v", "presence", "host", "instance", "room", "state", "tools",
            "branches", "reaching", "updated_at", "ended")


# ---------------------------------------------------------------- consent

def config_path(environ: Optional[Dict[str, str]] = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("XDG_CONFIG_HOME")
    root = Path(base) if base and os.path.isabs(base) else Path(env.get("HOME", "/nonexistent")) / ".config"
    return root / "gemini-prism" / "link"


def enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """Prism's own Link switch. Off unless the person turned it on."""
    env = os.environ if environ is None else environ
    override = env.get("PRISM_LINK", "").strip().lower()
    if override in ("1", "on", "true", "yes"):
        return True
    if override in ("0", "off", "false", "no"):
        return False
    try:
        return config_path(env).read_text(encoding="utf-8").strip() == "on"
    except OSError:
        return False


def set_enabled(on: bool, environ: Optional[Dict[str, str]] = None) -> Path:
    path = config_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("on\n" if on else "off\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- directory and salt (SPEC 2, 3)

def link_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("CYCLOPS_LINK_DIR")
    if override:
        return Path(override)
    state_home = env.get("XDG_STATE_HOME")
    if state_home and os.path.isabs(state_home):
        return Path(state_home) / "cyclops-link"
    return Path(env.get("HOME", "/nonexistent")) / ".local" / "state" / "cyclops-link"


def dir_is_safe(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not (st.st_mode & 0o077)


def prepare_dir(path: Path, create: bool) -> Optional[Path]:
    """The Link directory if it is safe to use; created 0700 when missing and create is set.
    An existing unsafe directory is refused, never repaired."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        if not create:
            return None
        try:
            os.makedirs(path, mode=0o700, exist_ok=False)
            os.chmod(path, 0o700)  # only the directory we just created
        except OSError:
            return None
    except OSError:
        return None
    return path if dir_is_safe(path) else None


def salt_is_valid(path: Path) -> bool:
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_size != 65:
            return False
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            data = f.read(66)
    except OSError:
        return False
    return SALT_RE.match(data) is not None


def load_salt(directory: Path, create: bool) -> Optional[bytes]:
    path = directory / ".salt"
    if create:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32).hex().encode() + b"\n")
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            pass
        except OSError:
            return None
    if not salt_is_valid(path):
        return None
    try:
        return bytes.fromhex(path.read_bytes()[:64].decode("ascii"))
    except (OSError, ValueError):
        return None


def derive(salt: bytes, kind: str, identity: bytes) -> str:
    return hashlib.sha256(b"cyclops-link/v1/" + kind.encode("ascii") + b"\x00" + salt + identity).hexdigest()[:16]


def room_for(salt: bytes, folder: str) -> str:
    real = os.path.realpath(folder)
    if len(real) > 1:
        real = real.rstrip("/")
    return derive(salt, "room", os.fsencode(real))


def instance_for(salt: bytes, session_id: str) -> str:
    return derive(salt, "instance", HOST.encode() + b"\n" + session_id.encode("utf-8", "surrogateescape"))


# ---------------------------------------------------------------- records (SPEC 4)

def _int(v: Any) -> bool:
    return type(v) is int


def _finite(v: Any) -> bool:
    return (type(v) is int or type(v) is float) and math.isfinite(v)


def _reject_constant(_name: str):
    raise ValueError("non-finite constant")


def parse(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def valid(filename: str, obj: Any) -> bool:
    if not isinstance(obj, dict) or any(k not in obj for k in REQUIRED):
        return False
    if not (_int(obj["v"]) and obj["v"] == 1):
        return False
    p = obj["presence"]
    if p not in PRESENCES or obj["host"] != HOST_OF[p]:
        return False
    if not (isinstance(obj["instance"], str) and HEX16.match(obj["instance"])):
        return False
    if not (isinstance(obj["room"], str) and HEX16.match(obj["room"])):
        return False
    if obj["state"] not in STATES:
        return False
    if not (_int(obj["tools"]) and 0 <= obj["tools"] <= 256):
        return False
    if not (_int(obj["branches"]) and 0 <= obj["branches"] <= 32):
        return False
    reach = obj["reaching"]
    if not isinstance(reach, list) or any(not isinstance(x, str) for x in reach):
        return False
    if len(set(reach)) != len(reach) or any(x not in PRESENCES or x == p for x in reach):
        return False
    if not (_finite(obj["updated_at"]) and obj["updated_at"] > 0):
        return False
    if type(obj["ended"]) is not bool:
        return False
    return filename == f"{p}-{obj['instance']}.json"


def read_record(path: Path) -> Optional[Dict[str, Any]]:
    """One peer file, by SPEC 8.4 and 4. Anything doubtful is ignored completely."""
    if not NAME.match(path.name):
        return None
    try:
        st = os.lstat(path)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o022 or st.st_size > MAX_BYTES):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            raw = f.read(MAX_BYTES + 1)
    except OSError:
        return None
    if len(raw) > MAX_BYTES:
        return None
    obj = parse(raw)
    return obj if valid(path.name, obj) else None


def write_record(directory: Path, record: Dict[str, Any]) -> bool:
    """Atomic publish (SPEC 7): 0600 temp file in the Link directory, fsync, rename."""
    name = f"{record['presence']}-{record['instance']}.json"
    data = json.dumps(record, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(data) > MAX_BYTES:
        return False
    tmp = directory / f".{record['presence']}-{record['instance']}.{secrets.token_hex(4)}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp, directory / name)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- the writer (SPEC 5, 6)

class Writer:
    """Publishes one Antigravity session. Lives in Prism's session daemon."""

    def __init__(self, session_id: str, folder: str, environ: Optional[Dict[str, str]] = None):
        self.environ = os.environ if environ is None else environ
        self.session_id = session_id
        self.folder = folder
        self.directory: Optional[Path] = None
        self.instance = ""
        self.room = ""
        self.failures = 0
        self.refused = False
        self.last: Optional[Dict[str, Any]] = None
        self.written_at = 0.0
        self.ended_at: Optional[float] = None

    def _ready(self) -> bool:
        if self.refused or self.failures >= MAX_FAILURES:
            return False
        if self.directory is not None:
            return True
        directory = prepare_dir(link_dir(self.environ), create=True)
        salt = load_salt(directory, create=True) if directory else None
        if directory is None or salt is None:
            self.refused = True
            return False
        self.directory = directory
        self.instance = instance_for(salt, self.session_id)
        self.room = room_for(salt, self.folder)
        return True

    def publish(self, state: str, *, tools: int = 0, branches: int = 0,
                reaching: Iterable[str] = (), now: Optional[float] = None, ended: bool = False) -> bool:
        """Publish a real change, or refresh the heartbeat. Never raises."""
        try:
            if state not in STATES or not self._ready():
                return False
            reach = []
            for p in reaching:
                if p in PRESENCES and p != PRESENCE and p not in reach:
                    reach.append(p)
            record = {"v": 1, "presence": PRESENCE, "host": HOST, "instance": self.instance, "room": self.room,
                      "state": "ended" if ended else state,
                      "tools": max(0, min(256, int(tools))), "branches": max(0, min(32, int(branches))),
                      "reaching": reach, "updated_at": round(time.time() if now is None else now, 3),
                      "ended": bool(ended)}
            if write_record(self.directory, record):
                self.failures = 0
                self.last = record
                self.written_at = record["updated_at"]
                if ended and self.ended_at is None:
                    self.ended_at = record["updated_at"]
                return True
            self.failures += 1
            return False
        except Exception:
            self.failures += 1
            return False

    def heartbeat(self, now: Optional[float] = None) -> bool:
        """Refresh updated_at when nothing changed for HEARTBEAT_SECONDS (never ends a session)."""
        now = time.time() if now is None else now
        if self.last is None or self.last["ended"] or now - self.written_at < HEARTBEAT_SECONDS:
            return False
        r = self.last
        return self.publish(r["state"], tools=r["tools"], branches=r["branches"], reaching=r["reaching"], now=now)

    def end(self, now: Optional[float] = None) -> bool:
        """Publish ended:true. Only for the host's truthful end, or Link switched off."""
        if self.last is None:
            return False
        return self.publish("ended", now=now, ended=True)

    def cleanup(self, now: Optional[float] = None) -> bool:
        """After the grace period, delete this session's own file (and nothing else)."""
        now = time.time() if now is None else now
        if self.directory is None or self.ended_at is None or now - self.ended_at < END_GRACE_SECONDS:
            return False
        try:
            os.unlink(self.directory / f"{PRESENCE}-{self.instance}.json")
        except OSError:
            pass
        return True


# ---------------------------------------------------------------- the reader (SPEC 8, 9, 10, 11)

def bearing(viewer: str, peer: str) -> Optional[int]:
    if viewer == peer:
        return None
    a, b = math.radians(SEATS[viewer]), math.radians(SEATS[peer])
    return round(math.degrees(math.atan2(math.sin(b) - math.sin(a), math.cos(b) - math.cos(a)))) % 360


def present(record: Dict[str, Any], now: float, room: str, policy: str) -> bool:
    return (not record["ended"] and now - FRESH_SECONDS < record["updated_at"] <= now + FUTURE_SLACK
            and (policy == "everywhere" or record["room"] == room))


def compose(own: Dict[str, Any], records: List[Dict[str, Any]], now: float, policy: str = "room") -> Dict[str, Any]:
    """The canonical view: peers (sorted) and threads (class pairs), from valid records."""
    me = f"{own['presence']}-{own['instance']}"
    peers = [r for r in records if f"{r['presence']}-{r['instance']}" != me and present(r, now, own["room"], policy)]
    live_self = not own["ended"]
    threads = set()
    for r in peers + ([own] if live_self else []):
        for b in r["reaching"]:
            if any(q["presence"] == b for q in peers) or (b == own["presence"] and live_self and r is not own):
                threads.add((r["presence"], b))
    out = sorted(({"presence": r["presence"], "instance": r["instance"], "state": r["state"], "tools": r["tools"],
                   "branches": r["branches"], "bearing": bearing(own["presence"], r["presence"])} for r in peers),
                 key=lambda p: (p["presence"], p["instance"]))
    return {"peers": out, "threads": [{"from": a, "to": b} for a, b in sorted(threads)]}


class Reader:
    """Polls the Link directory at most once a second, stat-first, never following links."""

    def __init__(self, environ: Optional[Dict[str, str]] = None):
        self.environ = os.environ if environ is None else environ
        self.cache: Dict[str, Tuple[Tuple[int, int, int], Optional[Dict[str, Any]]]] = {}
        self.last_poll = -1e9
        self.records: List[Dict[str, Any]] = []
        self.salt: Optional[bytes] = None

    def poll(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        now = time.monotonic() if now is None else now
        if now - self.last_poll < 1.0:
            return self.records
        self.last_poll = now
        directory = prepare_dir(link_dir(self.environ), create=False)
        if directory is None:
            self.records, self.cache = [], {}
            return self.records
        if self.salt is None:
            self.salt = load_salt(directory, create=False)
        seen = {}
        try:
            names = os.listdir(directory)
        except OSError:
            return self.records
        for name in names:
            if not NAME.match(name):
                continue
            path = directory / name
            try:
                st = os.lstat(path)
            except OSError:
                continue
            sig = (st.st_mtime_ns, st.st_size, st.st_ino)
            cached = self.cache.get(name)
            seen[name] = cached if cached and cached[0] == sig else (sig, read_record(path))
        self.cache = seen
        self.records = [r for _, r in seen.values() if r is not None]
        return self.records

    def own_room(self, folder: str) -> Optional[str]:
        return room_for(self.salt, folder) if self.salt else None

    def own_instance(self, session_id: str) -> Optional[str]:
        return instance_for(self.salt, session_id) if self.salt else None


# ---------------------------------------------------------------- Prism's own state → the shared vocabulary

def coarse_state(phase: str, previous: Optional[str] = None) -> Optional[str]:
    """Map Prism's observed phase to a V1 word, or keep the last truthful word.

    Antigravity tells Prism when an invocation starts and when a turn stops; it has no passive
    event at tool start (PreToolUse is an approval gate Prism must not answer), so Prism never
    publishes `tool`, never counts tools in flight, never reaches, and never claims `thinking`.
    """
    mapping = {"wake": "working", "attending": "working", "working": "working",
               "resolved": "stopped", "halted": "stopped", "ended": "ended", "ready": "idle"}
    return mapping.get(phase, previous)
