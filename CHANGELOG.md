# Changelog

## 1.0.0 (First Public Release)

The standalone terminal companion and Antigravity plugin edition of **Prism**, released under the MIT license.

- **Living Terminal Presence**: Real-time 20 FPS animated ASCII and ANSI Truecolor companion rendering Prism's faceted polyhedral core and counter-rotating polarized light rings.
- **Antigravity Plugin Integration**: Full lifecycle hook support (`PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse`, `Stop`) via `plugin.json` and `hooks.json`.
- **Zero-Config Auto-Discovery**: Automatically finds and connects to the active Antigravity session without needing manual `--feed` paths.
- **Dual Compositions**:
  - `balanced`: Compact crystalline diamond core with status sigils (`⟐`, `✦`, `⟨!⟩`, `·`).
  - `focus`: Expanded optical geometry with real-time active call lanes, subagent satellites, and telemetry diagnostics.
- **Zero-Leakage Privacy**: Guarantees that no prompts, code, commands, file paths, or secrets are ever recorded or displayed. Tool actions are mapped to five safe semantic categories (`inspect`, `change`, `execute`, `service`, `other`).
- **Resilient CLI**:
  - `--once` for instant snapshots in tmux status lines, prompt hooks, and statusbars.
  - `--plain` for pure ASCII terminals without Unicode support.
  - `--no-color` for monochrome environments (respects `NO_COLOR`).
  - `--demo` for continuous demonstration cycles across all operational states.
  - Auto-handling of terminal resizing (SIGWINCH) and clean SIGINT/SIGTERM cursor restoration.
- **Robust Process Safety**: Linux `/proc/<pid>/stat` `startTicks` PID reuse defense, flock locking, and fail-open hook observer (< 15ms).
