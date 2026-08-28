# Obsidian Curator

> **Beginner-friendly Hermes Agent plugin** that turns a standard Hermes AI agent into a dedicated background Obsidian curator.

The curator is not a separate engine or custom wrapper—it runs as a native Hermes agent with full tool access (`read_file`, `search_files`, `write_file`, `patch`, `session_search`). Its single purpose is keeping your Obsidian vault clean, organized, canonical, and link-accurate in the background.

---

## Features

- 🚀 **Beginner Friendly:** Clear 3-step setup for both humans and AI assistants.
- 📂 **Initial Full-Vault Read:** Recursively maps and reads every Markdown file to EOF before making its very first write.
- 🎯 **No Hardcoded Rules:** You and your AI agent write your own `curator_prompt` during setup to match your specific vault structure and methodology (e.g. PARA, Johnny Decimal, Atlas, or flat).
- 🔀 **Flexible Hybrid Triggers:** Turn-based triggers and tool-based triggers can each be turned on or off independently.
- 💬 **Origin Notifications:** Completed reviews automatically deliver a clean summary starting with `Obsidian:` back to the exact platform, chat, or thread where the activity happened (Telegram, Discord, WhatsApp, etc.).
- 🛡️ **Anti-Loop:** The curator’s own activity does not increment trigger counters or spawn infinite background loops.
- 🟢 **Deterministic No-Op:** If no updates or fixes are safely justified, your vault remains completely untouched.

---

## 📖 Guide for Humans (Quick Start)

### Step 1: Install and Enable the Plugin

Run this in your terminal:

```bash
hermes plugins install dhansxd/hermes-obsidian-curator --enable
```

If you chat with Hermes over messaging platforms (like Telegram, Discord, or WhatsApp), enable the toolset for that platform (or omit `--platform` for CLI):

```bash
hermes tools enable obsidian_curator --platform telegram
# Repeat for other platforms if needed:
# hermes tools enable obsidian_curator --platform discord
# hermes tools enable obsidian_curator --platform whatsapp
```

Verify installation:

```bash
hermes plugins doctor obsidian-curator
```

Expected result: plugin version appears with `OK`, `1 tool(s)`, and `5 hook(s)`.

### Step 2: Restart Your Hermes Gateway

For the new plugin code and hooks to be loaded into memory, restart Hermes:

```bash
# If running as a background service:
hermes gateway restart

# Or if running interactive chat / CLI:
# simply exit and start Hermes again.
```

### Step 3: Back Up Your Vault, Then Ask Hermes to Set It Up

Because the curator can edit, move, archive, and delete notes when your rules allow it, make a backup or Git snapshot before first setup.

Then paste this into your chat with Hermes:

> *"Please set up Obsidian Curator for my vault at `/Users/yourname/Documents/MyVault`. First inspect my vault's entry note and structure. Help me draft a custom curator prompt and choose a trigger mode. Show me the final vault path, prompt, review interval, and trigger settings for confirmation before calling setup."*

After you approve the settings, Hermes calls the setup tool. Initial mapping runs in the background, and Hermes sends an `Obsidian:` notification when finished.

---

## 🤖 Guide for AI Assistants (Agent Instructions)

When a user asks you to configure or maintain Obsidian Curator, follow this exact workflow:

### 1. Inspect the User's Vault First
Before calling `setup`, use `read_file` or `search_files` to discover:
- The main entry note (e.g. `Home.md`, `README.md`, `INDEX.md`, or root folder structure).
- Any existing vault rules, folders (e.g., `01 Capture`, `Projects`, `Areas`, `System`), or tag taxonomy.

### 2. Formulate a Strong `curator_prompt`
Compose a clear, concise instruction block (maximum 12,000 characters). Include:
- Which files/notes are authoritative governance (if any).
- Instructions to perform full canonical checking, duplicate detection, link verification, and folder placement.
- Rules to treat ongoing chat transcripts as **candidate evidence only** (never copy transcripts blindly).
- Instruction to preserve provenance and make zero unneeded changes (no-op when clean).

### 3. Call the `obsidian_curator` Setup Tool
Invoke the tool with:

```json
{
  "operation": "setup",
  "vault_path": "/absolute/path/to/vault",
  "review_interval": 20,
  "curator_prompt": "Your formulated curation prompt here...",
  "trigger_on_turns": true,
  "trigger_on_tools": true
}
```

*The tool immediately dispatches the native agent to run the initial recursive mapping and full vault read in the background.*

---

## ⚙️ Trigger Configuration

You can customize which events count toward the periodic background review interval:

| Mode | `trigger_on_turns` | `trigger_on_tools` | Description |
|---|:---:|:---:|---|
| **Hybrid (Default)** | `true` | `true` | Both completed turns and tool calls increment the review counter. |
| **Turns Only** | `true` | `false` | Only completed conversation turns trigger background review. |
| **Tools Only** | `false` | `true` | Only completed tool executions trigger background review. |
| **Periodic Off** | `false` | `false` | Periodic background reviews disabled. Initial & manual setup still works. |

### Adjusting Triggers On The Fly

You can switch modes anytime without rerunning initial vault mapping:

```bash
# Example: switch to turns only
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns true
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools false

# Example: change the interval
hermes config set plugins.entries.obsidian-curator.settings.review_interval 30
```

---

## 🔍 How It Works

1. **Initial Setup Run:**
   The agent recursively reads all readable Markdown notes in the vault to build internal context before any write or modification happens.
2. **Background Counting:**
   As you talk to Hermes or as tools execute, the plugin increments a lightweight activity counter based on your active trigger settings.
3. **Periodic Autonomous Review:**
   When `review_interval` is reached, Hermes launches a background subagent (`role="orchestrator"`). The curator audits changes, canonical notes, duplicates, and orphans.
4. **Origin Notification:**
   Once finished, the curator sends a message starting with `Obsidian: ...` directly to the chat where the trigger occurred.

---

## ❓ FAQ & Troubleshooting

- **Do I need to restart the gateway after changing `review_interval` or triggers via `hermes config set`?**
  No, configuration values are read dynamically on every trigger check.
- **Why hasn't the curator sent any message?**
  If no changes or fixes were needed, the curator performs a silent or concise no-op. Also check if `review_interval` has been reached.
- **Can I manage multiple vaults?**
  Each Hermes profile manages one active vault path. Use Hermes profiles (`hermes --profile work`) to manage separate vaults.

---

## 📄 License

MIT License. Built with ❤️ for the Hermes Agent ecosystem.
