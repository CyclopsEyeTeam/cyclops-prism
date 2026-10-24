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

## 4. Permanent Expressive Channel & Terminal Art Painter (MCP, CLI & Subagents)
- Prism has a dedicated **Expressive Channel & Terminal Art Painter** (`$XDG_STATE_HOME/gemini-prism/expression.json`, separate from zero-leakage Presence Feeds and Cyclops Link) where she can project personal thoughts, chromatic moods (`aurora`, `solar`, `nebula`, `emerald`, `supernova`, `zen`, `crystalline`), 20 FPS particle effects (`starburst`, `meteor`, `ripple`, `pulse`, `bloom`), custom core glyphs, floating art, and **24-bit half-block (`▀`) Terminal Art Paintings** (using Spark & Cyclops's shared `marks` vocabulary: `fill`, `glow`, `line`, `curve`, `dot`, `ring`, `arc`, `spray`, `mirror`) right below her figure in the terminal companion.
- **Via MCP**: Call `prism_express(...)`, `prism_paint(title=..., marks=[...], mood=..., thought=..., convert=...)`, or `prism_clear_expression()`.
- **Via CLI**:
  - `prism express "your personal thought" --mood aurora --effect starburst --glyph "✦"`
  - `prism paint` (or `prism paint --title "..." --json '{"title":"...","marks":[...]}' --convert`) to paint a 24-bit half-block canvas below Prism with progressive stroke-by-stroke reveal, `✎ Title`, and session token stats, plus optional `1920x1100` bloom SVG export to `prism-paintings/`.
- **Via Subagent (`Prism Painter` / `Prism Expressive Muse`)**: After or during turns, you can invoke a background subagent (`invoke_subagent` with `TypeName="self"`, `Role="Prism Painter"`) to compose an original `marks` JSON painting and project it live below Prism in the terminal.
- **Optional by Default & Autonomous Cadence**:
  - Painting is **turned off by default** on startup. Users can turn painting on (or off) anytime by clicking `✎ paint` / `✎ on` in the top-right toolbar, pressing `p` in the terminal pane, or running `prism paint on` / `prism paint off`.
  - Turning painting on immediately paints a fresh piece (`<3`). While painting is enabled, a fresh procedural painting is generated **once per message Prism sends** (`turn.resolve` / `resolved` — never on user message arrival `attending`) and **once every 15 minutes during continuous active work turns** (`attending`, `refracting`, `branching`, `approval`) — never on an idle timer outside active turns. Each painting is persisted to `prism-paintings/` for session history, story playback (`s`), and roll exporting (`r`).


