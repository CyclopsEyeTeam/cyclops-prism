"""test_link.py - Comprehensive test suite for Cyclops Link v1 implementation."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest

import link


class TestCyclopsLink(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test-cyclops-link-"))
        self.env = {
            "CYCLOPS_LINK": "1",
            "CYCLOPS_LINK_DIR": str(self.test_dir),
            "HOME": str(self.test_dir),
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_link_off_by_default(self):
        # Without flag or env var, link is off
        self.assertFalse(link.is_link_enabled(environ={}))
        self.assertTrue(link.is_link_enabled(environ={}, flag=True))
        self.assertTrue(link.is_link_enabled(environ={"CYCLOPS_LINK": "1"}))
        self.assertTrue(link.is_link_enabled(environ={"PRISM_LINK": "1"}))

    def test_instance_and_room_hashes(self):
        inst = link.compute_instance("test-session-123")
        self.assertEqual(len(inst), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in inst))

        room = link.compute_room("/tmp/my-project")
        self.assertEqual(len(room), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in room))

    def test_state_mapping(self):
        self.assertEqual(link.map_to_shared_state("ready"), "idle")
        self.assertEqual(link.map_to_shared_state("idle"), "idle")
        self.assertEqual(link.map_to_shared_state("attending"), "thinking")
        self.assertEqual(link.map_to_shared_state("refracting"), "tool")
        self.assertEqual(link.map_to_shared_state("branching"), "working")
        self.assertEqual(link.map_to_shared_state("approval"), "waiting")
        self.assertEqual(link.map_to_shared_state("crystallized"), "idle")
        self.assertEqual(link.map_to_shared_state("ended"), "ended")

    def test_write_and_clean_link_file(self):
        session_id = "test-session-abc"
        target_path = link.write_link_file(
            session_id,
            "refracting",
            tools=2,
            branches=1,
            reaching=["spark"],
            ended=False,
            environ=self.env,
            link_enabled=True,
        )
        self.assertIsNotNone(target_path)
        self.assertTrue(target_path.is_file())

        # Check permissions (0600)
        mode = target_path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

        # Check content
        data = json.loads(target_path.read_text(encoding="utf-8"))
        self.assertEqual(data["v"], 1)
        self.assertEqual(data["presence"], "prism")
        self.assertEqual(data["host"], "antigravity")
        self.assertEqual(data["state"], "tool")
        self.assertEqual(data["tools"], 2)
        self.assertEqual(data["branches"], 1)
        self.assertEqual(data["reaching"], ["spark"])
        self.assertEqual(data["ended"], False)
        self.assertIsInstance(data["updated_at"], float)

        # Clean file
        link.clean_link_file(session_id, environ=self.env)
        self.assertFalse(target_path.is_file())

    def test_peer_reading_and_filtering(self):
        my_session = "my-prism-session"
        my_room = link.compute_room()

        # 1. Write mock Spark peer in same room
        spark_file = self.test_dir / "spark-1111222233334444.json"
        spark_file.write_text(
            json.dumps({
                "v": 1,
                "presence": "spark",
                "host": "claude-code",
                "instance": "1111222233334444",
                "room": my_room,
                "state": "thinking",
                "tools": 0,
                "branches": 0,
                "reaching": ["prism"],
                "updated_at": time.time(),
                "ended": False,
            }),
            encoding="utf-8",
        )

        # 2. Write mock Keeper peer in different room
        keeper_file = self.test_dir / "keeper-5555666677778888.json"
        keeper_file.write_text(
            json.dumps({
                "v": 1,
                "presence": "keeper",
                "host": "codex",
                "instance": "5555666677778888",
                "room": "different_room_id",
                "state": "tool",
                "tools": 1,
                "branches": 0,
                "reaching": [],
                "updated_at": time.time(),
                "ended": False,
            }),
            encoding="utf-8",
        )

        # 3. Write stale peer (> 15s)
        stale_file = self.test_dir / "spark-aaaaaaaaaaaaaaaa.json"
        stale_file.write_text(
            json.dumps({
                "v": 1,
                "presence": "spark",
                "host": "claude-code",
                "instance": "aaaaaaaaaaaaaaaa",
                "room": my_room,
                "state": "idle",
                "tools": 0,
                "branches": 0,
                "reaching": [],
                "updated_at": time.time() - 30.0,
                "ended": False,
            }),
            encoding="utf-8",
        )

        reader = link.PeerLinkReader(link_dir=self.test_dir)

        # Room-filtered read: only Spark should match
        peers = reader.read_peers(my_session, current_room=my_room, everywhere=False, link_enabled=True)
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0]["presence"], "spark")
        self.assertEqual(peers[0]["state"], "thinking")
        self.assertEqual(peers[0]["reaching"], ["prism"])

        # Everywhere read: Spark and Keeper should match (stale is filtered out)
        # Advance clock slightly to bypass 1s cache
        time.sleep(1.05)
        all_peers = reader.read_peers(my_session, current_room=my_room, everywhere=True, link_enabled=True)
        self.assertEqual(len(all_peers), 2)
        presences = {p["presence"] for p in all_peers}
        self.assertEqual(presences, {"spark", "keeper"})


if __name__ == "__main__":
    unittest.main()
