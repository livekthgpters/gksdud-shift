import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("watch_upstream", Path(__file__).with_name("watch-upstream.py"))
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
UPSTREAM, FORK = "a" * 40, "b" * 40


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.comparison = "diverged"
        self.runs = []

    def api(self, path, method="GET", payload=None):
        self.calls.append((path, method, payload))
        if method == "POST":
            return None
        if path == f"repos/{watch.UPSTREAM}/git/ref/heads/main":
            return {"object": {"sha": UPSTREAM}}
        if path == f"repos/{watch.FORK}/git/ref/heads/main":
            return {"object": {"sha": FORK}}
        if "/compare/" in path:
            return {"status": self.comparison}
        return {"workflow_runs": self.runs}

    def state(self):
        return {"upstream": UPSTREAM, "fork": FORK, "dispatched_at": 100}

    def run_record(self, status, conclusion=None):
        return {"display_title": watch.TITLE + UPSTREAM, "status": status, "conclusion": conclusion,
                "html_url": "https://github.com/livekthgpters/gksdud/actions/runs/1"}

    def test_current_fork_never_dispatches(self):
        for comparison in ("identical", "ahead"):
            self.comparison = comparison
            self.assertEqual(watch.inspect({}, self.api)["status"], "current")
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))

    def test_completed_merge_is_reported_only_once(self):
        self.comparison = "ahead"
        state = dict(self.state(), fork="c" * 40)
        self.assertEqual(watch.inspect(state, self.api)["status"], "merged")
        self.assertEqual(watch.inspect(state, self.api)["status"], "current")

    def test_changed_fork_dispatches_fixed_repository_and_event(self):
        state = {}
        self.assertEqual(watch.inspect(state, self.api, now=100)["status"], "dispatched")
        self.assertEqual(self.calls[-1], (f"repos/{watch.FORK}/dispatches", "POST", {
            "event_type": "upstream_changed", "client_payload": {"upstream_sha": UPSTREAM}}))
        self.assertEqual(state, self.state())

    def test_dry_run_has_no_writes(self):
        state = {}
        self.assertEqual(watch.inspect(state, self.api, dry_run=True)["status"], "would_dispatch")
        self.assertEqual(state, {})
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))

    def test_running_merge_and_dispatch_propagation_are_deduplicated(self):
        self.runs = [self.run_record("in_progress")]
        self.assertEqual(watch.inspect({}, self.api)["status"], "pending")
        self.runs = []
        self.assertEqual(watch.inspect(self.state(), self.api, now=200)["status"], "pending")
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))

    def test_lost_dispatch_is_retried_after_an_hour(self):
        self.assertEqual(watch.inspect(self.state(), self.api, now=3700)["status"], "dispatched")

    def test_failed_merge_stops_until_explicit_retry(self):
        self.runs = [self.run_record("completed", "failure")]
        self.assertEqual(watch.inspect(self.state(), self.api)["status"], "failed")
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))
        self.assertEqual(watch.inspect(self.state(), self.api, retry=True)["status"], "dispatched")

    def test_new_fork_commit_can_retry_a_previously_failed_merge(self):
        self.runs = [self.run_record("completed", "failure")]
        self.assertEqual(watch.inspect(dict(self.state(), fork="c" * 40), self.api)["status"], "dispatched")

    def test_new_upstream_commit_is_detected_after_a_failure(self):
        self.runs = [dict(self.run_record("completed", "failure"), display_title=watch.TITLE + "c" * 40)]
        self.assertEqual(watch.inspect(dict(self.state(), upstream="c" * 40), self.api)["status"], "dispatched")

    def test_unknown_comparison_and_invalid_sha_fail_closed(self):
        self.comparison = "unexpected"
        with self.assertRaises(RuntimeError):
            watch.inspect({}, self.api)
        with self.assertRaises(ValueError):
            watch.commit("main; echo secret")
        self.assertTrue(all(method == "GET" for _, method, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
