"""activity.py - Privacy adapter, tool classifier, and state reducer for Prism.

Ensures zero prompt, code, path, secret or command leakage.
Transforms raw Antigravity hook payloads into normalized Presence events.
"""

import hashlib
import time
from typing import Any, Dict, Optional
import feed_state


def digest(value: Any) -> str:
    """Produce a deterministic SHA-256 lowercase hex string from any scalar identifier."""
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_tool(name: Any) -> str:
    """Reduce tool names strictly to the 5 finite safe classes: inspect, change, execute, service, other."""
    if not isinstance(name, str) or len(name) > 256 or not name:
        return "other"
    lowered = name.casefold()

    # Service / MCP integrations
    if lowered.startswith("mcp__") or lowered.startswith("mcp_"):
        return "service"

    # File inspection / reading
    if lowered in {
        "view_file",
        "grep_search",
        "find_by_name",
        "list_dir",
        "read_url_content",
        "read",
        "open",
        "search",
        "find",
        "file_search",
        "ripgrep",
        "cat",
    }:
        return "inspect"

    # File modification / creation
    if lowered in {
        "write_to_file",
        "replace_file_content",
        "apply_patch",
        "edit",
        "write",
        "file_change",
    }:
        return "change"

    # Command execution
    if lowered in {
        "run_command",
        "bash",
        "shell",
        "exec",
        "command",
        "terminal",
        "exec_command",
    }:
        return "execute"

    return "other"


def is_subagent_tool(name: Any) -> bool:
    """Identify tools that manage concurrent subagents / parallel branches."""
    if not isinstance(name, str):
        return False
    return name.casefold() in {"invoke_subagent", "manage_subagents", "send_message"}


def adapt_hook_event(
    payload: Dict[str, Any],
    sequence: int,
    matching_key: Optional[str] = None,
    at: Optional[float] = None,
    is_branch: Optional[bool] = None,
    state: Optional["PrismState"] = None,
) -> Optional[Dict[str, Any]]:
    """Convert an Antigravity hook payload into a strictly sanitized Presence event."""
    if not isinstance(payload, dict) or not isinstance(sequence, int) or sequence < 1:
        return None

    stamp = float(time.time() if at is None else at)
    if not feed_state.is_finite_number(stamp):
        return None

    hook_event = payload.get("hookEvent") or payload.get("hook_event_name")
    if not hook_event or not isinstance(hook_event, str):
        # Auto-detect hook event from payload structure if omitted
        if "toolCall" in payload:
            hook_event = "PreToolUse"
        elif "toolName" in payload or "error" in payload:
            hook_event = "PostToolUse"
        elif "invocationNum" in payload:
            hook_event = "PreInvocation"
        elif "terminationReason" in payload:
            hook_event = "Stop"
        else:
            return None

    conv_id = payload.get("conversationId", "")
    step_idx = payload.get("stepIdx", 0)

    # 1. PreInvocation -> session.wake or turn.attend
    if hook_event == "PreInvocation":
        inv_num = payload.get("invocationNum", 1)
        event_type = "session.wake" if inv_num == 1 else "turn.attend"
        return {"seq": sequence, "t": stamp, "type": event_type}

    # 2. PreToolUse -> approval.request, branch.start, or refract.start
    elif hook_event == "PreToolUse":
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        raw_key = matching_key or digest(f"{conv_id}:{step_idx}:{tool_name}")

        # Explicit consent gating
        if payload.get("explicitConsentRequired") is True or payload.get("decision") == "ask":
            kind = classify_tool(tool_name)
            return {"seq": sequence, "t": stamp, "type": "approval.request", "kind": kind, "key": raw_key}

        # Subagent invocation
        if is_subagent_tool(tool_name) or is_branch is True:
            return {"seq": sequence, "t": stamp, "type": "branch.start", "key": raw_key}

        # Ordinary tool invocation
        kind = classify_tool(tool_name)
        return {"seq": sequence, "t": stamp, "type": "refract.start", "kind": kind, "key": raw_key}

    # 3. PostToolUse -> refract.resolve, refract.halt, or branch.resolve
    elif hook_event == "PostToolUse":
        raw_key = matching_key or digest(f"{conv_id}:{step_idx}")
        tool_name = payload.get("toolName", "")

        # Error return
        if payload.get("error"):
            return {"seq": sequence, "t": stamp, "type": "refract.halt", "key": raw_key}

        # Subagent return: check tool name, payload flag, explicit param, or state's active_branches
        is_sub = (
            is_subagent_tool(tool_name)
            or payload.get("isSubagent") is True
            or is_branch is True
            or (state is not None and raw_key in state.active_branches)
        )
        if is_sub:
            return {"seq": sequence, "t": stamp, "type": "branch.resolve", "key": raw_key}

        # Standard tool resolution
        return {"seq": sequence, "t": stamp, "type": "refract.resolve", "key": raw_key}

    # 4. Stop -> turn.resolve or turn.halt
    elif hook_event == "Stop":
        reason = payload.get("terminationReason", "model_stop")
        if reason == "model_stop":
            return {"seq": sequence, "t": stamp, "type": "turn.resolve"}
        else:
            return {"seq": sequence, "t": stamp, "type": "turn.halt"}

    # 5. Explicit interaction events (e.g. copied response)
    elif hook_event in {"reply.copied", "Copied"}:
        return {"seq": sequence, "t": stamp, "type": "reply.copied"}

    return None


class PrismState:
    """In-memory state reducer for Prism. Maintains strictly bounded active calls and transition history."""

    def __init__(self):
        self.transitions = []
        self.active_calls = {}  # key -> { kind, seq, t }
        self.active_branches = {}  # key -> { seq, t }
        self.mode = "idle"
        self.offer = None

    def apply(self, event: Dict[str, Any]) -> None:
        """Apply a normalized Presence event to update Prism's internal state."""
        if not isinstance(event, dict) or "type" not in event:
            return

        ev_type = event["type"]
        key = event.get("key")
        kind = event.get("kind")
        seq = event.get("seq", 0)
        t = event.get("t", 0.0)

        # 1. Update transition ribbon
        self.transitions.append(event)
        if len(self.transitions) > feed_state.RIBBON_LIMIT:
            self.transitions = self.transitions[-feed_state.RIBBON_LIMIT :]

        # 2. Update relational maps
        if ev_type == "refract.start" and key:
            if len(self.active_calls) < feed_state.ACTIVE_CALLS_LIMIT:
                self.active_calls[key] = {"kind": kind or "other", "seq": seq, "t": t}
        elif ev_type in {"refract.resolve", "refract.halt"} and key:
            self.active_calls.pop(key, None)
        elif ev_type == "branch.start" and key:
            if len(self.active_branches) < feed_state.ACTIVE_BRANCHES_LIMIT:
                self.active_branches[key] = {"seq": seq, "t": t}
        elif ev_type == "branch.resolve" and key:
            self.active_branches.pop(key, None)

        # 3. Update overall mode & offer
        if ev_type == "session.wake":
            self.mode = "idle"
            self.offer = None
        elif ev_type == "turn.attend":
            self.mode = "attending"
            self.offer = None
        elif ev_type == "approval.request":
            self.mode = "approval"
        elif ev_type == "turn.resolve":
            self.mode = "resolved"
            self.offer = "crystallize"
        elif ev_type == "turn.halt":
            self.mode = "halted"
            self.offer = None
        elif ev_type == "reply.copied":
            self.offer = None
            if self.mode == "resolved":
                self.mode = "idle"
        elif ev_type == "session.end":
            self.mode = "ended"

        # Reconcile active working modes
        if self.active_calls:
            self.mode = "refracting"
        elif self.active_branches:
            self.mode = "branching"

    def state_summary(self) -> str:
        """Generate a truthful, human-readable one-line state string."""
        if self.mode == "idle":
            return "Prism · ready"
        elif self.mode == "attending":
            return "Prism · attending"
        elif self.mode == "approval":
            return "Prism · awaiting consent"
        elif self.mode == "refracting":
            kinds = {call["kind"] for call in self.active_calls.values()}
            kinds_str = ", ".join(sorted(kinds)) if kinds else "inspect"
            return f"Prism · refracting · {kinds_str}"
        elif self.mode == "branching":
            count = len(self.active_branches)
            return f"Prism · parallel synthesis · {count} branches"
        elif self.mode == "resolved":
            return "Prism · crystallized · 1 ready" if self.offer else "Prism · resolved"
        elif self.mode == "halted":
            return "Prism · halted"
        elif self.mode == "ended":
            return "Prism · ended"
        return "Prism · ready"
