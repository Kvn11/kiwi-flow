# Library Skills Frontend — Design

**Status:** approved
**Date:** 2026-04-25
**Scope:** frontend only (backend already implemented)

## Goal

Mirror the existing regular-skills frontend wiring so users can list and toggle library skills (the on-demand `skill-library/` system, discovered by the agent via the `skill_search` tool) from the Settings dialog.

## Non-goals

- No install / upload flow (backend has no POST endpoint for library skills; library skills are filesystem-discovered from a flat layout).
- No `path` field surfaced in the UI (mirror regular skills exactly).
- No public/custom split (library is flat; the concept doesn't apply).
- No search / filter (regular skills don't have it; library is small enough).
- No bulk enable/disable, no skill-detail modal.
- No artifact-viewer changes.

## Backend (already shipped, for reference)

`backend/app/gateway/routers/library_skills.py` exposes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/library-skills` | list all (with enabled state) |
| GET | `/api/library-skills/{name}` | details for one |
| PUT | `/api/library-skills/{name}` | toggle (`{enabled: bool}`) |

Toggle persists to `extensions_config.json` under `librarySkills` and resets the in-process registry cache. No prompt-cache invalidation is needed — library skills never appear in the system prompt.

`LibrarySkillResponse` fields: `name`, `description`, `license`, `enabled`, `path`.

## Architecture

A parallel mirror of the regular-skills frontend, isolated in its own module. New top-level Settings nav entry **"Library Skills"** sits alongside **"Skills"**. Renders a list of library skills with name, description, and a toggle switch — no install button, no tabs, no extra fields.

```
Backend (already exists)              Frontend (new)
─────────────────────────             ──────────────
GET  /api/library-skills      ◄────── core/library-skills/api.ts
PUT  /api/library-skills/:n   ◄────── core/library-skills/api.ts
                                      core/library-skills/hooks.ts (TanStack Query)
                                      core/library-skills/type.ts
                                      core/library-skills/index.ts
                                      └─ used by ─►  components/workspace/settings/
                                                       library-skill-settings-page.tsx
                                                     └─ wired in ─►  settings-dialog.tsx
```

A sibling folder under `core/` (`core/library-skills/` next to `core/skills/`) mirrors the backend split (separate router, separate registry).

## File layout

### New files

| Path | Purpose |
|---|---|
| `frontend/src/core/library-skills/type.ts` | `LibrarySkill` type (`name`, `description`, `license`, `enabled`, `path`). `path` is carried for fidelity to the backend response shape; the UI does not render it (see Non-goals). |
| `frontend/src/core/library-skills/api.ts` | `loadLibrarySkills()`, `enableLibrarySkill(name, enabled)` |
| `frontend/src/core/library-skills/hooks.ts` | `useLibrarySkills()`, `useEnableLibrarySkill()` |
| `frontend/src/core/library-skills/index.ts` | barrel re-export |
| `frontend/src/components/workspace/settings/library-skill-settings-page.tsx` | settings page UI |

### Modified files

| Path | Change |
|---|---|
| `frontend/src/components/workspace/settings/settings-dialog.tsx` | Add `"library-skills"` to `SettingsSection` union, add nav entry with `LibraryIcon` from `lucide-react`, render `<LibrarySkillSettingsPage />`, and add `t.settings.sections.librarySkills` to the `useMemo` dependency array so the sections list refreshes on locale changes |
| `frontend/src/core/i18n/locales/types.ts` | Add `librarySkills` slot under `settings.sections` (camelCase key, paired with the hyphenated `"library-skills"` id — same naming asymmetry as existing entries) and a top-level `settings.librarySkills` block (`title`, `description`, `emptyTitle`, `emptyDescription`) |
| `frontend/src/core/i18n/locales/en-US.ts` | English copy |
| `frontend/src/core/i18n/locales/zh-CN.ts` | Chinese copy |

## Data flow

1. `LibrarySkillSettingsPage` mounts → calls `useLibrarySkills()` → TanStack Query hits `GET /api/library-skills` → returns `{skills: LibrarySkill[]}` → cached under key `["library-skills"]`.
2. User flips a `Switch` → `useEnableLibrarySkill().mutate({skillName, enabled})` → `PUT /api/library-skills/{name}` with `{enabled}` body → on success, invalidates `["library-skills"]` → refetch.
3. Backend writes `extensions_config.json` and resets the in-process registry. Subsequent `skill_search` calls reflect the new state immediately.

This mirrors the regular-skills query/mutation lifecycle (`useSkills` / `useEnableSkill`) exactly.

## Component shape

```tsx
// library-skill-settings-page.tsx (sketch)
export function LibrarySkillSettingsPage() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useLibrarySkills();
  return (
    <SettingsSection
      title={t.settings.librarySkills.title}
      description={t.settings.librarySkills.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : error ? (
        <div>Error: {error.message}</div>
      ) : (
        <LibrarySkillsList skills={skills}/>
      )}
    </SettingsSection>
  );
}
```

`LibrarySkillsList` renders `Item` / `ItemContent` / `ItemActions` / `Switch` rows — the same primitives as `SkillSettingsList`, minus the tabs row and the create button.

Empty state uses `Empty` with `LibraryIcon` and the i18n empty copy.

The toggle `Switch` is disabled when `env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"` (mirror).

## Settings nav integration

In `settings-dialog.tsx`:

- Extend `SettingsSection` union: add `"library-skills"`.
- Add a sections entry: `{ id: "library-skills", label: t.settings.sections.librarySkills, icon: LibraryIcon }` placed immediately after the existing `"skills"` entry.
- Add render branch: `{activeSection === "library-skills" && <LibrarySkillSettingsPage />}`.
- `LibraryIcon` is already in `lucide-react`.

The page is self-contained (no `onClose` prop required; there is no navigation away).

## Error handling

Mirrors regular skills: render `error.message` inline. No special toasts.

Mutation failures bubble through TanStack Query's default error path; the next refetch reconciles state if the backend rejects the toggle. Because the backend `PUT` returns the updated skill, an optimistic update is unnecessary — the post-mutation invalidation refetches authoritative state.

## Testing

Unit tests under `frontend/tests/unit/`, Vitest + `@/` alias (mirrors existing `tests/unit/` layout). The Vitest config (`frontend/vitest.config.ts`) only includes `**/*.test.ts` (no `.tsx`), and the project has no `@testing-library/react` / DOM env — so tests are restricted to pure logic that doesn't render React.

- `tests/unit/core/library-skills/api.test.ts`
  - `loadLibrarySkills` parses `{skills: [...]}` shape
  - `enableLibrarySkill` issues a `PUT` to `/api/library-skills/{name}` with `{enabled}` body

No hooks test, no component test. Both would require adding `@testing-library/react` + a DOM env (jsdom/happy-dom), which the project doesn't currently use. This mirrors existing coverage: `core/skills/` has zero tests today, and the new module gets one focused fetch-layer test rather than zero. Adding hook/component infrastructure is out of scope for this v1 mirror.

No E2E for v1.

## Out of scope (future work)

- An install endpoint for library skills (backend POST + artifact-viewer wire-up for a hypothetical `.libskill` archive). Today, library skills are dropped into `skill-library/` on disk.
- Search / filter inside the page if the library grows large.
- Surfacing the `path` field if users start asking how the agent finds skills.
