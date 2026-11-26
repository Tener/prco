#!/usr/bin/env bash
# Record demo/demo.gif from demo/demo.tape. Runs vhs in a minimal environment
# so variables of the invoking shell (e.g. a coding agent's, which make gh
# print agent-only hints) don't leak into the recording.
set -euo pipefail
cd "$(dirname "$0")/.."
exec env -i \
  HOME="$HOME" \
  USER="$USER" \
  PATH="$PATH" \
  LANG="${LANG:-en_US.UTF-8}" \
  TERM=xterm-256color \
  vhs demo/demo.tape
