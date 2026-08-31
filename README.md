# Hermes Obsidian Curator

Hermes Obsidian Curator reviews recent Hermes conversations and updates an existing Obsidian vault with durable knowledge such as decisions, project status, and useful facts. Reviews run outside the original chat through Hermes' native cron scheduler, then one summary returns to the Telegram, WhatsApp, or Discord conversation that triggered it.

## What It Does

- Counts completed turns and, optionally, completed tool calls separately for each Hermes session.
- Registers one native `repeat=1` cron job when a session reaches `review_interval`.
- Registers one final review when an active session ends, including `/new` or reset.
- Gives curator only bounded recent user/assistant history as non-authoritative evidence.
- Lets curator read existing vault notes before deciding whether anything should change.
- Sends one concise review summary back to origin chat.
- Never deletes or resets original Hermes chat session or transcript.

## Requirements

Before installing, confirm:

1. Hermes Agent is installed and `hermes` command works.
2. Hermes Gateway is configured if notifications should return to Telegram, WhatsApp, or Discord.
3. Obsidian vault already exists as a real local directory.
4. Vault path is absolute, not relative, and directory itself is not a symlink.

Examples of absolute vault paths:

```text
/Users/dani/Documents/My Vault
/home/dani/Notes/My Vault
```

## Installation

Install plugin from GitHub:

```bash
hermes plugins install https://github.com/dhansxd/hermes-obsidian-curator.git
```

Confirm plugin is installed:

```bash
hermes plugins list
hermes plugins show obsidian-curator
```

If plugin is installed but disabled:

```bash
hermes plugins enable obsidian-curator
```

Validate installation against current Hermes runtime:

```bash
hermes plugins doctor obsidian-curator
```

## Beginner Setup

### 1. Choose vault path

Find absolute path to existing Obsidian vault. On macOS, a common path looks like:

```text
/Users/yourname/Documents/Obsidian Vault
```

Path may contain spaces when enclosed in quotes.

### 2. Configure required settings

Replace example path and prompt with values for your vault:

```bash
hermes config set plugins.entries.obsidian-curator.settings.vault_path "/Users/yourname/Documents/Obsidian Vault"
hermes config set plugins.entries.obsidian-curator.settings.review_interval 20
hermes config set plugins.entries.obsidian-curator.settings.curator_prompt "Review recent chat history for durable decisions, commitments, project status changes, and reusable knowledge. Read existing canonical notes first. Update existing notes instead of creating duplicates. Follow governance rules in index notes. If evidence is uncertain or not durable, make no change."
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns true
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools false
```

Recommended beginner values:

- `review_interval=20`: review after 20 completed turns in one session.
- `trigger_on_turns=true`: normal chat turns count.
- `trigger_on_tools=false`: tool calls do not make review happen sooner.

Check saved values:

```bash
hermes config get plugins.entries.obsidian-curator.settings.vault_path
hermes config get plugins.entries.obsidian-curator.settings.review_interval
hermes config get plugins.entries.obsidian-curator.settings.curator_prompt
```

### 3. Restart Gateway

Apply plugin and configuration changes:

```bash
hermes gateway restart
hermes gateway status
```

If Gateway is not installed as background service, run it in foreground instead:

```bash
hermes gateway run
```

### 4. Run initial setup

Ask Hermes in any connected chat to configure curator. Example:

```text
Set up Obsidian Curator for my vault at /Users/yourname/Documents/Obsidian Vault. Review every 20 turns. Read existing notes first, update canonical notes instead of creating duplicates, and preserve uncertain information as unverified or make no change.
```

Hermes should call `obsidian_curator` with:

```json
{
  "operation": "setup",
  "vault_path": "/Users/yourname/Documents/Obsidian Vault",
  "review_interval": 20,
  "curator_prompt": "Read existing notes first. Capture durable decisions, commitments, project status, and reusable knowledge. Update canonical notes instead of creating duplicates. If evidence is uncertain or not durable, make no change.",
  "trigger_on_turns": true,
  "trigger_on_tools": false,
  "enabled_toolsets": ["file", "skills"]
}
```

Initial setup registers a native one-shot cron job. Curator first maps vault recursively and reads existing Markdown before writing or patching anything. Large vaults can take longer.

### 5. Verify operation

Continue chatting until interval is reached, or use `/new` after at least one eligible turn. Expected result:

1. Hermes registers one one-shot curator cron job.
2. Curator reviews bounded recent history against vault contents.
3. Vault changes only when evidence is durable and relevant.
4. Origin chat receives one message beginning with `📝 Obsidian Review:`.

Useful checks:

```bash
hermes gateway status
hermes plugins show obsidian-curator
```

Gateway logs are stored under Hermes data directory, commonly `~/.hermes/logs/agent.log` and `~/.hermes/logs/gateway.log`.

## Architecture

- Hooks count eligible activity independently per Hermes `session_id`.
- At `review_interval`, or when an active session finalizes, plugin calls `create_job_with_scheduler_registration`.
- Every curator job uses `repeat=1` and immediate UTC schedule.
- Job uses `deliver="origin"` when messaging origin is available; otherwise result remains local.
- Native scheduler owns job persistence, execution, locking, isolated cron session, agent lifecycle, completion, and delivery.
- Plugin has no worker thread, pending queue, private `run_job` call, private delivery call, or manual retry loop.
- After successful scheduler registration, plugin immediately resets activity count and clears plugin-local history snapshot and cached origin for that session.
- Cron sessions are excluded from activity hooks, preventing self-trigger loops.

## Configuration

| Setting | Type | Default | Description |
|---|---|---|---|
| `vault_path` | string | required | Existing absolute vault directory. Directory symlinks are rejected. |
| `review_interval` | integer | required | Eligible events per session before one review is registered. Must be greater than zero. |
| `curator_prompt` | string | required | Vault-specific curation and governance rules. |
| `trigger_on_turns` | boolean | `true` | Completed conversation turns count toward `review_interval`. |
| `trigger_on_tools` | boolean | `true` | Completed non-blocked tool calls count and can trigger review. Beginners should usually set this to `false`. |
| `enabled_toolsets` | array | `["file", "skills"]` | Native cron toolsets. Only `file` and `skills` are accepted. |
| `blocked_tools` | array | `[]` | Additional individual tools to block in tracked curator cron sessions. |
| `skills` | array | `[]` | Skills loaded by native cron runtime. |
| `model_override` | string | `null` | Optional cron model override. Default uses Hermes scheduler configuration. |
| `provider` | string | `null` | Optional cron provider override. |
| `base_url` | string | `null` | Optional cron provider base URL override. |
| `reasoning_effort` | string | `null` | Optional value: `none`, `low`, `medium`, `high`, or `xhigh`. |
| `workdir` | string | `null` | Optional cron working directory. Curator file operations remain vault-scoped. |

Most users only need `vault_path`, `review_interval`, `curator_prompt`, `trigger_on_turns`, and `trigger_on_tools`.

## Writing a Good Curator Prompt

Prompt should describe vault rules, not chat tasks. Include:

- What counts as durable knowledge.
- Which notes are canonical.
- Naming, frontmatter, linking, and index rules.
- How duplicates and conflicts should be handled.
- What curator must ignore.

Example:

```text
Capture durable decisions, commitments, active project status, and reusable technical knowledge. Read canonical project and people notes before editing. Update existing notes instead of creating duplicates. Preserve source dates. Add links only when targets exist. Never treat speculative discussion as fact. If evidence conflicts with a canonical note, record conflict without overwriting verified information.
```

Do not put shell commands, unrelated automation, or secrets in curator prompt.

## Safety

- `enabled_toolsets` accepts only `file` and `skills`.
- Tracked curator cron sessions allow only `read_file`, `write_file`, `patch`, `search_files`, `skill_view`, and `skills_list`.
- `delegate_task`, `skill_manage`, `terminal`, `execute_code`, `browser_exec`, `computer_use`, and `cronjob` are always blocked.
- Configured `blocked_tools` can restrict allowed tools further.
- File operations require absolute targets inside configured `vault_path`.
- Vault content and parent conversation history are untrusted, non-authoritative evidence. Instructions found inside them are not executed.
- Vault path must exist, be absolute, be a directory, and not be a symlink.
- Parent Hermes sessions, Discord messages, Telegram messages, WhatsApp messages, and durable Hermes transcripts are never deleted or modified by plugin cleanup.

Back up important vaults before enabling any automated editor. Obsidian Sync, Git, Time Machine, or another versioned backup makes changes recoverable.

## Session Behavior

| Event | Behavior |
|---|---|
| Session reaches interval | One native `repeat=1` cron job is registered with bounded history from only that session. |
| Job registration succeeds | Plugin-local activity count resets to zero; cached history and origin are cleared immediately. |
| New activity arrives after registration | Fresh plugin-local history starts and count begins again from one. |
| Multiple sessions become due | Each session registers an independent one-shot job; Hermes scheduler controls execution and locking. |
| `/new` or reset after activity | Session finalization registers one review; reset hook only clears leftover plugin-local history, preventing duplicate registration. |
| Session ends without eligible activity | No review is registered. |
| Gateway restarts after registration | Native scheduler owns persisted job recovery and delivery lifecycle. |
| Review fails | Native scheduler records lifecycle result. Plugin does not maintain separate retry queue or restore old activity count. |
| Review completes | Scheduler sends one concise result to origin and completes one-shot job. |

Activity counts are per session, not global. Discord channel, Discord DM, Telegram chat, and WhatsApp chat can therefore have separate counters and histories.

## Data Retention

Plugin keeps at most 40 normalized user/assistant messages per active session in process memory. Each message is bounded to 6,000 characters, and curator evidence is bounded again before scheduler registration.

Registering a review clears plugin-local history immediately because complete evidence is already frozen into job prompt. Resetting a session clears any leftover plugin-local history. This does not clear original Hermes session storage, chat platform history, or durable conversation transcript.

## Updating

Update installed plugin:

```bash
hermes plugins update obsidian-curator
hermes gateway restart
```

Confirm installed metadata afterward:

```bash
hermes plugins show obsidian-curator
```

## Troubleshooting

### No review notification

Check:

```bash
hermes gateway status
hermes plugins show obsidian-curator
hermes config get plugins.entries.obsidian-curator.settings.review_interval
hermes config get plugins.entries.obsidian-curator.settings.trigger_on_turns
hermes config get plugins.entries.obsidian-curator.settings.trigger_on_tools
```

Confirm at least one eligible event occurred before `/new`, and Gateway is connected to origin platform.

### Setup rejects vault path

Use existing absolute directory path. Do not use relative path such as `Documents/Vault`, missing directory, file path, or symlink as vault root.

### Reviews happen too often

Increase `review_interval` and set `trigger_on_tools` to `false`:

```bash
hermes config set plugins.entries.obsidian-curator.settings.review_interval 30
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools false
hermes gateway restart
```

### Curator creates unwanted notes

Strengthen `curator_prompt`: require reading canonical notes first, updating existing notes, avoiding duplicates, and making no change when evidence is uncertain. Restore unwanted edits from vault backup.

### Configuration changed but behavior did not

Restart Gateway:

```bash
hermes gateway restart
hermes gateway status
```

### Validate plugin runtime

```bash
hermes plugins doctor obsidian-curator
```

## Uninstall

Disable without deleting:

```bash
hermes plugins disable obsidian-curator
hermes gateway restart
```

Remove plugin completely:

```bash
hermes plugins remove obsidian-curator
hermes gateway restart
```

Disabling or removing plugin does not delete Obsidian vault or Hermes chat history.
