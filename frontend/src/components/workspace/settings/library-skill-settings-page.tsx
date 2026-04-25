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
