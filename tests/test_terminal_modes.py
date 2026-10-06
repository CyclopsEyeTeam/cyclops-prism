"""test_terminal_modes.py - Unit tests for terminal rendering compositions and flags."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import terminal


class TestTerminalModes(unittest.TestCase):
    def test_render_balanced_unicode(self):
        state = {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "hover": "Prism · ready"}
        frame = terminal.render_prism_frame(state, 80, 24, t=0.0, mode="balanced", unicode_mode=True, use_color=False)
        self.assertIn("⟐", frame)
        self.assertIn("⟨", frame)
        self.assertIn("Prism · ready", frame)

    def test_render_focus_telemetry(self):
        state = {"mode": "refracting", "ended": False, "offer": None, "activeCalls": 2, "activeBranches": 1, "lanes": [{"kind": "inspect"}, {"kind": "change"}], "hover": "Prism · refracting"}
        frame = terminal.render_prism_frame(state, 100, 30, t=1.0, mode="focus", unicode_mode=True, use_color=False)
        self.assertIn("Calls: 2", frame)
        self.assertIn("Branches: 1", frame)
        self.assertIn("Comp: focus", frame)
        self.assertIn("[inspect]", frame)
        self.assertIn("[change]", frame)

    def test_render_plain_ascii(self):
        state = {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "hover": "Prism · ready"}
        frame = terminal.render_prism_frame(state, 80, 24, t=0.0, mode="balanced", unicode_mode=False, use_color=False)
        self.assertNotIn("⟐", frame)
        self.assertNotIn("⟨", frame)
        self.assertIn("< o >", frame)
        # Ensure only ASCII characters
        self.assertTrue(all(ord(c) < 128 for c in frame), "Plain mode must not contain non-ASCII chars")

    def test_color_stripping(self):
        text_with_ansi = "\033[38;2;0;242;254mHello\033[0m"
        stripped = terminal._strip_colors(text_with_ansi)
        self.assertEqual(stripped, "Hello")

    def test_cli_once_execution(self):
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--no-color", "--plain"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Prism - ready", proc.stdout)

    def test_cli_demo_state_approval(self):
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--demo-state", "approval", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("awaiting consent", proc.stdout)

    def test_cli_demo_state_crystallize(self):
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--demo-state", "crystallize", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("crystallized", proc.stdout)

    def test_cli_subcommands(self):
        # Test 'once plain' positional sugar
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "once", "plain", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Prism - ready", proc.stdout)

        # Test 'focus once' positional sugar
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "focus", "once", "plain", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Comp: focus", proc.stdout)

    def test_terminal_resizing(self):
        state = {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "hover": "Prism · ready"}
        for w, h in [(40, 15), (80, 24), (120, 40)]:
            frame = terminal.render_prism_frame(state, w, h, t=0.0)
            lines = frame.split("\n")
            self.assertEqual(len(lines), h)
            for line in lines:
                self.assertEqual(len(terminal._strip_colors(line)), w)

    def test_top_compact_bounds(self):
        state = {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "hover": "Prism · ready"}
        for h in [10, 12, 14, 16]:
            frame = terminal.render_prism_frame(state, 100, h, t=0.0)
            lines = frame.split("\n")
            self.assertEqual(len(lines), h)
            stripped = terminal._strip_colors(frame)
            # Ensure status line is intact
            self.assertIn("Prism · ready", stripped)
            # Ensure Level 1 core is used for compact heights
            self.assertIn("⟨ ⟐ ⟩", stripped)

    def test_tmux_subcommands(self):
        # Outside tmux, should print notice with top or side instructions without crashing
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "tmux", "top"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Notice: Not currently inside a tmux session", proc.stdout)


if __name__ == "__main__":
    unittest.main()
