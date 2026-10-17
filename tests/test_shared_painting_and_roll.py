#!/usr/bin/env python3
"""Tests for shared Spark & Prism painting format, clickable tools, story, 4-way convert, and roll."""

from pathlib import Path
import sys
import tempfile
import time
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import painter
import roll
import terminal


class TestSharedPaintingAndRoll(unittest.TestCase):
    def test_colour_depth_tonemap(self):
        # <= 1.0 is untouched
        self.assertEqual(painter.tonemap_light(0.8, 0.4, 0.2), (0.8, 0.4, 0.2))
        self.assertEqual(painter.tonemap_light(1.0, 0.5, 0.0), (1.0, 0.5, 0.0))

        # > 1.0 keeps hue at full strength and spills excess toward white, fully white at 2.5x
        r, g, b = painter.tonemap_light(1.75, 0.875, 0.0)
        # At m=1.75, spill = (1.75 - 1.0)/1.5 = 0.5; normalized hue is (1.0, 0.5, 0.0)
        self.assertAlmostEqual(r, 1.0, places=4)
        self.assertAlmostEqual(g, 0.75, places=4)
        self.assertAlmostEqual(b, 0.5, places=4)

        # At 2.5x full, reaches pure white (1.0, 1.0, 1.0)
        self.assertEqual(painter.tonemap_light(2.5, 1.2, 0.3), (1.0, 1.0, 1.0))
        self.assertEqual(painter.tonemap_light(3.2, 0.1, 0.1), (1.0, 1.0, 1.0))

    def test_clamping_and_validation(self):
        raw = {
            "title": "Shared Lattice Test",
            "by": "spark",
            "marks": [
                {"k": "unknown_kind", "x": 0.5, "y": 0.5, "r": 0.1, "c": [1, 1, 1], "a": 1},
                {"k": "dot", "x": 1.5, "y": -0.4, "r": 0.99, "c": [1.2, -0.1, 0.5], "a": 1.5},
                {"k": "line", "pts": [[0.1, 0.2], [0.8, 0.9]], "w": 0.5, "c": [0.2, 0.4, 0.8], "a": 0.9},
                {"k": "spray", "x": 0.5, "y": 0.5, "r": 0.001, "n": 500, "s": 0.01, "c": [1, 1, 1], "a": 0.5},
            ],
        }
        p = painter.parse_painting(raw)
        self.assertIsNotNone(p)
        self.assertEqual(p["by"], "spark")
        self.assertEqual(p["shape"], "wide")  # default when missing
        self.assertEqual(len(p["marks"]), 3)  # unknown_kind skipped
        # Dot r clamped to 0.7 max
        self.assertEqual(p["marks"][0]["r"], 0.7)
        self.assertEqual(p["marks"][0]["x"], 1.0)
        self.assertEqual(p["marks"][0]["y"], 0.0)
        # Line w clamped to 0.12 max
        self.assertEqual(p["marks"][1]["w"], 0.12)
        # Spray r clamped to 0.004 min, n clamped to 200 max
        self.assertEqual(p["marks"][2]["r"], 0.004)
        self.assertEqual(p["marks"][2]["n"], 200)

    def test_opening_painting_seeded_only_by_hour_month_word(self):
        p = painter.generate_opening_painting(now=1792203439.0, seed_word="lantern")
        self.assertTrue(p.get("opening"))
        self.assertEqual(p["by"], "prism")
        self.assertEqual(p["shape"], "wide")
        self.assertIn("Lantern", p["title"])
        self.assertIn("October", p["title"])

    def test_bidirectional_folder_sharing_and_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prism_dir = root / "prism-paintings"
            spark_dir = root / "spark-paintings"
            prism_dir.mkdir()
            spark_dir.mkdir()

            t_base = time.time()
            p1 = painter.generate_opening_painting(now=t_base + 1.0, seed_word="crystal")
            painter.save_painting_json(p1, gallery_dir=prism_dir)

            # Simulate Spark writing a painting into spark-paintings/01-spark-dawn.json
            spark_json = spark_dir / "01-spark-dawn.json"
            spark_json.write_text(
                '{"title":"A door left ajar at three","marks":[{"k":"dot","x":0.5,"y":0.5,"r":0.1,"c":[1,0.7,0.5],"a":0.9}],"at":'
                + str(t_base + 5.0)
                + ',"by":"spark"}',
                encoding="utf-8",
            )
            # Corrupt file should be skipped gracefully
            (spark_dir / "02-broken.json").write_text("{not valid json", encoding="utf-8")

            loaded = painter.load_session_paintings(root, session_start=t_base)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["by"], "prism")
            self.assertTrue(loaded[0].get("opening"))
            self.assertEqual(loaded[1]["by"], "spark")
            self.assertEqual(loaded[1]["title"], "A door left ajar at three")

    def test_clickable_tools_progress_row_and_story_controls(self):
        p_spark = painter.parse_painting({
            "title": "Spark's Coral Horizon",
            "by": "spark",
            "opening": True,
            "at": time.time(),
            "marks": [{"k": "dot", "x": 0.5, "y": 0.5, "r": 0.1, "c": [0.95, 0.58, 0.4], "a": 0.9}],
        })
        state = {"mode": "idle", "ended": False, "offer": None, "activeCalls": 0, "activeBranches": 0, "lanes": [], "hover": "Prism · ready"}
        expr = {"v": 1, "painting": p_spark, "paintStats": {"paintings": 2, "tokens": 4200}}
        ui = {
            "story": {
                "active": True,
                "index": 1,
                "total": 2,
                "painting": p_spark,
                "paused": False,
                "at_end": False,
                "reveal": 1.0,
            },
            "job": {
                "active": True,
                "label": "laying down “Coral Horizon…” · 1/2",
                "fraction": 0.44,
            },
        }
        hitboxes = []
        frame = terminal.render_prism_frame(
            state, 80, 32, t=1.0, expression=expr, ui_state=ui, hitboxes=hitboxes
        )
        plain = terminal._strip_colors(frame)
        self.assertIn("▶ story", plain)
        self.assertIn("⇪ convert", plain)
        self.assertIn("◎ roll", plain)
        self.assertIn("44%", plain)
        self.assertIn("story · 2 of 2 ·", plain)
        self.assertIn("· Spark's", plain)
        self.assertIn("· her opening", plain)
        self.assertIn("⏸ pause", plain)
        self.assertIn("‹ back", plain)
        self.assertIn("next ›", plain)
        self.assertIn("■ end", plain)
        actions = {hb["action"] for hb in hitboxes}
        self.assertTrue({"tool_story", "tool_convert", "tool_roll", "story_pause", "story_back", "story_next", "story_end"}.issubset(actions))

    def test_four_way_convert_svg_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "prism-paintings"
            p_spark = painter.parse_painting({
                "title": "Shared Twilight",
                "by": "spark",
                "at": time.time(),
                "marks": [
                    {"k": "fill", "pts": [[0, 0], [1, 0], [1, 1], [0, 1]], "c": [0.1, 0.08, 0.15], "c2": [0.2, 0.1, 0.25], "grad": 0.25, "a": 0.95},
                    {"k": "glow", "x": 0.5, "y": 0.5, "r": 0.3, "c": [0.95, 0.6, 0.4], "a": 0.7},
                    {"k": "dot", "x": 0.5, "y": 0.5, "r": 0.04, "c": [1.0, 0.95, 0.9], "a": 1.0},
                ],
            })
            for way in ("truest", "faithful", "refined", "interpretive"):
                res = painter.convert_painting(p_spark, gallery_dir=out_dir, way=way)
                svg_text = Path(res["svg"]).read_text(encoding="utf-8")
                self.assertTrue(Path(res["png"]).is_file())
                self.assertIn(f"Spark · ", svg_text)
                self.assertIn(f"· {way}", svg_text)
                if way == "truest":
                    self.assertIn('id="layer0"', svg_text)
                    self.assertIn('id="layer3"', svg_text)
                    self.assertIn('id="shadow"', svg_text)
                    self.assertIn('id="bloom"', svg_text)

    def test_roll_music_and_mp4_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "prism-paintings"
            p1 = painter.generate_opening_painting(seed_word="aurora")
            p2 = painter.parse_painting({
                "title": "Spark's Ember",
                "by": "spark",
                "at": time.time() + 2.0,
                "marks": [
                    {"k": "glow", "x": 0.5, "y": 0.5, "r": 0.3, "c": [0.95, 0.55, 0.35], "a": 0.8},
                    {"k": "line", "pts": [[0.2, 0.6], [0.8, 0.4]], "w": 0.02, "c": [1.0, 0.8, 0.5], "a": 0.9},
                    {"k": "dot", "x": 0.5, "y": 0.5, "r": 0.04, "c": [1.0, 0.95, 0.9], "a": 1.0},
                ],
            })
            music = roll.analyze_session_music([p1, p2])
            self.assertIn(music["mode"], ("major", "dorian", "aeolian"))
            self.assertEqual(len(music["holds_beats"]), 2)
            self.assertGreaterEqual(music["holds_beats"][-1], 8)  # Last painting has +4 extra beats

            res = roll.build_session_roll([p1, p2], out_dir, mode="720p", project_name="gemini-prism")
            mp4_path = Path(res["path"])
            self.assertTrue(mp4_path.is_file())
            self.assertGreater(mp4_path.stat().st_size, 1000)

    def test_side_chat_panel_and_reply(self):
        p = painter.choose_curated_painting(0)
        reply = terminal.generate_painting_chat_reply("I love the warm colors and glow!", p)
        self.assertIn("supernova", reply.lower())

        state = {"mode": "resolved", "ended": False, "offer": "crystallize", "activeCalls": 0, "activeBranches": 0, "lanes": [], "hover": "Prism · crystallized · 1 ready"}
        expr = {
            "v": 1,
            "painting": p,
            "paintStats": {"paintings": 1, "tokens": 2100},
            "chat": [
                {"role": "user", "text": "tell me about the horizon"},
                {"role": "prism", "text": reply},
            ],
        }
        ui = {"chat_active": True, "chat_input": "what about Spark?"}
        hitboxes = []
        frame = terminal.render_prism_frame(state, 56, 38, t=1.0, expression=expr, ui_state=ui, hitboxes=hitboxes)
        plain = terminal._strip_colors(frame)
        self.assertIn("💬 chat", plain)
        self.assertIn("side chat", plain)
        self.assertIn("what about Spark?", plain)
        actions = {hb["action"] for hb in hitboxes}
        self.assertIn("tool_chat", actions)
        self.assertIn("chat_focus", actions)

        # Ensure every row (including rows with 2-cell wide glyphs like 💬) equals exact terminal column width
        for row_idx, raw_line in enumerate(frame.split("\n")):
            stripped_row = terminal._strip_colors(raw_line)
            cell_w = sum(terminal._char_cells(ch) for ch in stripped_row)
            self.assertEqual(cell_w, 56, f"Row {row_idx} overflowed/underflowed terminal width: {cell_w} != 56")


if __name__ == "__main__":
    unittest.main()
