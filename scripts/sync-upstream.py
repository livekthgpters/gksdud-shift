#!/usr/bin/env python3
"""Prepare/validate a merge, then publish only its verified commit. No force pushes."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

UPSTREAM = "https://github.com/codingnoye/gksdud.git"
FORK = "https://github.com/livekthgpters/gksdud-shift.git"
PROTECTED = (
    "ForkPolicy.swift", "ForkTests.swift", ".github/workflows/sync-upstream.yml",
    ".github/workflows/checks.yml", "scripts/check-fork.py", "scripts/validate.sh",
    "scripts/sync-upstream.py", "scripts/watch-upstream.py",
    "scripts/test_sync_upstream.py", "scripts/test_watch_upstream.py",
)


def git(root, *args, check=True):
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Git command failed")
    return result


def sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected a complete lowercase commit SHA")
    return value


def ancestor(root, older, newer):
    result = git(root, "merge-base", "--is-ancestor", sha(older), sha(newer), check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def clean(root):
    if git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise RuntimeError("Tracked files changed; refusing synchronization")


def preserve(root, base, candidate):
    for path in PROTECTED:
        original = git(root, "rev-parse", f"{sha(base)}:{path}").stdout.strip()
        merged = git(root, "rev-parse", f"{sha(candidate)}:{path}").stdout.strip()
        if merged != original:
            raise RuntimeError(f"Protected fork file changed: {path}")


def prepare(root, upstream_url=UPSTREAM):
    clean(root)
    base = sha(git(root, "rev-parse", "HEAD").stdout.strip())
    git(root, "fetch", "--no-tags", upstream_url, "refs/heads/main")
    upstream = sha(git(root, "rev-parse", "FETCH_HEAD").stdout.strip())
    result = {"base": base, "upstream": upstream, "changed": "false", "candidate": base}
    if ancestor(root, upstream, base):
        return result
    git(root, "switch", "--detach", base)
    git(root, "config", "user.name", "gksdud upstream sync")
    git(root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    merge = git(root, "merge", "--no-edit", upstream, check=False)
    if merge.returncode:
        conflicts = git(root, "diff", "--name-only", "--diff-filter=U").stdout.strip()
        git(root, "merge", "--abort", check=False)
        raise RuntimeError(f"Merge failed. Fork: {base}; upstream: {upstream}; conflicts:\n{conflicts}\n{merge.stderr}")
    candidate = sha(git(root, "rev-parse", "HEAD").stdout.strip())
    preserve(root, base, candidate)
    result.update(changed="true", candidate=candidate)
    return result


def validate_and_bundle(root, base, upstream, candidate, bundle, validator=None):
    base, upstream, candidate = map(sha, (base, upstream, candidate))
    if git(root, "rev-parse", "HEAD").stdout.strip() != candidate:
        raise RuntimeError("Candidate HEAD changed before validation")
    if not ancestor(root, base, candidate) or not ancestor(root, upstream, candidate):
        raise RuntimeError("Candidate does not contain both histories")
    preserve(root, base, candidate)
    clean(root)
    if validator is None:
        subprocess.run(["bash", "scripts/validate.sh"], cwd=root, check=True)
    else:
        validator()
    clean(root)
    if git(root, "rev-parse", "HEAD").stdout.strip() != candidate:
        raise RuntimeError("Candidate HEAD changed during validation")
    git(root, "update-ref", "refs/heads/sync-candidate", candidate)
    git(root, "bundle", "create", str(Path(bundle).resolve()), f"{base}..refs/heads/sync-candidate")


def publish(root, base, upstream, candidate, bundle, fork_url=FORK):
    base, upstream, candidate = map(sha, (base, upstream, candidate))
    git(root, "bundle", "verify", str(Path(bundle).resolve()))
    git(root, "fetch", str(Path(bundle).resolve()), "refs/heads/sync-candidate")
    if git(root, "rev-parse", "FETCH_HEAD").stdout.strip() != candidate:
        raise RuntimeError("Bundle commit differs from validated candidate")
    if not ancestor(root, base, candidate) or not ancestor(root, upstream, candidate):
        raise RuntimeError("Bundle does not contain both verified histories")
    preserve(root, base, candidate)
    current = git(root, "ls-remote", fork_url, "refs/heads/main").stdout.split()
    if not current or current[0] != base:
        raise RuntimeError("Fork main changed during validation; rerun synchronization")
    # The publish job sets authentication through environment Git config, never a URL or log.
    git(root, "push", fork_url, f"{candidate}:refs/heads/main")


def record(values):
    lines = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as output:
            output.write(lines)
    summary("\n".join(f"- {key}: `{value}`" for key, value in values.items()))
    print(lines, end="")


def summary(message):
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a") as output:
            output.write(message + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "validate", "publish"])
    parser.add_argument("--base")
    parser.add_argument("--upstream")
    parser.add_argument("--candidate")
    parser.add_argument("--bundle")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        if args.operation == "prepare":
            record(prepare(root))
        else:
            if not all((args.base, args.upstream, args.candidate, args.bundle)):
                parser.error("base, upstream, candidate and bundle are required")
            operation = validate_and_bundle if args.operation == "validate" else publish
            operation(root, args.base, args.upstream, args.candidate, args.bundle)
            summary(f"{args.operation} succeeded: `{args.candidate}` (upstream `{args.upstream}`)")
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        summary(f"Synchronization stopped; main was not updated.\n\n```\n{error}\n```")
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
