"""Cyclops Link V1 conformance for Prism's own implementation (scripts/link.py).

Driven by the vendored, language-neutral fixtures in tests/fixtures/cyclops-link-v1/
(copied verbatim from Cyclops Link commit 3ba5cab). Nothing here imports another presence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import link  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "cyclops-link-v1"
OTHER_UID = 4242


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def make(path: Path, fs: dict, content: bytes) -> bool:
    kind = fs.get("type", "file")
    if kind == "absent":
        return True
    if kind == "dir":
        path.mkdir()
    elif kind == "symlink":
        target = path.parent.parent / ("target-" + path.name)
        target.write_bytes(content)
        os.chmod(target, 0o600)
        path.symlink_to(target)
        return True
    else:
        path.write_bytes(content)
    os.chmod(path, int(fs.get("mode", "0600"), 8))
    if fs.get("owner") == "other":
        if os.getuid() != 0:
            return False
        os.chown(path, OTHER_UID, OTHER_UID)
    return True


class Derivation(unittest.TestCase):
    def setUp(self):
        self.d = load("derivation.json")
        self.salt = bytes.fromhex(self.d["salt_hex"])

    def test_rooms(self):
        for c in self.d["room"]:
            self.assertEqual(link.derive(self.salt, "room", os.fsencode(c["project_identity"])), c["expect"])

    def test_instances(self):
        for c in self.d["instance"]:
            ident = c["host"].encode() + b"\n" + c["session_id"].encode()
            self.assertEqual(link.derive(self.salt, "instance", ident), c["expect"])

    def test_prism_instance_helper_uses_antigravity_host(self):
        sid = "conv_8f1e2d3c4b5a69788776"
        want = [c["expect"] for c in self.d["instance"] if c["host"] == "antigravity" and c["session_id"] == sid][0]
        self.assertEqual(link.instance_for(self.salt, sid), want)

    def test_salt_validity(self):
        with tempfile.TemporaryDirectory() as t:
            for c in self.d["salt_validity"]:
                box = Path(t) / c["name"]
                box.mkdir(mode=0o700)
                if not make(box / ".salt", c["fs"], c["content"].encode()):
                    continue
                self.assertEqual(link.salt_is_valid(box / ".salt"), c["expect"] == "valid", c["name"])

    def test_directory_validity(self):
        with tempfile.TemporaryDirectory() as t:
            for c in self.d["directory_validity"]:
                holder = Path(t) / ("d-" + c["name"])
                holder.mkdir(mode=0o700)
                p = holder / "cyclops-link"
                if c["fs"]["type"] == "symlink":
                    real = holder / "real"
                    real.mkdir(mode=0o700)
                    p.symlink_to(real)
                elif not make(p, c["fs"], b""):
                    continue
                if c["expect"] == "create-0700-then-use":
                    self.assertEqual(link.prepare_dir(p, create=True), p)
                    self.assertEqual(os.lstat(p).st_mode & 0o777, 0o700)
                else:
                    before = os.lstat(p).st_mode
                    got = link.prepare_dir(p, create=True)
                    self.assertEqual(got is not None, c["expect"] == "use", c["name"])
                    self.assertEqual(os.lstat(p).st_mode, before, "an existing directory is never repaired")

    def test_new_salt_is_random_0600_and_never_published(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "link"
            d.mkdir(mode=0o700)
            salt = link.load_salt(d, create=True)
            self.assertEqual(len(salt), 32)
            self.assertEqual(os.lstat(d / ".salt").st_mode & 0o777, 0o600)
            self.assertEqual(link.load_salt(d, create=True), salt, "an existing salt is reused")


class Records(unittest.TestCase):
    def test_every_case(self):
        rc = load("records.json")
        with tempfile.TemporaryDirectory() as t:
            for c in rc["cases"]:
                ld = Path(t) / c["name"]
                ld.mkdir(parents=True, mode=0o700)
                if "record" in c:
                    content = json.dumps(c["record"]).encode()
                elif "raw_hex" in c:
                    content = bytes.fromhex(c["raw_hex"])
                else:
                    content = (c.get("raw") or "").encode()
                p = ld / c["filename"]
                if not make(p, c["fs"], content):
                    continue
                self.assertEqual(link.read_record(p) is not None, c["expect"] == "valid", c["name"])

    def test_ignored_names(self):
        rc = load("records.json")
        good = {"v": 1, "presence": "keeper", "host": "codex", "instance": rc["fixture_instances"]["keeper-1"],
                "room": rc["fixture_room"], "state": "idle", "tools": 0, "branches": 0, "reaching": [],
                "updated_at": 1000.0, "ended": False}
        with tempfile.TemporaryDirectory() as t:
            for name in rc["ignored_names"]:
                p = Path(t) / name
                p.write_text(json.dumps(good))
                os.chmod(p, 0o600)
                self.assertIsNone(link.read_record(p), name)


class Views(unittest.TestCase):
    def test_every_scenario(self):
        vs = load("views.json")
        for a in link.PRESENCES:
            for b in link.PRESENCES:
                if a != b:
                    self.assertEqual(link.bearing(a, b), vs["bearings"][f"{a}->{b}"])
        with tempfile.TemporaryDirectory() as t:
            for s in vs["scenarios"]:
                ld = Path(t) / s["name"]
                ld.mkdir(mode=0o700)
                for f in s["files"]:
                    p = ld / f["filename"]
                    p.write_text(json.dumps(f["record"]))
                    os.chmod(p, 0o600)
                records = [r for r in (link.read_record(p) for p in sorted(ld.iterdir())) if r]
                self.assertEqual(link.compose(s["self"], records, s["now"], s["policy"]), s["expect"], s["name"])

    def test_reader_paces_and_follows_atomic_updates(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"CYCLOPS_LINK_DIR": str(Path(t) / "link"), "HOME": t}
            w = link.Writer("conv-a", t, env)
            self.assertTrue(w.publish("working", now=1000.0))
            r = link.Reader(env)
            first = r.poll(now=10.0)
            self.assertEqual([x["state"] for x in first], ["working"])
            w.publish("stopped", now=1001.0)
            self.assertEqual([x["state"] for x in r.poll(now=10.5)], ["working"], "at most one poll a second")
            self.assertEqual([x["state"] for x in r.poll(now=11.1)], ["stopped"])
            leftovers = [n for n in os.listdir(Path(t) / "link") if n.endswith(".tmp")]
            self.assertEqual(leftovers, [], "no temp file is left behind")


class Lifecycle(unittest.TestCase):
    def test_off_by_default_and_no_shared_switch(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"HOME": t, "CYCLOPS_LINK": "1"}
            self.assertFalse(link.enabled(env))
            env["PRISM_LINK"] = "1"
            self.assertTrue(link.enabled(env))
            env2 = {"HOME": t}
            link.set_enabled(True, env2)
            self.assertTrue(link.enabled(env2))
            self.assertFalse(link.enabled(dict(env2, PRISM_LINK="0")))
            link.set_enabled(False, env2)
            self.assertFalse(link.enabled(env2))

    def test_heartbeat_never_ends_and_refreshes_within_five_seconds(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"CYCLOPS_LINK_DIR": str(Path(t) / "link")}
            w = link.Writer("conv-b", t, env)
            w.publish("idle", now=100.0)
            self.assertFalse(w.heartbeat(now=102.0))
            self.assertTrue(w.heartbeat(now=104.5))
            for k in range(30):
                w.heartbeat(now=105.0 + k * 4)
            path = Path(t) / "link" / f"prism-{w.instance}.json"
            rec = json.loads(path.read_text())
            self.assertFalse(rec["ended"])
            self.assertEqual(rec["state"], "idle")
            self.assertGreaterEqual(rec["updated_at"], 216.0)

    def test_truthful_end_then_grace(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"CYCLOPS_LINK_DIR": str(Path(t) / "link")}
            w = link.Writer("conv-c", t, env)
            w.publish("working", now=10.0)
            w.end(now=20.0)
            path = Path(t) / "link" / f"prism-{w.instance}.json"
            rec = json.loads(path.read_text())
            self.assertEqual((rec["state"], rec["ended"]), ("ended", True))
            self.assertFalse(w.cleanup(now=60.0))
            self.assertTrue(path.exists())
            self.assertTrue(w.cleanup(now=80.5))
            self.assertFalse(path.exists())

    def test_unsafe_directory_is_refused_and_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "link"
            d.mkdir()
            os.chmod(d, 0o777)
            w = link.Writer("conv-d", t, {"CYCLOPS_LINK_DIR": str(d)})
            self.assertFalse(w.publish("working"))
            self.assertEqual(os.lstat(d).st_mode & 0o777, 0o777)
            self.assertEqual(os.listdir(d), [])

    def test_write_failure_is_silent_and_bounded(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"CYCLOPS_LINK_DIR": str(Path(t) / "link")}
            w = link.Writer("conv-e", t, env)
            self.assertTrue(w.publish("working", now=1.0))
            with mock.patch.object(link, "write_record", return_value=False) as wr:
                for k in range(10):
                    self.assertFalse(w.publish("working", now=2.0 + k))
                self.assertEqual(wr.call_count, link.MAX_FAILURES, "stops trying after 3 failures in a row")

    def test_prism_never_publishes_tool_thinking_waiting_or_reaching(self):
        for phase in ("wake", "attending", "working", "resolved", "halted", "ended", "ready", "refracting",
                      "branching", "approval", "unknown"):
            word = link.coarse_state(phase, previous="working")
            self.assertNotIn(word, {"tool", "thinking", "waiting"}, phase)
        self.assertEqual(link.coarse_state("refracting", previous="stopped"), "stopped", "no guessed state")


class Privacy(unittest.TestCase):
    def test_adversarial_hook_payloads_never_leak(self):
        pv = load("privacy.json")
        facts = pv["host_facts"]
        with tempfile.TemporaryDirectory() as t:
            home = Path(t)
            env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home / "state"),
                       XDG_CONFIG_HOME=str(home / "config"), PRISM_LINK="1",
                       CYCLOPS_LINK_DIR=str(home / "link"), PRISM_NO_DAEMON="1")
            work = home / "acme-merger"
            work.mkdir()
            payloads = [
                {"hookEvent": "PreInvocation", "conversationId": facts["session_id"], "invocationNum": 1,
                 "prompt": facts["prompt"], "model": facts["model"], "user": facts["user"], "cwd": facts["cwd"]},
                {"hookEvent": "PostToolUse", "conversationId": facts["session_id"], "toolName": facts["tool_name"],
                 "toolCall": {"name": facts["tool_name"], "args": {"command": facts["command"], "argv": facts["arguments"]}},
                 "toolResult": facts["tool_result"], "callId": facts["call_id"], "paths": facts["paths"]},
                {"hookEvent": "Stop", "conversationId": facts["session_id"], "terminationReason": "model_stop",
                 "response": facts["response"]},
            ]
            for p in payloads:
                subprocess.run([sys.executable, str(ROOT / "scripts" / "hook.py"), "--event", p["hookEvent"]],
                               input=json.dumps(p), text=True, env=env, cwd=work, capture_output=True, timeout=10)
            files = list((home / "link").glob("prism-*.json"))
            self.assertEqual(len(files), 1)
            text = files[0].read_text()
            rec = json.loads(text)
            self.assertEqual((rec["state"], rec["tools"], rec["reaching"]), ("stopped", 0, []))
            everything = text + "".join(p.read_text(errors="replace") for p in (home / "link").iterdir() if p.is_file())
            for bad in pv["forbidden_substrings"]:
                self.assertNotIn(bad, everything)


if __name__ == "__main__":
    unittest.main()
