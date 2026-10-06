# Prism Agent Rules

When developing or executing tasks within environments paired with Prism:

## 1. Respect Privacy Boundaries
- Never attempt to bypass Prism's privacy filter. All event telemetry emitted to presence feeds must remain strictly zero-leakage.
- Tool arguments, file paths, shell commands, code bodies, and sensitive tokens must never be written to presence feeds or terminal logs.

## 2. Truthful Lifecycle Semantics
- Never fabricate fake events or simulate idle state while background tasks are actively running.
- Use explicit Antigravity lifecycle hooks (`PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse`, `Stop`) to report true state transitions.
- Acknowledge that `session.end` is terminal and cannot be resurrected.

## 3. Terminal Companion Conventions
- The standalone terminal CLI supports `--once` for lightweight snapshotting and `--mode focus` for full telemetry.
- Always handle terminal window resizing gracefully.
- Support non-color (`NO_COLOR` / `--no-color`) and plain ASCII (`--plain`) environments without crashing or emitting broken escape sequences.
