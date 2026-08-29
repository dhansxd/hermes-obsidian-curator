# Hermes Obsidian Curator

Native Hermes background review plugin dedicated to managing any Obsidian vault. It acts as an autonomous background curator that reviews your actual conversation history at configurable turn/tool intervals, audits canonical notes, and safely updates, merges, or creates notes without blind writes.

## Features

- **Global & Universal:** No hardcoded folder names or structures. Works on any Obsidian vault. On initial setup, recursively maps the vault structure to understand indexes, links, naming conventions, and governance notes.
- **Accurate History Snapshots:** Captures exact recent conversation turns (`user` & `assistant` messages) so the curator evaluates authentic session facts.
- **Flexible Capabilities (Cronjob-style):**
  - **Safe `file` + `skills` toolsets by default** (customizable via `allowed_toolsets`).
  - **Vault path enforcement** blocks file reads/writes/searches outside the configured vault.
  - **Tool-level blocking** via `blocked_tools`.
  - **Preloadable skills** via `skills` (loaded via `skill_view` before curation).
  - **Custom model override** via `model_override` in config or `model` in the setup tool (otherwise inherits the main chat model).
- **Configurable Hybrid Triggers:** Enable/disable turn triggers (`trigger_on_turns`) and tool-call triggers (`trigger_on_tools`) independently. Tool calls only count activity; automatic reviews wait for successful `post_llm_call`, after main agent finishes its full tool loop and final response.
- **Durable Rate-Limit Recovery:** A failed 429/quota review keeps bounded pending context and activity watermark in plugin state instead of discarding work.
  - With inherited parent model (`model_override: null`), next successful parent turn retries after model switch or same-model recovery.
  - With dedicated `model_override`, parent success alone does not retry; changing override or reaching provider reset time makes retry eligible at next completed parent-turn boundary.
  - No implicit fallback model.
- **Origin-Targeted Notifications:** Sends concise review summaries starting with `📝 Obsidian Review:` directly back to your active chat channel (Telegram, Discord, WhatsApp, etc.).

---

## 3-Step Quick Start (Beginner Friendly)

### 1. Install the Plugin
```bash
hermes plugins install https://github.com/dhansxd/hermes-obsidian-curator.git
```

### 2. Configure Your Vault & Preferences
Run setup through Hermes CLI or tell your AI agent:

```bash
hermes config set plugins.entries.obsidian-curator.settings.vault_path "/Users/yourname/Documents/Obsidian Vault"
hermes config set plugins.entries.obsidian-curator.settings.review_interval 20
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns true
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools true
```

Set your vault-specific curation governance rules:
```bash
hermes config set plugins.entries.obsidian-curator.settings.curator_prompt "Review recent chat history for decisions, project status changes, and durable knowledge. Read existing canonical notes first. Follow governance rules in index notes."
```

### 3. Run Initial Setup
Inside your Hermes chat session, tell Hermes:
> *"Tolong jalankan setup obsidian curator untuk vault-ku."*

Or invoke the setup tool directly:
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
| `vault_path` | string | *required* | Absolute path to your Obsidian vault directory. |
| `review_interval` | integer | `20` | Number of events (turns or tool calls) before running a review. |
| `curator_prompt` | string | *required* | Custom instructions telling the curator how to organize and curate your specific vault. |
| `trigger_on_turns` | boolean | `true` | When `true`, completed conversation turns count towards `review_interval`. |
| `trigger_on_tools` | boolean | `true` | When `true`, completed tool calls count towards `review_interval`. |
| `allowed_toolsets` | array | `["file", "skills"]` | Toolsets allowed for the curator. Add others only when your curator instructions require them. |
| `blocked_tools` | array | `[]` | Optional list of specific tool names to block (e.g. `["terminal"]`). |
| `skills` | array | `[]` | Optional list of skills to preload before curation (e.g. `["obsidian", "grounded-citations"]`). |
| `model_override` | string | `null` | Optional custom model override in plugin config. The setup tool accepts this as its `model` argument. Default inherits parent session. |

---

## Instructions for AI Agents Setting Up This Plugin

When a user asks you to configure or maintain Obsidian Curator:

1. **Verify Vault Path:** Always check that `vault_path` exists on disk using file tools before running setup.
2. **Review User Prompts:** Never hardcode vault paths or private file names inside repository code. Put user-specific guidelines into `curator_prompt`.
3. **Trigger Modes:**
   - **Hybrid (Recommended):** `trigger_on_turns: true`, `trigger_on_tools: true`.
   - **Turns Only:** `trigger_on_turns: true`, `trigger_on_tools: false`.
   - **Tools Only:** `trigger_on_turns: false`, `trigger_on_tools: true`.
   - **Manual Only:** Both `false` (setup still runs initial mapping, but background reviews stay quiet).
4. **Safety & Non-Destructive Operation:**
   - The curator agent runs with non-authoritative candidate evidence rules.
   - It must read existing notes before patching or writing new files.
   - All review outcomes report with `📝 Obsidian Review: <concise summary>`.
