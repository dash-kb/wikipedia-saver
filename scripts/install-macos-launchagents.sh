#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
SERVER_PLIST="$LAUNCH_AGENTS/com.local.wikipedia-saver.server.plist"
UPDATER_PLIST="$LAUNCH_AGENTS/com.local.wikipedia-saver.weekly.plist"

mkdir -p "$LAUNCH_AGENTS"

cat > "$SERVER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.wikipedia-saver.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$ROOT/scripts/run-server.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT/server.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/server.err.log</string>
</dict>
</plist>
PLIST

cat > "$UPDATER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.wikipedia-saver.weekly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$ROOT/scripts/update-all.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT/update.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/update.err.log</string>
</dict>
</plist>
PLIST

chmod +x "$ROOT/scripts/run-server.sh" "$ROOT/scripts/update-all.sh"
cd "$ROOT"
/usr/bin/env python3 -m wiki_saver.cli --repo "$ROOT/../local-wiki" init
launchctl unload "$SERVER_PLIST" >/dev/null 2>&1 || true
launchctl unload "$UPDATER_PLIST" >/dev/null 2>&1 || true
launchctl load "$SERVER_PLIST"
launchctl load "$UPDATER_PLIST"

echo "Installed and loaded:"
echo "  $SERVER_PLIST"
echo "  $UPDATER_PLIST"
