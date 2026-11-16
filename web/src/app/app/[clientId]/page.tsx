"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, userActor, type S } from "@/lib/api/client";
import { formatArs, formatDay, formatUsd, monthName } from "@/lib/format";
import { ErrorText } from "@/components/ui";

type Prompt = S<"PromptOut">;

const SUGGESTION_TO_ANSWER: Record<string, string> = { personal_transfer: "family", service_income: "work", own_transfer: "own" };
const ANSWERS = [
  { id: "work", title: "Un cliente: es por un trabajo", hint: "Te vamos a pedir la factura" },
  { id: "own", title: "Soy yo, desde otra cuenta", hint: "Banco, exchange o billetera propia" },
  { id: "family", title: "Familia o un regalo", hint: "No es un ingreso por trabajo" },
  { id: "other", title: "Otra cosa", hint: "Se lo pasamos a tu contador" },
];

const PERKS = [
  ["Tus facturas, directo de ARCA", "No mandás resúmenes ni capturas por WhatsApp."],
  ["Un contador matriculado revisa todo", "Nada te llega sin su aprobación."],
  ["Facturá desde la app", "Si a un cobro le falta factura, la emitís con un toque."],
  ["Avisos antes de pasarte de categoría", "Te recategorizás con tiempo, no con multas."],
];

export default function UserApp() {
  const { clientId } = useParams<{ clientId: string }>();
  const actor = userActor(clientId);
  const qc = useQueryClient();
  const home = useQuery({ queryKey: ["home", clientId], queryFn: () => api<S<"Home">>(`/clients/${clientId}/home`), refetchInterval: 3_000 });
  const threads = useQuery({
    queryKey: ["threads", clientId],
    queryFn: () => api<S<"Conversation">[]>(`/clients/${clientId}/conversations`),
    refetchInterval: 3_000,
  });
  const notices = useQuery({
    queryKey: ["notices", clientId],
    queryFn: () => api<S<"NotificationOut">[]>(`/clients/${clientId}/notifications`),
    refetchInterval: 3_000,
  });
  const post = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api(`/clients/${clientId}${path}`, { method: "POST", body, actor }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const link = useMutation({
    mutationFn: () => api<S<"ArcaLinkOut">>(`/clients/${clientId}/arca-link`, { method: "POST", actor }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const [screen, setScreen] = useState<"home" | "offer" | "enroll">("home");
  const [consent, setConsent] = useState(false);

  const h = home.data;
  if (!h) return <Phone>Cargando…</Phone>;
  const first = h.client.full_name.split(" ")[0];

  if (h.stage === "offer" && screen !== "enroll") {
    if (screen === "home") {
      return (
        <Phone>
          <Hello name={first} />
          <div className="grid gap-2.5 rounded-2xl border border-border bg-surface p-4">
            <Badge>Nuevo en Wallbit</Badge>
            <b className="text-lg">Tu contador, dentro de Wallbit</b>
            <span className="text-sm text-ink-muted">Olvidate de tu facturación: cada mes te decimos cuánto facturaste y cuánto pagar.</span>
            <Primary onClick={() => setScreen("offer")}>Conocer más</Primary>
          </div>
        </Phone>
      );
    }
    return (
      <Phone back={() => setScreen("home")}>
        <Badge>Nuevo en Wallbit</Badge>
        <h1 className="text-[28px] font-semibold leading-[34px]">Tu contador, dentro de Wallbit</h1>
        <p className="text-ink-muted">Olvidate de tu facturación y de tus impuestos. Cada mes te decimos cuánto facturaste y cuánto tenés que pagar.</p>
        <ul className="grid gap-3">
          {PERKS.map(([title, sub]) => (
            <li key={title} className="grid">
              <b className="font-medium">{title}</b>
              <span className="text-[13px] text-ink-muted">{sub}</span>
            </li>
          ))}
        </ul>
        <div className="mt-auto grid gap-2.5">
          <div className="flex justify-between rounded-xl bg-surface-muted px-3.5 py-3">
            <span className="text-ink-muted">Costo mensual</span>
            <b>[a definir]</b>
          </div>
          <Primary onClick={() => setScreen("enroll")}>Quiero mi contador</Primary>
          <span className="text-center text-[13px] text-ink-muted">Para usarlo vas a vincular tu cuenta de ARCA.</span>
        </div>
      </Phone>
    );
  }

  if (h.stage === "offer") {
    return (
      <Phone back={() => setScreen("offer")} step="Paso 1 de 2">
        <h1 className="text-[26px] font-semibold leading-8">Confirmá tus datos</h1>
        <p className="text-ink-muted">Los precargamos con lo que ya sabemos de tu cuenta Wallbit.</p>
        <Field label="Nombre y apellido" value={h.client.full_name} />
        <Field label="CUIT" value={h.client.cuit} />
        <Field label="Actividad" value={h.client.activity} />
        <p className="rounded-xl bg-surface-muted px-3.5 py-3 text-[13px]">Tu régimen y tu categoría de monotributo los leemos de ARCA en el próximo paso.</p>
        <label className="flex items-start gap-3 rounded-xl border border-primary bg-primary-tint p-3.5 text-[13px]">
          <input type="checkbox" className="mt-0.5 size-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>Autorizo a Wallbit y a su contador matriculado a ver mis movimientos y mis comprobantes de ARCA para calcular mis impuestos. Puedo revocarlo cuando quiera.</span>
        </label>
        <div className="mt-auto grid gap-2">
          <Primary
            disabled={!consent || post.isPending}
            onClick={() => post.mutate({ path: "/enrollment", body: { consent_version: h.consent_version, accepted: true } }, { onSuccess: () => setScreen("home") })}
          >
            Continuar
          </Primary>
          <ErrorText error={post.error} />
        </div>
      </Phone>
    );
  }

  if (h.stage === "link_arca") {
    return (
      <Phone step="Paso 2 de 2 · obligatorio">
        <h1 className="text-[26px] font-semibold leading-8">Vinculá tu cuenta de ARCA</h1>
        <p className="text-ink-muted">Así leemos las facturas que emitís y podés facturar desde Wallbit. Nunca emitimos nada sin que lo confirmes.</p>
        <ol className="grid list-decimal gap-1.5 pl-5 text-sm">
          <li>Ingresá a ARCA con tu clave fiscal.</li>
          <li>Autorizá a Wallbit a consultar y emitir tus comprobantes.</li>
        </ol>
        <span className="self-start rounded-md bg-status-pending-tint px-2.5 py-1.5 font-mono text-xs text-status-pending">MODO DEMO · no se conecta a ARCA</span>
        <div className="mt-auto grid gap-2">
          <Primary disabled={link.isPending} onClick={() => link.mutate()}>
            {link.isPending ? "Vinculando…" : "Vincular con ARCA"}
          </Primary>
          <ErrorText error={link.error} />
        </div>
      </Phone>
    );
  }

  const prompts = h.prompts;
  return (
    <Phone>
      <Hello name={first} />
      {link.data && (
        <div className="rounded-2xl bg-status-done-tint px-4 py-3 text-sm text-status-done">
          <b>Listo: tu cuenta está vinculada.</b> Importamos {link.data.imported.length} facturas de los últimos 12 meses y ya clasificamos tus movimientos.
        </div>
      )}
      {(notices.data ?? []).map((n) => (
        <div key={n.id} className="grid gap-2 rounded-2xl border border-border bg-surface p-4">
          <span className="justify-self-start rounded-full bg-status-done-tint px-2.5 py-0.5 text-xs font-medium text-status-done">Revisado por tu contador</span>
          <span className="text-xs text-ink-muted">Tu cierre de {monthName(n.period)}</span>
          <span className="font-mono text-[28px] font-semibold leading-[34px]">{formatArs(String(n.result.monthly_fee_ars))}</span>
          <span className="text-sm">
            Monotributo categoría {String(n.result.category)} · antes del <b>{formatDay(String(n.result.due_date))}</b>
          </span>
          <p className="whitespace-pre-line rounded-xl bg-surface-muted p-3 text-[13px] leading-5">{n.body}</p>
        </div>
      ))}
      <section className="grid gap-2.5 rounded-2xl border border-border bg-surface p-4">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold">Impuestos</h2>
          <span className="text-xs text-ink-muted">Categoría {h.client.category ?? "—"}</span>
        </div>
        {prompts.length === 0 ? (
          <span className="text-sm text-ink-muted">Todo en orden. Tu contador cierra el mes y te avisa cuánto pagar.</span>
        ) : (
          <span className="text-[13px] text-ink-muted">{prompts.length === 1 ? "1 cosa" : `${prompts.length} cosas`} para resolver ahora, así tu mes cierra solo.</span>
        )}
        {prompts.map((p) =>
          p.kind === "invoice_this" ? (
            <InvoiceTask key={p.id} prompt={p} busy={post.isPending} onIssue={(description) => post.mutate({ path: `/movements/${p.movement_id}/invoice`, body: { description } })} />
          ) : (
            <WhoIsTask key={p.id} prompt={p} busy={post.isPending} onAnswer={(answer) => post.mutate({ path: `/prompts/${p.id}/answer`, body: { answer } })} />
          ),
        )}
        <ErrorText error={post.error} />
      </section>
      {(threads.data ?? []).map((t) => (
        <ThreadCard key={t.alert_id} thread={t} clientId={clientId} onSend={(body) => post.mutate({ path: `/alerts/${t.alert_id}/messages`, body: { body } })} />
      ))}
    </Phone>
  );
}

function InvoiceTask({ prompt, busy, onIssue }: { prompt: Prompt; busy: boolean; onIssue: (description: string) => void }) {
  const [open, setOpen] = useState(false);
  const [desc, setDesc] = useState("Servicios profesionales");
  const p = prompt.payload as Record<string, string>;
  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <b className="font-medium">
        Cobraste {formatUsd(p.amount)} de {p.counterparty} y no tiene factura
      </b>
      <span className="text-[13px] text-ink-muted">{p.date ? formatDay(p.date) : ""} · Facturalo ahora y te olvidás.</span>
      {!open ? (
        <Primary onClick={() => setOpen(true)}>Facturar este cobro</Primary>
      ) : (
        <div className="grid gap-2 rounded-xl bg-surface-muted p-3 text-sm">
          <Row k="Cliente" v={p.counterparty ?? ""} />
          <Row k="Monto" v={formatUsd(p.amount)} />
          <Row k="Tipo de cambio" v={`${Number(p.fx_rate_ars).toLocaleString("es-AR")} · el del cobro`} />
          <Row k="Comprobante" v="Factura E" />
          <label className="grid gap-1 text-xs text-ink-muted">
            Descripción
            <input className="min-h-10 rounded-lg border border-input bg-surface px-3 text-sm text-ink" value={desc} onChange={(e) => setDesc(e.target.value)} />
          </label>
          <span className="text-xs text-ink-muted">Se emite en ARCA recién cuando confirmás (en la demo, ARCA simulado).</span>
          <Primary disabled={busy} onClick={() => onIssue(desc)}>
            Emitir factura
          </Primary>
        </div>
      )}
    </div>
  );
}

function WhoIsTask({ prompt, busy, onAnswer }: { prompt: Prompt; busy: boolean; onAnswer: (answer: string) => void }) {
  const p = prompt.payload as { counterparty: string; amount: string; date: string; suggestion?: { category: string; reasons: string[] } | null };
  const [choice, setChoice] = useState(p.suggestion ? (SUGGESTION_TO_ANSWER[p.suggestion.category] ?? "") : "");
  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <b className="font-medium">¿Quién es {p.counterparty}?</b>
      <span className="text-[13px] text-ink-muted">
        Te transfirió {formatUsd(p.amount)} el {formatDay(p.date)}. Te lo preguntamos una sola vez.
      </span>
      {p.suggestion && (
        <span className="rounded-xl bg-surface-muted px-3 py-2 text-[13px]">
          <b>Nuestra sugerencia:</b> {p.suggestion.reasons.join(", ")}.
        </span>
      )}
      <div role="group" aria-label="¿Qué es este cobro?" className="grid gap-2">
        {ANSWERS.map((a) => (
          <button
            key={a.id}
            aria-pressed={choice === a.id}
            onClick={() => setChoice(a.id)}
            className="grid rounded-xl border border-input bg-surface px-3.5 py-2.5 text-left aria-pressed:border-primary aria-pressed:bg-primary-tint"
          >
            <span className="text-[15px] font-medium">{a.title}</span>
            <span className="text-xs text-ink-muted">{a.hint}</span>
          </button>
        ))}
      </div>
      <Primary disabled={!choice || busy} onClick={() => onAnswer(choice)}>
        Listo
      </Primary>
    </div>
  );
}

function ThreadCard({ thread, clientId, onSend }: { thread: S<"Conversation">; clientId: string; onSend: (body: string) => void }) {
  const [text, setText] = useState("");
  return (
    <section className="grid gap-2.5 rounded-2xl border border-border bg-surface p-4">
      <div className="grid">
        <b>Tu contador te escribió</b>
        <span className="text-xs text-ink-muted">Sobre: {thread.title}</span>
      </div>
      {thread.messages.map((m) => {
        const mine = m.author === userActor(clientId);
        return (
          <div key={m.id} className={`max-w-[84%] rounded-2xl px-3.5 py-2.5 text-sm ${mine ? "justify-self-end bg-primary-tint" : "justify-self-start bg-surface-muted"}`}>
            {m.body}
          </div>
        );
      })}
      <input className="min-h-11 rounded-xl border border-input bg-surface px-3.5 text-sm" placeholder="Escribile a tu contador" value={text} onChange={(e) => setText(e.target.value)} />
      <Primary
        disabled={!text.trim()}
        onClick={() => {
          onSend(text);
          setText("");
        }}
      >
        Enviar
      </Primary>
    </section>
  );
}

function Phone({ children, back, step }: { children: React.ReactNode; back?: () => void; step?: string }) {
  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto mb-3 flex max-w-[390px] justify-between text-xs">
        <Link href="/app" className="text-primary">
          ‹ Cambiar de usuario
        </Link>
        <span className="font-mono text-ink-muted">App Wallbit · simulador</span>
      </div>
      <div className="mx-auto flex min-h-[760px] max-w-[390px] flex-col gap-4 overflow-hidden rounded-[32px] border-[10px] border-ink bg-surface px-5 py-5">
        {(back || step) && (
          <div className="flex items-center justify-between">
            {back ? (
              <button className="min-h-11 text-[15px] font-medium text-primary" onClick={back}>
                ‹ Volver
              </button>
            ) : (
              <span />
            )}
            {step && <span className="text-[13px] text-ink-muted">{step}</span>}
          </div>
        )}
        {children}
      </div>
    </main>
  );
}

function Hello({ name }: { name?: string }) {
  return (
    <div className="grid">
      <span className="text-[13px] text-ink-muted">Hola,</span>
      <b className="text-xl">{name}</b>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="self-start justify-self-start rounded-full bg-status-ready-tint px-2.5 py-0.5 text-xs font-medium text-status-ready">{children}</span>;
}

function Primary({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className="min-h-12 rounded-[14px] bg-primary text-base font-semibold text-primary-foreground disabled:opacity-45" {...props}>
      {children}
    </button>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <label className="grid gap-1 text-[13px] text-ink-muted">
      {label}
      <input className="min-h-12 rounded-xl border border-input bg-surface px-3.5 text-[15px] text-ink" defaultValue={value} />
    </label>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-ink-muted">{k}</span>
      <span className="text-right">{v}</span>
    </div>
  );
}
