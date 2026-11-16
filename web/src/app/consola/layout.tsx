import Link from "next/link";
import { DemoClock } from "@/components/console/DemoClock";
import { SideNav } from "@/components/console/SideNav";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <DemoClock />
      <div className="flex min-h-[calc(100vh-37px)] flex-wrap">
        <aside className="flex flex-[1_1_232px] flex-col gap-5 border-r border-border bg-sidebar px-3.5 py-5">
          <Link href="/consola" className="flex items-center gap-2.5 px-1.5">
            <span className="grid size-[30px] place-items-center rounded-lg bg-ink">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--bg)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M5 12l4 4L19 6" />
              </svg>
            </span>
            <span className="grid">
              <b className="text-[15px] leading-5">Cierre</b>
              <span className="text-xs text-ink-muted">Servicio contable · Wallbit</span>
            </span>
          </Link>
          <SideNav />
          <div className="mt-auto border-t border-border px-1.5 pt-3 text-xs text-ink-muted">
            C.P. Laura Gómez (ficticia) · demo sin login
            <br />
            <Link className="text-primary" href="/app">
              Abrir el simulador del usuario
            </Link>
          </div>
        </aside>
        <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-5 px-8 pb-10 pt-6">{children}</main>
      </div>
    </div>
  );
}
