"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ACCOUNTANT, api, type S } from "./client";
import { workingPeriod } from "@/lib/format";

export function useClock() {
  return useQuery({ queryKey: ["clock"], queryFn: () => api<S<"Clock">>("/demo/clock") });
}

export function useWorkingPeriod(): string | undefined {
  const clock = useClock();
  return clock.data ? workingPeriod(clock.data.today) : undefined;
}

export function useInbox(period: string | undefined) {
  return useQuery({
    queryKey: ["inbox", period],
    queryFn: () => api<S<"Inbox">>(`/period-closes?period=${period}`),
    enabled: !!period,
    // Closes are computed by Celery: poll a bit while anything may be recomputing.
    refetchInterval: 3_000,
  });
}

export function useClose(id: string) {
  return useQuery({
    queryKey: ["close", id],
    queryFn: () => api<S<"CloseDetail">>(`/period-closes/${id}`),
    refetchInterval: 3_000,
  });
}

/** POST as the accountant and refresh everything the console shows. */
export function useAccountantAction<TBody, TResult = unknown>(path: (vars: TBody) => string, body?: (vars: TBody) => unknown) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TBody) =>
      api<TResult>(path(vars), { method: "POST", body: body ? body(vars) : undefined, actor: ACCOUNTANT }),
    onSuccess: () => qc.invalidateQueries(),
  });
}
