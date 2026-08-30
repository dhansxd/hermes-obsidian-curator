# Hermes Obsidian Curator

Native Hermes background agent for Obsidian vault curation. Runs as an isolated cronjob-style worker: triggered by turn/tool intervals, reads last N turns, curates vault, delivers single notification—completely decoupled from parent session.

## Architecture (v0.7.0)

- **Cronjob-style execution** — not a delegation subagent. When `activity_count >= review_interval` (or session resets), spawns a standalone `AIAgent` on a daemon thread with:
  - `enabled_toolsets=["file", "skills"]`
  - `quiet_mode=True`, `skip_memory=True`, `skip_context_files=True`, `skip_background_review=True`
  - `platform="obsidian_curator"` (hooks ignore it)
- **Zero delegation injection** — no `delegate_tool`, no async delegation queue. Output goes once to origin chat via `send_message_tool`.
- **Simple state** — single `activity_count` counter, recent history LRU cache per session. No platform queues, sealed batches, correlation IDs, retry backoff plumbing.
- **Session switch flush** — `/new` or session reset with unreviewed activity triggers immediate curation so facts aren't lost.
- **Anti-loop** — child's `session_id` tracked in `_ACTIVE_CURATOR_SESSION_ID`; all hooks skip when session matches.

## Features

- **Universal vault** — no hardcoded folders. Initial setup recursively maps vault structure.
- **Accurate history** — exact last N `user`/`assistant` turns passed as non-authoritative candidate evidence.
- **Safety sandbox** — `pre_tool_call` blocks file ops outside configured `vault_path`; `delegate_task`, `skill_manage` always blocked.
- **Hybrid triggers** — `trigger_on_turns`, `trigger_on_tools` independently configurable. Tool calls only count activity; launches wait for `post_llm_call` boundary.
- **Rate-limit recovery** — failed 429 reviews persist pending context + watermark, retry on next safe turn (model switch or backoff elapsed).
- **Origin-targeted notification** — `📝 Obsidian Review: <summary>` sent once to Telegram/Discord/WhatsApp channel.

---

## 3-Step Quick Start

### 1. Install the Plugin
```bash
hermes plugins install https://github.com/dhansxd/hermes-obsidian-curator.git
```

### 2. Configure Your Vault & Preferences
```bash
hermes config set plugins.entries.obsidian-curator.settings.vault_path "/Users/yourname/Documents/Obsidian Vault"
hermes config set plugins.entries.obsidian-curator.settings.review_interval 20
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns true
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools true
```

Set vault-specific curation rules:
```bash
hermes config set plugins.entries.obsidian-curator.settings.curator_prompt "Review recent chat history for decisions, project status changes, and durable knowledge. Read existing canonical notes first. Follow governance rules in index notes."
```

### 3. Run Initial Setup
Inside Hermes chat:
> *"Tolong jalankan setup obsidian curator untuk vault-ku."*

Or invoke tool directly:
```json
{
  "operation": "setup",
  "vault_path": "/Users/yourname/Documents/Obsidian Vault",
  "review_interval": 20,
  "curator_prompt": "Audit recent chat history and update canonical notes."
}
```

---

## Configuration Reference

| Setting | Type | Default | Description |
|---|---|---|---|
| `vault_path` | string | *required* | Absolute path to Obsidian vault directory. |
| `review_interval` | integer | `20` | Events (turns or tool calls) before background review. |
| `curator_prompt` | string | *required* | Custom instructions for curating this vault. |
| `trigger_on_turns` | boolean | `true` | Completed turns count toward interval. |
| `trigger_on_tools` | boolean | `true` | Completed tool calls count toward interval. |
| `allowed_toolsets` | array | `["file", "skills"]` | Fixed — only `file` and `skills` accepted. |
| `blocked_tools` | array | `[]` | Optional individual tools to block. |
| `skills` | array | `[]` | Skills to preload via `skill_view` before curation. |
| `model_override` | string | `null` | Custom model for curator (null = inherit parent). |

---

## Instructions for AI Agents Setting Up This Plugin

1. **Verify Vault Path** — check `vault_path` exists on disk before setup.
2. **User Prompts Only** — never hardcode vault paths in repo code; put user rules in `curator_prompt`.
3. **Trigger Modes:**
   - **Hybrid (default):** `trigger_on_turns: true`, `trigger_on_tools: true`
   - **Turns Only:** `trigger_on_turns: true`, `trigger_on_tools: false`
   - **Tools Only:** `trigger_on_turns: false`, `trigger_on_tools: true`
   - **Manual:** both `false` (initial mapping still runs, background reviews disabled)
4. **Safety & Non-Destructive:**
   - Curator runs with non-authoritative candidate evidence rules.
   - Must read existing notes before patching/writing.
   - Reports with `📝 Obsidian Review: <concise summary>`.

---

## Session Behavior

| Event | Behavior |
|---|---|
| `post_llm_call` reaches `review_interval` | Spawns background worker; curates last N turns. |
| `post_tool_call` | Increments counter only; never launches mid-turn. |
| `/new` / `on_session_reset` / `on_session_finalize` with `activity_count > 0` | Immediately launches curator for abandoned session, then resets counter. |
| Curator running (thread alive) | New triggers are deferred until current worker finishes. |
| Curator session (`platform="obsidian_curator"`) | All hooks skip — no self-triggering, no double-counting. |
| Rate limit (429) | Saves `pending_review` with retry watermark; auto-retries on next safe turn after model switch or backoff. |