"""Exercise publication against disposable local Git repositories."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trek_validator", ROOT / "scripts/validate-trek-patch.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        self.remote = self.root / "fork.git"
        self.work = self.root / "work"
        self.env = os.environ | {
            "GIT_AUTHOR_NAME": "Sync test",
            "GIT_AUTHOR_EMAIL": "sync@example.invalid",
            "GIT_COMMITTER_NAME": "Sync test",
            "GIT_COMMITTER_EMAIL": "sync@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        self.feed = json.loads((ROOT / "Tamtaro-All-Templates-for-AIOStreams.json").read_text())
        baseline = copy.deepcopy(self.feed)
        for group in baseline[0]["metadata"]["inputs"]:
            if "subOptions" in group:
                group["subOptions"] = [c for c in group["subOptions"] if c.get("id") != "aiUpscaleTrek"]
        for key in validator.EXPRESSIONS:
            entries = baseline[0]["config"][key]
            if isinstance(entries, dict):
                entries = entries["__value"]
            entries[:] = [e for e in entries if "Trek AI Upscale" not in e.get("expression", "")]
        self.upstream.mkdir()
        self.git(self.upstream, "init", "-b", "main")
        self.write_feed(self.upstream, baseline)
        (self.upstream / "conflict.txt").write_text("base\n")
        self.commit(self.upstream, "upstream base")
        self.git(self.root, "clone", "--bare", str(self.upstream), str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.work))
        self.write_feed(self.work, self.feed)
        shutil.copytree(ROOT / "scripts", self.work / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.work / "conflict.txt").write_text("fork\n")
        self.commit(self.work, "fork patch and automation")
        self.git(self.work, "push", "origin", "main")

    def git(self, directory, *args):
        return subprocess.check_output(["git", *args], cwd=directory, env=self.env, stderr=subprocess.STDOUT, text=True).strip()

    def commit(self, directory, message):
        self.git(directory, "add", ".")
        self.git(directory, "commit", "-m", message)

    def write_feed(self, directory, feed):
        (directory / "Tamtaro-All-Templates-for-AIOStreams.json").write_text(json.dumps(feed, indent=2) + "\n")

    def published(self):
        return self.git(self.remote, "rev-parse", "main")

    def advance_upstream(self):
        (self.upstream / "upstream-update.txt").write_text("new upstream release\n")
        self.commit(self.upstream, "upstream update")
        return self.git(self.upstream, "rev-parse", "HEAD")

    def sync(self, env=None):
        return subprocess.run(["bash", "scripts/sync-upstream.sh", str(self.upstream)], cwd=self.work, env=env or self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def test_rebase_preserves_patch_and_repeat_is_noop(self):
        before = self.published()
        revision = self.advance_upstream()
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(before, self.published())
        self.git(self.remote, "merge-base", "--is-ancestor", revision, "main")
        validator.validate(json.loads(self.git(self.remote, "show", "main:Tamtaro-All-Templates-for-AIOStreams.json")))
        after = self.published()
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(after, self.published())

    def test_conflict_does_not_publish_and_aborts_rebase(self):
        before = self.published()
        (self.upstream / "conflict.txt").write_text("conflicting upstream change\n")
        self.commit(self.upstream, "conflicting update")
        result = self.sync()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.published())
        self.assertEqual(before, self.git(self.work, "rev-parse", "HEAD"))
        self.assertFalse((self.work / ".git/rebase-merge").exists())

    def test_invalid_patch_does_not_publish(self):
        bad = copy.deepcopy(self.feed)
        entries = bad[0]["config"]["rankedStreamExpressions"]["__value"]
        next(e for e in entries if "Trek AI Upscale" in e.get("expression", ""))["score"] = 0
        self.write_feed(self.work, bad)
        self.commit(self.work, "break upscale score")
        self.git(self.work, "push", "origin", "main")
        before = self.published()
        self.advance_upstream()
        result = self.sync()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("penalty cancellation", result.stdout)
        self.assertEqual(before, self.published())

    def test_concurrent_remote_update_is_preserved_by_lease(self):
        # Inject a new remote commit immediately before the sync's push.
        racer = self.root / "racer"
        self.git(self.root, "clone", str(self.remote), str(racer))
        (racer / "concurrent.txt").write_text("keep this change\n")
        self.commit(racer, "concurrent fork update")
        expected = self.git(racer, "rev-parse", "HEAD")
        wrapper_dir = self.root / "bin"
        wrapper_dir.mkdir()
        real_git = shutil.which("git")
        wrapper = wrapper_dir / "git"
        wrapper.write_text('#!/usr/bin/env bash\nset -e\nif [[ $1 == push ]]; then\n  "$TEST_REAL_GIT" -C "$TEST_RACER" push origin main\nfi\nexec "$TEST_REAL_GIT" "$@"\n')
        wrapper.chmod(0o755)
        self.advance_upstream()
        result = self.sync(self.env | {"PATH": str(wrapper_dir) + os.pathsep + self.env["PATH"], "TEST_REAL_GIT": real_git, "TEST_RACER": str(racer)})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("stale info", result.stdout)
        self.assertEqual(expected, self.published())

    def test_validator_rejects_lost_scope_control_and_preference_order(self):
        for mutation in ("scope", "control", "order"):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(self.feed)
                if mutation == "scope":
                    entry = next(e for e in bad[0]["config"]["includedStreamExpressions"] if "Trek AI Upscale" in e.get("expression", ""))
                    entry["expression"] = "passthrough(streams, 'excluded')"
                elif mutation == "control":
                    group = next(g for g in bad[0]["metadata"]["inputs"] if g["id"] == "sortingP2P")
                    group["subOptions"] = [c for c in group["subOptions"] if c["id"] != "aiUpscaleTrek"]
                else:
                    entries = bad[0]["config"]["preferredStreamExpressions"]
                    entry = next(e for e in entries if "Trek AI Upscale" in e.get("expression", ""))
                    entries.remove(entry)
                    entries.append(entry)
                with self.assertRaises(ValueError):
                    validator.validate(bad)


if __name__ == "__main__":
    unittest.main()
