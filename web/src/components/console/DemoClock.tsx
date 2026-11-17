"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ACCOUNTANT, api, type S } from "@/lib/api/client";
import { useClock } from "@/lib/api/hooks";
import { formatDay } from "@/lib/format";

const BUTTON = "rounded-md border border-current bg-surface px-2.5 py-0.5 text-ink disabled:opacity-50";

/** Prototype only: triggers the same tasks Celery Beat runs on day 1 and after day 5. */
export function DemoClock() {
  const clock = useClock();
  const qc = useQueryClient();
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const run = useMutation({
    mutationFn: (day: "day-1" | "day-5") => api<S<"DayOut">>(`/demo/${day}`, { method: "POST", actor: ACCOUNTANT }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const reset = useMutation({
    mutationFn: () => api<void>("/demo/reset", { method: "POST", actor: ACCOUNTANT }),
    onSuccess: () => {
      setConfirming(false);
      // Reseeding creates new ids, so any open close detail no longer exists.
      qc.clear();
      router.push("/consola");
    },
  });
  const busy = run.isPending || reset.isPending;
  const today = clock.data?.today;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-status-pending-tint px-4 py-2 font-mono text-xs text-status-pending">
      <span>
        MODO DEMO · solo en el prototipo · fecha simulada <b>{today ? formatDay(today) : "…"}</b>
      </span>
      <button className={BUTTON} disabled={busy} onClick={() => run.mutate("day-1")}>
        Simular día 1: iniciar cierre
      </button>
      <button className={BUTTON} disabled={busy} onClick={() => run.mutate("day-5")}>
        Simular día 5: vence el plazo
      </button>
      <span className="ml-auto flex items-center gap-2">
        {confirming ? (
          <>
            <span>¿Borrar todo y volver al inicio de la demo?</span>
            <button className={BUTTON} disabled={busy} onClick={() => reset.mutate()}>
              Sí, restablecer
            </button>
            <button className={BUTTON} disabled={busy} onClick={() => setConfirming(false)}>
              Cancelar
            </button>
          </>
        ) : (
          <button className={BUTTON} disabled={busy} onClick={() => setConfirming(true)}>
            Restablecer demo
          </button>
        )}
      </span>
      {busy && <span>procesando…</span>}
      {reset.isError && <span>No se pudo restablecer. Probá de nuevo o corré make seed.</span>}
    </div>
  );
}
