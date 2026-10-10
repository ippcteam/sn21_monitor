#!/bin/bash
# Installs (or reinstalls) the macOS LaunchAgent that runs `owner_share_lock.py --remind`
# Fri 09:00, Fri 16:00, Sat 10:00 and Mon 10:00 local time. It is silent unless a lock
# is owed, so the later slots only fire if Friday's lock hasn't been signed yet.
# A slot missed while the Mac is asleep runs on wake.
#
# Uninstall:
#   launchctl bootout gui/$(id -u)/com.sn21.owner-share-lock
#   rm ~/Library/LaunchAgents/com.sn21.owner-share-lock.plist
set -euo pipefail

LABEL="com.sn21.owner-share-lock"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/sn21-owner-share-lock.log"

[ -x "$PY" ] || { echo "No venv python at $PY"; exit 1; }

slot() {  # weekday (0=Sun) hour
  printf '    <dict><key>Weekday</key><integer>%s</integer><key>Hour</key><integer>%s</integer><key>Minute</key><integer>0</integer></dict>\n' "$1" "$2"
}

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$REPO/owner_share_lock.py</string>
    <string>--remind</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key>
  <array>
$(slot 5 9)
$(slot 5 16)
$(slot 6 10)
$(slot 1 10)
  </array>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL → $PLIST"
echo "Log: $LOG"
echo "Test now: launchctl kickstart gui/$(id -u)/$LABEL"
