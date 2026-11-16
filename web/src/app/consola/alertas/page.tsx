"use client";

import Link from "next/link";
import { useInbox, useWorkingPeriod } from "@/lib/api/hooks";
import { formatUsd, monthName } from "@/lib/format";
import { ALERT_LABEL } from "@/lib/labels";
import { Card, Chip } from "@/components/ui";

const ORDER = ["blocking", "waiting", "info"];

/** Same problem across clients, grouped by alert type (prototype: links to each close). */
export default function ByAlertPage() {
  const period = useWorkingPeriod();
  const inbox = useInbox(period);
  if (!period || !inbox.data) return <p className="text-ink-muted">Cargando…</p>;
  const groups = new Map<string, { severity: string; items: { close: string; name: string; title: string; amount: string | null }[] }>();
  for (const row of inbox.data.rows) {
    for (const a of row.alerts) {
      if (a.status !== "open") continue;
      const g = groups.get(a.type) ?? { severity: a.severity, items: [] };
      g.items.push({ close: row.close_id, name: row.full_name, title: a.title, amount: a.amount });
      groups.set(a.type, g);
    }
  }
  const sorted = [...groups.entries()].sort((a, b) => ORDER.indexOf(a[1].severity) - ORDER.indexOf(b[1].severity));
  return (
    <>
      <div className="grid gap-1">
        <div className="text-xs text-ink-muted">
          <Link href="/consola" className="text-primary">
            Bandeja
          </Link>{" "}
          / {monthName(period)} · paso 1 de 3
        </div>
        <h1 className="text-xl font-semibold">Resolver por alerta</h1>
        <span className="text-ink-muted">El mismo problema en muchos clientes se resuelve junto. Primero las bloqueantes.</span>
      </div>
      {sorted.length === 0 && <Card className="p-5 text-ink-muted">No hay alertas abiertas.</Card>}
      {sorted.map(([type, g]) => (
        <Card key={type} className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2.5 px-4 py-3">
            <b>{ALERT_LABEL[type] ?? type}</b>
            <Chip tone={g.severity === "blocking" ? "review" : g.severity === "waiting" ? "pending" : "neutral"}>
              {g.severity === "blocking" ? "Bloqueante" : g.severity === "waiting" ? "Espera al usuario" : "Informativa"}
            </Chip>
            <span className="ml-auto font-mono text-xs text-ink-muted">{g.items.length} casos</span>
          </div>
          <ul>
            {g.items.map((item) => (
              <li key={item.close + item.title} className="flex flex-wrap items-center gap-3 border-t border-border px-4 py-2.5 text-sm">
                <Link href={`/consola/cierres/${item.close}`} className="font-medium text-primary">
                  {item.name}
                </Link>
                <span className="text-ink-muted">{item.title}</span>
                {item.amount && <span className="ml-auto font-mono">{formatUsd(item.amount)}</span>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
      <p className="text-xs text-ink-muted">
        En el prototipo la resolución masiva (clasificar una contraparte en todos los clientes y guardarla como regla global) queda diseñada en el alta fidelidad; acá se resuelve cliente por cliente.
      </p>
    </>
  );
}
