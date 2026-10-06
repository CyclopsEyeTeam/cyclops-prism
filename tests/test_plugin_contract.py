"""test_plugin_contract.py - Validate Antigravity plugin manifest, hooks, and executable contract."""

import json
import os
from pathlib import Path
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


class TestPluginContract(unittest.TestCase):
    def test_plugin_json(self):
        p_path = PLUGIN_ROOT / "plugin.json"
        self.assertTrue(p_path.is_file(), "plugin.json must exist")
        data = json.loads(p_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "cyclops-prism")
        self.assertEqual(data.get("version"), "1.0.0")
        self.assertIn("hooks", data)
        self.assertIn("interface", data)

    def test_hooks_json(self):
        h_path = PLUGIN_ROOT / "hooks.json"
        self.assertTrue(h_path.is_file(), "hooks.json must exist")
        data = json.loads(h_path.read_text(encoding="utf-8"))
        self.assertTrue("cyclops-prism" in data or "gemini-prism" in data)
        hook_def = data.get("cyclops-prism") or data.get("gemini-prism")
        self.assertIn("PreInvocation", hook_def)
        self.assertIn("PostInvocation", hook_def)
        self.assertIn("PreToolUse", hook_def)
        self.assertIn("PostToolUse", hook_def)
        self.assertIn("Stop", hook_def)

        # Matchers on tool hooks
        self.assertEqual(hook_def["PreToolUse"][0]["matcher"], "*")
        self.assertEqual(hook_def["PostToolUse"][0]["matcher"], "*")

    def test_skill_and_rules(self):
        skill_path = PLUGIN_ROOT / "skills" / "gemini-prism" / "SKILL.md"
        self.assertTrue(skill_path.is_file(), "SKILL.md must exist")
        skill_text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---"), "SKILL.md must have YAML frontmatter")
        self.assertIn("name: gemini-prism", skill_text)

        rules_path = PLUGIN_ROOT / "rules" / "AGENTS.md"
        self.assertTrue(rules_path.is_file(), "AGENTS.md must exist")
        rules_text = rules_path.read_text(encoding="utf-8")
        self.assertIn("Privacy", rules_text)

    def test_executable_permissions(self):
        for script_rel in ["gemini-prism", "bin/prism", "scripts/hook.py", "scripts/terminal.py"]:
            p = PLUGIN_ROOT / script_rel
            self.assertTrue(p.is_file(), f"{script_rel} must exist")
            self.assertTrue(os.access(p, os.X_OK), f"{script_rel} must have execute permissions")


if __name__ == "__main__":
    unittest.main()
