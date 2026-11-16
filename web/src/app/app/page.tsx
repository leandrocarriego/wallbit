"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "@/lib/api/client";

export default function SimulateAs() {
  const clients = useQuery({ queryKey: ["clients"], queryFn: () => api<S<"ClientSummary">[]>("/clients") });
  return (
    <main className="mx-auto grid min-h-screen max-w-md content-start gap-4 px-4 py-10">
      <span className="justify-self-start rounded-md bg-status-pending-tint px-2.5 py-1.5 font-mono text-xs text-status-pending">
        MODO DEMO · reemplaza el login
      </span>
      <h1 className="text-2xl font-semibold">¿Quién sos?</h1>
      <p className="text-ink-muted">Elegí un usuario de Wallbit para ver la app como la vería.</p>
      {(clients.data ?? []).map((c) => (
        <Link key={c.id} href={`/app/${c.id}`} className="grid grid-cols-[40px_1fr_auto] items-center gap-3 rounded-xl border border-border bg-surface p-3.5 hover:border-ink">
          <span className="grid size-10 place-items-center rounded-full bg-surface-muted text-sm font-semibold">
            {c.full_name
              .split(" ")
              .map((p) => p[0])
              .join("")}
          </span>
          <span className="grid">
            <b>{c.full_name}</b>
            <span className="text-xs text-ink-muted">{c.activity}</span>
          </span>
          <span className="text-xs text-ink-muted">{c.arca_linked ? "con contador" : c.enrolled ? "falta ARCA" : "sin adherir"}</span>
        </Link>
      ))}
      <Link href="/consola" className="text-sm text-primary">
        Ir a la consola del contador
      </Link>
    </main>
  );
}
