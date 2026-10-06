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

# Launch Antigravity with Prism side-by-side:
agy --cyclops-prism

# Or using the shorthand command:
agy-prism
```

Antigravity will open in your main terminal pane with Prism running live in a companion pane on the right. Your focus is placed immediately on the `agy` prompt, and the companion closes cleanly when you exit.

---

## Features

- **Side-by-Side Terminal Companion**: Seamlessly splits your terminal window in tmux or terminal multiplexers with zero manual configuration.
- **Real-Time Lifecycle Hooks**: Connects directly to Antigravity's Go runtime (`PreInvocation`, `PostInvocation`, `PostToolUse`, `Stop`) with fail-open safety (< 15ms latency). Never gates or auto-approves tool executions.
- **Responsive Dynamic Terminal Canvas**: Polarized rings and crystalline geometry dynamically scale to any terminal size, featuring a multi-tier adaptive jewel core with nested facets on large and fullscreen windows.
- **Living 20 FPS Telemetry**: Animated Truecolor ANSI & ASCII renderer with automatic session discovery.
- **Dual Visual Modes**:
  - `balanced` (default): Compact diamond core with polarized light rings and status banner.
  - `focus`: Expanded optical geometry with real-time tool counts, branch counts, and lane diagnostics.
- **Strict Zero-Leakage Privacy**: Guarantees zero leakage. No prompts, code, commands, paths, or tokens are ever logged or displayed. Tool calls are strictly classified into five safe categories (`inspect`, `change`, `execute`, `service`, `other`).
- **Zero External Dependencies**: Implemented entirely using Python 3 standard library. No `pip` dependencies required.

---

## CLI Commands & Modes

### Launching Antigravity

Pass any standard `agy` arguments directly through the companion launcher:

```bash
# Continue previous conversation with Prism
agy --cyclops-prism -c

# Specify model and effort level
agy --cyclops-prism --model gemini-2.5-pro --effort high
```

### Standalone Companion Modes

You can also run `prism` independently from any terminal:

```bash
prism              # Live 20 FPS animated companion (auto-attaches to active session)
prism focus        # Expanded optical geometry with tool lanes and branch meters
prism tmux         # Dock Prism into a tmux split pane or statusbar
prism once         # Single-frame snapshot (ideal for prompts and status lines)
prism plain        # Pure ASCII mode (for terminals without Unicode support)
prism demo         # Continuous animated tour across all operational states
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
