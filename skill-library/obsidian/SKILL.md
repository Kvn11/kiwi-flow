---
name: obsidian
description: Use when reading, writing, searching, or organizing notes in an Obsidian vault that the LLM maintains as a persistent, compounding knowledge base (wiki). Triggers on tasks like "add this source to the vault", "ingest into the brain", "what does the wiki say about X", "lint/audit the notes", or any work against the user's brain vault.
---

# Obsidian Knowledge-Base Skill

LLM-wiki operating model on top of the `obsidian` CLI. For any KB task: pick the operation (ingest / query / lint), open its guide, then drive the vault with the CLI.

## Prerequisites

- Obsidian 1.12+ running
- CLI enabled in Settings → General → "Command line interface"

## Vault Convention

Syntax: `obsidian vault=<name> <command> [params]`. Always pass `vault=` first.

Primary vault is `brain`. DeerFlow notes live under `DeerFlow/`. See `reference_brain_vault` memory for layout.

## Operating Model: LLM Wiki

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

Two navigation files anchor each section:

- **Content index** (e.g. `DeerFlow/MOC.md`) — every page listed with a one-line summary. Update on every ingest. Read first when querying.
- **Chronological log** (e.g. `log.md`, or daily notes) — append-only. Prefix entries `## [YYYY-MM-DD] ingest|query|lint | <title>` so `grep "^## \["` works.

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
