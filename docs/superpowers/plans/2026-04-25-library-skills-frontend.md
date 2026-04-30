# Library Skills Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a frontend that lists and toggles "library skills" (the on-demand skill-search system) by mirroring the regular-skills frontend pattern, against the already-shipped `/api/library-skills` backend.

**Architecture:** New `core/library-skills/` module (api + hooks + type + barrel) that talks to `/api/library-skills`. New `LibrarySkillSettingsPage` component. New `"library-skills"` nav entry in `settings-dialog.tsx`. New `librarySkills` i18n block in en-US and zh-CN. One Vitest fetch-layer test for the API module.

**Tech Stack:** Next.js 16 / React 19 / TypeScript 5.8 / TanStack Query / Tailwind / Vitest. Lucide icons (`LibraryIcon`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-25-library-skills-frontend-design.md`

**Working directory for all paths below:** `/Users/kev/gitclones/kiwi-flow/`

**Commit cadence:** one commit at the end of each Task. All commits use the standard `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.

---

## Task 1: API module + Vitest

**Files:**
- Create: `frontend/src/core/library-skills/type.ts`
- Create: `frontend/src/core/library-skills/api.ts`
- Create: `frontend/src/core/library-skills/index.ts`
- Test: `frontend/tests/unit/core/library-skills/api.test.ts`

**Reference patterns to mirror:**
- `frontend/src/core/skills/type.ts`, `api.ts`, `index.ts`
- `frontend/tests/unit/core/api/stream-mode.test.ts` (Vitest style: bare `import { expect, test } from "vitest"`, no setup helpers, no DOM)

### Step 1: Write the failing test

- [ ] Create `frontend/tests/unit/core/library-skills/api.test.ts` with this content:

```ts
import { afterEach, expect, test, vi } from "vitest";

import { enableLibrarySkill, loadLibrarySkills } from "@/core/library-skills/api";

afterEach(() => {
  vi.restoreAllMocks();
});

test("loadLibrarySkills returns the parsed skills array", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        skills: [
          {
            name: "alpha",
            description: "first",
            license: "MIT",
            enabled: true,
            path: "/mnt/skill-library/alpha/SKILL.md",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  const skills = await loadLibrarySkills();

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(fetchSpy.mock.calls[0]?.[0]).toMatch(/\/api\/library-skills$/);
  expect(skills).toEqual([
    {
      name: "alpha",
      description: "first",
      license: "MIT",
      enabled: true,
      path: "/mnt/skill-library/alpha/SKILL.md",
    },
  ]);
});

test("enableLibrarySkill issues a PUT to the skill endpoint with the enabled flag", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        name: "alpha",
        description: "first",
        license: "MIT",
        enabled: false,
        path: "/mnt/skill-library/alpha/SKILL.md",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  await enableLibrarySkill("alpha", false);

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, init] = fetchSpy.mock.calls[0]!;
  expect(url).toMatch(/\/api\/library-skills\/alpha$/);
  expect(init?.method).toBe("PUT");
  expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
  const body = init?.body;
  expect(typeof body).toBe("string");
  expect(JSON.parse(body as string)).toEqual({ enabled: false });
});
```

### Step 2: Run the test to confirm it fails

- [ ] Run from `frontend/`:

```bash
pnpm test --run tests/unit/core/library-skills/api.test.ts
```

Expected: failure with module-resolution error like `Failed to resolve import "@/core/library-skills/api"`.

### Step 3: Create the type

- [ ] Create `frontend/src/core/library-skills/type.ts`:

```ts
export interface LibrarySkill {
  name: string;
  description: string;
  license: string | null;
  enabled: boolean;
  path: string;
}
```

`license` is nullable to match the backend's `license: str | None` field (`backend/app/gateway/routers/library_skills.py:41`). `path` is carried for fidelity to the response shape; the UI does not render it (per spec).

### Step 4: Create the API module

- [ ] Create `frontend/src/core/library-skills/api.ts`:

```ts
import { getBackendBaseURL } from "@/core/config";

import type { LibrarySkill } from "./type";

export async function loadLibrarySkills(): Promise<LibrarySkill[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/library-skills`);
  const json = await response.json();
  return json.skills as LibrarySkill[];
}

export async function enableLibrarySkill(skillName: string, enabled: boolean): Promise<LibrarySkill> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/library-skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ enabled }),
    },
  );
  return (await response.json()) as LibrarySkill;
}
```

### Step 5: Create the barrel re-export

- [ ] Create `frontend/src/core/library-skills/index.ts`:

```ts
export * from "./api";
export * from "./type";
```

### Step 6: Run the test to confirm it passes

- [ ] Run from `frontend/`:

```bash
pnpm test --run tests/unit/core/library-skills/api.test.ts
```

Expected: 2 passed.

### Step 7: Type check

- [ ] Run from `frontend/`:

```bash
pnpm typecheck
```

Expected: no errors.

### Step 8: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/core/library-skills/ frontend/tests/unit/core/library-skills/
git commit -m "$(cat <<'EOF'
feat(frontend): add library-skills API module

Mirror of core/skills/api.ts targeting /api/library-skills. Two
exports: loadLibrarySkills (GET list) and enableLibrarySkill (PUT
toggle). Fetch-layer Vitest covers URL, method, and body shape.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TanStack Query hooks

**Files:**
- Create: `frontend/src/core/library-skills/hooks.ts`

**Reference pattern:** `frontend/src/core/skills/hooks.ts`

No tests for this file (project lacks `@testing-library/react` and a DOM env — see spec Testing section).

### Step 1: Create the hooks module

- [ ] Create `frontend/src/core/library-skills/hooks.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { enableLibrarySkill, loadLibrarySkills } from "./api";

export function useLibrarySkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["library-skills"],
    queryFn: () => loadLibrarySkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useEnableLibrarySkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      enabled,
    }: {
      skillName: string;
      enabled: boolean;
    }) => {
      await enableLibrarySkill(skillName, enabled);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["library-skills"] });
    },
  });
}
```

### Step 2: Type check

- [ ] Run from `frontend/`:

```bash
pnpm typecheck
```

Expected: no errors.

### Step 3: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/core/library-skills/hooks.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add useLibrarySkills / useEnableLibrarySkill hooks

TanStack Query wrappers around the library-skills API. Mirror of
core/skills/hooks.ts: list query keyed on ["library-skills"];
mutation invalidates the same key on success.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: i18n strings

**Files:**
- Modify: `frontend/src/core/i18n/locales/types.ts`
- Modify: `frontend/src/core/i18n/locales/en-US.ts`
- Modify: `frontend/src/core/i18n/locales/zh-CN.ts`

**Why this comes before the component:** the component reads `t.settings.librarySkills.*`, so the type slot must exist first or `pnpm typecheck` will fail.

### Step 1: Add the `Translations` slots

- [ ] Edit `frontend/src/core/i18n/locales/types.ts`. Find the `settings.sections` block (currently lines 255-262) and add `librarySkills` immediately after `skills`:

```ts
sections: {
  appearance: string;
  memory: string;
  tools: string;
  skills: string;
  librarySkills: string;
  notification: string;
  about: string;
};
```

- [ ] In the same file, find the existing `skills` block under `settings` (currently lines 352-359) and add a `librarySkills` block immediately after it:

```ts
librarySkills: {
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
};
```

### Step 2: Add English copy

- [ ] Edit `frontend/src/core/i18n/locales/en-US.ts`. Find `settings.sections` (currently around line 326) and add `librarySkills` immediately after `skills`:

```ts
sections: {
  appearance: "Appearance",
  memory: "Memory",
  tools: "Tools",
  skills: "Skills",
  librarySkills: "Library Skills",
  notification: "Notification",
  about: "About",
},
```

- [ ] In the same file, find the existing `skills:` block (currently around line 430) and add a `librarySkills` block immediately after it (before `notification`):

```ts
librarySkills: {
  title: "Skill Library",
  description:
    "Manage the on-demand skill library. Disabled skills are excluded from skill_search results.",
  emptyTitle: "No library skills yet",
  emptyDescription:
    "Put skill folders under the `skill-library/` directory at the root of Kiwi. Each skill needs a `SKILL.md` file.",
},
```

### Step 3: Add Chinese copy

- [ ] Edit `frontend/src/core/i18n/locales/zh-CN.ts`. Find `settings.sections` (currently around line 311) and add `librarySkills` immediately after `skills`:

```ts
sections: {
  appearance: "外观",
  memory: "记忆",
  tools: "工具",
  skills: "技能",
  librarySkills: "技能库",
  notification: "通知",
  about: "关于",
},
```

- [ ] In the same file, find the existing `skills:` block (currently around line 412) and add a `librarySkills` block immediately after it (before `notification`):

```ts
librarySkills: {
  title: "技能库",
  description: "管理按需技能库。被禁用的技能将不会出现在 skill_search 的搜索结果中。",
  emptyTitle: "技能库为空",
  emptyDescription:
    "将技能文件夹放在 Kiwi 根目录下的 `skill-library/` 目录中。每个技能需要包含一个 `SKILL.md` 文件。",
},
```

### Step 4: Type check

- [ ] Run from `frontend/`:

```bash
pnpm typecheck
```

Expected: no errors. (If en-US or zh-CN drifts from the `Translations` interface — e.g., a misplaced key — TypeScript will fail here.)

### Step 5: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/core/i18n/locales/types.ts frontend/src/core/i18n/locales/en-US.ts frontend/src/core/i18n/locales/zh-CN.ts
git commit -m "$(cat <<'EOF'
feat(i18n): add librarySkills strings (en-US, zh-CN)

Adds settings.sections.librarySkills (nav label) and a
settings.librarySkills block (title, description, empty state)
in both locales, plus the matching slots in the Translations
interface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Library skills settings page component

**Files:**
- Create: `frontend/src/components/workspace/settings/library-skill-settings-page.tsx`

**Reference pattern:** `frontend/src/components/workspace/settings/skill-settings-page.tsx` (drop the tabs row, drop the create button, drop `onClose`, drop `category` filtering).

### Step 1: Create the page component

- [ ] Create `frontend/src/components/workspace/settings/library-skill-settings-page.tsx`:

```tsx
"use client";

import { LibraryIcon } from "lucide-react";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import {
  useEnableLibrarySkill,
  useLibrarySkills,
} from "@/core/library-skills/hooks";
import type { LibrarySkill } from "@/core/library-skills/type";
import { env } from "@/env";

import { SettingsSection } from "./settings-section";

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
        <LibrarySkillsList skills={skills} />
      )}
    </SettingsSection>
  );
}

function LibrarySkillsList({ skills }: { skills: LibrarySkill[] }) {
  const { mutate: enableLibrarySkill } = useEnableLibrarySkill();
  if (skills.length === 0) {
    return <EmptyLibrarySkill />;
  }
  return (
    <div className="flex w-full flex-col gap-4">
      {skills.map((skill) => (
        <Item className="w-full" variant="outline" key={skill.name}>
          <ItemContent>
            <ItemTitle>
              <div className="flex items-center gap-2">{skill.name}</div>
            </ItemTitle>
            <ItemDescription className="line-clamp-4">
              {skill.description}
            </ItemDescription>
          </ItemContent>
          <ItemActions>
            <Switch
              checked={skill.enabled}
              disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
              onCheckedChange={(checked) =>
                enableLibrarySkill({ skillName: skill.name, enabled: checked })
              }
            />
          </ItemActions>
        </Item>
      ))}
    </div>
  );
}

function EmptyLibrarySkill() {
  const { t } = useI18n();
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <LibraryIcon />
        </EmptyMedia>
        <EmptyTitle>{t.settings.librarySkills.emptyTitle}</EmptyTitle>
        <EmptyDescription>
          {t.settings.librarySkills.emptyDescription}
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
```

Notes for the implementer:
- This component does not accept an `onClose` prop. The existing `SkillSettingsPage` only takes one because its create-skill button navigates the dialog away; library skills have no such action.
- The `Empty` component is rendered without `EmptyContent`/`EmptyButton` — there's no install / create action.

### Step 2: Type check

- [ ] Run from `frontend/`:

```bash
pnpm typecheck
```

Expected: no errors. If `t.settings.librarySkills.*` is missing, this is the first place it'll surface.

### Step 3: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/components/workspace/settings/library-skill-settings-page.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add LibrarySkillSettingsPage

Lists library skills with name, description, and a per-row
toggle. Mirror of SkillSettingsPage minus tabs, create button,
and onClose.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire the page into the Settings dialog

**Files:**
- Modify: `frontend/src/components/workspace/settings/settings-dialog.tsx`

### Step 1: Extend the section union and import the icon + page

- [ ] Edit `frontend/src/components/workspace/settings/settings-dialog.tsx`. In the `lucide-react` import (currently lines 3-10), add `LibraryIcon` and normalize the named imports to alphabetical order (the project's convention per `frontend/CLAUDE.md`; the current block is not strictly sorted). Resulting import block:

```ts
import {
  BellIcon,
  BrainIcon,
  InfoIcon,
  LibraryIcon,
  PaletteIcon,
  SparklesIcon,
  WrenchIcon,
} from "lucide-react";
```

- [ ] Add the page import next to the existing `SkillSettingsPage` import:

```ts
import { LibrarySkillSettingsPage } from "@/components/workspace/settings/library-skill-settings-page";
```

- [ ] Extend the `SettingsSection` type union (currently lines 29-35) to include `"library-skills"`:

```ts
type SettingsSection =
  | "appearance"
  | "memory"
  | "tools"
  | "skills"
  | "library-skills"
  | "notification"
  | "about";
```

### Step 2: Add the nav entry to `useMemo`

- [ ] In the `sections` `useMemo` (currently lines 55-84), insert a new entry after the `skills` entry and update the dependency array. Result:

```ts
const sections = useMemo(
  () => [
    {
      id: "appearance",
      label: t.settings.sections.appearance,
      icon: PaletteIcon,
    },
    {
      id: "notification",
      label: t.settings.sections.notification,
      icon: BellIcon,
    },
    {
      id: "memory",
      label: t.settings.sections.memory,
      icon: BrainIcon,
    },
    { id: "tools", label: t.settings.sections.tools, icon: WrenchIcon },
    { id: "skills", label: t.settings.sections.skills, icon: SparklesIcon },
    {
      id: "library-skills",
      label: t.settings.sections.librarySkills,
      icon: LibraryIcon,
    },
    { id: "about", label: t.settings.sections.about, icon: InfoIcon },
  ],
  [
    t.settings.sections.appearance,
    t.settings.sections.memory,
    t.settings.sections.tools,
    t.settings.sections.skills,
    t.settings.sections.librarySkills,
    t.settings.sections.notification,
    t.settings.sections.about,
  ],
);
```

### Step 3: Add the render branch

- [ ] In the page-render block (currently lines 127-136), add the library-skills branch immediately after the `skills` branch:

```tsx
{activeSection === "skills" && (
  <SkillSettingsPage
    onClose={() => props.onOpenChange?.(false)}
  />
)}
{activeSection === "library-skills" && <LibrarySkillSettingsPage />}
{activeSection === "notification" && <NotificationSettingsPage />}
```

### Step 4: Type check + lint

- [ ] Run from `frontend/`:

```bash
pnpm typecheck
pnpm lint
```

Expected: both pass with no new errors.

### Step 5: Run the test suite end-to-end

- [ ] Run from `frontend/`:

```bash
pnpm test
```

Expected: all tests pass, including the two new `core/library-skills/api.test.ts` cases.

### Step 6: Manual smoke test (UI)

- [ ] Start dev server from repo root:

```bash
make dev
```

Browse to `http://localhost:2026`, open Settings, and verify:
  - A new "Library Skills" entry appears in the left nav with the library icon, between "Skills" and "About".
  - Clicking it shows the library-skills page with the title/description from `librarySkills.title` / `librarySkills.description`.
  - If `skill-library/` is empty, the empty state renders with the library icon and the empty copy.
  - If at least one library skill exists, it renders as a row with name, description, and a working toggle. Toggling persists across a page reload (writes to `extensions_config.json`).

If the backend isn't running with library skills configured, verifying the empty state alone is sufficient — the API call shape was already validated in Task 1.

### Step 7: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/components/workspace/settings/settings-dialog.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): wire LibrarySkillSettingsPage into Settings dialog

New nav entry "Library Skills" between Skills and About, using
lucide LibraryIcon and the new librarySkills i18n keys.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Final verification

### Step 1: Confirm clean state

- [ ] Run from repo root:

```bash
git status
git log --oneline -10
```

Expected: working tree clean (apart from anything that was already dirty before this plan started). Five new commits authored during this plan: API module, hooks, i18n, page component, dialog wiring.

### Step 2: Final lint + check

- [ ] Run from `frontend/`:

```bash
pnpm check
```

Expected: clean.

### Step 3: Stop here

The implementation is complete. There is no plan-level commit beyond the per-task commits above; nothing else is needed.

---

## Notes for the implementer

- **TDD scope**: only Task 1 has a Vitest. Tasks 2-5 are mechanical mirror work where the type checker is the safety net. If you find yourself reaching for `@testing-library/react` or jsdom, stop — that's a separate, larger initiative outside this plan's scope.
- **Path consistency**: all paths in commands are relative to the indicated cwd (`frontend/` or repo root). The repo root is `/Users/kev/gitclones/kiwi-flow/`.
- **Don't restructure regular skills.** If you notice cleanup opportunities in `core/skills/` while you're there, leave them alone. This plan is a strict mirror, not a refactor.
- **Backend assumption**: `/api/library-skills` is already shipped (`backend/app/gateway/routers/library_skills.py`). No backend changes are part of this plan.
