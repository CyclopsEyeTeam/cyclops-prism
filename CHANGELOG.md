# Changelog

## 1.2.1 - Clipboard Integration & Cold-Start Resilience

- **System Clipboard Integration (`xclip` / `wl-copy`)**: Added automatic system clipboard piping on mouse drag release in tmux companion sessions (`MouseDragEnd1Pane`), along with native keyboard copy-mode bindings (`Enter`, `y`, `c`, `Ctrl+c`) and right-click support.
- **Terminal Bypass via Shift**: Retained native terminal selection bypass so holding `Shift` while dragging or right-clicking enables standard terminal emulator context menus and `Ctrl+Shift+c`.
- **New `/copy` Slash Command**: Introduced `/copy` command to copy text, code blocks, or the latest assistant response directly into the OS clipboard.
- **Active Session Feed Discovery Fix**: Resolved cold-start monochrome/frozen state when launching `agy --prism`. The discovery routine (`find_active_feed()`) now ignores ended sessions and dead host processes, prioritizing active sessions with recent event timestamps.
- **Link View Peer Crash Guard**: Fixed a `TypeError` crash caused by uninitialized peer bearings and handled duplicate Prism peers safely.
- **Terminal Companion Redraw Resilience**: Added exception guards and cursor parking to prevent transient feed glitches from crashing the companion animation.
- **Optical Dispersion & Living Crystalline Presence**: Elevated the terminal companion with living chromatic spectral gradients along the polarized rings (cyclic interpolation through hyper-cyan, emerald teal, electric violet, solar gold, and pearl white). The central polyhedral facets dynamically awaken across lifecycle states: attending (nested facet `◈`), refracting (optical dispersion `❖`), parallel synthesis (polyhedral lattice `◇` with multi-hued satellite orbits), and crystallization (radiant warm white star `✦`).
- **Native Window Launch Mode**: Added `--native` / `--window` flags to open Prism in a standalone GUI terminal window outside of tmux.

## 1.2.0 - Cyclops Link

- **Cyclops Link** (off until `prism link on`): Prism, Spark and Keeper notice each other when they work in the same
  folder. Spark and Keeper appear in both companion layouts at their seats (lower left, lower right), each in their own
  exported look, with threads while one calls another. Prism shares only her coarse state; her session daemon keeps it
  fresh while Antigravity runs and says so when it closes.
- Prism's own Link mark sheet (`link-mark/prism.json`, with a 7 x 3 core for small hosts), exported from her renderer.
- Fixed: the live feed's reply offer was never computed, so a live session always showed `Prism · ready`; live states now
  show, including `crystallized` after a turn and `halted`.
- Fixed: `prism tmux status|top|side` failed for a missing `subprocess` import.
- The terminal CLI tests now run against an empty state folder instead of whatever session ran last on the machine.
- Every `PreInvocation` is a `turn.attend` (Prism's own fix), so the first turn reads `attending`, in agreement with the
  `working` she publishes through Link.

## 1.1.2 - Top View Layout & Flicker-Free Telemetry

- **Top View Companion Layout (`agy --prismtop` / `agy-prismtop`)**: Added support for launching Prism in a wide companion banner at the top of Antigravity (`split-window -b -v -l 14`) with automatic cursor focus placed directly into `agy` below.
- **Side View Option (`agy --prism` / `agy-prism`)**: Preserved the vertical side-by-side companion split (`split-window -h -l 35`) on the right.
- **Flicker-Free In-Place Redraw**: Eliminated screen clearing (`\033[J`) on 20 FPS ticks, resolving rapid terminal flashing / jumping. The terminal now overwrites in-place via cursor home (`\033[H`), only clearing on initial startup or terminal resize (`SIGWINCH`).
- **Compact Height Bounds Clamping**: Clamped polarized ring radii (`max_ry`) and core level selections to guarantee that Prism never collides with status banners or screen edges in compact top panes (10–14 rows).

## 1.1.1 - Critical Safety & Usability Release

- **Pure Observer Hook Architecture (Critical Security Fix)**: Completely removed the `PreToolUse` hook registration from `hooks.json`. In Antigravity's runtime, `PreToolUse` functions as an authorization gate rather than a passive observer; removing it ensures Prism never auto-approves tool executions, fully preserving interactive user authorization prompts and security boundaries.
- **Decoupled from Studio Wiring**: Removed all legacy `CYCLOPS_SESSION_ID` and `CYCLOPS_PRESENCE_ROOT` environment hooks, aligning Prism's clean standalone architecture with Spark and Keeper.
- **Responsive Dynamic Terminal Canvas**: Polarized rings and crystalline geometry dynamically scale to any terminal size (from compact split panes up to 95+ column fullscreen windows), featuring a 3-tier adaptive jewel core with nested facets.
- **Protocol Harmonization**: Held Cyclops Link implementation pending final frozen specification and official test fixtures from Claude Spark / Don.

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
