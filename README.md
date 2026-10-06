# Cyclops Prism: Standalone Terminal Presence & Antigravity Plugin

**Cyclops Prism** is a balanced, iridescent working presence and standalone terminal companion for Antigravity (`agy`).

It visualizes real-time model lifecycle events through a living faceted polyhedral core held in counter-rotating polarized light rings, with dynamic refraction rays for active tool executions and orbital nodes for concurrent subagent branches.

---

## Features

- **Living Terminal Companion**: Real-time 20 FPS animated ASCII and ANSI Truecolor terminal renderer.
- **Antigravity Plugin Ready**: Bundled with `plugin.json`, `hooks.json`, `skills/`, and `rules/` for seamless auto-discovery.
- **Zero-Config Auto-Discovery**: Automatically discovers and binds to active Antigravity sessions without requiring manual `--feed` paths.
- **Tmux & Statusbar Integration**: Instant single-frame snapshotting via `--once` for shell prompts, tmux status lines, and automation scripts.
- **Zero External Dependencies**: Implemented entirely in the Python 3.8+ standard library. Requires no `pip` packages.
- **Adaptive Compositions**:
  - `balanced` (default): Compact diamond core with dual polarized rings and status banner.
  - `focus`: Expanded geometry displaying real-time tool counts, branch counts, and active lanes.
- **Strict Zero-Leakage Privacy**: Emits no code, prompts, paths, or secrets. Tool actions are mapped strictly to five finite, safe semantic categories (`inspect`, `change`, `execute`, `service`, `other`).
- **Resilient Architecture**: Atomic file updates, Linux `/proc/<pid>/stat` PID reuse defense, and fail-open hook execution (< 15ms).

---

## Quickstart

Run directly from the repository root:

```bash
# Live interactive animated presence (20 FPS)
./gemini-prism

# Instant snapshot (non-interactive)
./gemini-prism --once

# Expanded telemetry mode
./gemini-prism --mode focus

# Pure ASCII fallback (no Unicode)
./gemini-prism --plain

# Demonstration mode (cycles through operational states)
./gemini-prism --demo

# Inspect a specific semantic state
./gemini-prism --once --demo-state refracting
./gemini-prism --once --demo-state approval
./gemini-prism --once --demo-state crystallize
```

---

## Installation & PATH Setup

To run `prism` from any directory in your shell:

### Option 1: Symlink to user binaries (Recommended)
```bash
mkdir -p ~/.local/bin
ln -s "$(pwd)/bin/prism" ~/.local/bin/prism
```
Ensure `~/.local/bin` is in your `$PATH`.

### Option 2: Add directory to PATH
Add to your `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="/path/to/gemini-prism/bin:$PATH"
```

Once installed, you can simply run:
```bash
prism
prism --once
prism --mode focus
```

---

## Tmux Integration

### 1. Dedicated Sidebar Pane
Split your tmux window and run Prism alongside your coding session:
```bash
tmux split-window -h -l 36 'prism'
```

### 2. Tmux Status Line
Embed Prism's live state in your tmux status bar (`~/.tmux.conf`):
```tmux
set -g status-interval 2
set -g status-right "#(prism --once --plain | grep -o 'Prism.*' | head -n 1) | %H:%M "
```

---

## Antigravity Plugin Installation

To enable `cyclops-prism` as an Antigravity plugin:

### Option A: Workspace Plugin (Project-Specific)
Clone or symlink this repository into your project's `.agents/plugins/`:
```bash
mkdir -p .agents/plugins
ln -s /path/to/cyclops-prism .agents/plugins/cyclops-prism
```

### Option B: Global Antigravity Registration
Add the path to `~/.gemini/config/plugins.json`:
```json
{
  "plugins": [
    {
      "path": "/path/to/cyclops-prism"
    }
  ]
}
```

When active, Antigravity automatically calls `scripts/hook.py` on lifecycle events (`PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse`, `Stop`), recording sanitized state to `~/.local/state/cyclops-prism/presence/` for `prism` to render.

---

## Sigils & State Vocabulary

| State | Glyph | ANSI Truecolor | Meaning |
| :--- | :---: | :--- | :--- |
| **Ready / Idle** | `⟐` | Hyper-cyan (`#00F2FE`) | Ambient breathing, waiting for work |
| **Attending** | `⟐` | Solar Gold (`#FFB020`) | Analyzing prompt / reading context |
| **Refracting** | `❖` | Emerald Teal / Gold / Cyan | Active tool calls (`inspect`, `change`, `execute`) |
| **Branching** | `◇` | Electric Violet (`#7928CA`) | Orchestrating concurrent subagent branches |
| **Approval** | `!` | Alert Red (`#FF4D4D`) | Awaiting user permission |
| **Crystallized** | `✦` | Warm White (`#FFF6D6`) | Turn complete, response ready |
| **Ended** | `·` | Dark Gray (`#374151`) | Session closed |

---

## Testing

Run the automated test suite:
```bash
python3 -B -m unittest discover -s tests -v
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
