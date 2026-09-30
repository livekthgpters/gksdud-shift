#!/bin/bash
# Shared checks for normal CI and an upstream merge candidate.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/check-fork.py
bash -n build.sh scripts/validate.sh scripts/cleanup-signing.sh signing/setup-local-signing.sh signing/verify-update-identity.sh
ruby -c scripts/prepare-release.rb
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 ruby scripts/test_release.rb
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/run-with-timeout.py 2 /usr/bin/true
if python3 scripts/run-with-timeout.py 0.1 /bin/sleep 5; then
  echo 'Timeout test unexpectedly succeeded' >&2
  exit 1
else
  test "$?" -eq 124
fi
GKSDUD_SIGN_MODE=ad-hoc bash build.sh
