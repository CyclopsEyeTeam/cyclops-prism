"""test_terminal_modes.py - Unit tests for terminal rendering compositions and flags."""

import os
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import terminal


# The CLI reads the live feed of whatever session ran last on this machine: tests run in an empty state home
_ISOLATED = dict(os.environ, XDG_STATE_HOME=tempfile.mkdtemp(prefix="prism-test-state-"),
                 XDG_CONFIG_HOME=tempfile.mkdtemp(prefix="prism-test-config-"))
_ISOLATED.pop("PRISM_LINK", None)
_ISOLATED.pop("TMUX", None)
_ISOLATED.pop("TMUX_PANE", None)


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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Prism - ready", proc.stdout)

    def test_cli_demo_state_approval(self):
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--demo-state", "approval", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("awaiting consent", proc.stdout)

    def test_cli_demo_state_crystallize(self):
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--demo-state", "crystallize", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("crystallized", proc.stdout)

    def test_cli_subcommands(self):
        # Test 'once plain' positional sugar
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "once", "plain", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Prism - ready", proc.stdout)

        # Test 'focus once' positional sugar
        cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "focus", "once", "plain", "--no-color"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=_ISOLATED)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Notice: Not currently inside a tmux session", proc.stdout)
        self.assertIn("mouse on", proc.stdout)

    def test_prism_personal_voice_and_facets(self):
        state = {"mode": "resolved", "ended": False, "offer": "crystallize", "activeCalls": 0, "activeBranches": 0, "hover": "Prism · crystallized · 1 ready"}
        frame = terminal.render_prism_frame(state, 80, 24, t=1.5, mode="balanced", unicode_mode=True, use_color=False)
        self.assertIn("⟨ ⟨ ✦ ⟩ ⟩", frame)
        self.assertIn("thought crystallized for you", frame)

    def test_post_tool_use_refraction_impulse(self):
        import json
        import time
        d = Path(tempfile.mkdtemp(prefix="prism-impulse-"))
        now = time.time()
        events = [
            {"seq": 1, "t": now - 5.0, "type": "turn.attend"},
            {"seq": 2, "t": now - 0.5, "type": "refract.resolve", "kind": "inspect", "key": "a" * 64},
        ]
        (d / "live.json").write_text(json.dumps({"events": events}), encoding="utf-8")
        st = terminal.load_feed_state(d, now=now)
        self.assertEqual(st["mode"], "refracting")
        self.assertEqual(st["lanes"], [{"kind": "inspect"}])
        self.assertEqual(st["spectrum"], {"inspect": 1})
        # After impulse window expires (>2.8s), returns to attending while keeping turn spectrum
        st_later = terminal.load_feed_state(d, now=now + 4.0)
        self.assertEqual(st_later["mode"], "attending")
        self.assertEqual(st_later["spectrum"], {"inspect": 1})

    def test_expressive_channel_rendering(self):
        state = {"mode": "attending", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "hover": "Prism · attending"}
        expr = {
            "thought": "dancing across the spectrum ;d <3",
            "mood": "aurora",
            "effect": "starburst",
            "glyph": "✦",
            "art": ["✧  PRISM MUSE  ✧"],
        }
        frame = terminal.render_prism_frame(state, 80, 24, t=1.2, mode="balanced", unicode_mode=True, use_color=True, expression=expr)
        stripped = terminal._strip_colors(frame)
        self.assertIn("dancing across the spectrum ;d <3", stripped)
        self.assertIn("PRISM MUSE", stripped)
        self.assertIn("⟨ ⟨ ✦ ⟩ ⟩", stripped)

        # Plain ASCII safety with expressive channel active
        frame_plain = terminal.render_prism_frame(state, 80, 24, t=1.2, mode="balanced", unicode_mode=False, use_color=False, expression=expr)
        self.assertIn("dancing across the spectrum ;d <3", frame_plain)
        self.assertTrue(all(ord(c) < 128 for c in frame_plain))

    def test_cli_express_and_mcp_server(self):
        import json
        import mcp_server
        env = dict(_ISOLATED, PRISM_EXPRESSION_FILE=str(Path(_ISOLATED["XDG_STATE_HOME"]) / "expr.json"))
        # 1. CLI `prism express`
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "terminal.py"),
            "express",
            "hello from prism channel",
            "--mood",
            "nebula",
            "--effect",
            "meteor",
            "--art",
            "* * *",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hello from prism channel", proc.stdout)

        # Verify `--once` renders the custom expression
        once_cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "--once", "--no-color"]
        once_proc = subprocess.run(once_cmd, capture_output=True, text=True, timeout=5, env=env)
        self.assertEqual(once_proc.returncode, 0)
        self.assertIn("hello from prism channel", once_proc.stdout)

        # 2. MCP JSON-RPC protocol (`initialize`, `tools/list`, `tools/call`)
        init_resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "cyclops-prism-express")

        list_resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {t["name"] for t in list_resp["result"]["tools"]}
        self.assertIn("prism_express", tool_names)
        self.assertIn("prism_clear_expression", tool_names)

        # 3. Clear expression via CLI
        clear_cmd = [sys.executable, str(SCRIPTS_DIR / "terminal.py"), "express", "--clear"]
        clear_proc = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=5, env=env)
        self.assertEqual(clear_proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()

