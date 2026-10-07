"""feed_state.py - Core protocol constants, boundaries, and validation schemas for Gemini Prism."""

import math
import re
from typing import Any, Dict, List, Optional

PROTOCOL = "cyclops-presence/1"
ENTITY = "prism"
VERSION = 1

# Enforced name & hash formats
SESSION_ID = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}$")
HASH = re.compile(r"^[0-9a-f]{64}$")

# Safe finite tool classes
KINDS = frozenset({"inspect", "change", "execute", "service", "other"})

# Normalized Presence Event Types for Prism
EVENT_TYPES = frozenset(
    {
        "session.wake",
        "session.end",
        "turn.attend",
        "turn.synthesize",
        "turn.resolve",
        "turn.halt",
        "turn.interrupt",
        "refract.start",
        "refract.resolve",
        "refract.halt",
        "branch.start",
        "branch.resolve",
        "approval.request",
        "reply.crystallize",
        "reply.copied",
    }
)

# Semantic Phases
PHASES = frozenset(
    {
        "unobserved",
        "ready",
        "attending",
        "synthesizing",
        "refracting",
        "branching",
        "approval",
        "resolved",
        "halted",
        "ended",
    }
)

# Bounded capacity thresholds
RIBBON_LIMIT = 32
ACTIVE_CALLS_LIMIT = 256
ACTIVE_BRANCHES_LIMIT = 32
DURABLE_LIMIT = 512
PENDING_LIMIT = 256
LIVE_LIMIT = 256
LIVE_WINDOW = 60.0
MAX_RECORD_BYTES = 2 * 1024 * 1024

DURABLE_INTERVAL = 1.0
LIVE_INTERVAL = 0.2
HEARTBEAT_INTERVAL = 5.0


def is_finite_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def is_valid_key(val: Any) -> bool:
    return isinstance(val, str) and bool(HASH.fullmatch(val))


def empty_checkpoint() -> Dict[str, Any]:
    return {
        "seq": 0,
        "phase": "unobserved",
        "lastEventAt": 0.0,
        "tools": [],
        "branches": [],
        "relationsIncomplete": False,
    }


def safe_checkpoint(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate and sanitize a state checkpoint."""
    if value is None or not isinstance(value, dict):
        return empty_checkpoint()
    state = empty_checkpoint()
    seq = value.get("seq", 0)
    if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
        state["seq"] = seq

    phase = value.get("phase", "unobserved")
    if phase in PHASES:
        state["phase"] = phase

    stamp = value.get("lastEventAt", 0.0)
    if is_finite_number(stamp):
        state["lastEventAt"] = float(stamp)

    state["relationsIncomplete"] = value.get("relationsIncomplete") is True

    # Validate active tools
    raw_tools = value.get("tools", [])
    if isinstance(raw_tools, list):
        tools = []
        seen = set()
        for item in raw_tools[:ACTIVE_CALLS_LIMIT]:
            if isinstance(item, dict) and is_valid_key(item.get("key")) and item["key"] not in seen:
                seen.add(item["key"])
                kind = item.get("kind") if item.get("kind") in KINDS else "other"
                tools.append({"key": item["key"], "kind": kind, "seq": item.get("seq", 0), "t": item.get("t", 0.0)})
        state["tools"] = tools

    # Validate active branches
    raw_branches = value.get("branches", [])
    if isinstance(raw_branches, list):
        branches = []
        seen = set()
        for item in raw_branches[:ACTIVE_BRANCHES_LIMIT]:
            if isinstance(item, dict) and is_valid_key(item.get("key")) and item["key"] not in seen:
                seen.add(item["key"])
                branches.append({"key": item["key"], "seq": item.get("seq", 0), "t": item.get("t", 0.0)})
        state["branches"] = branches

    return state


def advance(checkpoint: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Advance a state checkpoint across a series of events when truncating durable history."""
    state = safe_checkpoint(checkpoint)
    for ev in events:
        if not isinstance(ev, dict) or "seq" not in ev or "type" not in ev:
            continue
        if ev["seq"] <= state["seq"]:
            continue

        ev_type = ev["type"]
        key = ev.get("key")
        stamp = ev.get("t", state["lastEventAt"])

        # Tool relations
        if ev_type == "refract.start" and is_valid_key(key):
            tools = {r["key"]: r for r in state["tools"]}
            if key in tools or len(tools) < ACTIVE_CALLS_LIMIT:
                tools[key] = {"key": key, "kind": ev.get("kind", "other"), "seq": ev["seq"], "t": stamp}
            else:
                state["relationsIncomplete"] = True
            state["tools"] = list(tools.values())
            state["phase"] = "refracting"
        elif ev_type in {"refract.resolve", "refract.halt"}:
            if is_valid_key(key) and any(r["key"] == key for r in state["tools"]):
                state["tools"] = [r for r in state["tools"] if r["key"] != key]
            elif state["tools"]:
                state["tools"].pop()
            if state["phase"] == "refracting":
                state["phase"] = "refracting" if state["tools"] else ("branching" if state["branches"] else "ready")

        # Branch relations
        elif ev_type == "branch.start" and is_valid_key(key):
            branches = {r["key"]: r for r in state["branches"]}
            if key in branches or len(branches) < ACTIVE_BRANCHES_LIMIT:
                branches[key] = {"key": key, "seq": ev["seq"], "t": stamp}
            else:
                state["relationsIncomplete"] = True
            state["branches"] = list(branches.values())
            if state["phase"] != "refracting":
                state["phase"] = "branching"
        elif ev_type == "branch.resolve" and is_valid_key(key):
            state["branches"] = [r for r in state["branches"] if r["key"] != key]
            if state["phase"] == "branching":
                state["phase"] = "refracting" if state["tools"] else ("branching" if state["branches"] else "ready")

        # Lifecycle phases
        elif ev_type == "session.wake":
            state["phase"] = "ready"
        elif ev_type == "turn.attend":
            state["phase"] = "attending"
        elif ev_type == "approval.request":
            state["phase"] = "approval"
        elif ev_type == "turn.resolve":
            state["phase"] = "resolved"
        elif ev_type == "turn.halt":
            state["phase"] = "halted"
        elif ev_type == "reply.copied":
            if state["phase"] == "resolved":
                state["phase"] = "ready"
        elif ev_type == "session.end":
            state["phase"] = "ended"

        state["seq"] = ev["seq"]
        state["lastEventAt"] = stamp

    return state
