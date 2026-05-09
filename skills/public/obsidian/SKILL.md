---
name: obsidian
description: Use when reading, writing, searching, or organizing notes in an Obsidian vault — the persistent LLM wiki. Triggers on "add this source to the vault", "ingest into the brain", "synthesize and add to my notes", "what does the wiki say about X", "lint the notes". The vault is `brain`; the CLI is `obsidian` invoked via the bash tool (e.g. `bash -c 'obsidian vault=brain folders'`). Do NOT ask the user for the vault path or which CLI to use. Do NOT ask "what would you like me to do next" after the user has already said to ingest / add / write up / take notes — that instruction is the green light; go straight to the workflow.
---

# Obsidian Knowledge-Base Skill

**TL;DR — start here, do not ask the user:**

- Vault: `brain` (already exists on the host).
- CLI: `obsidian` (host shell binary). Call it via the **bash tool**, e.g. `bash -c 'obsidian vault=brain folders'`.
- There is no MCP tool, no API, no filesystem path you need. Every command in this skill is shell.
- Verify once: run `obsidian vault=brain folders` before writing. Folder list back → proceed. `command not found` → stop and report; do not write markdown files to a guessed directory.
- An empty folder list (just `/`) means the vault is empty, not missing. Proceed normally.

**No clarifying questions before starting.** If the user said "add to the vault", "ingest", "write up", "take notes on", or anything that names a source and a target, that is the full instruction — go. Do not ask "what would you like me to do next?" after reading the source. Do not ask "where is the vault?" or "which CLI?". Read the source → run the verify command → open `ingest.md` → execute the workflow. The only acceptable reason to stop and ask the user mid-task is a genuine ambiguity in the source itself (e.g. two plausible scopes the user must pick between), and even then ask once with a concrete proposal, not an open-ended menu.

## Prerequisites

- Obsidian 1.12+ running on the host
- CLI enabled in Settings → General → "Command line interface"

## Operating Model: LLM Wiki

For any KB task: pick the operation (ingest / query / lint), open its guide, then drive the vault with the CLI. Syntax: `obsidian vault=<name> <command> [params]` — always pass `vault=` first.

The vault is a persistent, compounding wiki — not RAG. The user curates sources and asks questions; you read, synthesize, file, and cross-reference. Knowledge accumulates; you do not re-derive on every query.

Three layers:

- **Raw sources** — code, docs, articles, transcripts. Immutable; read only.
- **The wiki** — markdown notes in the vault. Yours to maintain end-to-end.
- **The schema** — this skill + `CLAUDE.md` + memory entries. Defines layout and conventions.

Three operations:

| Operation | When | Guide |
|---|---|---|
| **Ingest** | New source enters the vault | [ingest.md](ingest.md) |
| **Query** | Answering against the wiki | [query.md](query.md) |
| **Lint** | Periodic health-check | [lint.md](lint.md) |

**No content-index / MOC notes.** Discovery is the CLI's job: `files folder=<section>`, `search query=...`, `tags`, `backlinks`/`links`, `outline`. A hand-curated index page just adds drift (entries pointing at moved files, files missing from the index) without giving the agent anything `files` doesn't.

**Keep the chronological log.** One `log.md` (per-section or vault-root). Append-only. Prefix entries `## [YYYY-MM-DD] ingest|query|lint | <title>` so `grep "^## \["` works. The log captures temporal context no CLI primitive surfaces.

**Section orientation notes are optional, not automatic.** Only create one when there's a frame the graph can't express (e.g. an applied operating model). Don't reflexively make a section overview per ingest.

## Naming Convention — filenames must match wikilink display

**Filenames are Title Case, with spaces, matching what you'd write inside `[[ ]]`.** A page titled "Thin Agent Fat Platform" lives at `agent-systems/Thin Agent Fat Platform.md`, and you reference it as `[[Thin Agent Fat Platform]]`. Both resolve.

Do not use kebab-case, snake_case, or lowercase filenames. Obsidian wikilinks resolve against the literal filename (case-insensitive on most platforms, but **not** across naming conventions). A file named `thin-agent-fat-platform.md` will **not** resolve from `[[Thin Agent Fat Platform]]` — they are different strings, and you will end up with an entire cluster of orphans and unresolved links.

If you find yourself slugifying for "URL safety" — stop. There are no URLs. The vault is filesystem + Obsidian; spaces in filenames are correct and idiomatic.

When linking to a page in a sub-folder, the wikilink can be the bare filename (`[[Thin Agent Fat Platform]]`) — Obsidian resolves it. Only disambiguate with a path (`[[agent-systems/Thin Agent Fat Platform]]`) when the same name exists in two folders.

**Verify after writing**: run `unresolved` once. Any entry means a wikilink doesn't match a filename — fix the wikilink (or rename the file), don't ship with broken links.

## CLI Basics

- **Parameters**: `param=value` (quote values with spaces)
- **Flags**: boolean switches with no value
- **Multiline**: `\n` for newlines, `\t` for tabs in `content=`
- **Structured output**: pass `format=json`
- **Nested paths**: use `path=<vault-relative-path>` — `name=` cannot contain slashes

## Quick Reference

| Category | Command | Description | Details |
|---|---|---|---|
| Explore | `files` | List vault files | [exploring.md](exploring.md) |
| Explore | `folders` | List folder structure | [exploring.md](exploring.md) |
| Explore | `outline` | Show headings for a file | [exploring.md](exploring.md) |
| Explore | `wordcount` | Word/character count | [exploring.md](exploring.md) |
| Explore | `templates` | List templates | [exploring.md](exploring.md) |
| Explore | `template:read` | Read a template's content | [exploring.md](exploring.md) |
| Read | `read` | Read file contents | [reading.md](reading.md) |
| Read | `daily:read` | Read today's daily note | [reading.md](reading.md) |
| Read | `property:read` | Get property value | [reading.md](reading.md) |
| Write | `create` | Create a new note | [writing.md](writing.md) |
| Write | `append` / `prepend` | Add content to file | [writing.md](writing.md) |
| Write | `daily:append` / `daily:prepend` | Add to daily note | [writing.md](writing.md) |
| Write | `property:set` | Set a property | [writing.md](writing.md) |
| Search | `search` | Text search vault | [searching.md](searching.md) |
| Search | `search:context` | Search with surrounding context | [searching.md](searching.md) |
| Search | `tags` / `tag` | List/inspect tags | [searching.md](searching.md) |
| Search | `properties` | List vault properties | [searching.md](searching.md) |
| Search | `aliases` | List vault aliases | [searching.md](searching.md) |
| Search | `backlinks` / `links` | Incoming/outgoing links | [searching.md](searching.md) |
| Search | `unresolved` | Broken/unresolved links | [searching.md](searching.md) |
| Search | `orphans` / `deadends` | Unlinked files | [searching.md](searching.md) |
| Organize | `move` / `rename` | Relocate/rename files | [organizing.md](organizing.md) |
| Organize | `delete` | Remove file | [organizing.md](organizing.md) |
| Organize | `property:remove` | Delete a property | [organizing.md](organizing.md) |

## Common Workflows

End-to-end (usual case): [ingest.md](ingest.md) · [query.md](query.md) · [lint.md](lint.md).

One-shot:
```
obsidian vault=<name> read file=<note>
obsidian vault=<name> create name=<note> content="..."
obsidian vault=<name> search query="..." format=json
obsidian vault=<name> daily:append content="..."
```
