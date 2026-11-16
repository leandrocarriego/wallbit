"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ACCOUNTANT, api } from "@/lib/api/client";
import { useInbox, useWorkingPeriod } from "@/lib/api/hooks";
import { formatUsd, monthName } from "@/lib/format";
import { ALERT_LABEL, STATUS_LABEL } from "@/lib/labels";
import { Button, CapBar, Card, Chip, StatusPill } from "@/components/ui";
import { estimate } from "@/components/console/plan";

const STATES = ["IN_REVIEW", "PENDING_DATA", "READY", "APPROVED", "NOTIFIED"] as const;
const HINT: Record<string, string> = {
  IN_REVIEW: "te esperan a vos",
  PENDING_DATA: "plazo 5, después pasan a vos",
  READY: "aprobables en lote",
  APPROVED: "notificación en cola",
  NOTIFIED: "ya saben cuánto pagar",
};

export default function InboxPage() {
  const period = useWorkingPeriod();
  const inbox = useInbox(period);
  const [filter, setFilter] = useState<string | null>(null);
  const qc = useQueryClient();
  const start = useMutation({
    mutationFn: () => api("/demo/day-1", { method: "POST", actor: ACCOUNTANT }),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (!period || !inbox.data) return <p className="text-ink-muted">Cargando…</p>;
  const data = inbox.data;
  const title = `Cierre de ${monthName(period)}`;

  if (!data.started) {
    return (
      <>
        <h1 className="text-xl font-semibold">{title}</h1>
        <Card className="grid justify-items-start gap-3 p-7">
          <StatusPill status="PENDING_DATA" />
          <b className="text-base">El cierre de {monthName(period)} todavía no arrancó</b>
          <span className="text-ink-muted">
            Arranca solo el día 1 a las 00:05 para todos los clientes adheridos. En la demo, disparalo a mano.
          </span>
          <Button variant="primary" onClick={() => start.mutate()} disabled={start.isPending}>
            Simular día 1: iniciar cierre
          </Button>
        </Card>
      </>
    );
  }

  const plan = estimate(data);
  const rows = filter ? data.rows.filter((r) => r.status === filter) : data.rows;
  const firstReview = data.rows.find((r) => r.status === "IN_REVIEW");
  const total = data.rows.length || 1;
  const notified = data.counts.NOTIFIED ?? 0;

  return (
    <>
      <div className="flex flex-wrap items-end gap-4">
        <div className="grid min-w-0 flex-[1_1_320px] gap-1">
          <h1 className="text-xl font-semibold">{title}</h1>
          <span className="text-ink-muted">Fecha simulada {data.today.split("-").reverse().join("/")} · vence el monotributo el 20</span>
        </div>
        <Link href="/consola/lote" className="inline-flex min-h-9 items-center rounded-md border border-input bg-surface px-3.5 font-medium">
          Aprobar {data.counts.READY ?? 0} listos
        </Link>
      </div>

      <Card className="grid gap-3.5 p-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h2 className="text-[15px] font-semibold">Plan para cerrar {monthName(period)}</h2>
          <span className="text-xs text-ink-muted">Lo masivo primero: una decisión resuelve muchos clientes.</span>
          <span className="ml-auto text-ink-muted">
            Te quedan <b className="font-mono text-base text-ink">{plan.label}</b>
          </span>
        </div>
        <ol className="grid gap-3 md:grid-cols-3">
          <Step n={1} now={plan.blocking > 0} title="Resolver por alerta" sub={`${plan.blocking} casos bloqueantes`} href="/consola/alertas" cta="Empezar" />
          <Step
            n={2}
            now={plan.blocking === 0 && plan.review > 0}
            title="Revisar uno por uno"
            sub={`${plan.review} clientes en revisión`}
            href={firstReview ? `/consola/cierres/${firstReview.close_id}` : "/consola"}
            cta="Revisión guiada"
          />
          <Step n={3} now={plan.review === 0 && plan.ready > 0} title="Aprobar en lote" sub={`${plan.ready} listos`} href="/consola/lote" cta="Ir al lote" />
        </ol>
      </Card>

      <section aria-label="Clientes por estado" className="grid gap-3">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {STATES.map((s) => (
            <button
              key={s}
              aria-pressed={filter === s}
              onClick={() => setFilter(filter === s ? null : s)}
              className="grid gap-1.5 rounded-[10px] border border-border bg-surface p-3.5 text-left aria-pressed:border-ink aria-pressed:shadow-[inset_0_0_0_1px_var(--ink)]"
            >
              <StatusPill status={s} />
              <span className="font-mono text-[22px] font-medium leading-7">{data.counts[s] ?? 0}</span>
              <span className="text-xs text-ink-muted">{HINT[s]}</span>
            </button>
          ))}
        </div>
        <div className="grid gap-1.5">
          <div className="flex h-2 overflow-hidden rounded-full bg-surface-muted" aria-hidden>
            {(["NOTIFIED", "READY", "IN_REVIEW", "PENDING_DATA"] as const).map((s) => (
              <div
                key={s}
                style={{ width: `${((data.counts[s] ?? 0) / total) * 100}%` }}
                className={{ NOTIFIED: "bg-status-done", READY: "bg-status-ready", IN_REVIEW: "bg-status-review", PENDING_DATA: "bg-status-pending" }[s]}
              />
            ))}
          </div>
          <span className="text-xs text-ink-muted">
            {notified} de {data.rows.length} notificados.
          </span>
        </div>
      </section>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-surface-muted text-left text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                <th className="px-3 py-2.5 font-medium">Cliente</th>
                <th className="px-3 py-2.5 font-medium">Cat.</th>
                <th className="px-3 py-2.5 text-right font-medium">Facturado</th>
                <th className="px-3 py-2.5 text-right font-medium">Cobrado</th>
                <th className="w-40 px-3 py-2.5 font-medium">Tope 12 meses</th>
                <th className="px-3 py-2.5 font-medium">Alertas</th>
                <th className="px-3 py-2.5 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.close_id} className="border-t border-border hover:bg-surface-muted">
                  <td className="px-3 py-2.5">
                    <Link href={`/consola/cierres/${r.close_id}`} className="font-medium hover:underline">
                      {r.full_name}
                    </Link>
                    <div className="font-mono text-xs text-ink-muted">{r.cuit}</div>
                  </td>
                  <td className="px-3 py-2.5">{r.category ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular">{formatUsd(r.invoiced_usd)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular">{formatUsd(r.collected_usd)}</td>
                  <td className="px-3 py-2.5">
                    <CapBar pct={r.cap_usage_pct != null ? Number(r.cap_usage_pct) : null} />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {r.alerts.length === 0 && <span className="text-xs text-ink-muted">—</span>}
                      {r.alerts.map((a) => (
                        <Chip key={a.id} tone={a.status === "resolved" ? "neutral" : a.severity === "blocking" ? "review" : a.severity === "waiting" ? "pending" : "neutral"}>
                          {ALERT_LABEL[a.type] ?? a.type}
                          {a.status === "resolved" ? " · resuelta" : ""}
                        </Chip>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusPill status={r.status} />
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-ink-muted">
                    Ningún cliente {filter ? `en "${STATUS_LABEL[filter]}"` : "todavía"}.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function Step({ n, now, title, sub, href, cta }: { n: number; now: boolean; title: string; sub: string; href: string; cta: string }) {
  return (
    <li className={`grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 gap-y-1 rounded-[10px] border bg-surface p-3.5 ${now ? "border-primary shadow-[inset_0_0_0_1px_var(--primary-base)]" : "border-border"}`}>
      <span className={`row-span-3 grid size-7 place-items-center rounded-full font-mono text-xs ${now ? "bg-primary text-primary-foreground" : "bg-surface-muted text-ink-muted"}`}>{n}</span>
      <b>{title}</b>
      <span className="text-xs text-ink-muted">{sub}</span>
      <Link
        href={href}
        className={`mt-1.5 inline-flex min-h-8 items-center justify-self-start rounded-md border px-2.5 text-[13px] font-medium ${now ? "border-primary bg-primary text-primary-foreground" : "border-input bg-surface"}`}
      >
        {cta}
      </Link>
    </li>
  );
}
