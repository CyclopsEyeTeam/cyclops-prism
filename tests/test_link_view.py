"""test_link_view.py - Prism shows Spark and Keeper in their own looks, at their seats, only when linked."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import link  # noqa: E402
import link_view  # noqa: E402
import terminal  # noqa: E402


def _strip(frame):
    return terminal._strip_colors(frame).split("\n")


class LinkedRoom:
    """A private Link directory with real V1 records, as Spark and Keeper would publish them."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="prism-link-view-")
        self.env = dict(os.environ, CYCLOPS_LINK_DIR=self.tmp + "/link", PRISM_LINK="1",
                        XDG_CONFIG_HOME=self.tmp + "/config", XDG_STATE_HOME=self.tmp + "/state")
        self.dir = link.prepare_dir(Path(self.env["CYCLOPS_LINK_DIR"]), create=True)
        self.salt = link.load_salt(self.dir, create=True)
        self.room = link.room_for(self.salt, os.path.realpath(os.getcwd()))

    def put(self, presence, host, session, state, reaching=(), tools=0, branches=0, ended=False, room=None, at=None):
        record = {"v": 1, "presence": presence, "host": host,
                  "instance": link.derive(self.salt, "instance", (host + "\n" + session).encode()),
                  "room": room or self.room, "state": state, "tools": tools, "branches": branches,
                  "reaching": list(reaching), "updated_at": time.time() if at is None else at, "ended": ended}
        self.assert_ok(link.write_record(self.dir, record))
        return record

    @staticmethod
    def assert_ok(ok):
        assert ok


class MarkSheets(unittest.TestCase):
    def test_vendored_sheets_are_the_peers_own_and_valid(self):
        for presence in ("spark", "keeper", "prism"):
            sheet = link_view.load_sheet(presence)
            self.assertIsNotNone(sheet, presence)
            self.assertIn("idle", sheet["frames"])
            raw = json.loads((ROOT / "link-mark" / f"{presence}.json").read_text(encoding="utf-8"))
            self.assertIn("own", raw["note"].lower())
        self.assertTrue((ROOT / "link-mark" / "SOURCE.md").is_file())

    def test_every_link_state_has_a_frame_from_the_peer_herself(self):
        for presence in ("spark", "keeper"):
            sheet = link_view.load_sheet(presence)
            for state in link.STATES:
                self.assertIn(link_view.frame_for(sheet, state), sheet["frames"])

    def test_a_malformed_or_linked_sheet_is_refused_and_no_mark_is_invented(self):
        d = Path(tempfile.mkdtemp())
        (d / "spark.json").write_text('{"v": 1, "presence": "keeper"}')
        self.assertIsNone(link_view.load_sheet("spark", d))
        (d / "real.json").write_text((ROOT / "link-mark" / "spark.json").read_text())
        os.symlink(d / "real.json", d / "keeper.json")
        self.assertIsNone(link_view.load_sheet("keeper", d))


class PrismSeesThem(unittest.TestCase):
    def render(self, room, width=35, height=40, **kw):
        watch = link_view.Watch(room.env)
        view = watch.view(None)
        state = terminal.get_demo_state(0, forced_state="attending")
        frame = terminal.render_prism_frame(state, width, height, t=1.0, link_state=view, link_sheets=watch.sheets, **kw)
        return view, frame

    def test_off_by_default_nothing_is_read_or_drawn(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "s", "tool")
        env = dict(room.env)
        env.pop("PRISM_LINK")
        self.assertIsNone(link_view.Watch(env).view(None))

    def test_spark_lower_left_keeper_lower_right_in_their_own_looks(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "s", "tool", tools=1)
        room.put("keeper", "codex", "k", "waiting")
        view, frame = self.render(room)
        self.assertEqual([p["presence"] for p in view["peers"]], ["keeper", "spark"])
        self.assertEqual({p["presence"]: p["bearing"] for p in view["peers"]}, {"spark": 240, "keeper": 300})
        lines = _strip(frame)
        label_row = next(i for i, l in enumerate(lines) if "spark · tool" in l)
        keeper_row = next(i for i, l in enumerate(lines) if "keeper · waiting" in l)
        self.assertLess(lines[label_row].index("spark"), 17)
        self.assertGreater(lines[keeper_row].index("keeper · waiting"), 17)
        self.assertGreater(min(label_row, keeper_row), 30)   # below Prism's rings, above her banner
        # Spark's own half-block cells and Keeper's own woven braille, with their own colours
        body = "\n".join(lines[label_row + 1:])
        self.assertTrue(any(ch in body for ch in "▀▄"))
        self.assertTrue(any(0x2800 < ord(ch) <= 0x28FF for ch in body))
        spark = link_view.load_sheet("spark")
        fg = next(c[1] for row in spark["frames"]["tool"] for c in row if c[1])
        self.assertIn("38;2;%d;%d;%d" % tuple(fg), frame)

    def test_threads_exist_only_while_a_record_says_it_is_reaching(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "s", "tool", reaching=["prism"])
        room.put("keeper", "codex", "k", "working")
        view, frame = self.render(room)
        self.assertEqual(view["threads"], [{"from": "spark", "to": "prism"}])
        self.assertIn("·", "\n".join(l for l in _strip(frame) if "spark" not in l))
        room.put("spark", "claude-code", "s", "working")
        view, quiet = self.render(room)
        self.assertEqual(view["threads"], [])

    def test_absent_peers_are_not_drawn_stale_ended_or_another_room(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "a", "tool", at=time.time() - 30)
        room.put("spark", "claude-code", "b", "tool", ended=True)
        room.put("keeper", "codex", "c", "tool", room="0123456789abcdef")
        view, frame = self.render(room)
        self.assertEqual(view["peers"], [])
        self.assertNotIn("spark", "\n".join(_strip(frame)))

    def test_two_keepers_are_one_mark_counted_never_merged_away(self):
        room = LinkedRoom()
        room.put("keeper", "codex", "k1", "tool")
        room.put("keeper", "codex", "k2", "idle")
        view, frame = self.render(room)
        self.assertEqual(len(view["peers"]), 2)
        self.assertIn("×2", "\n".join(_strip(frame)))

    def test_top_layout_and_plain_mode_still_fit(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "s", "thinking", reaching=["keeper"])
        room.put("keeper", "codex", "k", "tool")
        view, frame = self.render(room, width=120, height=14)
        lines = _strip(frame)
        self.assertEqual(len(lines), 14)
        self.assertTrue(all(len(l) == 120 for l in lines))
        self.assertIn("Prism · attending", lines[12])
        view, plain = self.render(room, width=35, height=40, unicode_mode=False, use_color=False)
        self.assertTrue(all(ord(c) < 128 for c in plain))

    def test_the_drawing_holds_nothing_but_presence_names_and_states(self):
        room = LinkedRoom()
        room.put("spark", "claude-code", "secret-session-id", "tool", reaching=["keeper"], tools=3, branches=2)
        room.put("keeper", "codex", "/home/someone/project", "waiting")
        view, frame = self.render(room, width=90, height=30, mode="focus")
        text = "\n".join(_strip(frame))
        for leak in ("secret-session-id", "/home/someone", room.room, view["peers"][0]["instance"], "claude-code", "codex"):
            self.assertNotIn(leak, text)
        self.assertIn("Link: on · Keeper, Spark", text)

    def test_another_prism_peer_does_not_crash(self):
        room = LinkedRoom()
        # Put another prism instance in the room (e.g. from previous run or separate terminal)
        room.put("prism", "antigravity", "other-prism-session", "working")
        room.put("spark", "claude-code", "s", "tool")
        view, frame = self.render(room)
        # Verify another prism does not crash rendering and Spark is still drawn
        self.assertIsNotNone(frame)
        self.assertIn("spark · tool", "\n".join(_strip(frame)))
        self.assertEqual(link_view.status(view), "Link: on · Spark")


class Commands(unittest.TestCase):
    def test_prism_link_on_off_status_is_her_own_switch(self):
        room = LinkedRoom()
        env = dict(room.env)
        env.pop("PRISM_LINK")
        run = lambda *a: subprocess.run([sys.executable, str(ROOT / "scripts" / "terminal.py"), "link", *a],
                                        capture_output=True, text=True, env=env, timeout=10)
        self.assertIn("Prism Link: off", run("status").stdout)
        self.assertIn("Prism Link on", run("on").stdout)
        self.assertEqual((Path(env["XDG_CONFIG_HOME"]) / "gemini-prism" / "link").read_text().strip(), "on")
        room.put("keeper", "codex", "k", "tool")
        out = run("status").stdout
        self.assertIn("Prism Link: on", out)
        self.assertIn("keeper tool", out)
        self.assertIn("Prism Link off", run("off").stdout)
        env["CYCLOPS_LINK"] = "1"
        self.assertIn("Prism Link: off", run("status").stdout)


class LiveFeedOffer(unittest.TestCase):
    def test_a_resolved_turn_holds_its_reply_out_until_a_new_turn(self):
        d = Path(tempfile.mkdtemp())
        events = [{"seq": 1, "t": 1, "type": "session.wake"}, {"seq": 2, "t": 2, "type": "turn.attend"},
                  {"seq": 3, "t": 3, "type": "turn.resolve"}]
        (d / "live.json").write_text(json.dumps({"events": events}))
        state = terminal.load_feed_state(d)
        self.assertEqual((state["mode"], state["offer"]), ("resolved", "crystallize"))
        self.assertIn("crystallized", state["hover"])
        events.append({"seq": 4, "t": 4, "type": "turn.attend"})
        (d / "live.json").write_text(json.dumps({"events": events}))
        state = terminal.load_feed_state(d)
        self.assertEqual((state["mode"], state["offer"]), ("attending", None))


if __name__ == "__main__":
    unittest.main()
