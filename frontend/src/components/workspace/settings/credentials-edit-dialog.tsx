"use client";

import { EyeIcon, EyeOffIcon } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { CredentialEntry } from "@/core/credentials";
import { useUpdateCredential } from "@/core/credentials";
import { useI18n } from "@/core/i18n/hooks";

type Props = {
  entry: CredentialEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CredentialsEditDialog({ entry, open, onOpenChange }: Props) {
  const { t } = useI18n();
  const formId = useId();
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const { mutate: updateCredential, isPending } = useUpdateCredential();

  // Reset on each open — never echo previously-stored values into the form.
  useEffect(() => {
    if (open) {
      setFieldValues({});
      setRevealed({});
    }
  }, [open, entry?.skill_name]);

  if (!entry) return null;

  const handleChange = (name: string, value: string) => {
    setFieldValues((prev) => ({ ...prev, [name]: value }));
  };

  const toggleReveal = (name: string) => {
    setRevealed((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const submitValues: Record<string, string> = {};
    for (const [name, value] of Object.entries(fieldValues)) {
      if (value.length > 0) {
        submitValues[name] = value;
      }
    }
    if (Object.keys(submitValues).length === 0) {
      onOpenChange(false);
      return;
    }

    updateCredential(
      { skillName: entry.skill_name, fieldValues: submitValues },
      {
        onSuccess: () => {
          toast.success(t.settings.credentials.updateSuccess);
          onOpenChange(false);
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : String(err));
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {t.settings.credentials.editTitle.replace("{skill}", entry.skill_name)}
          </DialogTitle>
          <DialogDescription>
            {t.settings.credentials.editDescription}
          </DialogDescription>
        </DialogHeader>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          {entry.fields.map((field) => {
            const wasSet = entry.fields_set.includes(field.name);
            const placeholder = wasSet
              ? "••••••••"
              : t.settings.credentials.fieldEmptyPlaceholder;
            const currentValue = fieldValues[field.name] ?? "";

            return (
              <div key={field.name} className="flex flex-col gap-1.5">
                <label
                  htmlFor={`${formId}-${field.name}`}
                  className="text-sm font-medium"
                >
                  {field.label}
                </label>
                {field.type === "textarea" ? (
                  <Textarea
                    id={`${formId}-${field.name}`}
                    value={currentValue}
                    placeholder={placeholder}
                    onChange={(e) => handleChange(field.name, e.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                ) : (
                  <div className="relative">
                    <Input
                      id={`${formId}-${field.name}`}
                      type={revealed[field.name] ? "text" : "password"}
                      value={currentValue}
                      placeholder={placeholder}
                      onChange={(e) => handleChange(field.name, e.target.value)}
                      className="pr-9"
                      autoComplete="off"
                    />
                    <button
                      type="button"
                      onClick={() => toggleReveal(field.name)}
                      className="text-muted-foreground hover:text-foreground absolute inset-y-0 right-2 flex items-center"
                      aria-label={
                        revealed[field.name]
                          ? t.settings.credentials.hideValue
                          : t.settings.credentials.showValue
                      }
                    >
                      {revealed[field.name] ? (
                        <EyeOffIcon className="size-4" />
                      ) : (
                        <EyeIcon className="size-4" />
                      )}
                    </button>
                  </div>
                )}
                {wasSet && (
                  <p className="text-muted-foreground text-xs">
                    {t.settings.credentials.fieldAlreadySet}
                  </p>
                )}
              </div>
            );
          })}
        </form>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t.common.cancel}
          </Button>
          <Button form={formId} type="submit" disabled={isPending}>
            {isPending ? t.common.loading : t.common.save}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
