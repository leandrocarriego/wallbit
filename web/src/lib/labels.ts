export const STATUS_LABEL: Record<string, string> = {
  PENDING_DATA: "Esperando usuario",
  IN_REVIEW: "En revisión",
  READY: "Listo",
  APPROVED: "Aprobado",
  NOTIFIED: "Notificado",
};

export const STATUS_TONE: Record<string, "pending" | "review" | "ready" | "done"> = {
  PENDING_DATA: "pending",
  IN_REVIEW: "review",
  READY: "ready",
  APPROVED: "done",
  NOTIFIED: "done",
};

export const CATEGORY_LABEL: Record<string, string> = {
  service_income: "Cobro por trabajo",
  platform_withdrawal: "Retiro de plataforma",
  own_transfer: "Transferencia propia",
  conversion: "Conversión",
  refund_reversal: "Devolución",
  investment_income: "Rendimiento",
  personal_transfer: "Familia o regalo",
  card_expense: "Gasto con tarjeta",
  outgoing_payment: "Pago saliente",
  unclassified: "Sin clasificar",
};

export const SOURCE_LABEL: Record<string, string> = {
  structural: "tipo de movimiento",
  global_rule: "regla global",
  invoice_match: "match con factura",
  invoice_history: "historial ARCA",
  user_declared: "declaración del usuario",
  accountant: "contador",
  none: "—",
};

export const ALERT_LABEL: Record<string, string> = {
  unbilled_collection: "Cobro sin facturar",
  unclassified: "Sin clasificar",
  non_billable_risk: "No facturable con riesgo",
  exceeds_category: "Supera su categoría",
  exceeds_regime: "Supera el régimen",
  invoiced_not_collected: "Facturado sin cobro",
  near_cap: "Cerca del tope",
  strong_variation: "Variación fuerte",
};

export const BILLABLE = new Set(["service_income", "platform_withdrawal"]);
