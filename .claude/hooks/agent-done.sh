#!/bin/bash
# SubagentStop hook: free the oldest slot taken by agent-cap.sh.
dir="${CLAUDE_PROJECT_DIR:-.}/.claude/agent-guard"
oldest=$(ls -tr "$dir" 2>/dev/null | head -n 1)
[ -n "$oldest" ] && rm -f "$dir/$oldest"
exit 0
