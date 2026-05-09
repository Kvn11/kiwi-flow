# Ingest: Add a Source to the Wiki

Integrate the source into the wiki, not just chat. A source typically touches **5–15 pages**; if you only touched a summary, you haven't cross-referenced.

## Capture, don't compress

The wiki's value is the **specifics**, not the thesis. The thesis is one sentence; a smart reader can re-derive it. The numbers, names, paths, hooks, code snippets, comparison tables, and diagrams are what they cannot re-derive — that is what must land in the vault.

For every page you write, sweep the source for:

- **Numbers and thresholds** — token counts, line limits, percentages, timeouts, cardinalities ("49 core skills, 304+ library skills", "<150 lines", "compact at >85%").
- **Proper names** — file paths (`.claude/.output/features/{id}/`), artifact names (`MANIFEST.yaml`, `feedback-loop-state.json`), hook scripts (`feedback-loop-stop.sh`), skill IDs (`iterating-to-completion`), commands, role names.
- **Original terminology** — coined terms in the source ("Attention Dilution", "Leaf Node execution", "Cyborg Approach"). Quote them; do not rename to a generic synonym.
- **Code, config, and schemas** — short snippets that show the design (a JSON state shape, a CLI invocation, a YAML stanza). Fence them.
- **Lists the source enumerates** — "the 16 phases", "the 8 enforcement layers", "the 5 roles" — preserve as a table or list, in order. Don't reduce to "several phases".
- **Comparison tables** — keep the rows. They encode the author's distinctions.
- **Concrete examples and before/after** — preserve the example, not only the lesson it illustrates.
- **Diagrams** — port to mermaid (quoted labels, per `feedback_diagrams`). A diagram is a claim; don't drop it.

If a page reads like a textbook definition with no number, no proper noun, and no example, you over-compressed. Go back to the source.

## Workflow

Steps are ordered so each one's prerequisites exist when you reach it. Don't reorder.

1. **Read the source.** `read` for vault sources; read files directly for code/docs outside the vault.
2. **Plan the page set.** Walk the source's section headings, numbered tables, and coined terms. List the distinct subsystems each merits its own page. The plan is yours — do not ask the user to approve it. The user's instruction to ingest is the green light; planning is part of the work, not a checkpoint. Only stop and ask if the source itself is genuinely ambiguous about its own scope (rare). Most sources land **5–15 pages**; settling at the floor without justification means you under-scoped — go back to the source.
3. **Write the source summary FIRST, before any concept page.** One page, under `<section>/sources/<title>.md`. Frontmatter: `type: source`, ingest date, link to original. This is the landing node every concept will cite — it must exist before any `[[link]]` points at it. Writing concept pages with `Source trail: [[...]]` references to a file you haven't created yet is the most common ingest failure.
4. **Write concept pages — one per concept, dense with specifics.** For each:
   - `search query="<entity>" format=json` to find existing pages; `read` candidates.
   - `append` to existing pages with `[[link]]` to the source summary. `create` if none exist.
   - Apply the **Capture, don't compress** rules above: numbers, names, paths, original terminology, full enumerations, comparison rows. Bullets and tables beat prose.
   - Do not append a generic "how this maps to my vault" coda to every concept; only add transfer notes when the source itself implies a concrete vault action.
5. **Port diagrams.** If the source contains N architecture / sequence / flow diagrams, the cluster should contain ~N corresponding mermaid blocks, placed on the page whose claim each diagram makes. Quote all labels (per `feedback_diagrams` memory). Silently dropping diagrams is a defect — note "diagram omitted: <reason>" if you genuinely cannot port one.
6. **Log.** Append to the section's `log.md` (or create it): `## [YYYY-MM-DD] ingest | <title>` + pages touched. The log is append-only and chronological — do not retro-edit prior entries.
7. **Surface contradictions — never overwrite silently.** Keep both claims, mark older as `superseded`, flag to user.
8. **Verify before claiming done. Hard gate, not cleanup. Run, fix, re-run — iterate until clean.**

   This is not a "check the boxes" formality. Each check that returns anything non-empty is a real defect that must be repaired *before* moving on. The most common failure mode of this skill is: agent runs `unresolved`, sees N entries, ignores them, tells the user it's done. Don't. Fix every entry, re-run, and only stop when the check returns empty.

   Run these in order:

   **a) `unresolved`** — must return empty.
   - If it lists `[[Some Page]]`, that wikilink doesn't resolve to a real file.
   - Most common cause: filename casing/punctuation doesn't match the wikilink. (See SKILL.md → Naming Convention.) E.g., file `thin-agent-fat-platform.md` will not satisfy `[[Thin Agent Fat Platform]]`.
   - **Fix path:** either `move` the file to a name matching the wikilink, OR `str_replace`/edit the wikilinks to match the existing filename. Pick one convention and apply it everywhere — do not patch one and leave others broken.
   - Re-run `unresolved`. Repeat until empty.

   **b) `orphans`** — every new page must have ≥1 inbound link.
   - The source summary, a sibling concept, or the section's `log.md` entry all count as inbound links.
   - If a concept page is orphaned, add a `[[link]]` to it from the most natural neighbour (usually the source summary's `related:` block or body).
   - Re-run `orphans`. Repeat until empty (or until only pre-existing pages remain — orphans you didn't create are not yours to fix in this pass).

   **c) Section coverage** — walk the source's section headings/numbered subsystems. Each one is reflected in a page or explicitly omitted in the log entry with a reason.

   **d) Diagram count** — source has N architecture/flow/sequence diagrams, your cluster has ~N (or each omission is logged with a reason).

   **e) Page count** — in the 5–15 range for a substantial source. If you stopped at the floor, you under-scoped step 2.

   **Stop condition:** all five checks pass on a *fresh* run (not on the run that prompted fixes). Only then say done. Saying done with a non-empty `unresolved` or `orphans` is a defect, not a near-miss.

## Quality bar

Structural (verified in step 8):

- Every claim cites a source page; every new page has ≥1 inbound link.
- Frontmatter: `type` and `tags` always; `related` when there are real cross-links to name. `up:` is optional — set it only when there's a genuine parent concept page (not an MOC). Don't invent a parent to satisfy the field.
- Log entry written in-pass — never defer.

Content depth (per concept page):

- At least one **number, file path, or proper noun** from the source appears verbatim.
- Any list the source enumerates (phases, layers, roles, tiers) appears in full.
- At least one **concrete example, code snippet, or comparison row** if the source provides one.
- The page would let a reader rebuild the mechanism, not just recognise the name.

## Anti-patterns

| Symptom | Problem | Fix |
|---|---|---|
| Every concept page is 150–200 words of definition + abstract paraphrase | Thesis-only summarization — the value is gone | Re-open the source; pull numbers, names, code |
| Uniform template (`Definition` / `Pattern` / `Adaptation`) on every page | Template is squeezing out source-specific structure | Let each concept's natural shape (list, table, diagram) win |
| The source enumerates N items; the page says "several" or names 2 | Lossy compression of the author's taxonomy | Restore the full list, in order |
| Compared 4 systems → page mentions only one | Comparison tables hold the design contrasts | Port the table verbatim |
| No file paths, no hook names, no token counts anywhere in the cluster | Mechanics didn't survive the rewrite | Add a "Concrete artifacts" section per page |
| Concept pages cite `[[Source X]]` but Source X file doesn't exist | Wrote concepts before the summary; broken `[[link]]` graph | Write the source page first (step 3), always |
| Source has 4 mermaid diagrams; cluster has zero | Treated diagrams as decoration | Port them; or log "diagram omitted: <reason>" |
| Stopped at 5 pages on a paper with 10+ named subsystems | Coverage floor ≠ adequacy | Re-scope (step 2) against the source's headings |
| Told the user "done" without running `unresolved` and `orphans` | Skipped step 8 | Step 8 is a gate, not cleanup |
| Ran `unresolved`, saw N entries, said done anyway | Treated the check as a formality | Fix every entry, re-run on a fresh state, only stop at empty |
| Created an `MOC.md` or "Content index" page listing every other note | Hand-curated indexes are drift factories; the CLI does this with `files` | Skip it. If section orientation matters, write a real concept page, not an index |
| Set `up: [[MOC]]` on every new page | Cargo-culted parent field — the MOC doesn't exist anymore | Omit `up:` or point at an actual parent concept |
| Filenames are kebab-case (`thin-agent-fat-platform.md`) but wikilinks are Title Case (`[[Thin Agent Fat Platform]]`) | Naming conventions don't match — every wikilink is unresolved | Filenames are Title Case with spaces, matching wikilinks. See SKILL.md → Naming Convention |
| Slugified filenames "for URL safety" | There are no URLs; you orphaned the entire cluster | Use spaces and Title Case in filenames |
| Asked "what would you like me to do next?" / "should I turn this into X or Y?" after reading the source | The instruction was already given — asking is a stall | Skip to step 2, plan silently, then write |
| Offered an open-ended menu of possible outputs (brief / memo / notes / critique / …) | Same stall, dressed as helpfulness | Pick the action the user named ("add to the vault" → ingest) and start |

## Batch vs. one-at-a-time

One at a time when the user is in the loop. Batch only on explicit hand-off ("process all of these"); even then, surface contradictions per-source, not at the end.
