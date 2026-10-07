---
description: Copy text, code, or the last assistant response to system clipboard
argument-hint: [last|code|<text>]
---

# /copy

Copy content directly to the system clipboard using the system clipboard utility (`xclip` or `wl-copy`).

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. If arguments are provided (e.g. specific text, snippet, or selector):
   - Pipe the content directly into the system clipboard:
     ```bash
     printf "%s" "$ARGUMENTS" | (xclip -selection clipboard 2>/dev/null || wl-copy 2>/dev/null)
     ```
2. If argument is `code` or no arguments are provided:
   - Extract the code or latest assistant message from the conversation transcript and copy it to the system clipboard.
3. Inform the user concisely that the content has been copied to their system clipboard.
