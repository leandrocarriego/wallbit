// The accountant's day after day 5: several accountants work the in-review closes in parallel
// (open, read, write to the user, resolve or classify, approve) and finally approve the ready
// ones in batch. Measures what the system adds to each review; human time is measured in
// production with the "Productividad del contador" dashboard.
// Run after day_5_expiry. Knobs: VUS (accountants, default 5), MAX (closes to review).
import http from "k6/http";
import exec from "k6/execution";
import { check } from "k6";
import { Trend } from "k6/metrics";
import { API, JSON_HEADERS, PERIOD, progress } from "./lib/common.js";

const review = new Trend("close_review_ms", true);
const batch = new Trend("batch_approve_seconds", false);
const VUS = Number(__ENV.VUS || 5);

export const options = {
  setupTimeout: "2m",
  teardownTimeout: "5m",
  scenarios: {
    workday: { executor: "shared-iterations", vus: VUS, iterations: Number(__ENV.MAX || 200), maxDuration: "15m" },
  },
  thresholds: {
    "http_req_duration{op:detail}": ["p(95)<300"],
    "http_req_duration{op:action}": ["p(95)<500"],
    "http_req_duration{op:approve}": ["p(95)<500"],
    close_review_ms: ["p(95)<2000"], // system time for a whole review, all calls included
    batch_approve_seconds: ["max<10"],
    http_req_failed: ["rate<0.01"],
  },
};

export function setup() {
  const ids = [];
  for (let offset = 0; ; offset += 500) {
    const page = http.get(`${API}/period-closes?period=${PERIOD}&status=IN_REVIEW&limit=500&offset=${offset}`).json();
    ids.push(...page.rows.map((r) => r.close_id));
    if (page.rows.length < 500) break;
  }
  if (!ids.length) throw new Error("No hay cierres en revisión: corré antes month_close_burst y day_5_expiry.");
  console.log(`${ids.length} cierres en revisión`);
  return { ids };
}

export default function (data) {
  const id = data.ids[exec.scenario.iterationInTest];
  if (!id) return;
  const as = (op) => ({ headers: { ...JSON_HEADERS, "X-Actor": `contador-${exec.vu.idInTest}` }, tags: { op } });
  const started = Date.now();

  http.post(`${API}/period-closes/${id}/views`, null, as("view"));
  const detail = http.get(`${API}/period-closes/${id}`, as("detail")).json();
  http.get(`${API}/period-closes/${id}/message-preview`, as("detail"));

  let status = detail.status;
  const open = detail.alerts.filter((a) => a.status === "open" && a.severity !== "info");
  if (open[0] && Math.random() < 0.3) {
    http.post(`${API}/period-closes/${id}/alerts/${open[0].id}/messages`, JSON.stringify({ body: "Hola, ¿nos contás qué es este cobro?" }), as("action"));
  }
  for (const a of open) {
    const res =
      a.type === "unclassified" && a.subject_id
        ? http.post(`${API}/period-closes/${id}/movements/${a.subject_id}/classify`, JSON.stringify({ category: "personal_transfer", reason: "Decisión del contador" }), as("action"))
        : http.post(`${API}/period-closes/${id}/alerts/${a.id}/resolve`, JSON.stringify({ resolution: "Revisado por el contador" }), as("action"));
    if (check(res, { "action accepted": (r) => r.status === 200 })) status = res.json().status;
  }
  if (status === "READY") {
    const res = http.post(`${API}/period-closes/${id}/approve`, JSON.stringify({ attested: true }), as("approve"));
    check(res, { "approved": (r) => r.status === 200 });
  }
  review.add(Date.now() - started);
}

export function teardown() {
  const started = Date.now();
  const res = http.post(`${API}/period-closes/batch-approve`, JSON.stringify({ period: PERIOD, include_info: true, attested: true }), {
    headers: { ...JSON_HEADERS, "X-Actor": "contador-1", "Idempotency-Key": `k6-${started}` },
    tags: { op: "batch" },
    timeout: "5m",
  });
  const seconds = (Date.now() - started) / 1000;
  batch.add(seconds);
  check(res, { "batch approved": (r) => r.status === 200 });
  console.log(`Lote: ${JSON.stringify(res.json())} en ${seconds.toFixed(1)} s · ${JSON.stringify(progress().by_status)}`);
}
