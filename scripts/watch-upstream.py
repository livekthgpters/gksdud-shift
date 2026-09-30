#!/usr/bin/env python3
"""External one-shot upstream detector; dispatch only when the fork needs a merge."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time

UPSTREAM = "codingnoye/gksdud"
FORK = "livekthgpters/gksdud"
TITLE = "Sync upstream "


def api(path, method="GET", payload=None):
    command = ["gh", "api", "--hostname", "github.com", "--method", method, path]
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"GitHub API failed ({method} {path}); check gh authentication and repository permissions")
    return json.loads(result.stdout) if result.stdout.strip() else None


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("GitHub returned an invalid commit SHA")
    return value


def inspect(state, request=api, now=None, dry_run=False, retry=False):
    now = time.time() if now is None else now
    upstream = commit(request(f"repos/{UPSTREAM}/git/ref/heads/main")["object"]["sha"])
    fork = commit(request(f"repos/{FORK}/git/ref/heads/main")["object"]["sha"])
    result = {"upstream": upstream, "fork": fork}
    comparison = request(f"repos/{FORK}/compare/{upstream}...{fork}")["status"]
    if comparison in ("ahead", "identical"):
        if state.get("upstream") == upstream and state.get("fork") != fork:
            if not dry_run:
                state.update(upstream=upstream, fork=fork)
            return dict(result, status="merged")
        return dict(result, status="current")
    if comparison not in ("behind", "diverged"):
        raise RuntimeError("Unexpected comparison result; refusing dispatch")
    runs = request(f"repos/{FORK}/actions/workflows/sync-upstream.yml/runs?event=repository_dispatch&per_page=30")["workflow_runs"]
    matching = [run for run in runs if run.get("display_title") == TITLE + upstream]
    active = [run for run in matching if run["status"] != "completed"]
    if active:
        return dict(result, status="pending", run_url=active[0]["html_url"])
    same_pair = state.get("upstream") == upstream and state.get("fork") == fork
    if same_pair and matching and matching[0].get("conclusion") in ("failure", "timed_out", "action_required") and not retry:
        return dict(result, status="failed", run_url=matching[0]["html_url"])
    # Dispatch acknowledgement can precede the run appearing in the API. Retry a lost event after an hour.
    if same_pair and not matching and now - state.get("dispatched_at", 0) < 3600 and not retry:
        return dict(result, status="pending")
    if dry_run:
        return dict(result, status="would_dispatch")
    request(f"repos/{FORK}/dispatches", "POST", {
        "event_type": "upstream_changed",
        "client_payload": {"upstream_sha": upstream},
    })
    state.update(upstream=upstream, fork=fork, dispatched_at=now)
    return dict(result, status="dispatched")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(__file__).resolve().parent.parent / ".local/upstream-watch.json")
    parser.add_argument("--dry-run", action="store_true", help="Read GitHub state without dispatching or saving state")
    parser.add_argument("--retry", action="store_true", help="Explicitly retry a failed or recently dispatched merge")
    args = parser.parse_args()
    try:
        if args.dry_run:
            state = json.loads(args.state.read_text()) if args.state.exists() else {}
            result = inspect(state, dry_run=True, retry=args.retry)
        else:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            with args.state.with_suffix(".lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    print(json.dumps({"status": "busy"}))
                    return 0
                state = json.loads(args.state.read_text()) if args.state.exists() else {}
                result = inspect(state, retry=args.retry)
                temporary = args.state.with_suffix(".tmp")
                temporary.write_text(json.dumps(state) + "\n")
                temporary.replace(args.state)
        print(json.dumps(result))
        return 1 if result["status"] == "failed" else 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Upstream detection stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
