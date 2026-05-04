# Query: Answer Against the Wiki

Search the wiki first. Don't re-derive from raw sources unless the wiki is genuinely missing the info — that's a sign of incomplete prior ingest.

## Workflow

1. **Index first.** `read file=MOC` (or section index). Pick candidates from one-line summaries.
2. **Search.** `search:context query="<term>" format=json`. Use `format=json` whenever parsing.
3. **Read targeted.** `outline` long pages first, then `read` the relevant section. Don't dump full pages into context.
4. **Trace the link neighborhood.** `backlinks` and `links` — the answer often sits one hop away.
5. **Synthesize with citations.** Every non-trivial claim cites a `[[Page]]`. Surface contradictions; don't pick a side silently.
6. **File if it has lasting value.** `create` a new page and link it from the index. Throwaway clarifications stay in chat.
7. **Log.** `## [YYYY-MM-DD] query | <summary>` with `[[links]]` to consulted pages and any new page.

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
