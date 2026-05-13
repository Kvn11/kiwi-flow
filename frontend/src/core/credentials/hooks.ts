import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { clearCredential, listCredentials, updateCredential } from "./api";
import type { CredentialEntry } from "./types";

const CREDENTIALS_QUERY_KEY = ["credentials"] as const;

export function useCredentials() {
  const { data, isLoading, error } = useQuery({
    queryKey: CREDENTIALS_QUERY_KEY,
    queryFn: () => listCredentials(),
  });
  return { credentials: data ?? [], isLoading, error };
}

export function useUpdateCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      fieldValues,
    }: {
      skillName: string;
      fieldValues: Record<string, string>;
    }) => updateCredential(skillName, fieldValues),
    onSuccess: (updated) => {
      queryClient.setQueryData<CredentialEntry[]>(
        CREDENTIALS_QUERY_KEY,
        (prev) =>
          prev?.map((e) =>
            e.skill_name === updated.skill_name ? updated : e,
          ) ?? prev,
      );
    },
  });
}

export function useClearCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (skillName: string) => clearCredential(skillName),
    onSuccess: (_data, skillName) => {
      queryClient.setQueryData<CredentialEntry[]>(
        CREDENTIALS_QUERY_KEY,
        (prev) =>
          prev?.map((e) =>
            e.skill_name === skillName
              ? {
                  ...e,
                  configured: false,
                  fields_set: [],
                  has_token: false,
                  token_expires_at: null,
                  updated_at: null,
                }
              : e,
          ) ?? prev,
      );
    },
  });
}
