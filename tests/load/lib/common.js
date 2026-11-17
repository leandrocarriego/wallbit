// Shared helpers for the load scenarios.
import http from "k6/http";
import encoding from "k6/encoding";

export const API = __ENV.API_URL || "http://api:8000/api/v1";
export const RABBIT = __ENV.RABBIT_URL || "http://rabbitmq:15672";
export const PERIOD = "2026-10";
export const JSON_HEADERS = { "Content-Type": "application/json" };

export const progress = () => http.get(`${API}/period-closes/progress?period=${PERIOD}`, { tags: { page: "progress" } }).json();

export function deadLetters() {
  const auth = { headers: { Authorization: `Basic ${encoding.b64encode("wallbit:wallbit")}` } };
  return http.get(`${RABBIT}/api/queues/%2F/dead_letter`, auth).json().messages;
}

/** Every active client id (the user list is small enough to load at once). */
export function activeClients() {
  return http
    .get(`${API}/clients`)
    .json()
    .filter((c) => c.enrolled && c.arca_linked)
    .map((c) => c.id);
}

/** Wait until no close is dirty (every recompute drained). Returns seconds waited, or -1 on timeout. */
export function waitUntilClean(sleep, timeoutSeconds = 900) {
  const started = Date.now();
  let p = progress();
  while (p.dirty > 0 && Date.now() - started < timeoutSeconds * 1000) {
    sleep(1);
    p = progress();
  }
  return { p, seconds: p.dirty > 0 ? -1 : (Date.now() - started) / 1000 };
}

export const pick = (list) => list[Math.floor(Math.random() * list.length)];
