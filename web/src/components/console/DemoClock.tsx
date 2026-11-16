"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ACCOUNTANT, api, type S } from "@/lib/api/client";
import { useClock } from "@/lib/api/hooks";
import { formatDay } from "@/lib/format";

/** Prototype only: triggers the same tasks Celery Beat runs on day 1 and after day 5. */
export function DemoClock() {
  const clock = useClock();
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: (day: "day-1" | "day-5") => api<S<"DayOut">>(`/demo/${day}`, { method: "POST", actor: ACCOUNTANT }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const today = clock.data?.today;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-status-pending-tint px-4 py-2 font-mono text-xs text-status-pending">
      <span>
        MODO DEMO · solo en el prototipo · fecha simulada <b>{today ? formatDay(today) : "…"}</b>
      </span>
      <button
        className="rounded-md border border-current bg-surface px-2.5 py-0.5 text-ink disabled:opacity-50"
        disabled={run.isPending}
        onClick={() => run.mutate("day-1")}
      >
        Simular día 1: iniciar cierre
      </button>
      <button
        className="rounded-md border border-current bg-surface px-2.5 py-0.5 text-ink disabled:opacity-50"
        disabled={run.isPending}
        onClick={() => run.mutate("day-5")}
      >
        Simular día 5: vence el plazo
      </button>
      {run.isPending && <span>procesando…</span>}
    </div>
  );
}
