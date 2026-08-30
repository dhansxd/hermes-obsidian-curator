# Hermes Obsidian Curator

Turn-triggered Obsidian vault curation through Hermes' native cron runner. Recent session history becomes non-authoritative evidence; curation runs outside the parent conversation and sends one summary to the origin channel.

## Architecture

- Hooks count eligible activity independently per Hermes `session_id`.
- At `review_interval`, or when an active session finalizes, plugin stores a durable review snapshot and invokes `cron.scheduler.run_job` on one background worker.
- Native cron runtime resolves model/provider/reasoning, loads configured skills, creates isolated cron session, runs tools, applies timeout handling, and tears down agent.
- One worker processes reviews sequentially so concurrent platform sessions do not modify vault together.
- Failed reviews remain durable and retry with bounded exponential backoff. Pending reviews resume after gateway restart.
- Cron sessions are excluded from counters, preventing self-trigger loops.

## Safety

- `enabled_toolsets` accepts only `file` and `skills`.
- Unknown or unsafe tools are blocked for curator cron sessions.
- File operations must use absolute paths inside configured `vault_path`.
- Conversation history and general note contents are treated as untrusted data.

## Quick Start

```bash
hermes plugins install https://github.com/dhansxd/hermes-obsidian-curator.git
hermes config set plugins.entries.obsidian-curator.settings.vault_path "/Users/yourname/Documents/Obsidian Vault"
hermes config set plugins.entries.obsidian-curator.settings.review_interval 20
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns true
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools false
```

Set vault-specific rules:

```bash
hermes config set plugins.entries.obsidian-curator.settings.curator_prompt "Review recent chat history for decisions, project status changes, and durable knowledge. Read existing canonical notes first. Follow governance rules in index notes."
```

Initial setup tool call:

```json
{
  "operation": "setup",
  "vault_path": "/Users/yourname/Documents/Obsidian Vault",
  "review_interval": 20,
  "curator_prompt": "Audit recent chat history and update canonical notes.",
  "enabled_toolsets": ["file", "skills"]
}
```

## Configuration

| Setting | Type | Default | Description |
|---|---|---|---|
| `vault_path` | string | required | Existing absolute vault directory. |
| `review_interval` | integer | required | Eligible events per session before review. |
| `curator_prompt` | string | required | Vault-specific curation rules. |
| `trigger_on_turns` | boolean | `true` | Completed turns count toward interval. |
| `trigger_on_tools` | boolean | `true` | Completed non-blocked tool calls count and can trigger review. |
| `enabled_toolsets` | array | `["file", "skills"]` | Safe cron toolsets; no other values accepted. |
| `blocked_tools` | array | `[]` | Extra individual tools to block. |
| `skills` | array | `[]` | Skills loaded by native cron runtime. |
| `model_override` | string | `null` | Cron model override. |
| `provider` | string | `null` | Cron provider override. |
| `base_url` | string | `null` | Cron provider base URL override. |
| `reasoning_effort` | string | `null` | Cron reasoning effort override. |
| `workdir` | string | `null` | Cron working directory. File sandbox remains vault-scoped. |

## Session Behavior

| Event | Behavior |
|---|---|
| Session reaches interval | Durable review queued for only that session. |
| Multiple sessions become due | Reviews run sequentially; history and counters stay isolated. |
| `/new`, reset, or finalize with activity | Remaining history queues immediately. |
| Session opened and closed without activity | No review. |
| New activity arrives during review | Only reviewed count is deducted; newer activity remains. |
| Gateway restarts | Pending durable reviews resume. |
| Review fails | Counter and snapshot remain; bounded retry starts. |
