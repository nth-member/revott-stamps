#!/usr/bin/env bash
# The cron entry, five minutes after each JOMO SFO-WAM feed refresh:
#   5-59/15 * * * * $HOME/revott-stamps/stage/cron.sh
# Logs to ~/.cache/revott-stamps/refresh.log, kept to its last 2000 lines.
LOG="$HOME/.cache/revott-stamps/refresh.log"
mkdir -p "$(dirname "$LOG")"
{ echo "== $(TZ=Africa/Lagos date '+%Y-%m-%d %H:%M') Nsukka"; "$(dirname "$0")/refresh.sh" --push; } >> "$LOG" 2>&1
tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
