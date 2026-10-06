# Cyclops Prism: Antigravity Terminal Presence Plugin

**Cyclops Prism** is an Antigravity (`agy`) terminal presence plugin that reflects real-time model lifecycle events as a living, crystalline companion.

It visualizes active model thinking and tool execution through a faceted polyhedral core held in counter-rotating polarized light rings, with dynamic refraction rays for active tool operations and orbital nodes for concurrent subagent branches.

---

## Features

- **Antigravity Terminal Plugin**: First-class Antigravity plugin with native lifecycle hooks (`PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse`, `Stop`).
- **Slash Commands in `agy`**: Type `/prism`, `/focus`, or `/tmux` directly inside your Antigravity chat.
- **Built-in Tmux Integration**: Split a companion pane side-by-side with one command (`prism tmux`) or bind to your tmux status line (`prism tmux status`).
- **Living 20 FPS Companion**: Real-time animated ANSI Truecolor & ASCII renderer with auto-feed discovery.
- **Dual Visual Compositions**:
  - `balanced` (default): Compact diamond core with dual polarized rings and status banner.
  - `focus`: Expanded optical geometry displaying real-time tool counts, branch counts, and active lanes.
- **Strict Zero-Leakage Privacy**: Emits no code, prompts, paths, or secrets. Tool actions are mapped strictly to five finite, safe semantic categories (`inspect`, `change`, `execute`, `service`, `other`).
- **Zero External Dependencies**: Implemented entirely with the Python 3.8+ standard library. Requires no `pip` dependencies.

---

## Launching Antigravity with Prism

Launch `agy` directly alongside Prism as a living sidecar companion:

```bash
# Option 1: Native agy flag
agy --cyclops-prism

# Option 2: Dedicated command
agy-prism
```

This automatically opens Antigravity in your main terminal pane with Prism animated at 20 FPS in a right-hand companion pane (35 cols wide), with focus immediately on your `agy` prompt. When you exit `agy`, the companion pane closes cleanly.

---

## One-Step Installation

From this directory, run:

```bash
./install.sh
```

This will automatically:
1. Link `prism` and `agy-prism` into `~/.local/bin/`.
2. Configure the `agy --cyclops-prism` helper in `~/.bashrc`.
3. Register the plugin into Antigravity via `agy plugin install .`.

To uninstall at any time:
```bash
./install.sh --uninstall
```

---

## Using Inside Antigravity (`agy`)

When working inside an Antigravity (`agy`) session, you can use these slash commands:

| Command | Action |
| :--- | :--- |
| **`/prism`** | Renders Prism's current state and crystalline ASCII diamond in the conversation. |
| **`/focus`** (or `/prism focus`) | Renders the expanded optical telemetry frame with active tool calls and lanes. |
| **`/tmux`** (or `/prism tmux`) | Splits your tmux window and opens Prism in a side companion pane. |

---

## Tmux Integration

Prism includes built-in tmux commands:

### 1. Open Companion in Side Pane
```bash
# Inside tmux: automatically splits pane to the right (35 cols wide)
prism tmux
```

If not currently in tmux, `prism tmux` gives the exact one-liner to launch tmux with Prism side-by-side:
```bash
tmux new-session \; split-window -h -l 35 'prism' \; select-pane -L
```

### 2. Bind to Tmux Status Bar
```bash
prism tmux status
```
This automatically configures `status-right` in tmux to display Prism's live state glyph and message in real time.

---

## CLI Shortcuts & Modes

You can run `prism` from any terminal:

```bash
prism              # Live 20 FPS animated companion
prism focus        # Live companion in expanded telemetry focus mode
prism once         # Single-frame snapshot (ideal for prompts and scripts)
prism plain        # Pure ASCII fallback mode (no Unicode glyphs)
prism demo         # Continuous cycling tour across all operational states
```

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
