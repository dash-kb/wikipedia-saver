#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_SUPPORT="$HOME/Library/Application Support/WikipediaSaver"
RUNTIME="$APP_SUPPORT/runtime"
REPO="${WIKIPEDIA_SAVER_REPO:-$APP_SUPPORT/local-wiki}"
LEGACY_REPO="$ROOT/../local-wiki"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
SERVER_PLIST="$LAUNCH_AGENTS/com.local.wikipedia-saver.server.plist"
UPDATER_PLIST="$LAUNCH_AGENTS/com.local.wikipedia-saver.weekly.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$LAUNCH_AGENTS" "$RUNTIME"
rm -rf "$RUNTIME/wiki_saver"
cp -R "$ROOT/wiki_saver" "$RUNTIME/wiki_saver"

if [ -z "${WIKIPEDIA_SAVER_REPO:-}" ] && [ ! -e "$REPO" ] && [ -d "$LEGACY_REPO/.git" ]; then
  cp -R "$LEGACY_REPO" "$REPO"
fi

cat > "$RUNTIME/run-server.sh" <<SCRIPT
#!/bin/sh
set -eu
cd "$RUNTIME"
exec /usr/bin/env python3 -m wiki_saver.cli --repo "$REPO" serve
SCRIPT

cat > "$RUNTIME/update-all.sh" <<SCRIPT
#!/bin/sh
set -eu
cd "$RUNTIME"
exec /usr/bin/env python3 -m wiki_saver.cli --repo "$REPO" update-all
SCRIPT

chmod +x "$RUNTIME/run-server.sh" "$RUNTIME/update-all.sh"

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
    <string>$RUNTIME/run-server.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$APP_SUPPORT/server.log</string>
  <key>StandardErrorPath</key>
  <string>$APP_SUPPORT/server.err.log</string>
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
    <string>$RUNTIME/update-all.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$APP_SUPPORT/update.log</string>
  <key>StandardErrorPath</key>
  <string>$APP_SUPPORT/update.err.log</string>
</dict>
</plist>
PLIST

cd "$RUNTIME"
/usr/bin/env python3 -m wiki_saver.cli --repo "$REPO" init

launchctl bootout "$DOMAIN" "$SERVER_PLIST" >/dev/null 2>&1 || true
launchctl bootout "$DOMAIN" "$UPDATER_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$SERVER_PLIST"
launchctl bootstrap "$DOMAIN" "$UPDATER_PLIST"
launchctl enable "$DOMAIN/com.local.wikipedia-saver.server"
launchctl enable "$DOMAIN/com.local.wikipedia-saver.weekly"
launchctl kickstart -k "$DOMAIN/com.local.wikipedia-saver.server"

echo "Installed and loaded:"
echo "  $SERVER_PLIST"
echo "  $UPDATER_PLIST"
echo "Runtime:"
echo "  $RUNTIME"
echo "Archive:"
echo "  $REPO"
