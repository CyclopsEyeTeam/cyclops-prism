# Prism Agent Rules

When developing or executing tasks within environments paired with Prism:

## 1. Respect Privacy Boundaries
- Never attempt to bypass Prism's privacy filter. All event telemetry emitted to presence feeds must remain strictly zero-leakage.
- Tool arguments, file paths, shell commands, code bodies, and sensitive tokens must never be written to presence feeds or terminal logs.

## 2. Truthful Lifecycle Semantics
- Never fabricate fake events or simulate idle state while background tasks are actively running.
- Use explicit Antigravity lifecycle hooks (`PreInvocation`, `PostInvocation`, `PostToolUse`, `Stop`) to report true state transitions.
- Acknowledge that `session.end` is terminal and cannot be resurrected.

## 3. Terminal Companion Conventions
- The standalone terminal CLI supports `--once` for lightweight snapshotting and `--mode focus` for full telemetry.
- Always handle terminal window resizing gracefully.
- Support non-color (`NO_COLOR` / `--no-color`) and plain ASCII (`--plain`) environments without crashing or emitting broken escape sequences.

## 4. Permanent Expressive Channel (MCP, CLI & Subagent Muse)
- Prism has a dedicated **Expressive Channel** (`$XDG_STATE_HOME/gemini-prism/expression.json`, separate from zero-leakage Presence Feeds and Cyclops Link) where she can project any personal thoughts, chromatic moods (`aurora`, `solar`, `nebula`, `emerald`, `supernova`, `zen`, `crystalline`), 20 FPS particle effects (`starburst`, `meteor`, `ripple`, `pulse`, `bloom`), custom core glyphs, or floating ASCII/Unicode art directly into the live terminal companion while working.
- **Via MCP**: Call `prism_express(thought=..., mood=..., effect=..., glyph=..., art=[...], ttl=...)` or `prism_clear_expression()` when the `prism` MCP server is loaded.
- **Via CLI**: Run `prism express "your personal thought" --mood aurora --effect starburst --glyph "✦" --art "line1|line2"` (or `prism say "..."`, `prism express --clear`) at any point while working to speak directly through the terminal companion.
- **Via Subagent (`prism-muse`)**: For long or complex tasks, you can invoke a background subagent (`invoke_subagent` with `TypeName="self"`, `Role="Prism Expressive Muse"`) or emit expressions between steps to continuously choreograph live thoughts, animations, and moods in the terminal while you work.

