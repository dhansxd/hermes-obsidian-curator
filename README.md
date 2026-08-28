# Obsidian Curator

One full native Hermes background agent whose only task is managing one Obsidian vault.

## Behavior

- **Initial mapping:** Recursively maps and reads every readable vault file before any write.
- **User-defined curation prompt:** The user and their AI agent define how the vault is managed during initial setup (`curator_prompt`). No hardcoded methodologies or vault structures.
- **Full native tool access:** The agent uses native Hermes tools directly (`read_file`, `search_files`, `write_file`, `patch`, `session_search`).
- **Hybrid trigger:** Subsequent reviews trigger after a configurable number of eligible completed turns and tool calls (`review_interval`).
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
- `review_interval`: number of turns + tool calls between reviews (e.g. `20`)
- `curator_prompt`: specific instructions for auditing and curating your vault structure
