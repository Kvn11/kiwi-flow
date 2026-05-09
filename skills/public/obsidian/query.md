# Query: Answer Against the Wiki

Search the wiki first. Don't re-derive from raw sources unless the wiki is genuinely missing the info — that's a sign of incomplete prior ingest.

## Workflow

1. **Discover candidates.** `files folder=<section>` to scope, then `search:context query="<term>" format=json`. Use `format=json` whenever parsing. Also useful: `tags`, `properties`, `aliases` for facet navigation. There is no MOC — the CLI is the index.
2. **Read targeted.** `outline` long pages first, then `read` the relevant section. Don't dump full pages into context.
3. **Trace the link neighborhood.** `backlinks` and `links` — the answer often sits one hop away.
4. **Synthesize with citations.** Every non-trivial claim cites a `[[Page]]`. Surface contradictions; don't pick a side silently.
5. **File if it has lasting value.** `create` a new page and `[[link]]` it from at least one existing page (so it isn't orphaned). Throwaway clarifications stay in chat.
6. **Log.** Append to `log.md`: `## [YYYY-MM-DD] query | <summary>` with `[[links]]` to consulted pages and any new page.

## File or skip?

| File | Skip |
|---|---|
| Synthesizes 3+ pages | One-line factual lookup |
| Likely to be re-asked | Transient state (current PR, today's status) |
| Introduces a comparison/decision/analysis | Already on a single existing page (link to it) |
| Surfaces a contradiction | User's follow-up has no further action |

When in doubt, file. Over-filing is cheap.

## Wiki missing the answer

1. Say so explicitly — don't fabricate from raw to fill the gap.
2. Offer to ingest the missing source(s).
3. If the gap is structural (concept appears across pages with no dedicated page), flag as a lint finding.

## Output formats

Markdown reply, comparison table, mermaid diagram (quoted labels), or slide deck — match the question. If lasting value, file regardless of format.
