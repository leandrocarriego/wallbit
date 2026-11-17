// During the month: many users getting paid at once. Each event is a movement arriving from
// Wallbit, classified on arrival; if the app asks the user something, the user answers or
// invoices right away (most of them), like in the real flow.
// Requires the volume seed before day 1: `make seed-volume n=2000`.
// Knobs: RATE (events per second, default 20) and DURATION (default 1m).
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";
import { API, JSON_HEADERS, activeClients, pick } from "./lib/common.js";

const RATE = Number(__ENV.RATE || 20);
const prompts = new Counter("prompts_opened");
const actedOn = new Counter("prompts_acted_on");

export const options = {
  scenarios: {
    payments: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: __ENV.DURATION || "1m",
      preAllocatedVUs: Math.max(10, RATE),
      maxVUs: RATE * 4,
    },
  },
  thresholds: {
    "http_req_duration{op:ingest}": ["p(95)<500"],
    "http_req_duration{op:answer}": ["p(95)<500"],
    "http_req_duration{op:invoice}": ["p(95)<800"],
    http_req_failed: ["rate<0.01"],
    dropped_iterations: ["count==0"], // the API kept up with the arrival rate
  },
};

const COMPANIES = ["Acme Corp", "Globex Inc", "Initech LLC", "Hooli GmbH", "Northwind Ltd", "Contoso Ltd", "Pied Piper Inc"];
const PEOPLE = Array.from({ length: 40 }, (_, i) => `Persona ${String.fromCharCode(65 + (i % 26))}. ${i}`);
const ANSWERS = ["work", "family", "own"];

export function setup() {
  const clients = activeClients();
  if (!clients.length) throw new Error("No hay clientes activos: corré `make seed-volume`.");
  return { clients };
}

function movement(client) {
  const roll = Math.random();
  const base = {
    client_id: client,
    external_id: `k6-${Date.now()}-${__VU}-${__ITER}-${Math.floor(Math.random() * 1e9)}`,
    occurred_at: "2026-10-30T18:00:00Z",
    currency: "USD",
    fx_rate_ars: "1450",
  };
  if (roll < 0.45) // a payment from a company abroad
    return { ...base, type: "incoming_transfer", direction: "in", amount: String(300 + Math.floor(Math.random() * 1500)), counterparty: pick(COMPANIES), origin_country: "US" };
  if (roll < 0.75) // a transfer from a person nobody knows yet
    return { ...base, type: "incoming_transfer", direction: "in", amount: String(50 + Math.floor(Math.random() * 400)), counterparty: pick(PEOPLE), origin_country: "AR" };
  return { ...base, type: "card_payment", direction: "out", amount: "25" };
}

export default function (data) {
  const client = pick(data.clients);
  const actor = { headers: { ...JSON_HEADERS, "X-Actor": "wallbit-core" }, tags: { op: "ingest" } };
  const res = http.post(`${API}/movements`, JSON.stringify(movement(client)), actor);
  if (!check(res, { "movement ingested": (r) => r.status === 200 })) return;
  const body = res.json();
  const mine = body.prompts.filter((p) => p.movement_id === body.movement_id);
  prompts.add(mine.length);

  const user = (op) => ({ headers: { ...JSON_HEADERS, "X-Actor": `client:${client}` }, tags: { op } });
  for (const p of mine) {
    if (p.kind === "who_is" && Math.random() < 0.8) {
      const r = http.post(`${API}/clients/${client}/prompts/${p.id}/answer`, JSON.stringify({ answer: pick(ANSWERS) }), user("answer"));
      check(r, { "answer accepted": (x) => x.status === 200 }) && actedOn.add(1);
    } else if (p.kind === "invoice_this" && Math.random() < 0.7) {
      const r = http.post(`${API}/clients/${client}/movements/${p.movement_id}/invoice`, JSON.stringify({ description: "Servicios de desarrollo" }), user("invoice"));
      check(r, { "invoice issued": (x) => x.status === 200 }) && actedOn.add(1);
    }
  }
}
