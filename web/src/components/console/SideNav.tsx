"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useInbox, useWorkingPeriod } from "@/lib/api/hooks";
import { estimate } from "./plan";

export function SideNav() {
  const path = usePathname();
  const period = useWorkingPeriod();
  const inbox = useInbox(period);
  const counts = inbox.data?.counts ?? {};
  const items = [
    { href: "/consola", label: "Bandeja", n: inbox.data?.rows.length },
    { href: "/consola/alertas", label: "Resolver por alerta" },
    { href: "/consola/lote", label: "Aprobar en lote", n: counts.READY },
  ];
  const eta = inbox.data ? estimate(inbox.data) : null;
  return (
    <>
      <nav aria-label="Secciones" className="grid gap-0.5">
        {items.map((item) => {
          const on = item.href === "/consola" ? path === "/consola" || path.startsWith("/consola/cierres") : path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={on ? "page" : undefined}
              className={`flex min-h-9 items-center justify-between rounded-md border px-2.5 font-medium ${on ? "border-border bg-surface text-ink" : "border-transparent text-ink-muted hover:text-ink"}`}
            >
              {item.label}
              {item.n != null && <span className="font-mono text-xs text-ink-muted">{item.n}</span>}
            </Link>
          );
        })}
      </nav>
      {eta && inbox.data?.started && (
        <div className="grid gap-2 rounded-[10px] border border-border bg-surface p-3.5">
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-subtle">Te quedan</span>
          <span className="font-mono text-[22px] font-medium leading-7">{eta.label}</span>
          <span className="text-xs text-ink-muted">Estimado con 35 s por caso masivo y 3,5 min por revisión.</span>
        </div>
      )}
    </>
  );
}
