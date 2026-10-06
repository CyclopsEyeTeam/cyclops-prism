---
description: Display current Prism terminal presence status and telemetry
argument-hint: [focus|tmux|status]
---

# /prism

Display Prism's live working presence and crystalline state.

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. If arguments include `focus`: Run `prism focus --once --plain` and present the expanded telemetry frame.
2. If arguments include `tmux`: Run `prism tmux` to split a side companion pane inside tmux.
3. If arguments include `status`: Run `prism tmux status` to bind Prism to the tmux status-right bar.
4. If no arguments or default: Run `prism once --plain` and display the current presence glyph, faceted core, and state banner.
