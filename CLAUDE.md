# Market Scrapper — project rules

## Agent limits (hard rules)

- Never have more than **2 agents alive at once**. The main session agent counts as one, so at most **one** extra subagent may exist at any moment.
- Default is zero extra agents. Do exploration, analysis, and edits inline with Read, Bash, Edit, and parallel tool calls. Only spawn a subagent when the user explicitly asks for one.
- Never spawn agents from inside a subagent (no nesting, no forks, no parallel explorer fan-out).
- Enforced by hooks in `.claude/settings.json`: `.claude/hooks/agent-cap.sh` blocks the Agent tool once the cap is reached, and `.claude/hooks/agent-done.sh` frees a slot when a subagent stops. Do not edit or bypass these hooks without the user's say-so.

## Shell

- The Bash tool must run zsh (`CLAUDE_CODE_SHELL=/bin/zsh` in `~/.claude/settings.json`). fish stalls on startup here and makes every command time out.
