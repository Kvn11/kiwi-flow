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
