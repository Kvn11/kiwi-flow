# Lint: Health-Check the Wiki

Triggered by "lint the wiki", "audit the brain vault", "check for stale notes". Most findings are mechanical (fix in-pass); contradictions and stale claims need user judgment.

## Structural checks

Run in order; collect findings before fixing.

| Check | Command | Looking for |
|---|---|---|
| Broken links | `unresolved format=json` | Wikilinks to non-existent files (typos, deleted, renames not propagated) |
| Orphans | `orphans` | No inbound links — usually a missing reference, not a useless page |
| Dead ends | `deadends` | No outbound links — under-developed or never integrated |
| Tag drift | `tags counts format=json` | Singletons suggest typos or fragmented categories |
| Property drift | `properties counts format=json` | Inconsistent frontmatter across pages of the same `type` |
| Index drift | `read file=MOC` + `files ext=md folder=<section>` | Files missing from the index, or index entries pointing at moved/deleted files |

## Semantic checks (manual review)

- **Contradictions** — read recent `log.md` ingests, cross-check against older entity pages.
- **Stale claims** — properties or numbers newer sources have updated.
- **Missing concept pages** — terms appearing across pages with no dedicated page (`search query="<term>"`).
- **Synthesis gaps** — entity pages that list facts without connecting them.

## Workflow

1. Run structural checks; collect into a single report.
2. Group by severity:
   - **Auto-fix**: link repairs from renames, missing index entries, orphans with an obvious parent.
   - **Surface**: contradictions, stale claims, missing concept pages, ambiguous orphans.
3. Apply auto-fixes (`move` to repair renames; `append` to MOC; add `[[links]]` from natural parents).
4. Surface judgment calls — for each: which pages disagree, when each was updated, recommended resolution. Wait for user before editing.
5. Suggest follow-up sources for obvious gaps.
6. Log: `## [YYYY-MM-DD] lint | <section>` with counts per finding type.

## When to skip

- Fewer than ~20 notes — structural checks are noisy.
- Right after a large ingest — expect transient orphans and pending index entries; wait for ingest to settle.
