import type { S } from "@/lib/api/client";

/** Fixed averages for the prototype (STATUS: estimation simplified). */
const MASS_SECONDS = 35;
const REVIEW_MINUTES = 3.5;
const BATCH_MINUTES = 5;

export function estimate(inbox: S<"Inbox">) {
  const blocking = inbox.rows.flatMap((r) => r.alerts.filter((a) => a.severity === "blocking" && a.status === "open"));
  const review = inbox.rows.filter((r) => r.status === "IN_REVIEW").length;
  const ready = inbox.counts.READY ?? 0;
  const minutes = (blocking.length * MASS_SECONDS) / 60 + review * REVIEW_MINUTES + (ready ? BATCH_MINUTES : 0);
  const rounded = Math.ceil(minutes);
  const label = rounded === 0 ? "nada" : rounded >= 60 ? `~${Math.floor(rounded / 60)} h ${String(rounded % 60).padStart(2, "0")} min` : `~${rounded} min`;
  return { blocking: blocking.length, review, ready, minutes: rounded, label };
}
