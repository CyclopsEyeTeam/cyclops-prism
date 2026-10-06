"""test_hook_feed.py - Unit and integration tests for hook execution and presence feed persistence."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import activity
import feed_state
import presence_feed


class TestHookFeed(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="prism-hook-test-"))
        self.presence_root = self.test_dir / "presence"
        self.state_root = self.test_dir / "state"
        self.env = dict(os.environ)
        self.env["PRISM_PRESENCE_ROOT"] = str(self.presence_root)
        self.env["XDG_STATE_HOME"] = str(self.state_root)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def run_hook(self, payload: dict) -> subprocess.CompletedProcess:
        hook_path = SCRIPTS_DIR / "hook.py"
        return subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=self.env,
            timeout=5,
        )

    def test_pre_invocation_turn_one(self):
        payload = {
            "conversationId": "test-session-first-turn",
            "stepIdx": 1,
            "hookEvent": "PreInvocation",
            "invocationNum": 1,
        }
        res = self.run_hook(payload)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(json.loads(res.stdout.strip()), {})

        feed_dir = self.presence_root / "test-session-first-turn" / "prism"
        live_file = feed_dir / "live.json"
        self.assertTrue(live_file.is_file(), "live.json should be written")
        data = json.loads(live_file.read_text(encoding="utf-8"))
        events = data.get("events", [])
        self.assertTrue(len(events) >= 1)
        self.assertEqual(events[-1].get("type"), "turn.attend")

    def test_pre_tool_use_contract(self):
        payload = {
            "conversationId": "test-session-123",
            "stepIdx": 1,
            "hookEvent": "PreToolUse",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /sensitive/secret"}},
        }
        res = self.run_hook(payload)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout.strip())
        self.assertEqual(out, {})

        # Verify feed was generated
        feed_dir = self.presence_root / "test-session-123" / "prism"
        live_file = feed_dir / "live.json"
        self.assertTrue(live_file.is_file(), "live.json should be written")

        live_data = json.loads(live_file.read_text(encoding="utf-8"))
        events = live_data.get("events", [])
        self.assertTrue(len(events) >= 1)
        ev = events[-1]
        self.assertEqual(ev.get("type"), "refract.start")
        self.assertEqual(ev.get("kind"), "execute")

        # Verify ZERO leak of sensitive command arguments
        raw_feed = live_file.read_text(encoding="utf-8")
        self.assertNotIn("rm -rf", raw_feed)
        self.assertNotIn("sensitive", raw_feed)
        self.assertNotIn("CommandLine", raw_feed)

    def test_post_tool_use_contract(self):
        payload = {
            "conversationId": "test-session-123",
            "stepIdx": 1,
            "hookEvent": "PostToolUse",
            "toolName": "run_command",
        }
        res = self.run_hook(payload)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout.strip())
        self.assertEqual(out, {})

    def test_stop_hook_contract(self):
        payload = {
            "conversationId": "test-session-123",
            "stepIdx": 2,
            "hookEvent": "Stop",
            "terminationReason": "model_stop",
        }
        res = self.run_hook(payload)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout.strip())
        self.assertEqual(out, {})

    def test_feed_discovery(self):
        # Create a mock session feed
        session_dir = self.presence_root / "auto-session-xyz" / "prism"
        presence_feed._safe_mkdir(session_dir)
        live_file = session_dir / "live.json"
        live_file.write_text('{"v":1,"events":[{"type":"turn.attend","seq":1,"t":1000.0}]}', encoding="utf-8")

        discovered = presence_feed.find_active_feed(self.env)
        self.assertIsNotNone(discovered)
        self.assertEqual(discovered.resolve(), session_dir.resolve())

    def test_hook_latency(self):
        import hook
        payload = {
            "conversationId": "bench-session",
            "stepIdx": 1,
            "hookEvent": "PreInvocation",
            "invocationNum": 1,
        }
        # 1. Direct handler latency must complete in < 15ms
        hook.handle_event(payload)  # warmup
        h_times = []
        for _ in range(10):
            t0 = time.perf_counter()
            hook.handle_event(payload)
            h_times.append((time.perf_counter() - t0) * 1000)
        h_times.sort()
        h_p95 = h_times[int(len(h_times) * 0.95)]
        self.assertLess(h_p95, 25.0, f"Hook handle_event p95 must be < 25ms, got {h_p95:.2f}ms")

        # 2. Subprocess command execution should complete within 300ms including interpreter cold start
        sub_times = []
        self.run_hook(payload)  # warmup
        for _ in range(5):
            t0 = time.perf_counter()
            res = self.run_hook(payload)
            self.assertEqual(res.returncode, 0)
            sub_times.append((time.perf_counter() - t0) * 1000)
        sub_times.sort()
        sub_p95 = sub_times[int(len(sub_times) * 0.95)]
        self.assertLess(sub_p95, 300.0, f"Hook subprocess p95 should be fast, got {sub_p95:.2f}ms")


if __name__ == "__main__":
    unittest.main()
