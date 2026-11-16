const ars = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 });
const usd = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

/** Money arrives as strings (Decimal on the wire) and is only formatted at the edge. */
export function formatUsd(value: string | null | undefined): string {
  if (value == null) return "—";
  return `USD ${usd.format(Number(value))}`;
}

export function formatArs(value: string | null | undefined): string {
  if (value == null) return "—";
  return ars.format(Number(value)).replace(/\s/g, " ");
}

export function formatDay(iso: string): string {
  const [, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function monthName(period: string): string {
  const [year, month] = period.split("-");
  return `${MONTHS[Number(month) - 1] ?? ""} ${year ?? ""}`;
}

/** The close being worked on: last month during the first days, else the current month. */
export function workingPeriod(todayIso: string): string {
  const [y, m, d] = todayIso.split("-").map(Number) as [number, number, number];
  if (d > 5) return `${y}-${String(m).padStart(2, "0")}`;
  const prev = m === 1 ? [y - 1, 12] : [y, m - 1];
  return `${prev[0]}-${String(prev[1]).padStart(2, "0")}`;
}
