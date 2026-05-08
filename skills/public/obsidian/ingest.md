# Ingest: Add a Source to the Wiki

Integrate the source into the wiki, not just chat. A source typically touches **5–15 pages**; if you only touched a summary, you haven't cross-referenced.

## Workflow

1. **Read the source.** `read` for vault sources; read files directly for code/docs outside the vault.
2. **Discuss takeaways.** Confirm scope and emphasis with the user before writing.
3. **Create the summary page.** One per source, under the right section (e.g. `DeerFlow/sources/<title>.md`). Frontmatter: `type: source`, ingest date, link to original.
4. **Update entity and concept pages.** For each entity:
   - `search query="<entity>" format=json`
   - `read` candidates, `append` new claims with `[[link]]` to the summary
   - If a concept is referenced but has no page, `create` one
5. **Update the content index.** `append` to the section's MOC: page title, one-line summary, date.
6. **Cross-reference.** `[[wikilinks]]` between summary and every page touched. Run `unresolved` after to catch typos.
7. **Log.** `## [YYYY-MM-DD] ingest | <title>` + pages touched.
8. **Surface contradictions — never overwrite silently.** Keep both claims, mark older as `superseded`, flag to user.

## Quality bar

- Every claim cites a source page.
- Every new page has ≥1 inbound link (else orphan).
- Frontmatter matches vault conventions: `tags`, `type`, `up`, `related`.
- Index reflects the new page in-pass — never defer.
- Diagrams: mermaid with quoted labels (per `feedback_diagrams` memory).

## Batch vs. one-at-a-time

One at a time when the user is in the loop. Batch only on explicit hand-off ("process all of these"); even then, surface contradictions per-source, not at the end.
