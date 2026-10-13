#!/usr/bin/env bash
# Daily clipper run (macOS/Linux). Called by launchd; safe to run by hand.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || exit 1

# launchd starts with a bare PATH; add the usual install locations for ffmpeg and claude.
export PATH="$HOME/.local/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$PATH"

# Pick up campaign changes pushed from Claude sessions; carry on offline if this fails.
git pull --ff-only >/dev/null 2>&1 || true

exec "$REPO/.venv/bin/python" -m clipper daily "$@"
