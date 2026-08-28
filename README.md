# Obsidian Curator

One full native Hermes background agent whose only task is managing one Obsidian vault.

## Behavior

- Initial setup recursively maps and reads every readable vault file before any write.
- Later reviews launch after a configurable number of completed parent turns.
- The agent uses native `session_search`, `read_file`, `search_files`, `write_file`, and `patch` directly.
- Vault structure, canonical notes, and edit method are discovered rather than hardcoded.
- No important knowledge means no vault changes.
- Curator activity does not trigger another curator run.

## Install

```bash
hermes plugins install dhansxd/hermes-obsidian-curator --enable
hermes tools enable obsidian_curator --platform <platform>
```

Replace `<platform>` with your active surface, such as `telegram`, `discord`, `whatsapp`, or `cli`. Restart gateway manually after installation so it loads the plugin.

## Setup

Tell Hermes:

> Set up Obsidian Curator for `/absolute/path/to/vault` with review interval `N` completed turns.

Setup launches the same background agent used for later reviews. It returns immediately while the initial full-vault mapping continues in the background.
