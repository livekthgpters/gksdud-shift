#!/usr/bin/env python3
"""Fail closed if the fork's build/test entry points disappear."""
from pathlib import Path


def check(root):
    root = Path(root)
    required = {
        "build.sh": ["ForkPolicy.swift", "ForkTests.swift", '"$test_app/Contents/MacOS/gksdud" --self-test'],
        "SelfTest.swift": ["runForkTests()"],
        "main.swift": ["0xffff00000004", "Shift ⇧ + Space ␣"],
    }
    for name, markers in required.items():
        content = (root / name).read_text()
        for marker in markers:
            if marker not in content:
                raise RuntimeError(f"Missing fork entry point in {name}: {marker}")


if __name__ == "__main__":
    check(Path(__file__).resolve().parent.parent)
