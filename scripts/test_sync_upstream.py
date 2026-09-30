import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sync_upstream", Path(__file__).with_name("sync-upstream.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        # Synthetic repositories must not inherit developer hooks/signing settings.
        isolation = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"})
        isolation.start()
        self.addCleanup(isolation.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.upstream = self.root / "upstream"
        self.fork = self.root / "fork"
        self.work = self.root / "work"
        self.upstream.mkdir()
        self.git(self.upstream, "init", "-b", "main")
        self.identity(self.upstream)
        for path in sync.PROTECTED:
            file = self.upstream / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(f"Protected fork fixture: {path}\n")
        (self.upstream / "source.txt").write_text("original\n")
        self.commit(self.upstream, "Initial fixture")
        subprocess.run(["git", "clone", "--bare", str(self.upstream), str(self.fork)], check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.fork), str(self.work)], check=True, capture_output=True)
        self.identity(self.work)
        (self.work / "fork-feature.txt").write_text("Shift + Space\n")
        self.base = self.commit(self.work, "Fork feature")
        self.git(self.work, "push", "origin", "main")
        self.bundle = self.root / "candidate.bundle"

    def git(self, root, *args):
        return sync.git(root, *args).stdout.strip()

    def identity(self, root):
        self.git(root, "config", "user.name", "Sync test")
        self.git(root, "config", "user.email", "sync@example.invalid")

    def commit(self, root, message):
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def update(self):
        (self.upstream / "upstream-feature.txt").write_text("New upstream behavior\n")
        return self.commit(self.upstream, "Upstream feature")

    def candidate(self):
        self.update()
        return sync.prepare(self.work, str(self.upstream))

    def validate(self, candidate, validator=lambda: None):
        sync.validate_and_bundle(self.work, candidate["base"], candidate["upstream"], candidate["candidate"], self.bundle, validator)

    def publish(self, candidate):
        sync.publish(self.work, candidate["base"], candidate["upstream"], candidate["candidate"], self.bundle, str(self.fork))

    def main_sha(self):
        return self.git(self.fork, "rev-parse", "refs/heads/main")

    def test_no_changes_skip_merge_and_validation(self):
        candidate = sync.prepare(self.work, str(self.upstream))
        self.assertEqual(candidate["changed"], "false")
        self.assertEqual(candidate["candidate"], self.base)
        self.assertEqual(self.main_sha(), self.base)

    def test_normal_merge_publishes_exact_verified_commit_and_both_histories(self):
        candidate = self.candidate()
        self.validate(candidate)
        self.assertEqual(self.main_sha(), self.base)
        self.publish(candidate)
        self.assertEqual(self.main_sha(), candidate["candidate"])
        self.assertTrue(sync.ancestor(self.work, self.base, candidate["candidate"]))
        self.assertTrue(sync.ancestor(self.work, candidate["upstream"], candidate["candidate"]))
        self.assertEqual(self.git(self.fork, "show", "main:fork-feature.txt"), "Shift + Space")
        self.assertEqual(self.git(self.fork, "show", "main:upstream-feature.txt"), "New upstream behavior")

    def test_conflict_does_not_update_main(self):
        (self.work / "source.txt").write_text("Fork modification\n")
        base = self.commit(self.work, "Fork change")
        self.git(self.work, "push", "origin", "main")
        (self.upstream / "source.txt").write_text("Upstream modification\n")
        self.commit(self.upstream, "Conflicting change")
        with self.assertRaisesRegex(RuntimeError, "source.txt"):
            sync.prepare(self.work, str(self.upstream))
        self.assertEqual(self.main_sha(), base)
        self.assertEqual(self.git(self.work, "status", "--porcelain"), "")

    def test_validation_failure_has_no_bundle_or_main_update(self):
        candidate = self.candidate()

        def fail():
            raise RuntimeError("Build failed")

        with self.assertRaisesRegex(RuntimeError, "Build failed"):
            self.validate(candidate, fail)
        self.assertFalse(self.bundle.exists())
        self.assertEqual(self.main_sha(), self.base)

    def test_main_changed_during_validation_is_not_overwritten(self):
        candidate = self.candidate()
        self.validate(candidate)
        other = self.root / "other"
        subprocess.run(["git", "clone", str(self.fork), str(other)], check=True, capture_output=True)
        self.identity(other)
        (other / "concurrent.txt").write_text("Another contributor\n")
        concurrent = self.commit(other, "Concurrent main update")
        self.git(other, "push", "origin", "main")
        with self.assertRaisesRegex(RuntimeError, "main changed"):
            self.publish(candidate)
        self.assertEqual(self.main_sha(), concurrent)

    def test_removed_or_changed_protected_files_stop_synchronization(self):
        path = self.upstream / "ForkPolicy.swift"
        path.unlink()
        self.commit(self.upstream, "Remove fork policy")
        with self.assertRaises(RuntimeError):
            sync.prepare(self.work, str(self.upstream))
        self.assertEqual(self.main_sha(), self.base)

    def test_changed_protected_workflow_stops_synchronization(self):
        (self.upstream / ".github/workflows/sync-upstream.yml").write_text("Changed workflow\n")
        self.commit(self.upstream, "Change protected workflow")
        with self.assertRaisesRegex(RuntimeError, "Protected fork file changed"):
            sync.prepare(self.work, str(self.upstream))
        self.assertEqual(self.main_sha(), self.base)

    def test_wrong_bundle_commit_cannot_be_published(self):
        candidate = self.candidate()
        self.validate(candidate)
        wrong = dict(candidate, candidate=self.base)
        with self.assertRaisesRegex(RuntimeError, "differs"):
            self.publish(wrong)
        self.assertEqual(self.main_sha(), self.base)

    def test_validation_cannot_mutate_tracked_candidate(self):
        candidate = self.candidate()

        def mutate():
            (self.work / "fork-feature.txt").write_text("Lost feature\n")

        with self.assertRaisesRegex(RuntimeError, "Tracked files changed"):
            self.validate(candidate, mutate)
        self.assertFalse(self.bundle.exists())
        self.assertEqual(self.main_sha(), self.base)

    def test_dirty_worktree_and_untrusted_sha_are_rejected(self):
        (self.work / "fork-feature.txt").write_text("Uncommitted\n")
        with self.assertRaisesRegex(RuntimeError, "Tracked files changed"):
            sync.prepare(self.work, str(self.upstream))
        with self.assertRaises(ValueError):
            sync.sha("main; echo secret")
        self.assertEqual(self.main_sha(), self.base)


if __name__ == "__main__":
    unittest.main()
