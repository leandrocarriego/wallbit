"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ACCOUNTANT, api } from "@/lib/api/client";
import { useInbox, useWorkingPeriod } from "@/lib/api/hooks";
import { formatUsd, monthName, plural } from "@/lib/format";
import { ALERT_LABEL } from "@/lib/labels";
import { Button, CapBar, Card, Chip, ErrorText, StatusPill } from "@/components/ui";

type BatchResult = { approved: number; skipped: number; replayed: boolean };

export default function BatchPage() {
  const period = useWorkingPeriod();
  // Every ready close (up to 500 per page in the prototype).
  const inbox = useInbox(period, { status: "READY", limit: 500 });
  const qc = useQueryClient();
  const [includeInfo, setIncludeInfo] = useState(true);
  const [attested, setAttested] = useState(false);
  // One key per screen visit: a double click or a retry never approves twice.
  const [key] = useState(() => `batch-${crypto.randomUUID()}`);
  const run = useMutation({
    mutationFn: () =>
      api<BatchResult>("/period-closes/batch-approve", {
        method: "POST",
        actor: ACCOUNTANT,
        headers: { "Idempotency-Key": key },
        body: { period, include_info: includeInfo, attested: true },
      }),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (!period || !inbox.data) return <p className="text-ink-muted">Cargando…</p>;
  const ready = inbox.data.rows;
  const withInfo = ready.filter((r) => r.alerts.some((a) => a.severity === "info"));
  const total = includeInfo ? ready.length : ready.length - withInfo.length;
  const sorted = [...ready].sort((a, b) => b.alerts.length - a.alerts.length);

  if (run.data) {
    return (
      <Card className="grid justify-items-start gap-3 p-6">
        <StatusPill status="APPROVED" />
        <b className="text-2xl">{plural(run.data.approved, "cierre aprobado", "cierres aprobados")}</b>
        <span className="text-ink-muted">
          Cada uno guardó su snapshot inmutable y su aviso salió a la cola de notificaciones. {run.data.skipped > 0 && `${run.data.skipped} quedaron afuera.`}
        </span>
        <span className="font-mono text-xs text-ink-muted">Idempotency-Key {key} · reintentar no duplica nada</span>
        <Link href="/consola" className="inline-flex min-h-9 items-center rounded-md border border-input px-3.5 font-medium">
          Volver a la bandeja
        </Link>
      </Card>
    );
  }

  return (
    <>
      <div className="grid gap-1">
        <div className="text-xs text-ink-muted">
          <Link href="/consola" className="text-primary">
            Bandeja
          </Link>{" "}
          / {monthName(period)} · paso 3 de 3
        </div>
        <h1 className="text-xl font-semibold">
          Aprobar {plural(total, "cierre", "cierres")} de {monthName(period)}
        </h1>
        <span className="text-ink-muted">Ninguno tiene alertas bloqueantes. Mirá primero los que tienen alertas informativas.</span>
      </div>

      <Card className="px-4 py-1">
        <div className="flex justify-between border-b border-border py-3">
          <span>Sin alertas</span>
          <span className="font-mono">{ready.length - withInfo.length}</span>
        </div>
        <div className="flex justify-between border-b border-border py-3">
          <span>Con alertas informativas</span>
          <span className="font-mono">{withInfo.length}</span>
        </div>
        <label className="flex items-start gap-2.5 border-b border-border py-3">
          <input type="checkbox" className="mt-0.5 size-4" checked={includeInfo} onChange={(e) => setIncludeInfo(e.target.checked)} />
          <span>Incluir los que tienen alertas informativas. El mensaje de cada uno lleva su advertencia.</span>
        </label>
        <div className="flex justify-between py-3 font-semibold">
          <span>Se aprueban y notifican</span>
          <span className="font-mono">{total}</span>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h2 className="text-[15px] font-semibold">Primero lo que conviene mirar</h2>
        </div>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-surface-muted text-left text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
              <th className="px-3 py-2.5 font-medium">Cliente</th>
              <th className="px-3 py-2.5 text-right font-medium">Facturado</th>
              <th className="w-40 px-3 py-2.5 font-medium">Tope 12 meses</th>
              <th className="px-3 py-2.5 font-medium">Alertas</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.close_id} className="border-t border-border">
                <td className="px-3 py-2.5">
                  <Link className="font-medium text-primary" href={`/consola/cierres/${r.close_id}`}>
                    {r.full_name}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-right font-mono">{formatUsd(r.invoiced_usd)}</td>
                <td className="px-3 py-2.5">
                  <CapBar pct={r.cap_usage_pct != null ? Number(r.cap_usage_pct) : null} />
                </td>
                <td className="px-3 py-2.5">
                  {r.alerts.map((a) => (
                    <Chip key={a.id} tone="pending">
                      {ALERT_LABEL[a.type]}
                    </Chip>
                  ))}
                </td>
              </tr>
            ))}
            {ready.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-ink-muted">
                  No hay cierres listos todavía.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card className="grid gap-3.5 p-4">
        <label className="flex items-start gap-2.5">
          <input type="checkbox" className="mt-0.5 size-4" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
          <span>
            Revisé los criterios de este lote y, como contador matriculado, apruebo {total === 1 ? "el cierre" : <>los <b className="font-mono">{total}</b> cierres</>} y su comunicación {total === 1 ? "al cliente" : "a los clientes"}.
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="primary" disabled={!attested || total === 0 || run.isPending} onClick={() => run.mutate()}>
            Aprobar y notificar {total}
          </Button>
          <span className="ml-auto font-mono text-xs text-ink-muted">Idempotency-Key {key} · tandas de 100 · snapshot y auditoría por cierre</span>
        </div>
        <ErrorText error={run.error} />
      </Card>
    </>
  );
}
