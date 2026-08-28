# Obsidian Curator

One full native Hermes background agent whose only task is managing one Obsidian vault.

## Behavior

- **Initial mapping:** Recursively maps and reads every readable vault file before any write.
- **User-defined curation prompt:** The user and their AI agent define how the vault is managed during initial setup (`curator_prompt`). No hardcoded methodologies or vault structures.
- **Full native tool access:** The agent uses native Hermes tools directly (`read_file`, `search_files`, `write_file`, `patch`, `session_search`).
- **Flexible triggers:** Completed turns and completed tool calls can be enabled independently with `trigger_on_turns` and `trigger_on_tools`. Enabled events share `review_interval`. Set both to `false` to disable periodic reviews without disabling initial/manual setup.
- **Origin notifications:** Notifications starting with `Obsidian:` are delivered back to the originating chat/platform target (`telegram`, `discord`, `whatsapp`, etc.).
- **Anti-loop:** The curator agent's own activity does not trigger new curator runs.
- **Deterministic no-op:** If no changes are needed, the vault remains untouched.

## Install

```bash
hermes plugins install dhansxd/hermes-obsidian-curator --enable
hermes tools enable obsidian_curator --platform <platform>
```

Replace `<platform>` with your active surface (`telegram`, `discord`, `whatsapp`, `cli`, etc.). Restart gateway manually after installation so it loads the plugin.

## Setup

Set up the plugin by calling the `obsidian_curator` tool with:
- `operation`: `"setup"`
- `vault_path`: `/absolute/path/to/vault`
- `review_interval`: number of enabled trigger events between reviews (e.g. `20`)
- `curator_prompt`: specific instructions for auditing and curating your vault structure
- `trigger_on_turns`: count completed conversation turns (`true` by default)
- `trigger_on_tools`: count completed tool calls (`true` by default)

Trigger modes:

| Mode | `trigger_on_turns` | `trigger_on_tools` |
|---|---:|---:|
| Hybrid | `true` | `true` |
| Turns only | `true` | `false` |
| Tools only | `false` | `true` |
| Periodic reviews off | `false` | `false` |

Change switches later without rerunning initial mapping:

```bash
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_turns false
hermes config set plugins.entries.obsidian-curator.settings.trigger_on_tools true
```

Both `false` disables periodic reviews only. Initial/manual setup remains available.
