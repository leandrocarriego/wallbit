// After day 1, before day 5: every user with a pending question answers it at once
// (or invoices the payment). Each answer recomputes that close through the `recompute` queue.
// Measures the API under the rush and how long until every close is recomputed.
// Run after month_close_burst.
import http from "k6/http";
import exec from "k6/execution";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";
import { API, JSON_HEADERS, activeClients, deadLetters, pick, progress, waitUntilClean } from "./lib/common.js";

const drain = new Trend("recompute_drain_seconds", false);
const VUS = Number(__ENV.VUS || 20);

export const options = {
  setupTimeout: "5m",
  teardownTimeout: "16m",
  scenarios: {
    // Each user (VU) takes every VUS-th question, so all of them get answered once.
    answers: { executor: "per-vu-iterations", vus: VUS, iterations: 1, maxDuration: "10m" },
  },
  thresholds: {
    "http_req_duration{op:answer}": ["p(95)<500"],
    "http_req_duration{op:invoice}": ["p(95)<800"],
    http_req_failed: ["rate<0.01"],
    recompute_drain_seconds: ["max<120"], // every affected close recomputed within 2 minutes
    checks: ["rate>0.99"],
  },
};

export function setup() {
  if (progress().total === 0) throw new Error("No hay cierres: corré antes month_close_burst.");
  const clients = activeClients();
  const prompts = [];
  for (let i = 0; i < clients.length; i += 100) {
    const chunk = clients.slice(i, i + 100);
    const responses = http.batch(chunk.map((c) => ["GET", `${API}/clients/${c}/prompts`]));
    responses.forEach((r, j) => r.json().forEach((p) => prompts.push({ client: chunk[j], ...p })));
  }
  console.log(`${prompts.length} preguntas abiertas`);
  return { prompts, started: Date.now() };
}

export default function (data) {
  for (let i = exec.vu.idInTest - 1; i < data.prompts.length; i += VUS) answer(data.prompts[i]);
}

function answer(p) {
  const params = (op) => ({ headers: { ...JSON_HEADERS, "X-Actor": `client:${p.client}` }, tags: { op } });
  const res =
    p.kind === "who_is"
      ? http.post(`${API}/clients/${p.client}/prompts/${p.id}/answer`, JSON.stringify({ answer: pick(["work", "family", "own"]) }), params("answer"))
      : http.post(`${API}/clients/${p.client}/movements/${p.movement_id}/invoice`, JSON.stringify({ description: "Servicios" }), params("invoice"));
  check(res, { "user action accepted": (r) => r.status === 200 });
}

export function teardown(data) {
  const { p } = waitUntilClean(sleep);
  const seconds = (Date.now() - data.started) / 1000;
  if (p.dirty === 0) drain.add(seconds);
  check(deadLetters(), { "dead letter queue is empty": (n) => n === 0 });
  console.log(`Todo recalculado ${seconds.toFixed(1)} s después de la primera respuesta · ${JSON.stringify(p.by_status)}`);
}
