"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ACCOUNTANT, api, type S } from "@/lib/api/client";
import { useAccountantAction, useClose, useInbox } from "@/lib/api/hooks";
import { formatArs, formatDateTime, formatDay, formatUsd, monthName } from "@/lib/format";
import { CATEGORY_LABEL, SOURCE_LABEL } from "@/lib/labels";
import { Button, CapBar, Card, Chip, ErrorText, Kbd, Label, StatusPill } from "@/components/ui";

type Alert = S<"AlertOut">;
type Movement = S<"MovementOut">;
type Toast = { text: string; undo?: () => void } | null;

const TEMPLATES = {
  factura: (name: string, m?: Movement) =>
    `Hola ${name}, vimos un cobro de ${m?.counterparty ?? "un cliente"} por ${formatUsd(m?.amount)} del ${m ? formatDay(m.occurred_on) : ""} que no tiene factura en ARCA. Si te falta, podés emitirla desde la app con “Facturar este cobro”.`,
  que: (name: string, m?: Movement) => `Hola ${name}, ¿nos contás qué es la transferencia de ${m?.counterparty ?? ""} por ${formatUsd(m?.amount)}?`,
  plazo: (name: string) => `Hola ${name}, necesitamos este dato antes del 7 para cerrar tu mes. ¡Gracias!`,
};

export default function CloseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const close = useClose(id);
  const inbox = useInbox(close.data?.period);
  const qc = useQueryClient();
  const [toast, setToast] = useState<Toast>(null);
  const [openThread, setOpenThread] = useState<string | null>(null);
  const [showOk, setShowOk] = useState(false);
  const [tab, setTab] = useState<"mov" | "inv" | "trace" | "log">("mov");
  const [attested, setAttested] = useState(false);

  const queue = useMemo(
    () => (inbox.data?.rows ?? []).filter((r) => r.status === "IN_REVIEW" || r.status === "READY").map((r) => r.close_id),
    [inbox.data],
  );
  const pos = queue.indexOf(id);
  const go = (delta: number) => {
    if (!queue.length) return;
    const next = queue[(pos + delta + queue.length) % queue.length];
    if (next && next !== id) router.push(`/consola/cierres/${next}`);
  };

  const resolve = useAccountantAction<{ alert: string; undo?: boolean }>(
    (v) => `/period-closes/${id}/alerts/${v.alert}/${v.undo ? "reopen" : "resolve"}`,
    (v) => (v.undo ? undefined : { resolution: "Resuelto por el contador" }),
  );
  const classify = useAccountantAction<{ movement: string; category: string | null }>(
    (v) => `/period-closes/${id}/movements/${v.movement}/classify`,
    (v) => ({ category: v.category, reason: v.category ? "Decisión del contador" : null }),
  );
  const approve = useAccountantAction<void, S<"SnapshotOut">>(() => `/period-closes/${id}/approve`, () => ({ attested: true }));
  const preview = useQuery({
    queryKey: ["preview", id, close.data?.version],
    queryFn: () => api<S<"PreviewOut">>(`/period-closes/${id}/message-preview`),
    enabled: !!close.data,
  });

  const data = close.data;
  const movements = data?.movements ?? [];
  const byId = new Map(movements.map((m) => [m.id, m]));
  const blocking = (data?.alerts ?? []).filter((a) => a.severity !== "info" && a.status === "open");
  const canApprove = data?.status === "READY" && attested;

  const doResolve = (a: Alert) =>
    resolve.mutate({ alert: a.id }, { onSuccess: () => setToast({ text: `${a.title}: resuelta`, undo: () => resolve.mutate({ alert: a.id, undo: true }) }) });
  const doClassify = (m: Movement, category: string) =>
    classify.mutate(
      { movement: m.id, category },
      { onSuccess: () => setToast({ text: `${m.counterparty}: ${CATEGORY_LABEL[category]}`, undo: () => classify.mutate({ movement: m.id, category: null }) }) },
    );
  const doApprove = () =>
    approve.mutate(undefined, {
      onSuccess: () => {
        setToast({ text: "Aprobado: snapshot congelado y aviso en cola." });
        setAttested(false);
        const rest = queue.filter((q) => q !== id);
        if (rest[0]) setTimeout(() => router.push(`/consola/cierres/${rest[0]}`), 900);
      },
    });

  // Each opening is audited as close.viewed: it is the start of the review time metric.
  useEffect(() => {
    api(`/period-closes/${id}/views`, { method: "POST", actor: ACCOUNTANT }).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      // Shortcuts stay active on checkboxes (the attestation), not while typing.
      if (el?.closest('textarea, select, input:not([type="checkbox"])') || e.metaKey || e.ctrlKey) return;
      if (e.key === "j" || e.key === "J") go(1);
      else if (e.key === "k" || e.key === "K") go(-1);
      else if ((e.key === "a" || e.key === "A") && canApprove) doApprove();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.undo ? 10_000 : 3_000);
    return () => clearTimeout(t);
  }, [toast]);

  if (!data) return <p className="text-ink-muted">Cargando…</p>;
  const r = data.result as Record<string, string & unknown> | null;
  const client = data.client as Record<string, string>;
  const firstName = String(client.full_name).split(" ")[0] ?? "";
  const attention = movements.filter((m) => m.category === "unclassified" || (["service_income", "platform_withdrawal"].includes(m.category ?? "") && !m.invoice_number));
  const shown = showOk ? movements : attention;

  return (
    <>
      {queue.length > 0 && pos >= 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[10px] bg-primary-tint px-3.5 py-2.5">
          <StatusPill status="IN_REVIEW" />
          <b className="font-mono">
            {pos + 1} de {queue.length}
          </b>
          <span className="text-xs text-ink-muted">
            <Kbd>J</Kbd> / <Kbd>K</Kbd> siguiente y anterior · <Kbd>A</Kbd> aprobar · al aprobar pasa sola al siguiente
          </span>
          <Link href="/consola" className="ml-auto text-[13px] text-ink-muted hover:text-ink">
            Salir de la revisión
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <div className="grid min-w-0 flex-[1_1_280px] gap-0.5">
          <div className="text-xs text-ink-muted">
            <Link href="/consola" className="text-primary">
              Bandeja
            </Link>{" "}
            / {monthName(data.period)}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold">{client.full_name}</h1>
            <StatusPill status={data.status} />
          </div>
          <span className="font-mono text-xs text-ink-muted">
            CUIT {client.cuit} · {client.activity} · Monotributo {client.category} · {client.jurisdiction}
          </span>
        </div>
        <Button onClick={() => go(-1)} aria-label="Cliente anterior">
          ‹ <Kbd>K</Kbd>
        </Button>
        <Button onClick={() => go(1)} aria-label="Cliente siguiente">
          <Kbd>J</Kbd> ›
        </Button>
      </div>

      <section aria-label="Alertas" className="grid gap-2.5">
        {data.alerts.length === 0 && <Card className="p-4 text-ink-muted">Sin alertas: el cierre está listo para aprobar.</Card>}
        {data.alerts.map((a) => (
          <AlertCard
            key={a.id}
            alert={a}
            closeId={id}
            movement={a.subject_id ? byId.get(a.subject_id) : undefined}
            firstName={firstName}
            threadOpen={openThread === a.id}
            onToggleThread={() => setOpenThread(openThread === a.id ? null : a.id)}
            onResolve={() => doResolve(a)}
            onReopen={() => resolve.mutate({ alert: a.id, undo: true })}
            onClassify={doClassify}
            busy={resolve.isPending || classify.isPending}
          />
        ))}
        <ErrorText error={resolve.error ?? classify.error} />
      </section>

      {r && (
        <Card className="grid grid-cols-2 md:grid-cols-4">
          <Kpi label="Facturado" value={formatUsd((r.invoiced_by_currency as unknown as Record<string, string>)?.USD ?? "0")} sub={`${formatArs(r.invoiced_ars)} · ${data.invoices.length} Facturas E`} />
          <Kpi label="Cobrado en Wallbit" value={formatUsd(r.collected_usd)} sub="cobros por trabajo del mes" />
          <div className="grid content-start gap-1.5 border-l border-border px-4 py-3.5">
            <Label>Acumulado 12 meses</Label>
            <span className="font-mono text-[22px] font-medium leading-7">{String(r.cap_usage_pct).replace(".", ",")}%</span>
            <CapBar pct={Number(r.cap_usage_pct)} />
            <span className="text-xs text-ink-muted">
              {formatArs(r.rolling_12m_ars)} de {formatArs(r.category_cap_ars)}
            </span>
          </div>
          <Kpi label="A pagar" value={formatArs(r.monthly_fee_ars)} sub={`Cuota ${r.category} · vence ${formatDay(String(r.due_date))}`} />
        </Card>
      )}

      <div className="flex flex-wrap items-start gap-4">
        <Card className="min-w-0 flex-[999_1_520px] overflow-hidden">
          <div role="tablist" className="flex gap-5 border-b border-border px-4">
            {(
              [
                ["mov", `Movimientos ${movements.length}`],
                ["inv", `Facturas ${data.invoices.length}`],
                ["trace", "Cómo se calculó"],
                ["log", "Historial"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className="-mb-px border-b-2 border-transparent py-2.5 text-sm font-medium text-ink-muted aria-selected:border-ink aria-selected:text-ink"
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "mov" && (
            <>
              <div className="flex flex-wrap items-center gap-2.5 px-4 py-3">
                <span>
                  <b>{movements.length} movimientos</b> <span className="text-ink-muted">· {movements.length - attention.length} OK ·</span>{" "}
                  <span className="font-medium text-status-review">{attention.length} requieren atención</span>
                </span>
                <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowOk(!showOk)}>
                  {showOk ? "Ocultar los OK" : `Mostrar los ${movements.length - attention.length} OK`}
                </Button>
              </div>
              <Table
                head={["Fecha", "Movimiento", "USD", "Clasificación", "Origen"]}
                rows={shown.map((m) => [
                  formatDay(m.occurred_on),
                  `${m.direction === "in" ? "Entra" : "Sale"} · ${m.counterparty ?? m.type}`,
                  `${m.direction === "in" ? "+" : "−"}${Number(m.amount).toLocaleString("es-AR")}`,
                  `${CATEGORY_LABEL[m.category ?? ""] ?? "—"}${m.invoice_number ? ` · ${m.invoice_number}` : ""}`,
                  SOURCE_LABEL[m.source ?? ""] ?? "—",
                ])}
              />
            </>
          )}
          {tab === "inv" && (
            <Table
              head={["Comprobante", "Fecha", "Cliente", "USD", "TC", "Origen"]}
              rows={data.invoices.map((i) => [
                i.number,
                formatDay(i.issued_on),
                i.customer_name,
                Number(i.amount).toLocaleString("es-AR"),
                Number(i.fx_rate_ars).toLocaleString("es-AR"),
                i.source === "arca_issued" ? "emitida desde Wallbit" : "importada de ARCA",
              ])}
            />
          )}
          {tab === "trace" && r && (
            <ol className="grid gap-2 p-4">
              {(r.trace as unknown as { label: string; value: string }[]).map((t, i) => (
                <li key={i} className="grid grid-cols-[22px_1fr_auto] gap-2.5 border-b border-dashed border-border pb-2 text-sm">
                  <span className="font-mono text-xs text-ink-subtle">{i + 1}</span>
                  <span>{t.label}</span>
                  <span className="font-mono tabular">{t.value}</span>
                </li>
              ))}
              <li className="font-mono text-xs text-ink-muted">
                motor v{data.engine_version} · parámetros {data.params_name} · versión del cierre {data.version} · valores ficticios
              </li>
            </ol>
          )}
          {tab === "log" && (
            <ul className="grid gap-2 p-4 text-sm">
              {data.history.map((h, i) => (
                <li key={i} className="grid grid-cols-[100px_140px_1fr] gap-2.5">
                  <span className="font-mono text-xs text-ink-muted">{formatDateTime(h.created_at)}</span>
                  <span className="truncate font-mono text-xs">{h.actor}</span>
                  <span>{h.action}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <aside className="grid min-w-0 flex-[1_1_300px] gap-3.5">
          <Card className="overflow-hidden">
            <div className="flex justify-between border-b border-border bg-surface-muted px-3.5 py-2.5">
              <Label>Lo que va a ver {firstName}</Label>
              <span className="text-xs text-ink-muted">plantilla v{preview.data?.template_version ?? "…"}</span>
            </div>
            <p className="whitespace-pre-line p-3.5 text-sm leading-6">{preview.data?.message}</p>
          </Card>
          <Card className="grid gap-2.5 p-3.5">
            {data.status === "READY" ? (
              <label className="flex items-start gap-2.5 text-sm">
                <input type="checkbox" className="mt-0.5 size-4 accent-[var(--primary-base)]" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
                <span>Revisé este cierre y, como contador matriculado, apruebo su comunicación al cliente.</span>
              </label>
            ) : (
              <span className={`text-xs ${data.status === "IN_REVIEW" ? "text-status-review" : "text-ink-muted"}`}>
                {data.status === "IN_REVIEW"
                  ? `Resolvé ${blocking.length === 1 ? "la alerta bloqueante" : `las ${blocking.length} alertas bloqueantes`} para aprobar.`
                  : data.status === "PENDING_DATA"
                    ? "Espera una respuesta del usuario (plazo día 5)."
                    : "Cierre aprobado: el snapshot está congelado."}
              </span>
            )}
            <Button variant="primary" disabled={!canApprove || approve.isPending} onClick={doApprove}>
              Aprobar y notificar <Kbd>A</Kbd>
            </Button>
            <ErrorText error={approve.error} />
          </Card>
        </aside>
      </div>

      {toast && (
        <div role="status" className="fixed bottom-6 right-8 flex items-center gap-3.5 rounded-[10px] bg-ink px-4 py-3 text-sm text-background shadow-[var(--shadow-pop)]">
          <span>{toast.text}</span>
          {toast.undo && (
            <button
              className="rounded-md border border-current px-2.5 py-0.5 text-[13px] font-medium"
              onClick={() => {
                toast.undo?.();
                setToast(null);
                qc.invalidateQueries();
              }}
            >
              Deshacer
            </button>
          )}
        </div>
      )}
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="grid content-start gap-1.5 border-l border-border px-4 py-3.5 first:border-l-0">
      <Label>{label}</Label>
      <span className="font-mono text-[22px] font-medium leading-7">{value}</span>
      <span className="text-xs text-ink-muted">{sub}</span>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-surface-muted text-left text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
            {head.map((h) => (
              <th key={h} className="px-3 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {row.map((cell, j) => (
                <td key={j} className={`px-3 py-2.5 ${j === 0 || /^[+−\d]/.test(cell) ? "font-mono tabular" : ""}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={head.length} className="px-3 py-5 text-center text-ink-muted">
                Nada para mostrar.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function AlertCard(props: {
  alert: Alert;
  closeId: string;
  movement?: Movement;
  firstName: string;
  threadOpen: boolean;
  onToggleThread: () => void;
  onResolve: () => void;
  onReopen: () => void;
  onClassify: (m: Movement, category: string) => void;
  busy: boolean;
}) {
  const { alert: a, movement: m } = props;
  const resolved = a.status === "resolved";
  const stripe = resolved ? "bg-status-done" : a.severity === "blocking" ? "bg-status-review" : a.severity === "waiting" ? "bg-status-pending" : "bg-input";
  const suggestion = (m?.suggestion ?? null) as { category: string; reasons: string[] } | null;
  const [other, setOther] = useState("");
  return (
    <div className={`grid grid-cols-[4px_minmax(0,1fr)] overflow-hidden rounded-[10px] border border-border bg-surface ${resolved ? "opacity-60" : ""}`}>
      <span className={stripe} aria-hidden />
      <div className="grid gap-3 p-3.5">
        <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
          <div className="grid min-w-0 flex-[1_1_320px] gap-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <b className="text-[15px]">{a.title}</b>
              <Chip tone={resolved ? "done" : a.severity === "blocking" ? "review" : a.severity === "waiting" ? "pending" : "neutral"}>
                {resolved ? "Resuelta" : a.severity === "blocking" ? "Bloqueante" : a.severity === "waiting" ? "Espera al usuario" : "Informativa"}
              </Chip>
            </div>
            <span className="text-sm text-ink-muted">{a.detail}</span>
            {a.type === "unclassified" && suggestion && !resolved && (
              <span className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <Chip>Sugerencia: {CATEGORY_LABEL[suggestion.category]}</Chip>
                <span className="text-ink-muted">{suggestion.reasons.join(" · ")}</span>
              </span>
            )}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {resolved ? (
              <Button size="sm" variant="ghost" onClick={props.onReopen}>
                Deshacer
              </Button>
            ) : (
              <>
                {a.type === "unbilled_collection" && (
                  <Button size="sm" onClick={props.onToggleThread}>
                    {props.threadOpen ? "Cerrar conversación" : `Escribirle a ${props.firstName}`}
                  </Button>
                )}
                {a.type === "unclassified" && m && suggestion && (
                  <Button size="sm" variant="primary" disabled={props.busy} onClick={() => props.onClassify(m, suggestion.category)}>
                    Aplicar sugerencia
                  </Button>
                )}
                {a.type === "unclassified" && m && (
                  <select
                    aria-label="Clasificar como"
                    className="min-h-8 rounded-md border border-input bg-surface px-2 text-[13px]"
                    value={other}
                    onChange={(e) => {
                      setOther(e.target.value);
                      if (e.target.value) props.onClassify(m, e.target.value);
                    }}
                  >
                    <option value="">Elegir otra…</option>
                    {["service_income", "own_transfer", "personal_transfer"].map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABEL[c]}
                      </option>
                    ))}
                  </select>
                )}
                {a.severity !== "info" && a.type !== "unclassified" && (
                  <Button size="sm" variant="ghost" disabled={props.busy} onClick={props.onResolve}>
                    Marcar resuelto
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
        {props.threadOpen && <Thread closeId={props.closeId} alert={a} movement={m} firstName={props.firstName} />}
      </div>
    </div>
  );
}

function Thread({ closeId, alert, movement, firstName }: { closeId: string; alert: Alert; movement?: Movement; firstName: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState(() => TEMPLATES.factura(firstName, movement));
  const key = ["messages", alert.id];
  const messages = useQuery({
    queryKey: key,
    queryFn: () => api<S<"MessageOut">[]>(`/period-closes/${closeId}/alerts/${alert.id}/messages`),
    refetchInterval: 2_500,
  });
  const send = async () => {
    if (!text.trim()) return;
    await api(`/period-closes/${closeId}/alerts/${alert.id}/messages`, { method: "POST", body: { body: text }, actor: ACCOUNTANT });
    setText("");
    await qc.invalidateQueries({ queryKey: key });
  };
  return (
    <div className="grid gap-2.5 rounded-[10px] border border-border p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <Label>Conversación sobre esta alerta</Label>
        <span className="ml-auto text-xs text-ink-muted">{firstName} la ve en la app · cada mensaje queda en el historial</span>
      </div>
      {(messages.data ?? []).map((m) => {
        const mine = m.author === ACCOUNTANT;
        return (
          <div key={m.id} className={`grid max-w-[78%] gap-1 rounded-[10px] px-3 py-2.5 text-sm ${mine ? "justify-self-end bg-primary-tint" : "justify-self-start bg-surface-muted"}`}>
            <span className="text-xs text-ink-muted">
              {mine ? "Vos" : firstName} · {formatDateTime(m.created_at)}
            </span>
            <span>{m.body}</span>
          </div>
        );
      })}
      {!messages.data?.length && <span className="text-sm text-ink-muted">Todavía no le escribiste. Elegí una plantilla o escribí.</span>}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Plantillas de mensaje">
        <button className="rounded-full border border-input px-2.5 py-0.5 text-xs" onClick={() => setText(TEMPLATES.factura(firstName, movement))}>
          Pedir factura
        </button>
        <button className="rounded-full border border-input px-2.5 py-0.5 text-xs" onClick={() => setText(TEMPLATES.que(firstName, movement))}>
          Preguntar qué es
        </button>
        <button className="rounded-full border border-input px-2.5 py-0.5 text-xs" onClick={() => setText(TEMPLATES.plazo(firstName))}>
          Recordar plazo
        </button>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2">
        <label className="grid gap-1">
          <span className="text-xs text-ink-muted">Mensaje para {firstName}</span>
          <textarea className="min-h-16 rounded-md border border-input bg-surface px-2.5 py-2 text-sm" value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <Button variant="primary" onClick={send}>
          Enviar
        </Button>
      </div>
      <span className="text-xs text-ink-muted">
        Cuando {firstName} emita la factura desde la app, llega de ARCA, se vincula sola al cobro y esta alerta desaparece.
      </span>
    </div>
  );
}
