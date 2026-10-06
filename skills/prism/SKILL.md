---
name: prism
description: >-
  Inspect or launch Prism terminal presence. Supports /prism, /prism focus, and /prism tmux.
---

# /prism

Antigravity slash command and companion interface for Prism terminal presence.

## Instructions

When the user invokes `/prism` or asks about Prism presence:
- **Default `/prism`**: Run `prism once --plain` (or `${PLUGIN_ROOT}/gemini-prism once --plain`) using `run_command` and present the resulting ASCII presence frame and state line to the user.
- **`/prism focus`**: Run `prism focus --once --plain` using `run_command` to render the expanded telemetry view showing active call lanes and subagent satellites.
- **`/prism tmux`**: Run `prism tmux` using `run_command` to open Prism in a dedicated tmux companion pane.
