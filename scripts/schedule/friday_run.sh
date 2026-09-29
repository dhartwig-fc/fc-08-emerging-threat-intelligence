#!/bin/bash
# FC08 Friday run, started by launchd (scripts/schedule/uk.fc08.friday-run.plist, installed by the OWNER with
# tools/schedule.py install). Bash 3.2: no arrays of pairs, no mapfile.
#
# THE TOKEN. The long-lived subscription token (`claude setup-token`, run by the owner) lives in the login
# Keychain under service uk.fc08.claude-oauth-token. This script reads it into ONE variable and hands it to the
# Python run as CLAUDE_CODE_OAUTH_TOKEN in that command's environment only. It is never written to a file,
# never printed, never on a command line, never in the plist or the log. Nothing here enables `set -x`.
# ANTHROPIC_API_KEY is unset first: it takes precedence over the token and bills pay-as-you-go (CLAUDE.md, Auth).
#
# ONE NOTIFICATION. tools/friday_run.py --scheduled posts it (the report's first two lines), refusals included.
# This script posts one only when Python never got that far: exit 2 or more (a crash, a missing interpreter).
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE="${FC08_KEYCHAIN_SERVICE:-uk.fc08.claude-oauth-token}"
SECURITY="${FC08_SECURITY:-/usr/bin/security}"
OSASCRIPT="${FC08_OSASCRIPT:-/usr/bin/osascript}"
PYTHON="${FC08_PYTHON:-$REPO/.venv/bin/python}"

notify() {
    "$OSASCRIPT" -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
        -e 'end run' "$1" "FC08 Friday run: CRASHED" >/dev/null 2>&1 || true
}

cd "$REPO" || { notify "The repository is not at $REPO."; exit 2; }
unset ANTHROPIC_API_KEY
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh start in $REPO"

FC08_TOKEN="$("$SECURITY" find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)"
if [ -z "$FC08_TOKEN" ]; then
    "$PYTHON" tools/friday_run.py --scheduled --refuse "no long-lived token in the login Keychain (service $SERVICE)"
    code=$?
else
    CLAUDE_CODE_OAUTH_TOKEN="$FC08_TOKEN" "$PYTHON" tools/friday_run.py --scheduled
    code=$?
fi
FC08_TOKEN=""
unset FC08_TOKEN
if [ "$code" -ge 2 ]; then
    notify "The run did not finish (exit $code). See ~/Library/Logs/uk.fc08.friday-run.log"
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh end, exit $code"
exit "$code"
