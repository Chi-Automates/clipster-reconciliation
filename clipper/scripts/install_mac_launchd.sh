#!/usr/bin/env bash
# Installs a launchd agent that runs the clipper daily at 07:00. If the Mac was asleep at
# 07:00, launchd runs it on wake (it does not run if the Mac was fully shut down).
set -euo pipefail
HOUR="${1:-7}"
MINUTE="${2:-0}"
SCRIPT="$(cd "$(dirname "$0")" && pwd)/run_daily.sh"
LOGDIR="$HOME/clipper-data/logs"
PLIST="$HOME/Library/LaunchAgents/com.gistroom.clipper.plist"
mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"
chmod +x "$SCRIPT"

# Bake in the PATH that can see claude and ffmpeg right now.
EXTRA_PATH="$(dirname "$(command -v claude)"):$(dirname "$(command -v ffmpeg)")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.gistroom.clipper</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SCRIPT</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$EXTRA_PATH:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$LOGDIR/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/launchd.err.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Runs daily at $(printf '%02d:%02d' "$HOUR" "$MINUTE"). Run now with: launchctl start com.gistroom.clipper"
