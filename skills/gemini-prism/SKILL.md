---
name: gemini-prism
description: >-
  Inspect, launch, and monitor the Prism Terminal Presence companion.
  Provides real-time crystalline telemetry, state inspection, and live session monitoring.
---

# Prism Terminal Presence

The `gemini-prism` plugin provides a quiet, responsive terminal companion that reflects real model lifecycle activity in real time. It renders a faceted polyhedral core held in counter-rotating polarized light rings, with dynamic refraction rays for active tool calls and satellite nodes for subagent branches.

## Quick CLI Usage

You can launch or query Prism directly from the terminal or shell commands:

```bash
# 1. Live interactive 20 FPS presence
./gemini-prism

# 2. Instant snapshot (ideal for tmux status lines or shell prompts)
./gemini-prism --once

# 3. Expanded telemetry mode (shows active calls, branches, and composition stats)
./gemini-prism --mode focus

# 4. Pure ASCII fallback (disables Unicode glyphs)
./gemini-prism --plain

# 5. Continuous demonstration cycle across all semantic states
./gemini-prism --demo

# 6. Specific demonstration state
./gemini-prism --once --demo-state refracting
./gemini-prism --once --demo-state approval
./gemini-prism --once --demo-state crystallize
```

## Semantic States & Sigil Vocabulary

| State | Glyph | Color | Meaning |
| :--- | :---: | :--- | :--- |
| **Ready / Idle** | `⟐` | Hyper-cyan (`#00F2FE`) | Waiting for user interaction; calm ambient rotation |
| **Attending** | `⟐` | Solar Gold (`#FFB020`) | Ingesting prompt or analyzing context |
| **Refracting** | `❖` | Emerald Teal / Gold / Cyan | Actively executing tool calls (inspect, change, execute, service) |
| **Branching** | `◇` | Electric Violet (`#7928CA`) | Orchestrating concurrent subagent branches |
| **Approval** | `!` | Alert Red (`#FF4D4D`) | Awaiting user consent or review |
| **Crystallized** | `✦` | Warm White (`#FFF6D6`) | Turn completed, response ready |
| **Ended** | `·` | Neutral Gray (`#6B7280`) | Session terminated |

## Tmux & Status Line Integration

### Tmux Split Window
Run Prism continuously in a side pane:
```bash
tmux split-window -h -l 35 'prism'
# or with direct script path:
tmux split-window -h -l 35 './gemini-prism'
```

### Tmux Status Line
Embed the live state glyph in `tmux.conf`:
```tmux
set -g status-right "#(prism --once --plain | grep -o 'Prism.*' | head -n 1)"
```

## Privacy & Safety

Prism operates strictly on a **zero-leakage** boundary:
- No user prompts, instructions, or chat text are ever recorded or displayed.
- No code snippets, file contents, diffs, or commands are exposed.
- Tool operations are categorized strictly into 5 safe semantic kinds: `inspect`, `change`, `execute`, `service`, `other`.
- All session correlation keys use one-way SHA-256 hashes.
