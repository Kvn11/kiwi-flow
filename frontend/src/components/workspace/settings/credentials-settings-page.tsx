"use client";

import { KeyRoundIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { CredentialEntry } from "@/core/credentials";
import { useClearCredential, useCredentials } from "@/core/credentials";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { CredentialsEditDialog } from "./credentials-edit-dialog";
import { SettingsSection } from "./settings-section";

type DialogState =
  | { kind: "edit"; entry: CredentialEntry }
  | { kind: "clear"; entry: CredentialEntry }
  | null;

export function CredentialsSettingsPage() {
  const { t } = useI18n();
  return (
    <SettingsSection
      title={t.settings.credentials.title}
      description={t.settings.credentials.description}
    >
      <CredentialsBody />
    </SettingsSection>
  );
}

function CredentialsBody() {
  const { t } = useI18n();
  const { credentials, isLoading, error } = useCredentials();

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">{t.common.loading}</div>;
  }
  if (error) {
    return (
      <div className="text-destructive text-sm">
        {error instanceof Error ? error.message : String(error)}
      </div>
    );
  }
  if (credentials.length === 0) {
    return <EmptyCredentials />;
  }
  return <CredentialsList credentials={credentials} />;
}

function EmptyCredentials() {
  const { t } = useI18n();
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <KeyRoundIcon />
        </EmptyMedia>
        <EmptyTitle>{t.settings.credentials.emptyTitle}</EmptyTitle>
        <EmptyDescription>
          {t.settings.credentials.emptyDescription}
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function CredentialsList({ credentials }: { credentials: CredentialEntry[] }) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const close = () => setDialog(null);

  return (
    <div className="flex w-full flex-col gap-3">
      {credentials.map((entry) => (
        <CredentialRow
          key={entry.skill_name}
          entry={entry}
          onEdit={() => setDialog({ kind: "edit", entry })}
          onClear={() => setDialog({ kind: "clear", entry })}
        />
      ))}

      <CredentialsEditDialog
        entry={dialog?.kind === "edit" ? dialog.entry : null}
        open={dialog?.kind === "edit"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      />

      <ClearConfirmDialog
        entry={dialog?.kind === "clear" ? dialog.entry : null}
        open={dialog?.kind === "clear"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      />
    </div>
  );
}

function CredentialRow({
  entry,
  onEdit,
  onClear,
}: {
  entry: CredentialEntry;
  onEdit: () => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  return (
    <Item className="w-full" variant="outline">
      <ItemContent>
        <ItemTitle className="flex items-center gap-2">
          {entry.skill_name}
          <StatusPill configured={entry.configured} />
        </ItemTitle>
        <ItemDescription>
          {entry.configured
            ? t.settings.credentials.rowDescriptionConfigured.replace(
                "{count}",
                String(entry.fields.length),
              )
            : t.settings.credentials.rowDescriptionUnconfigured.replace(
                "{count}",
                String(entry.fields.length - entry.fields_set.length),
              )}
        </ItemDescription>
      </ItemContent>
      <ItemActions>
        <Button size="sm" variant="outline" onClick={onEdit}>
          {t.common.edit}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onClear}
          aria-label={t.settings.credentials.clear}
          disabled={!entry.configured && entry.fields_set.length === 0}
        >
          <Trash2Icon className="size-4" />
        </Button>
      </ItemActions>
    </Item>
  );
}

function StatusPill({ configured }: { configured: boolean }) {
  const { t } = useI18n();
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1",
        configured
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          configured ? "bg-emerald-500" : "bg-muted-foreground/40",
        )}
      />
      {configured
        ? t.settings.credentials.statusConfigured
        : t.settings.credentials.statusUnconfigured}
    </Badge>
  );
}

function ClearConfirmDialog({
  entry,
  open,
  onOpenChange,
}: {
  entry: CredentialEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { mutate: clearCredential, isPending } = useClearCredential();

  if (!entry) return null;

  const handleConfirm = () => {
    clearCredential(entry.skill_name, {
      onSuccess: () => {
        toast.success(t.settings.credentials.clearSuccess);
        onOpenChange(false);
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : String(err));
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {t.settings.credentials.clearConfirmTitle.replace(
              "{skill}",
              entry.skill_name,
            )}
          </DialogTitle>
          <DialogDescription>
            {t.settings.credentials.clearConfirmDescription}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t.common.cancel}
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? t.common.loading : t.settings.credentials.clear}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
