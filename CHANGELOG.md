# Changelog

## 1.2.0

- **Cyclops Link v1 Implementation**: Added decentralized local peer presence protocol (`scripts/link.py`), allowing Spark (Claude Code), Keeper (Codex), and Prism (Antigravity) to observe each other's status and render real-time handoff threads.
- **Pure Observer Hook Architecture**: Completely removed `PreToolUse` gating hook to guarantee that Prism never acts as an authorization gate or bypasses user tool approval prompts. All lifecycle hooks now run as purely non-interfering observers.
- **Decoupled from Studio**: Removed all legacy `CYCLOPS_SESSION_ID` and `CYCLOPS_PRESENCE_ROOT` environment hooks, aligning Prism's clean standalone architecture with Spark and Keeper.

## 1.1.0

- **Integrated agy Launcher**: Introduced `agy --cyclops-prism` and `agy-prism` command to launch Antigravity CLI and Prism side-by-side in a split tmux terminal automatically.
- **Hook Protocol Hardening**: Explicit `--event` parameters passed in `hooks.json` to guarantee strict compliance with Antigravity's Go runtime (`PreToolUse` allow contract, `PostToolUse` empty object contract).
- **Automated Lifecycle Teardown**: Automatic cleanup of Prism companion panes upon Antigravity session exit.
- **Enhanced Installer**: Added `install.sh` support for `agy-prism` and shell helper registration in `~/.bashrc`.

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
