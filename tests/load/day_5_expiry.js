// Day 5 (the morning of day 6 in the calendar): unanswered questions expire and go to the
// accountant, and every open close is recomputed at once through the `recompute` queue.
// Run after month_close_burst (optionally after late_answers).
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";
import { API, deadLetters, progress, waitUntilClean } from "./lib/common.js";

const burst = new Trend("day5_burst_seconds", false);

export const options = {
  scenarios: { day5: { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "16m" } },
  thresholds: { day5_burst_seconds: ["max<600"], checks: ["rate==1"] },
};

export function setup() {
  const p = progress();
  if (p.total === 0) throw new Error("No hay cierres: corré antes month_close_burst.");
  return { before: p.by_status };
}

export default function (data) {
  const started = Date.now();
  const res = http.post(`${API}/demo/day-5`, null, { headers: { "X-Actor": "k6" } });
  check(res, { "day 5 accepted": (r) => r.status === 200 });
  const marked = progress().dirty;
  const { p } = waitUntilClean(sleep);
  const seconds = (Date.now() - started) / 1000;
  burst.add(seconds);
  check(p, { "every close recomputed": (x) => x.dirty === 0 });
  check(deadLetters(), { "dead letter queue is empty": (n) => n === 0 });
  console.log(`${marked} cierres recalculados en ${seconds.toFixed(1)} s · antes ${JSON.stringify(data.before)} · después ${JSON.stringify(p.by_status)}`);
}
