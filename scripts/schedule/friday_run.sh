#!/bin/bash
# FC08 Friday run, started by launchd (scripts/schedule/uk.fc08.friday-run.plist, installed by the OWNER with
# tools/schedule.py install). Bash 3.2: no arrays of pairs, no mapfile.
#
# THE TOKEN. The long-lived subscription token (`claude setup-token`, run by the owner) lives in the login
# Keychain under service uk.fc08.claude-oauth-token. This script reads it into ONE variable and hands it to the
# Python run as CLAUDE_CODE_OAUTH_TOKEN in that command's environment only. It is never written to a file,
# never printed, never on a command line, never in the plist or the log, and never exported (so it does not
# reach any later command, including the notify() below). ANTHROPIC_API_KEY is unset first: it takes
# precedence over the token and bills pay-as-you-go (CLAUDE.md, Auth). CLAUDE_CODE_OAUTH_TOKEN is ALSO unset
# first (fix round 2, N-2): under launchd this is a no-op, but a shell the owner already exported a real token
# into (e.g. Claude Code's own session) must not leak it into `security` or a crash's own `osascript` call --
# the ONE token that ever reaches Python is the one this script itself reads from the Keychain below.
#
# ONE NOTICE -- THE EXIT-CODE CONTRACT (fix round 1, I-1/I-2; see tools/friday_run.py's docstring). The notice
# is an ALERT WINDOW (`display alert ... giving up after 86400`), not a notification: `display notification`
# was measured accepted (exit 0) but never shown on the owner's Mac, with no Script Editor entry in System
# Settings -> Notifications to grant -- there was nothing to fix by permissioning. `display alert` was
# measured working. tools/friday_run.py --scheduled posts the one alert itself (the report's first two lines)
# and signals that it did so with its exit code: 0 (acceptable) or NOTIFIED_EXIT below (refused/failed). ANY
# OTHER exit code -- 1 (its own notify() call failed, though the run itself finished), 2 (a bad flag), 3 (a
# crash) or anything else (an import-time failure, a missing interpreter, a broken venv) -- means Python
# posted NOTHING, and this script posts the one alert instead, worded to say only what is true of every one of
# those cases: it did not post its own alert, not that it necessarily "did not finish" (fix round 2, N-4).
# This is checked against the EXACT reserved value, never a `>=` threshold: a threshold reads a larger
# "acceptable" code range as "already notified" the moment the reserved value crosses it.
set -u
set +o xtrace +o verbose  # defensive: neither an inherited launchd env nor `bash -x` prints the token
NOTIFIED_EXIT=10          # tools/friday_run.py's SCHEDULED_NOTIFIED_EXIT -- keep the two literals in sync
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE="${FC08_KEYCHAIN_SERVICE:-uk.fc08.claude-oauth-token}"
SECURITY="${FC08_SECURITY:-/usr/bin/security}"
OSASCRIPT="${FC08_OSASCRIPT:-/usr/bin/osascript}"
PYTHON="${FC08_PYTHON:-$REPO/.venv/bin/python}"
# The Keychain account. launchd normally sets USER for a LaunchAgent, but under `set -u` an unset USER would
# kill the read below and REFUSE with a misleading "no token" (final review, M-3): fall back to id -un.
ACCOUNT="${USER:-$(id -un)}"

# display alert ... giving up after 86400 BLOCKS osascript until the owner clicks OK or 24h elapses, so it must
# never run in the foreground here: backgrounded with `&` and detached from job control with `disown`, so this
# function -- and the script -- returns immediately, and the alert window outlives the script's own exit. The
# words still reach osascript as ARGUMENTS after `--`, never spliced into the AppleScript source.
notify() {
    "$OSASCRIPT" -e 'on run argv' \
        -e 'display alert (item 1 of argv) message (item 2 of argv) giving up after 86400' \
        -e 'end run' -- "FC08 Friday run: CRASHED" "$1" >/dev/null 2>&1 &
    disown 2>/dev/null || true
}

cd "$REPO" || { notify "The repository is not at $REPO."; exit 2; }
unset ANTHROPIC_API_KEY
unset CLAUDE_CODE_OAUTH_TOKEN
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh start in $REPO"

FC08_TOKEN="$("$SECURITY" find-generic-password -a "$ACCOUNT" -s "$SERVICE" -w 2>/dev/null)"
if [ -z "$FC08_TOKEN" ]; then
    "$PYTHON" tools/friday_run.py --scheduled --refuse "no long-lived token in the login Keychain (service $SERVICE)"
    code=$?
else
    CLAUDE_CODE_OAUTH_TOKEN="$FC08_TOKEN" "$PYTHON" tools/friday_run.py --scheduled
    code=$?
fi
FC08_TOKEN=""
unset FC08_TOKEN
if [ "$code" -ne 0 ] && [ "$code" -ne "$NOTIFIED_EXIT" ]; then
    notify "The run did not post its alert (exit $code). See ~/Library/Logs/uk.fc08.friday-run.log"
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh end, exit $code"
exit "$code"
