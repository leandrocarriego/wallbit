import type { S } from "@/lib/api/client";

/** Fixed averages for the prototype (STATUS: estimation simplified). */
const MASS_SECONDS = 35;
const REVIEW_MINUTES = 3.5;
const BATCH_MINUTES = 5;

export function estimate(inbox: S<"Inbox">) {
  // Totals come from the API (aggregate queries), not from the current page of rows.
  const blocking = inbox.blocking_alerts;
  const review = inbox.counts.IN_REVIEW ?? 0;
  const ready = inbox.counts.READY ?? 0;
  const minutes = (blocking * MASS_SECONDS) / 60 + review * REVIEW_MINUTES + (ready ? BATCH_MINUTES : 0);
  const rounded = Math.ceil(minutes);
  const label = rounded === 0 ? "nada" : rounded >= 60 ? `~${Math.floor(rounded / 60)} h ${String(rounded % 60).padStart(2, "0")} min` : `~${rounded} min`;
  return { blocking, review, ready, minutes: rounded, label };
}
