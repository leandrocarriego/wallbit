import type { ButtonHTMLAttributes, ReactNode } from "react";
import { STATUS_LABEL, STATUS_TONE } from "@/lib/labels";

type Variant = "primary" | "outline" | "ghost";

const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground border-primary hover:brightness-110",
  outline: "bg-surface text-ink border-input hover:bg-surface-muted",
  ghost: "bg-transparent text-ink-muted border-transparent hover:bg-surface-muted",
};

export function Button({
  variant = "outline",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  const sizing = size === "sm" ? "min-h-8 px-2.5 text-[13px]" : "min-h-9 px-3.5 text-sm";
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${sizing} ${VARIANT[variant]} ${className}`}
      {...props}
    />
  );
}

const TONE: Record<string, string> = {
  pending: "bg-status-pending-tint text-status-pending",
  review: "bg-status-review-tint text-status-review",
  ready: "bg-status-ready-tint text-status-ready",
  done: "bg-status-done-tint text-status-done",
  neutral: "bg-surface-muted text-ink-muted",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium ${TONE[STATUS_TONE[status] ?? "neutral"]}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Chip({ tone = "neutral", children }: { tone?: keyof typeof TONE; children: ReactNode }) {
  return <span className={`inline-flex h-5 items-center whitespace-nowrap rounded px-1.5 text-xs ${TONE[tone]}`}>{children}</span>;
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <section className={`rounded-[10px] border border-border bg-surface ${className}`}>{children}</section>;
}

export function Label({ children }: { children: ReactNode }) {
  return <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-subtle">{children}</span>;
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-grid h-[18px] min-w-[18px] place-items-center rounded border border-b-2 border-input bg-surface px-1 font-mono text-[11px] text-ink">
      {children}
    </kbd>
  );
}

export function CapBar({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-xs text-ink-muted">—</span>;
  const color = pct >= 100 ? "bg-status-review" : pct >= 80 ? "bg-status-pending" : "bg-status-done";
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_40px] items-center gap-2">
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="font-mono text-xs tabular">{pct.toFixed(1).replace(".", ",")}%</span>
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="text-sm text-status-review">{error instanceof Error ? error.message : "Algo salió mal."}</p>;
}
