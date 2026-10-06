# Cyclops Prism: Antigravity Terminal Presence Plugin

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Antigravity](https://img.shields.io/badge/Antigravity-CLI_Plugin-00F2FE.svg)](https://github.com/CyclopsEyeTeam/cyclops-prism)

**Cyclops Prism** is an Antigravity (`agy`) terminal presence plugin that reflects real-time model lifecycle events as a living, crystalline companion.

It pairs directly with the Antigravity CLI, visualizing model thinking, tool executions, and subagent branches through a faceted polyhedral core held in counter-rotating polarized light rings at 20 FPS.

```text
       ╲ ╲  ╲     ╱  ╱ ╱        
    ╲╲      ╱     ╲      ╱╱     
   ╲     ╱     ▲     ╲     ╱    
    ╱╱ ╱     ⟨ ⟐ ⟩     ╲ ╲╲     
   ╱      ╲    ▼     ╱     ╲    
    ╱╱      ╲     ╱      ╲╲     
       ╱  ╱ ╱     ╲  ╲ ╲        
       ⟐  Prism · ready         
```

---

## Quickstart

### 1. Install

Clone the repository and run the one-step installer:

```bash
git clone https://github.com/CyclopsEyeTeam/cyclops-prism.git
cd cyclops-prism
chmod +x install.sh
./install.sh
```

The installer will automatically:
- Symlink the `prism` and `agy-prism` binaries into `~/.local/bin/`.
- Register the `agy --cyclops-prism` launcher helper in `~/.bashrc`.
- Install and configure the plugin hooks in Antigravity (`agy`).

### 2. Launch

Navigate to any working directory or project of your choice and launch Antigravity with Prism:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Side View: Antigravity with Prism companion on the right
agy --prism
# (or shorthand: agy-prism)

# Top View: Wide crystalline companion banner on top of Antigravity
agy --prismtop
# (or shorthand: agy-prismtop)
```

Antigravity will open in your active pane with Prism running live in its companion pane. Your focus is placed immediately on the `agy` prompt, and the companion closes cleanly when you exit.

---

## Features

- **Flexible Companion Layouts**: Supports both **Side View** (`agy --prism`, companion pane on the right) and **Top View** (`agy --prismtop`, wide banner companion on top).
- **Flicker-Free 20 FPS Telemetry**: Smooth ANSI Truecolor & ASCII renderer with in-place redraw and automatic session discovery.
- **Real-Time Lifecycle Hooks**: Connects directly to Antigravity's Go runtime (`PreInvocation`, `PostInvocation`, `PostToolUse`, `Stop`) with fail-open safety (< 15ms latency). Never gates or auto-approves tool executions.
- **Responsive Dynamic Terminal Canvas**: Polarized rings and crystalline geometry dynamically scale to any terminal size and aspect ratio, with adaptive jewel cores tailored for compact top banners as well as expanded full-screen panes.
- **Dual Visual Modes**:
  - `balanced` (default): Compact diamond core with polarized light rings and status banner.
  - `focus`: Expanded optical geometry with real-time tool counts, branch counts, and lane diagnostics.
- **Strict Zero-Leakage Privacy**: Guarantees zero leakage. No prompts, code, commands, paths, or tokens are ever logged or displayed. Tool calls are strictly classified into five safe categories (`inspect`, `change`, `execute`, `service`, `other`).
- **Zero External Dependencies**: Implemented entirely using Python 3 standard library. No `pip` dependencies required.

---

## CLI Commands & Modes

### Launching Antigravity

Pass any standard `agy` arguments directly through either companion layout:

```bash
# Side View (companion pane on right)
agy --prism -c
# Or: agy-prism -c

# Top View (companion banner on top)
agy --prismtop --model gemini-2.5-pro
# Or: agy-prismtop --model gemini-2.5-pro
```

### Standalone Companion Modes

You can also run `prism` independently from any terminal:

```bash
prism                   # Live 20 FPS animated companion (auto-attaches to active session)
prism focus             # Expanded optical geometry with tool lanes and branch meters
prism tmux [side|top]   # Dock Prism into a tmux split pane (side or top)
prism once              # Single-frame snapshot (ideal for prompts and status lines)
prism plain             # Pure ASCII mode (for terminals without Unicode support)
prism demo              # Continuous animated tour across all operational states
```

---

## State Vocabulary & Sigils

| State | Glyph | ANSI Truecolor | Meaning |
| :--- | :---: | :--- | :--- |
| **Ready / Idle** | `⟐` | Hyper-cyan (`#00F2FE`) | Ambient breathing, waiting for prompt |
| **Attending** | `⟐` | Solar Gold (`#FFB020`) | Model reasoning and reading context |
| **Refracting** | `❖` | Emerald / Gold / Cyan | Tool calls in flight (`inspect`, `change`, `execute`) |
| **Branching** | `◇` | Electric Violet (`#7928CA`) | Orchestrating concurrent subagent branches |
| **Approval** | `!` | Alert Red (`#FF4D4D`) | Awaiting user tool permission |
| **Crystallized** | `✦` | Warm White (`#FFF6D6`) | Turn complete, answer rendered |
| **Ended** | `·` | Dark Gray (`#374151`) | Session closed |

---

## Uninstallation

To completely remove the launchers and Antigravity plugin:

```bash
./install.sh --uninstall
```

---

## Testing

Run the comprehensive unit test suite:

```bash
python3 -B -m unittest discover -s tests -v
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
