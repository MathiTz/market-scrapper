#!/bin/bash
# PreToolUse hook for the Agent tool: cap at 2 agents total (main + 1 subagent).
MAX_EXTRA=1
dir="${CLAUDE_PROJECT_DIR:-.}/.claude/agent-guard"
mkdir -p "$dir"

# Slots older than 30 minutes are treated as leaked (crashed or denied agents).
find "$dir" -type f -mmin +30 -delete 2>/dev/null

live=$(find "$dir" -type f | wc -l | tr -d ' ')
if [ "$live" -ge "$MAX_EXTRA" ]; then
  echo "Blocked: agent cap reached. Max 2 agents at once (main + 1 subagent). Do the work inline or wait for the running subagent to finish." >&2
  exit 2
fi

touch "$dir/agent-$(date +%s)-$$"
exit 0
