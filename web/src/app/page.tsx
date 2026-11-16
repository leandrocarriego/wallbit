import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl content-center gap-6 px-6 py-16">
      <div className="grid gap-2">
        <h1 className="text-2xl font-semibold">Cierre · Servicio contable Wallbit</h1>
        <p className="text-ink-muted">Prototipo con datos ficticios. Abrí las dos vistas en pestañas separadas para seguir la demo.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Link href="/consola" className="grid gap-1 rounded-[10px] border border-border bg-surface p-5 hover:border-ink">
          <b>Consola del contador</b>
          <span className="text-sm text-ink-muted">Bandeja, revisión guiada, aprobación en lote.</span>
        </Link>
        <Link href="/app" className="grid gap-1 rounded-[10px] border border-border bg-surface p-5 hover:border-ink">
          <b>App del usuario (simulador)</b>
          <span className="text-sm text-ink-muted">Adhesión con ARCA, avisos del mes, mensajes y mi cierre.</span>
        </Link>
      </div>
    </main>
  );
}
